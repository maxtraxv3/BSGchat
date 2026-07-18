"""Microphone capture and speaker playback for G.729.1 frames."""

from __future__ import annotations

import queue
import threading
from typing import Callable

import numpy as np

from shared.g729ev import FRAME_SAMPLES, SAMPLE_RATE, G729EVCodec


class VoiceEngine:
    """Capture → G.729EV encode; G.729EV decode → playback."""

    def __init__(
        self,
        on_frame: Callable[[bytes], None],
        bitrate_kbps: int = 24,
        input_device: int | None = None,
        output_device: int | None = None,
    ) -> None:
        self.on_frame = on_frame
        self.codec_tx = G729EVCodec(bitrate_kbps)
        self.codec_rx = G729EVCodec(bitrate_kbps)
        self.input_device = input_device
        self.output_device = output_device
        self._play_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=50)
        self._running = False
        self._stream_in = None
        self._stream_out = None
        self._sd = None

    def set_bitrate(self, kbps: int) -> None:
        self.codec_tx.set_bitrate(kbps)

    def start(self) -> None:
        if self._running:
            return
        import sounddevice as sd

        self._sd = sd
        self._running = True

        def _in_cb(indata, frames, time_info, status):  # noqa: ARG001
            if not self._running:
                return
            mono = indata[:, 0] if indata.ndim > 1 else indata
            pcm = np.clip(mono * 32767.0, -32768, 32767).astype(np.int16)
            if len(pcm) != FRAME_SAMPLES:
                # sounddevice should give exact blocksize; pad/trim just in case
                if len(pcm) < FRAME_SAMPLES:
                    pcm = np.pad(pcm, (0, FRAME_SAMPLES - len(pcm)))
                else:
                    pcm = pcm[:FRAME_SAMPLES]
            try:
                blob = self.codec_tx.encode(pcm)
                self.on_frame(blob)
            except Exception:
                pass

        def _out_cb(outdata, frames, time_info, status):  # noqa: ARG001
            try:
                pcm = self._play_q.get_nowait()
            except queue.Empty:
                outdata.fill(0)
                return
            f = pcm.astype(np.float32) / 32768.0
            if len(f) < frames:
                f = np.pad(f, (0, frames - len(f)))
            outdata[:, 0] = f[:frames]

        self._stream_in = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=FRAME_SAMPLES,
            device=self.input_device,
            callback=_in_cb,
        )
        self._stream_out = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=FRAME_SAMPLES,
            device=self.output_device,
            callback=_out_cb,
        )
        self._stream_in.start()
        self._stream_out.start()

    def push_remote_frame(self, blob: bytes) -> None:
        if not self._running:
            return
        try:
            pcm = self.codec_rx.decode(blob)
            try:
                self._play_q.put_nowait(pcm)
            except queue.Full:
                try:
                    self._play_q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._play_q.put_nowait(pcm)
                except queue.Full:
                    pass
        except Exception:
            pass

    def stop(self) -> None:
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


def list_devices() -> str:
    try:
        import sounddevice as sd

        return str(sd.query_devices())
    except Exception as exc:
        return f"(sounddevice unavailable: {exc})"
