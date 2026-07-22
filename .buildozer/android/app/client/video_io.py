"""ASCIILINE capture: webcam, desktop screen share, and remote render.

Sources (camera / screen) are independent tracks. Both can run at once; each
frame is tagged so receivers can display them separately.

Screen share uses :mod:`client.screencap` which auto-selects a working backend
(grim / spectacle / mss / ImageMagick) — needed because mss is black on many
Wayland compositors (including KDE kwin_wayland).
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Literal

import numpy as np

from client.screencap import Region as CapRegion
from client.screencap import ScreenGrabber, backend_status, list_monitors
from shared.asciline import (
    FLAG_CAMERA,
    FLAG_REGION,
    FLAG_SCREEN,
    AsciiLineDecoder,
    AsciiLineEncoder,
)

SourceName = Literal["camera", "screen"]

# re-export for client.main
__all__ = ["VideoEngine", "CaptureRegion", "list_monitors", "backend_status"]


class CaptureRegion(CapRegion):
    """Pixel region in global desktop coordinates."""

    def as_mss(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


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
        # The encoder only accepts flags. We do not pass mode/pixel kwargs here.
        self.encoder = AsciiLineEncoder(width=width, height=height, fps=fps, flags=flags)
        self.fps = fps
        self._running = False
        self._thread: threading.Thread | None = None

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
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
        screen_backend: str | None = None,
        mode: int = 5,
        pixel: bool = True,
    ) -> None:
        self.on_frame = on_frame
        self.width = width
        self.height = height
        self.fps = fps
        self.camera_index = camera_index
        self.monitor = monitor
        self.region = region
        self.screen_width = screen_width or max(width, 120)
        self.screen_height = screen_height or max(height, 40)
        self.screen_fps = screen_fps if screen_fps is not None else 30
        self.screen_backend_pref = screen_backend

        # Store global runtime preferences
        self.mode = mode
        self.pixel = pixel

        self.decoder = AsciiLineDecoder()
        self._latest_remote: dict[str, str] = {}
        self._latest_meta: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._camera: _Track | None = None
        self._screen: _Track | None = None
        self._cap = None
        self.grabber: ScreenGrabber | None = None
        self.screen_backend_name: str | None = None

    # --- remote cache --------------------------------------------------------

    def push_remote_frame(self, blob: bytes, source_hint: str | None = None) -> str:
        fr = self.decoder.decode(blob)
        if source_hint:
            src = source_hint
        elif fr.flags & FLAG_SCREEN:
            src = "screen"
        elif fr.flags & FLAG_CAMERA:
            src = "camera"
        else:
            src = "video"

        # Push embedded JPEG to Canvas viewer for screen frames (avoid decode+re-encode)
        if fr.img_b64 and src == "screen":
            import base64
            from client.web_viewer import push_viewer_frame_jpeg
            try:
                jpg_bytes = base64.b64decode(fr.img_b64)
                push_viewer_frame_jpeg(jpg_bytes)
            except Exception:
                pass

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
            if self._latest_remote:
                return next(iter(self._latest_remote.values()))
            return ""

    def remote_sources(self) -> list[str]:
        with self._lock:
            return sorted(self._latest_remote.keys())

    # --- camera --------------------------------------------------------------

    def start_camera(self, mode: int | None = None, pixel: bool | None = None) -> None:
        if self._camera is not None:
            return

        m = mode if mode is not None else self.mode
        p = pixel if pixel is not None else self.pixel

        import cv2

        self._cap = cv2.VideoCapture(self.camera_index)
        if not self._cap.isOpened():
            self._cap = None

        # Pack mode and pixel settings into the bitwise flags array
        flags = FLAG_CAMERA | (m << 8) | (1 if p else 0)

        track = _Track(
            "camera",
            lambda b: self.on_frame(b, "camera"),
            self.width,
            self.height,
            self.fps,
            flags,
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

    def start_screen(self, mode: int | None = None, pixel: bool | None = None) -> None:
        if self._screen is not None:
            return

        m = mode if mode is not None else self.mode
        p = pixel if pixel is not None else self.pixel

        grabber = ScreenGrabber(preferred=self.screen_backend_pref)
        name = grabber.probe(monitor=self.monitor)
        self.grabber = grabber
        self.screen_backend_name = name

        fps = min(self.screen_fps, grabber.max_fps)

        # Pack mode and pixel settings into the bitwise flags array
        flags = FLAG_SCREEN | (FLAG_REGION if self.region is not None else 0)
        flags |= (m << 8) | (1 if p else 0)

        track = _Track(
            "screen",
            lambda b: self.on_frame(b, "screen"),
            self.screen_width,
            self.screen_height,
            fps,
            flags,
        )
        track._running = True
        track._thread = threading.Thread(
            target=self._screen_loop, args=(track,), name="asciline-screen", daemon=True
        )
        self._screen = track
        track._thread.start()

    def _screen_loop(self, track: _Track) -> None:
        import base64
        import cv2

        from client.web_viewer import push_viewer_frame_jpeg

        period = 1.0 / max(track.fps, 1)
        assert self.grabber is not None

        # Start streaming capture so frames are always ready (avoids blocking on slow backends)
        if self.mode == 5:
            self.grabber.start_streaming(
                monitor=self.monitor, region=self.region, color=True
            )
        else:
            self.grabber.start_streaming(
                monitor=self.monitor, region=self.region, color=False
            )

        try:
            while track._running:
                start = time.time()
                try:
                    frame = self.grabber.get_latest()
                    if frame is None:
                        time.sleep(0.01)
                        continue

                    if self.mode == 5:
                        # frame is BGR from streaming capture
                        thumb = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
                        ok, jpg_buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 60])
                        if ok:
                            jpg_bytes = jpg_buf.tobytes()
                            push_viewer_frame_jpeg(jpg_bytes)
                            img_b64 = base64.b64encode(jpg_bytes).decode()
                        else:
                            img_b64 = ""
                        blob = track.encoder.encode_color(frame, use_blocks=self.pixel, img_b64=img_b64)
                    else:
                        if frame.ndim == 3:
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.shape[2] >= 3 else frame[:, :, 0]
                        blob = track.encoder.encode_gray(frame)

                    track.on_frame(blob)
                except Exception as exc:
                    import sys
                    print(f"[screen] capture error: {exc}", file=sys.stderr, flush=True)
                elapsed = time.time() - start
                time.sleep(max(0.0, period - elapsed))
        finally:
            self.grabber.stop_streaming()

    def stop_screen(self) -> None:
        if self._screen:
            self._screen.stop()
            self._screen = None
        self.grabber = None

    def set_monitor(self, index: int) -> None:
        self.monitor = index
        self.region = None

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
