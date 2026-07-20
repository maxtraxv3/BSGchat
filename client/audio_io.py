"""Mic + system-loopback audio using free IMA-ADPCM (lowest CPU / light bandwidth).

The wire format is always 8 kHz ADPCM. Local audio devices run at a standard
rate (48 kHz by default) with lightweight linear resampling to/from 8 kHz.
This avoids "invalid sample rate" errors on devices that don't support 8 kHz.
"""

from __future__ import annotations

import queue
import sys
import threading
from typing import Callable

import numpy as np

from shared.adpcm import (
    FRAME_SAMPLES,
    SAMPLE_RATE,
    WIRE_TAG,
    ADPCMCodec,
)

AudioFrameCB = Callable[[bytes, str], None]

# Local device rate — pick a standard rate most hardware supports.
DEVICE_SR = 48000
# How many device samples correspond to one 20 ms ADPCM frame.
DEVICE_FRAME = DEVICE_SR * 20 // 1000  # 960 @ 48 kHz


def _resample_to_8k(pcm48: np.ndarray) -> np.ndarray:
    """Downsample 48 kHz int16 → 8 kHz int16 via linear interpolation."""
    n_in = len(pcm48)
    n_out = n_in * SAMPLE_RATE // DEVICE_SR
    if n_out == 0:
        return np.zeros(0, dtype=np.int16)
    indices = np.linspace(0, n_in - 1, n_out)
    lo = indices.astype(np.int32)
    hi = np.minimum(lo + 1, n_in - 1)
    frac = (indices - lo).astype(np.float32)
    out = (pcm48[lo].astype(np.float32) * (1 - frac) + pcm48[hi].astype(np.float32) * frac).astype(np.int16)
    return out


def _resample_from_8k(pcm8: np.ndarray, target_len: int) -> np.ndarray:
    """Upsample 8 kHz int16 → target_len at device rate via linear interpolation."""
    n_in = len(pcm8)
    if n_in == 0 or target_len == 0:
        return np.zeros(target_len, dtype=np.int16)
    indices = np.linspace(0, n_in - 1, target_len)
    lo = indices.astype(np.int32)
    hi = np.minimum(lo + 1, n_in - 1)
    frac = (indices - lo).astype(np.float32)
    out = (pcm8[lo].astype(np.float32) * (1 - frac) + pcm8[hi].astype(np.float32) * frac).astype(np.int16)
    return out


def list_devices() -> str:
    try:
        import sounddevice as sd

        return str(sd.query_devices())
    except Exception as exc:
        return f"(sounddevice unavailable: {exc})"


def find_loopback_device() -> int | None:
    try:
        import sounddevice as sd
    except Exception:
        return None

    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    prefer_substrings = (
        "loopback",
        "monitor of",
        "monitor",
        "blackhole",
        "soundflower",
        "cable output",
        "stereo mix",
        "what u hear",
        "wave out mix",
    )
    candidates: list[tuple[int, int]] = []
    for i, d in enumerate(devices):
        if d["max_input_channels"] < 1:
            continue
        name = (d["name"] or "").lower()
        score = 0
        for j, sub in enumerate(prefer_substrings):
            if sub in name:
                score = 100 - j
                break
        if score:
            candidates.append((score, i))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]

    if sys.platform == "win32":
        try:
            out = sd.default.device[1]
            if out is not None and int(out) >= 0:
                return int(out)
        except Exception:
            pass
    return None


def _wasapi_loopback_settings():
    if sys.platform != "win32":
        return None
    try:
        import sounddevice as sd

        if hasattr(sd, "WasapiSettings"):
            return sd.WasapiSettings(loopback=True)
    except Exception:
        return None
    return None


class VoiceEngine:
    """Mic capture → ADPCM; remote ADPCM → speakers. Optional system loopback TX."""

    def __init__(
        self,
        on_frame: AudioFrameCB,
        input_device: int | None = None,
        output_device: int | None = None,
        dtx: bool = True,
    ) -> None:
        self.on_frame = on_frame
        self.input_device = input_device
        self.output_device = output_device
        self.dtx = dtx
        self.codec_mic_tx = ADPCMCodec(dtx=dtx)
        self.codec_sys_tx = ADPCMCodec(dtx=dtx)
        self.codec_mic_rx = ADPCMCodec(dtx=False)
        self.codec_sys_rx = ADPCMCodec(dtx=False)
        self._play_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=80)
        self._running = False
        self._sys_running = False
        self._stream_in = None
        self._stream_out = None
        self._stream_sys = None
        self.system_device: int | None = None
        # Accumulate device samples that don't fill a full ADPCM frame
        self._in_buf: np.ndarray = np.zeros(0, dtype=np.int16)

    def start_listen(self) -> None:
        """Start speaker-only (receive) mode, no mic capture."""
        if self._running:
            return
        self._ensure_output_only()

    def start(self) -> None:
        if self._running:
            return
        import sounddevice as sd

        self._running = True
        self._in_buf = np.zeros(0, dtype=np.int16)

        def _in_cb(indata, frames, time_info, status):  # noqa: ARG001
            if not self._running:
                return
            mono = indata[:, 0] if indata.ndim > 1 else indata.reshape(-1)
            pcm_chunk = np.clip(mono * 32767.0, -32768, 32767).astype(np.int16)
            self._in_buf = np.concatenate([self._in_buf, pcm_chunk])
            while len(self._in_buf) >= DEVICE_FRAME:
                chunk = self._in_buf[:DEVICE_FRAME]
                self._in_buf = self._in_buf[DEVICE_FRAME:]
                pcm8 = _resample_to_8k(chunk)
                if len(pcm8) != FRAME_SAMPLES:
                    pcm8 = (np.pad(pcm8, (0, FRAME_SAMPLES - len(pcm8)))
                            if len(pcm8) < FRAME_SAMPLES else pcm8[:FRAME_SAMPLES])
                try:
                    blob = self.codec_mic_tx.encode(pcm8)
                    if blob is not None:
                        self.on_frame(blob, "mic")
                except Exception:
                    pass

        def _out_cb(outdata, frames, time_info, status):  # noqa: ARG001
            try:
                pcm48 = self._play_q.get_nowait()
            except queue.Empty:
                outdata.fill(0)
                return
            # pcm48 is already at device rate; convert to float32 for output
            if len(pcm48) < frames:
                pcm48 = np.pad(pcm48, (0, frames - len(pcm48)))
            f = pcm48.astype(np.float32) / 32768.0
            outdata[:, 0] = f[:frames]

        self._stream_in = sd.InputStream(
            samplerate=DEVICE_SR,
            channels=1,
            dtype="float32",
            blocksize=DEVICE_FRAME,
            device=self.input_device,
            callback=_in_cb,
        )
        self._stream_out = sd.OutputStream(
            samplerate=DEVICE_SR,
            channels=1,
            dtype="float32",
            blocksize=DEVICE_FRAME,
            device=self.output_device,
            callback=_out_cb,
        )
        self._stream_in.start()
        self._stream_out.start()

    def start_system_audio(self, device: int | None = None) -> str:
        if self._sys_running:
            return "system audio already on"
        if not self._running:
            self.start()

        import sounddevice as sd

        dev = device if device is not None else find_loopback_device()
        extra = None
        note = ""
        if dev is None:
            raise RuntimeError(
                "no system/loopback device found. "
                "Windows: enable Stereo Mix or use default output (WASAPI loopback). "
                "macOS: install BlackHole and set multi-output device. "
                "Linux: use a Pulse/PipeWire monitor source."
            )

        if sys.platform == "win32":
            extra = _wasapi_loopback_settings()
            try:
                info = sd.query_devices(dev)
                if info["max_input_channels"] < 1 and extra is None:
                    raise RuntimeError("WASAPI loopback not available in sounddevice")
            except Exception:
                pass
            note = f"device={dev} wasapi_loopback={extra is not None}"
        else:
            note = f"device={dev} ({sd.query_devices(dev)['name']})"

        self.system_device = dev
        self._sys_running = True

        def _sys_cb(indata, frames, time_info, status):  # noqa: ARG001
            if not self._sys_running:
                return
            mono = indata[:, 0] if indata.ndim > 1 else indata.reshape(-1)
            if indata.ndim > 1 and indata.shape[1] > 1:
                mono = indata.mean(axis=1)
            pcm_chunk = np.clip(mono * 32767.0, -32768, 32767).astype(np.int16)
            pcm8 = _resample_to_8k(pcm_chunk)
            if len(pcm8) != FRAME_SAMPLES:
                pcm8 = (np.pad(pcm8, (0, FRAME_SAMPLES - len(pcm8)))
                        if len(pcm8) < FRAME_SAMPLES else pcm8[:FRAME_SAMPLES])
            try:
                blob = self.codec_sys_tx.encode(pcm8)
                if blob is not None:
                    self.on_frame(blob, "system")
            except Exception:
                pass

        kwargs = dict(
            samplerate=DEVICE_SR,
            channels=1,
            dtype="float32",
            blocksize=DEVICE_FRAME,
            device=dev,
            callback=_sys_cb,
        )
        if extra is not None:
            kwargs["extra_settings"] = extra
            try:
                self._stream_sys = sd.InputStream(**kwargs)
                self._stream_sys.start()
            except Exception:
                kwargs["channels"] = 2
                self._stream_sys = sd.InputStream(**kwargs)
                self._stream_sys.start()
        else:
            try:
                self._stream_sys = sd.InputStream(**kwargs)
                self._stream_sys.start()
            except Exception:
                kwargs["channels"] = 2
                self._stream_sys = sd.InputStream(**kwargs)
                self._stream_sys.start()

        return note

    def stop_system_audio(self) -> None:
        self._sys_running = False
        if self._stream_sys is not None:
            try:
                self._stream_sys.stop()
                self._stream_sys.close()
            except Exception:
                pass
            self._stream_sys = None

    def push_remote_frame(self, blob: bytes, track: str = "mic") -> None:
        if not self._running:
            try:
                self._ensure_output_only()
            except Exception:
                return
        try:
            codec = self.codec_sys_rx if track == "system" else self.codec_mic_rx
            pcm8 = codec.decode(blob)  # 8 kHz int16, FRAME_SAMPLES
            # Upsample to device rate
            pcm48 = _resample_from_8k(pcm8, DEVICE_FRAME)
            try:
                self._play_q.put_nowait(pcm48)
            except queue.Full:
                try:
                    self._play_q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._play_q.put_nowait(pcm48)
                except queue.Full:
                    pass
        except Exception:
            pass

    def _ensure_output_only(self) -> None:
        if self._stream_out is not None:
            self._running = True
            return
        import sounddevice as sd

        self._running = True

        def _out_cb(outdata, frames, time_info, status):  # noqa: ARG001
            try:
                pcm48 = self._play_q.get_nowait()
            except queue.Empty:
                outdata.fill(0)
                return
            if len(pcm48) < frames:
                pcm48 = np.pad(pcm48, (0, frames - len(pcm48)))
            f = pcm48.astype(np.float32) / 32768.0
            outdata[:, 0] = f[:frames]

        self._stream_out = sd.OutputStream(
            samplerate=DEVICE_SR,
            channels=1,
            dtype="float32",
            blocksize=DEVICE_FRAME,
            device=self.output_device,
            callback=_out_cb,
        )
        self._stream_out.start()

    def stop(self) -> None:
        self.stop_system_audio()
        self._running = False
        for s in (self._stream_in, self._stream_out):
            if s is not None:
                try:
                    s.stop()
                    s.close()
                except Exception:
                    pass
        self._stream_in = None
        self._stream_out = None
        while not self._play_q.empty():
            try:
                self._play_q.get_nowait()
            except queue.Empty:
                break


def codec_info() -> str:
    return (
        f"{WIRE_TAG}  {SAMPLE_RATE} Hz mono  {FRAME_SAMPLES} samples/20ms  "
        f"~{ADPCMCodec().bitrate} kb/s active  DTX on silence  (free / public-domain IMA)"
    )
