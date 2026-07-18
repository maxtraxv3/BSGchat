"""ASCIILINE — line-oriented ASCII video format for E2E chat.

ASCIILINE streams grayscale (or optional ANSI-color) frames as plain UTF-8
text lines so they can be rendered in any terminal without a pixel pipeline
on the receiver.

Wire format (UTF-8 text inside the encrypted VIDEO payload):

    ASCIILINE/1.0
    W:<cols> H:<rows> FPS:<n> SEQ:<u32> TS:<ms> FLAGS:<hex>
    <row 0>
    <row 1>
    ...
    <row H-1>
    .

Each data row is exactly W characters from the luminance ramp. The frame
terminates with a single '.' line.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

# Classic 70-char ramp (dark → bright); truncated variants work too
RAMP = np.array(list(" .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"))
RAMP_SIMPLE = np.array(list(" .:-=+*#%@"))

# FLAGS bits in the ASCIILINE header
FLAG_CAMERA = 0x01
FLAG_SCREEN = 0x02
FLAG_REGION = 0x04  # screen region crop (not full monitor)


def source_from_flags(flags: int) -> str:
    if flags & FLAG_SCREEN:
        return "screen"
    if flags & FLAG_CAMERA:
        return "camera"
    return "video"


@dataclass
class AsciiLineFrame:
    width: int
    height: int
    fps: int
    seq: int
    timestamp_ms: int
    flags: int
    rows: list[str]
    source: str = "video"

    def encode(self) -> bytes:
        header = (
            f"ASCIILINE/1.0\n"
            f"W:{self.width} H:{self.height} FPS:{self.fps} "
            f"SEQ:{self.seq} TS:{self.timestamp_ms} FLAGS:{self.flags:x} "
            f"SRC:{self.source}\n"
        )
        body = "\n".join(self.rows)
        return (header + body + "\n.\n").encode("utf-8")

    @classmethod
    def decode(cls, data: bytes) -> AsciiLineFrame:
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if not lines or not lines[0].startswith("ASCIILINE/"):
            raise ValueError("not an ASCIILINE frame")
        if len(lines) < 2:
            raise ValueError("missing ASCIILINE header")
        meta = {}
        for tok in lines[1].split():
            if ":" in tok:
                k, v = tok.split(":", 1)
                meta[k] = v
        width = int(meta.get("W", "0"))
        height = int(meta.get("H", "0"))
        fps = int(meta.get("FPS", "10"))
        seq = int(meta.get("SEQ", "0"))
        ts = int(meta.get("TS", "0"))
        flags = int(meta.get("FLAGS", "0"), 16)
        source = meta.get("SRC") or source_from_flags(flags)

        rows: list[str] = []
        for line in lines[2:]:
            if line == ".":
                break
            rows.append(line[:width].ljust(width) if width else line)
        if height and len(rows) < height:
            rows.extend([" " * width] * (height - len(rows)))
        elif height and len(rows) > height:
            rows = rows[:height]
        return cls(width, height, fps, seq, ts, flags, rows, source=source)

    def render(self) -> str:
        return "\n".join(self.rows)


class AsciiLineEncoder:
    """Raster frame → ASCIILINE bytes."""

    def __init__(
        self,
        width: int = 80,
        height: int = 36,
        fps: int = 8,
        ramp: str | None = None,
        flags: int = 0,
        source: str | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.flags = flags
        self.source = source or source_from_flags(flags)
        # denser ramp for screen share (UI text readability)
        if ramp:
            self.ramp = np.array(list(ramp))
        elif flags & FLAG_SCREEN:
            self.ramp = RAMP
        else:
            self.ramp = RAMP_SIMPLE
        self._seq = 0

    def encode_gray(self, gray: np.ndarray) -> bytes:
        """gray: HxW uint8 or float image (any size — will be resized)."""
        import cv2

        if gray.dtype != np.uint8:
            g = np.clip(gray, 0, 255).astype(np.uint8)
        else:
            g = gray
        if g.ndim == 3:
            g = cv2.cvtColor(g, cv2.COLOR_BGR2GRAY)
        # AREA downsample preserves more UI detail for screen share
        interp = cv2.INTER_AREA
        resized = cv2.resize(g, (self.width, self.height), interpolation=interp)
        # optional contrast stretch
        lo, hi = np.percentile(resized, [2, 98] if (self.flags & FLAG_SCREEN) else [5, 95])
        if hi <= lo:
            hi = lo + 1
        norm = np.clip((resized.astype(np.float32) - lo) / (hi - lo), 0, 1)
        idx = (norm * (len(self.ramp) - 1)).astype(np.int32)
        chars = self.ramp[idx]
        rows = ["".join(row.tolist()) for row in chars]
        fr = AsciiLineFrame(
            width=self.width,
            height=self.height,
            fps=self.fps,
            seq=self._seq,
            timestamp_ms=int(time.time() * 1000) & 0xFFFFFFFF,
            flags=self.flags,
            rows=rows,
            source=self.source,
        )
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        return fr.encode()


class AsciiLineDecoder:
    """ASCIILINE bytes → terminal string."""

    def decode(self, data: bytes) -> AsciiLineFrame:
        return AsciiLineFrame.decode(data)
