"""Lightweight Canvas viewer — serves JPEG frames + PCM audio to a browser.

No external dependencies beyond sounddevice (for audio capture).
The browser polls GET /frame and GET /audio, renders via requestAnimationFrame.
"""

from __future__ import annotations

import base64
import http.server
import json
import struct
import threading
import webbrowser
from typing import Optional

import cv2
import numpy as np


_VIEWER_HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ASCIILINE Canvas Viewer</title>
<style>
  * { margin: 0; padding: 0; }
  body { background: #000; overflow: hidden; display: flex;
         align-items: center; justify-content: center; height: 100vh; }
  canvas { image-rendering: pixelated; max-width: 100vw; max-height: 100vh; }
  #info { position: fixed; top: 8px; left: 8px; color: #888;
          font: 12px monospace; pointer-events: none; z-index: 1; }
  #audio-btn { position: fixed; top: 8px; right: 8px; z-index: 1;
               padding: 6px 14px; background: #333; color: #ccc;
               border: 1px solid #555; border-radius: 4px; cursor: pointer;
               font: 13px monospace; }
  #audio-btn:hover { background: #444; }
</style>
</head>
<body>
<div id="info"></div>
<button id="audio-btn">Enable Sound</button>
<canvas id="c"></canvas>
<script>
const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');
const info = document.getElementById('info');
const audioBtn = document.getElementById('audio-btn');
let frames = 0, lastFps = 0, fpsTime = performance.now();
let audioCtx = null, audioEnabled = false, audioPending = false;
let audioNextTime = 0;
const SAMPLE_RATE = 8000;
const CHUNK_MS = 40;

function enableAudio() {
  if (!audioCtx) {
    audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
  }
  if (audioCtx.state === 'suspended') audioCtx.resume();
  audioEnabled = true;
  audioBtn.textContent = 'Mute';
  audioBtn.style.borderColor = '#555';
  if (!audioPending) pollAudio();
}

audioBtn.addEventListener('click', () => {
  if (!audioEnabled) {
    enableAudio();
  } else {
    audioEnabled = false;
    audioBtn.textContent = 'Unmute';
    audioBtn.style.borderColor = '#a66';
  }
});

function pollAudio() {
  if (!audioEnabled) { audioPending = false; return; }
  audioPending = true;
  fetch('/audio')
    .then(r => r.json())
    .then(data => {
      if (data.pcm && audioEnabled) {
        if (!audioCtx) audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
        if (audioCtx.state === 'suspended') audioCtx.resume();
        const raw = atob(data.pcm);
        const buf = new Int16Array(raw.length / 2);
        for (let i = 0; i < buf.length; i++)
          buf[i] = (raw.charCodeAt(i*2) & 0xff) | (raw.charCodeAt(i*2+1) << 8);
        const abuf = audioCtx.createBuffer(1, buf.length, SAMPLE_RATE);
        const float32 = abuf.getChannelData(0);
        for (let i = 0; i < buf.length; i++) float32[i] = buf[i] / 32768;
        // Schedule playback: if we're ahead, play immediately; otherwise skip
        const now = audioCtx.currentTime;
        if (audioNextTime < now) audioNextTime = now;
        const src = audioCtx.createBufferSource();
        src.buffer = abuf;
        src.connect(audioCtx.destination);
        src.start(audioNextTime);
        audioNextTime += abuf.duration;
        // If we've fallen behind by more than 2 chunks, snap forward
        if (audioNextTime < now - CHUNK_MS * 2 / 1000) audioNextTime = now;
      }
      setTimeout(pollAudio, CHUNK_MS);
    })
    .catch(() => { setTimeout(pollAudio, CHUNK_MS); });
}

function tick() {
  fetch('/frame')
    .then(r => r.json())
    .then(data => {
      if (data.data) {
        const img = new Image();
        img.onload = () => {
          if (canvas.width !== img.width || canvas.height !== img.height) {
            canvas.width = img.width;
            canvas.height = img.height;
          }
          ctx.drawImage(img, 0, 0);
          frames++;
          const now = performance.now();
          if (now - fpsTime >= 1000) {
            lastFps = frames;
            frames = 0;
            fpsTime = now;
          }
          info.textContent = img.width + 'x' + img.height + ' ' + lastFps + ' fps';
          setTimeout(tick, 33);
        };
        img.src = 'data:image/jpeg;base64,' + data.data;
      } else {
        setTimeout(tick, 100);
      }
    })
    .catch(() => { setTimeout(tick, 200); });
}
tick();
</script>
</body>
</html>"""


class _FrameServer:
    """HTTP server that serves the Canvas viewer page, JPEG frames, and PCM audio."""

    def __init__(self) -> None:
        self._jpeg: bytes = b""
        self._pcm: bytes = b""  # raw int16 PCM chunks
        self._lock = threading.Lock()
        self._server: Optional[http.server.HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._audio_thread: Optional[threading.Thread] = None
        self._audio_running = False

    def push_frame(self, bgr: np.ndarray, quality: int = 60) -> None:
        """Encode a BGR frame as JPEG and store it."""
        ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if ok:
            with self._lock:
                self._jpeg = buf.tobytes()

    def push_frame_jpeg(self, jpeg_bytes: bytes) -> None:
        """Store pre-encoded JPEG bytes directly (avoids double encode)."""
        with self._lock:
            self._jpeg = jpeg_bytes

    def push_audio(self, pcm_int16: np.ndarray) -> None:
        """Store a chunk of int16 PCM audio."""
        with self._lock:
            self._pcm = pcm_int16.tobytes()

    def start(self, port: int = 0) -> int:
        """Start the HTTP server on *port* (0 = random). Returns the actual port."""
        server_ref = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/frame":
                    with server_ref._lock:
                        data = server_ref._jpeg
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    b64 = base64.b64encode(data).decode() if data else ""
                    self.wfile.write(json.dumps({"data": b64}).encode())
                elif self.path == "/audio":
                    with server_ref._lock:
                        pcm = server_ref._pcm
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    b64 = base64.b64encode(pcm).decode() if pcm else ""
                    self.wfile.write(json.dumps({"pcm": b64}).encode())
                elif self.path == "/":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(_VIEWER_HTML.encode())
                else:
                    self.send_error(404)

            def log_message(self, fmt: str, *args: object) -> None:
                pass

        self._server = http.server.HTTPServer(("127.0.0.1", port), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._thread.start()
        return self._server.server_address[1]

    def start_audio_capture(self) -> None:
        """Start capturing system audio from the loopback/monitor device."""
        if self._audio_running:
            return
        self._audio_running = True
        self._audio_thread = threading.Thread(
            target=self._audio_loop, daemon=True
        )
        self._audio_thread.start()

    def _audio_loop(self) -> None:
        """Capture system audio from the default output sink's monitor via pw-record."""
        import sys
        import subprocess
        import shutil
        import struct

        try:
            # Find default output sink and construct monitor source name
            result = subprocess.run(
                ["pactl", "info"],
                capture_output=True, text=True, timeout=5,
            )
            sink_name = None
            for line in result.stdout.splitlines():
                if line.startswith("Default Sink:"):
                    sink_name = line.split(":", 1)[1].strip()
                    break
            if not sink_name:
                print("[viewer-audio] no default sink found via pactl", file=sys.stderr, flush=True)
                self._audio_running = False
                return

            monitor_source = sink_name + ".monitor"

            # Verify the monitor source exists
            result = subprocess.run(
                ["pactl", "list", "sources", "short"],
                capture_output=True, text=True, timeout=5,
            )
            if monitor_source not in result.stdout:
                print(f"[viewer-audio] monitor source '{monitor_source}' not found", file=sys.stderr, flush=True)
                self._audio_running = False
                return

            RATE = 8000
            CHANNELS = 1
            CHUNK_SAMPLES = 320  # 40ms at 8kHz

            print(f"[viewer-audio] capturing from {monitor_source}", file=sys.stderr, flush=True)

            proc = subprocess.Popen(
                [
                    "pw-record",
                    "--target", monitor_source,
                    "--format", "s16",
                    "--rate", str(RATE),
                    "--channels", str(CHANNELS),
                    "-a",  # raw output, no container
                    "-",  # stdout
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )

            chunk_bytes = CHUNK_SAMPLES * 2  # s16 = 2 bytes per sample
            while self._audio_running:
                raw = proc.stdout.read(chunk_bytes)
                if not raw or len(raw) < chunk_bytes:
                    break
                with self._lock:
                    self._pcm = raw

            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception as exc:
            print(f"[viewer-audio] error: {exc}", file=sys.stderr, flush=True)
            self._audio_running = False

    def stop(self) -> None:
        self._audio_running = False
        if self._server:
            self._server.shutdown()
            self._server = None


def open_viewer(port: int) -> None:
    """Open the Canvas viewer in the default browser."""
    webbrowser.open(f"http://127.0.0.1:{port}")


_viewer_server: Optional[_FrameServer] = None
_viewer_ever_active: bool = False  # once True, terminal display stays suppressed


def start_viewer(port: int = 0) -> int:
    """Start the viewer server and open the browser. Returns the port."""
    global _viewer_server, _viewer_ever_active
    if _viewer_server is not None:
        return -1  # already running
    _viewer_server = _FrameServer()
    _viewer_ever_active = True
    actual_port = _viewer_server.start(port)
    _viewer_server.start_audio_capture()
    open_viewer(actual_port)
    return actual_port


def push_viewer_frame(bgr: np.ndarray, quality: int = 60) -> None:
    """Push a BGR frame to the viewer (if running)."""
    if _viewer_server is not None:
        _viewer_server.push_frame(bgr, quality)


def push_viewer_frame_jpeg(jpeg_bytes: bytes) -> None:
    """Push pre-encoded JPEG bytes to the viewer (if running)."""
    if _viewer_server is not None:
        _viewer_server.push_frame_jpeg(jpeg_bytes)


def stop_viewer() -> None:
    """Stop the viewer server."""
    global _viewer_server
    if _viewer_server is not None:
        _viewer_server.stop()
        _viewer_server = None
