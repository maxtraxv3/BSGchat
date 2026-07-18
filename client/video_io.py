"""ASCIILINE capture: webcam, desktop screen share, and remote render.

Sources (camera / screen) are independent tracks. Both can run at once; each
frame is tagged so receivers can display them separately.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Literal

import numpy as np

from shared.asciline import (
    FLAG_CAMERA,
    FLAG_REGION,
    FLAG_SCREEN,
    AsciiLineDecoder,
    AsciiLineEncoder,
)

SourceName = Literal["camera", "screen"]


@dataclass
class CaptureRegion:
    """Pixel region in global desktop coordinates (mss style)."""

    left: int
    top: int
    width: int
    height: int

    def as_mss(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


def list_monitors() -> list[dict]:
    """Return mss monitor list (index 0 = virtual all-monitors desktop)."""
    from mss import MSS

    with MSS() as sct:
        out = []
        for i, m in enumerate(sct.monitors):
            item = {"index": i, **{k: m[k] for k in ("left", "top", "width", "height") if k in m}}
            if i == 0:
                item["label"] = "all"
            else:
                item["label"] = m.get("output") or f"monitor-{i}"
                item["primary"] = bool(m.get("is_primary"))
            out.append(item)
        return out


class _Track:
    def __init__(
        self,
        name: SourceName,
        on_frame: Callable[[bytes], None],
        width: int,
        height: int,
        fps: int,
        flags: int,
    ) -> None:
        self.name = name
        self.on_frame = on_frame
        self.encoder = AsciiLineEncoder(width=width, height=height, fps=fps, flags=flags)
        self.fps = fps
        self._running = False
        self._thread: threading.Thread | None = None

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None


class VideoEngine:
    """Multi-source ASCIILINE transmitter + remote frame cache."""

    def __init__(
        self,
        on_frame: Callable[[bytes, SourceName], None],
        width: int = 80,
        height: int = 28,
        fps: int = 6,
        camera_index: int = 0,
        monitor: int = 1,
        region: CaptureRegion | None = None,
        screen_width: int | None = None,
        screen_height: int | None = None,
        screen_fps: int | None = None,
    ) -> None:
        self.on_frame = on_frame
        self.width = width
        self.height = height
        self.fps = fps
        self.camera_index = camera_index
        self.monitor = monitor
        self.region = region
        # Screen often benefits from a wider canvas for UI text
        self.screen_width = screen_width or max(width, 120)
        self.screen_height = screen_height or max(height, 40)
        self.screen_fps = screen_fps or min(fps, 5)

        self.decoder = AsciiLineDecoder()
        self._latest_remote: dict[str, str] = {}  # source → ascii text
        self._latest_meta: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._camera: _Track | None = None
        self._screen: _Track | None = None
        self._cap = None
        self._sct = None

    # --- remote cache --------------------------------------------------------

    def push_remote_frame(self, blob: bytes, source_hint: str | None = None) -> str:
        """Decode and cache; return resolved source name."""
        fr = self.decoder.decode(blob)
        if source_hint:
            src = source_hint
        elif fr.flags & FLAG_SCREEN:
            src = "screen"
        elif fr.flags & FLAG_CAMERA:
            src = "camera"
        else:
            src = "video"
        with self._lock:
            self._latest_remote[src] = fr.render()
            self._latest_meta[src] = {
                "width": fr.width,
                "height": fr.height,
                "seq": fr.seq,
                "flags": fr.flags,
            }
        return src

    def get_remote_view(self, source: str = "screen") -> str:
        with self._lock:
            if source in self._latest_remote:
                return self._latest_remote[source]
            # fall back to any available
            if self._latest_remote:
                return next(iter(self._latest_remote.values()))
            return ""

    def remote_sources(self) -> list[str]:
        with self._lock:
            return sorted(self._latest_remote.keys())

    # --- camera --------------------------------------------------------------

    def start_camera(self) -> None:
        if self._camera is not None:
            return
        import cv2

        self._cap = cv2.VideoCapture(self.camera_index)
        if not self._cap.isOpened():
            self._cap = None

        track = _Track(
            "camera",
            lambda b: self.on_frame(b, "camera"),
            self.width,
            self.height,
            self.fps,
            FLAG_CAMERA,
        )
        track._running = True
        track._thread = threading.Thread(
            target=self._camera_loop, args=(track,), name="asciline-camera", daemon=True
        )
        self._camera = track
        track._thread.start()

    def _camera_loop(self, track: _Track) -> None:
        import cv2

        period = 1.0 / max(track.fps, 1)
        t0 = 0.0
        while track._running:
            start = time.time()
            if self._cap is not None:
                ok, frame = self._cap.read()
                if not ok:
                    frame = self._test_pattern(t0)
                else:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                frame = self._test_pattern(t0)
            t0 += period
            try:
                blob = track.encoder.encode_gray(frame)
                track.on_frame(blob)
            except Exception:
                pass
            elapsed = time.time() - start
            time.sleep(max(0.0, period - elapsed))

    def stop_camera(self) -> None:
        if self._camera:
            self._camera.stop()
            self._camera = None
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    # --- screen share --------------------------------------------------------

    def start_screen(self) -> None:
        if self._screen is not None:
            return
        flags = FLAG_SCREEN | (FLAG_REGION if self.region is not None else 0)
        track = _Track(
            "screen",
            lambda b: self.on_frame(b, "screen"),
            self.screen_width,
            self.screen_height,
            self.screen_fps,
            flags,
        )
        track._running = True
        track._thread = threading.Thread(
            target=self._screen_loop, args=(track,), name="asciline-screen", daemon=True
        )
        self._screen = track
        track._thread.start()

    def _screen_loop(self, track: _Track) -> None:
        from mss import MSS

        period = 1.0 / max(track.fps, 1)
        with MSS() as sct:
            while track._running:
                start = time.time()
                try:
                    frame = self._grab_screen(sct)
                    blob = track.encoder.encode_gray(frame)
                    track.on_frame(blob)
                except Exception:
                    pass
                elapsed = time.time() - start
                time.sleep(max(0.0, period - elapsed))

    def _grab_screen(self, sct) -> np.ndarray:
        if self.region is not None:
            shot = sct.grab(self.region.as_mss())
        else:
            monitors = sct.monitors
            idx = self.monitor
            if idx < 0 or idx >= len(monitors):
                idx = 1 if len(monitors) > 1 else 0
            shot = sct.grab(monitors[idx])
        # mss returns BGRA
        bgra = np.array(shot, dtype=np.uint8)
        if bgra.ndim == 3 and bgra.shape[2] >= 3:
            # ITU-R BT.601 luma from BGR
            b = bgra[:, :, 0].astype(np.float32)
            g = bgra[:, :, 1].astype(np.float32)
            r = bgra[:, :, 2].astype(np.float32)
            gray = (0.114 * b + 0.587 * g + 0.299 * r).astype(np.uint8)
        else:
            gray = bgra.astype(np.uint8)
        return gray

    def stop_screen(self) -> None:
        if self._screen:
            self._screen.stop()
            self._screen = None

    def set_monitor(self, index: int) -> None:
        self.monitor = index
        self.region = None  # full monitor mode

    def set_region(self, left: int, top: int, width: int, height: int) -> None:
        if width < 8 or height < 8:
            raise ValueError("region too small")
        self.region = CaptureRegion(left, top, width, height)

    def clear_region(self) -> None:
        self.region = None

    # --- lifecycle -----------------------------------------------------------

    def start(self, source: SourceName = "camera") -> None:
        if source == "camera":
            self.start_camera()
        elif source == "screen":
            self.start_screen()
        else:
            raise ValueError(f"unknown source {source}")

    def stop(self) -> None:
        self.stop_camera()
        self.stop_screen()

    @property
    def camera_active(self) -> bool:
        return self._camera is not None

    @property
    def screen_active(self) -> bool:
        return self._screen is not None

    def _test_pattern(self, t: float) -> np.ndarray:
        h, w = 240, 320
        yy, xx = np.mgrid[0:h, 0:w]
        wave = (np.sin((xx + t * 40) * 0.05) + np.cos((yy - t * 25) * 0.07)) * 0.5 + 0.5
        return (wave * 255).astype(np.uint8)
