"""G.729.1 (Annex J / G.729EV) multi-layer wideband voice codec.

ITU-T G.729.1 is an embedded variable bit-rate extension of G.729, also known
as G.729EV (Annex J context). It codes 50–7000 Hz speech at 16 kHz with a
20 ms frame and bit rates:

    8, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32 kbit/s

Layer structure (bytes per 20 ms frame):
    L1  core (G.729-like NB)     20 B   →  8 kb/s
    L2  NB enhancement            10 B   → 12 kb/s cumulative
    L3  TDBWE time domain         5 B    → 14 kb/s
    L4+ MDCT enhancement layers   5 B ea → up to 32 kb/s

This module implements that **frame layout and layer embedding** with an open
reimplementation of the signal path (band-split, LPC residual coding, MDCT
enhancement). It is **not** bit-exact with the ITU-T floating-point reference
(which is patent-encumbered). The on-wire payload type is tagged
`G729EV/open-v1` so peers can negotiate.

Production deployments that require bit-exact G.729.1 interoperability should
swap `G729EVCodec` for a licensed ITU binary via the same encode/decode API.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

# --- G.729.1 constants -------------------------------------------------------

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 320
NB_BAND = 4000  # core processes lower band (decimated to 8 kHz → 160 samples)

# Cumulative bit rates (kbit/s) and bytes per frame for each layer cut
LAYER_RATES_KBPS = (8, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32)
# Bytes added by each successive layer (sums to rate*FRAME_MS/8)
LAYER_BYTES = (20, 10, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5)

assert all(
    sum(LAYER_BYTES[: i + 1]) * 8 // FRAME_MS == LAYER_RATES_KBPS[i]
    for i in range(len(LAYER_RATES_KBPS))
)

PAYLOAD_MIME = "audio/G729EV; codecs=open-v1"
MAX_FRAME_BYTES = sum(LAYER_BYTES)  # 80 bytes @ 32 kb/s


def rate_to_layers(kbps: int) -> int:
    """Return number of layers (1..12) for a target bit rate."""
    if kbps <= LAYER_RATES_KBPS[0]:
        return 1
    for i, r in enumerate(LAYER_RATES_KBPS):
        if kbps <= r:
            return i + 1
    return len(LAYER_RATES_KBPS)


def layers_to_bytes(n_layers: int) -> int:
    n = max(1, min(n_layers, len(LAYER_BYTES)))
    return sum(LAYER_BYTES[:n])


@dataclass
class G729EVFrame:
    """One 20 ms embedded bitstream."""

    seq: int
    layers: int
    data: bytes  # truncated to active layers

    def pack(self) -> bytes:
        # header: magic(2) version(1) layers(1) seq(4) = 8 bytes + payload
        if not (1 <= self.layers <= 12):
            raise ValueError("layers must be 1..12")
        need = layers_to_bytes(self.layers)
        payload = self.data[:need].ljust(need, b"\x00")
        return struct.pack("!2sBBI", b"EV", 1, self.layers, self.seq & 0xFFFFFFFF) + payload

    @classmethod
    def unpack(cls, blob: bytes) -> G729EVFrame:
        if len(blob) < 8:
            raise ValueError("G.729EV frame too short")
        magic, ver, layers, seq = struct.unpack("!2sBBI", blob[:8])
        if magic != b"EV" or ver != 1:
            raise ValueError("not a G729EV/open-v1 frame")
        need = layers_to_bytes(layers)
        data = blob[8 : 8 + need]
        if len(data) < need:
            data = data.ljust(need, b"\x00")
        return cls(seq=seq, layers=layers, data=data)


class _LPC:
    """Simple order-10 autocorrelation LPC (Levinson-Durbin)."""

    ORDER = 10

    @staticmethod
    def analyze(x: np.ndarray) -> np.ndarray:
        x = x.astype(np.float64)
        # Hamming window
        w = 0.54 - 0.46 * np.cos(2 * np.pi * np.arange(len(x)) / (len(x) - 1))
        xw = x * w
        r = np.correlate(xw, xw, mode="full")
        r = r[len(xw) - 1 : len(xw) - 1 + _LPC.ORDER + 1]
        if r[0] < 1e-12:
            return np.zeros(_LPC.ORDER)
        # Levinson-Durbin
        a = np.zeros(_LPC.ORDER)
        e = float(r[0])
        for i in range(_LPC.ORDER):
            acc = r[i + 1]
            for j in range(i):
                acc -= a[j] * r[i - j]
            k = acc / e if e > 1e-12 else 0.0
            k = float(np.clip(k, -0.999, 0.999))
            a_new = a.copy()
            a_new[i] = k
            for j in range(i):
                a_new[j] = a[j] - k * a[i - 1 - j]
            a = a_new
            e *= 1.0 - k * k
        return a

    @staticmethod
    def residual(x: np.ndarray, a: np.ndarray) -> np.ndarray:
        y = np.zeros_like(x, dtype=np.float64)
        for n in range(len(x)):
            s = float(x[n])
            for k in range(min(_LPC.ORDER, n)):
                s -= a[k] * float(x[n - 1 - k])
            y[n] = s
        return y

    @staticmethod
    def synthesize(e: np.ndarray, a: np.ndarray, mem: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        y = np.zeros(len(e), dtype=np.float64)
        m = mem.copy()
        for n in range(len(e)):
            s = float(e[n])
            for k in range(_LPC.ORDER):
                s += a[k] * m[k]
            y[n] = s
            m[1:] = m[:-1]
            m[0] = s
        return y, m


def _quantize_vec(v: np.ndarray, n_bits: int, scale: float) -> bytes:
    """Uniform mid-riser quantizer → packed bytes (little-endian bit pack simplified)."""
    levels = 1 << min(n_bits, 16)
    q = np.clip(np.round((v / scale) * (levels / 2 - 1)), -(levels // 2), levels // 2 - 1)
    # store as int16 array for simplicity (bit-packing would save more)
    return q.astype(np.int16).tobytes()


def _dequantize_vec(data: bytes, n: int, n_bits: int, scale: float) -> np.ndarray:
    levels = 1 << min(n_bits, 16)
    q = np.frombuffer(data[: n * 2], dtype=np.int16).astype(np.float64)
    if len(q) < n:
        q = np.pad(q, (0, n - len(q)))
    return (q / (levels / 2 - 1)) * scale


def _mdct_like(x: np.ndarray, n_bins: int) -> np.ndarray:
    """Lightweight spectral projection (DCT-II style) for enhancement layers."""
    n = len(x)
    t = np.arange(n)
    out = np.zeros(n_bins)
    for k in range(n_bins):
        out[k] = np.dot(x, np.cos(np.pi / n * (t + 0.5) * k))
    return out / n


def _imdct_like(c: np.ndarray, n: int) -> np.ndarray:
    n_bins = len(c)
    t = np.arange(n)
    y = np.zeros(n)
    for k in range(n_bins):
        y += c[k] * np.cos(np.pi / n * (t + 0.5) * k)
    return y * 2.0


class G729EVCodec:
    """Multi-layer embedded wideband encoder/decoder."""

    def __init__(self, target_kbps: int = 24) -> None:
        self.set_bitrate(target_kbps)
        self._seq = 0
        self._syn_mem_lo = np.zeros(_LPC.ORDER)
        self._syn_mem_hi = np.zeros(_LPC.ORDER)
        self._prev_hi = np.zeros(FRAME_SAMPLES // 2)

    def set_bitrate(self, kbps: int) -> None:
        self.layers = rate_to_layers(kbps)
        self.bitrate = LAYER_RATES_KBPS[self.layers - 1]

    def encode(self, pcm16: np.ndarray) -> bytes:
        """Encode one 20 ms mono int16 frame → packed G729EV frame."""
        if len(pcm16) != FRAME_SAMPLES:
            raise ValueError(f"expected {FRAME_SAMPLES} samples, got {len(pcm16)}")
        x = pcm16.astype(np.float64) / 32768.0

        # Split into lower / upper 8 kHz bands via simple half-band
        lo = x[0::2].copy()  # 160 samples @ 8 kHz (NB core)
        hi = x[1::2].copy()

        # --- L1 core: LPC + residual pulse coding (20 bytes) ---
        a_lo = _LPC.analyze(lo)
        res = _LPC.residual(lo, a_lo)
        # energy + 4 residual shape samples + 10 LPC reflection-ish coeffs
        energy = float(np.sqrt(np.mean(res * res) + 1e-12))
        # pick 4 strongest residual positions (simplified algebraic codebook)
        idx = np.argsort(np.abs(res))[-4:]
        pulses = res[idx]
        l1 = bytearray(20)
        # pack LPC as 10 int8
        lpc_q = np.clip(np.round(a_lo * 64), -127, 127).astype(np.int8)
        l1[0:10] = lpc_q.tobytes()
        l1[10] = int(np.clip(np.round(np.log2(energy + 1e-6) * 16 + 64), 0, 255))
        for i, (p, v) in enumerate(zip(idx, pulses)):
            l1[11 + i] = int(p) & 0xFF
            l1[15 + i] = int(np.clip(np.round(v / (energy + 1e-9) * 64), -127, 127)) % 256
            if l1[15 + i] > 127:
                # store signed via int8 reinterpret
                pass
        # rewrite pulse values as int8
        pulse_i8 = np.clip(np.round(pulses / (energy + 1e-9) * 64), -127, 127).astype(np.int8)
        l1[15:19] = pulse_i8.tobytes()
        l1[19] = 0  # reserved / parity

        parts = [bytes(l1)]

        # --- L2 NB enhancement (10 bytes): residual spectrum fill ---
        if self.layers >= 2:
            spec = _mdct_like(res, 5)
            parts.append(_quantize_vec(spec, 12, energy * 4 + 0.1)[:10].ljust(10, b"\x00"))

        # --- L3 TDBWE-like upper band envelope (5 bytes) ---
        if self.layers >= 3:
            env = float(np.sqrt(np.mean(hi * hi) + 1e-12))
            a_hi = _LPC.analyze(hi)
            l3 = bytearray(5)
            l3[0] = int(np.clip(np.round(np.log2(env + 1e-6) * 16 + 64), 0, 255))
            l3[1:5] = np.clip(np.round(a_hi[:4] * 64), -127, 127).astype(np.int8).tobytes()
            parts.append(bytes(l3))

        # --- L4+ MDCT enhancement layers (5 bytes each) ---
        if self.layers >= 4:
            full_spec = _mdct_like(x, 40)
            n_enh = self.layers - 3
            bins_per = max(1, 40 // max(n_enh, 1))
            for li in range(n_enh):
                sl = full_spec[li * bins_per : (li + 1) * bins_per]
                if len(sl) == 0:
                    parts.append(b"\x00" * 5)
                    continue
                # 1 byte log-scale + 4× int8 spectral coeffs (5 bytes total)
                sc = float(np.max(np.abs(sl)) + 1e-9)
                log_sc = int(np.clip(np.round(np.log2(sc + 1e-9) * 16 + 128), 0, 255))
                coeffs = sl[:4] if len(sl) >= 4 else np.pad(sl, (0, 4 - len(sl)))
                q = np.clip(np.round(coeffs / sc * 127), -127, 127).astype(np.int8)
                parts.append(bytes([log_sc]) + q.tobytes()[:4])

        data = b"".join(parts)
        assert len(data) == layers_to_bytes(self.layers)
        fr = G729EVFrame(seq=self._seq, layers=self.layers, data=data)
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        return fr.pack()

    def decode(self, blob: bytes) -> np.ndarray:
        """Decode packed frame → int16 mono PCM of FRAME_SAMPLES."""
        fr = G729EVFrame.unpack(blob)
        data = fr.data
        off = 0

        # L1
        l1 = data[off : off + 20]
        off += 20
        a_lo = np.frombuffer(l1[0:10], dtype=np.int8).astype(np.float64) / 64.0
        log_e = (l1[10] - 64) / 16.0
        energy = float(2.0 ** log_e)
        idx = list(l1[11:15])
        pulses = np.frombuffer(bytes(l1[15:19]), dtype=np.int8).astype(np.float64) / 64.0 * energy

        res = np.zeros(FRAME_SAMPLES // 2)
        for p, v in zip(idx, pulses):
            if 0 <= p < len(res):
                res[p] += v
        # mild noise fill for uncoded residual
        rng = np.random.default_rng((fr.seq * 2654435761) & 0xFFFFFFFF)
        res += rng.normal(0, energy * 0.15, size=res.shape)

        if fr.layers >= 2 and off + 10 <= len(data):
            l2 = data[off : off + 10]
            off += 10
            spec = _dequantize_vec(l2, 5, 12, energy * 4 + 0.1)
            res = res + _imdct_like(spec, len(res)) * 0.5

        lo, self._syn_mem_lo = _LPC.synthesize(res, a_lo, self._syn_mem_lo)

        # Upper band
        hi = np.zeros(FRAME_SAMPLES // 2)
        if fr.layers >= 3 and off + 5 <= len(data):
            l3 = data[off : off + 5]
            off += 5
            env = float(2.0 ** ((l3[0] - 64) / 16.0))
            a_hi = np.zeros(_LPC.ORDER)
            a_hi[:4] = np.frombuffer(l3[1:5], dtype=np.int8).astype(np.float64) / 64.0
            exc = rng.normal(0, env, size=FRAME_SAMPLES // 2)
            hi, self._syn_mem_hi = _LPC.synthesize(exc, a_hi, self._syn_mem_hi)
            # envelope match
            cur = float(np.sqrt(np.mean(hi * hi) + 1e-12))
            if cur > 1e-9:
                hi *= env / cur

        # Higher MDCT layers → add fullband residual
        full_add = np.zeros(FRAME_SAMPLES)
        if fr.layers >= 4:
            n_enh = fr.layers - 3
            coeffs = np.zeros(40)
            bins_per = max(1, 40 // max(n_enh, 1))
            for li in range(n_enh):
                if off + 5 > len(data):
                    break
                chunk = data[off : off + 5]
                off += 5
                sc = float(2.0 ** ((chunk[0] - 128) / 16.0))
                c = np.frombuffer(chunk[1:5], dtype=np.int8).astype(np.float64) / 127.0 * sc
                start = li * bins_per
                coeffs[start : start + len(c)] = c[: max(0, 40 - start)]
            full_add = _imdct_like(coeffs, FRAME_SAMPLES) * 0.35

        # Interleave lo/hi back to 16 kHz
        y = np.zeros(FRAME_SAMPLES)
        y[0::2] = lo
        y[1::2] = hi
        y += full_add
        y = np.clip(y, -1.0, 1.0)
        return (y * 32767.0).astype(np.int16)


def silence_frame(seq: int = 0, layers: int = 1) -> bytes:
    codec = G729EVCodec(LAYER_RATES_KBPS[layers - 1])
    codec._seq = seq
    return codec.encode(np.zeros(FRAME_SAMPLES, dtype=np.int16))
