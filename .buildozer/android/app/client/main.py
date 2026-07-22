#!/usr/bin/env python3
"""E2E encrypted chat client with ASCIILINE video and ADPCM voice."""

from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import os
import queue
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from typing import TYPE_CHECKING

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from shared.adpcm import SAMPLE_RATE
from shared.crypto import (
    SessionKeys,
    b64,
    b64d,
    derive_session,
    generate_identity,
    new_ephemeral,
)
from shared.protocol import FrameReader, MsgType, Packet, pack_json, unpack_json
from shared.image_share import (
    ImageMessage,
    load_and_convert,
    pack_image_payload,
    unpack_image_payload,
    save_received_image,
    format_image_info,
    format_image_preview,
    DEFAULT_QUALITY,
)
from shared.file_share import (
    FileMessage,
    make_file_id,
    pack_file_payload,
    unpack_file_payload,
    save_received_file,
    format_file_info,
    MAX_FILE_SIZE,
)

if TYPE_CHECKING:
    from client.audio_io import VoiceEngine
    from client.video_io import VideoEngine


def _enable_windows_vt() -> None:
    """Enable VT100 escape code processing on Windows console."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        STD_OUTPUT_HANDLE = -11
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        pass  # best-effort; works on Windows Terminal without this


_enable_windows_vt()


class ChatClient:
    def __init__(
        self,
        host: str,
        port: int,
        room: str,
        user_id: str,
        display: str,
        voice: bool,
        video: bool,
        screen: bool,
        cam: int,
        monitor: int,
        ascii_w: int,
        ascii_h: int,
        ascii_fps: int,
        screen_w: int,
        screen_h: int,
        screen_fps: int,
        mode: int,
        pixel: bool,
        auto_show_screen: bool = False,
        want_viewer: bool = False,
        tor_proxy: str = "",
        upnp: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.room = room
        self.user_id = user_id
        self.display = display
        self.want_voice = voice
        self.want_video = video
        self.want_screen = screen
        self.want_viewer = want_viewer
        self.cam = cam
        self.monitor = monitor
        self.ascii_w = ascii_w
        self.ascii_h = ascii_h
        self.ascii_fps = ascii_fps
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.screen_fps = screen_fps
        self.mode = mode
        self.pixel = pixel
        self.auto_show_screen = auto_show_screen
        self.tor_proxy = tor_proxy
        self.upnp = upnp
        self._upnp_mapping = None
        self._last_shown_seq: dict[str, int] = {}
        self._frame_lines: int = 0  # lines printed by last video frame (for in-place update)
        self._received_images: dict[str, tuple[ImageMessage, bytes, str]] = {}  # id → (meta, webp, preview)
        self._received_files: dict[str, tuple[FileMessage, bytes]] = {}  # id → (meta, file_bytes)
        self._input_device: int | None = None
        self._output_device: int | None = None

        self.identity_priv, self.identity_pub = generate_identity()
        self.eph_priv: X25519PrivateKey | None = None
        self.eph_pub: bytes = b""

        self.sessions: dict[str, SessionKeys] = {}
        self.peer_identity: dict[str, bytes] = {}
        self.peer_display: dict[str, str] = {}
        self.pending_eph: dict[str, bytes] = {}  # peer → their eph pub awaiting ours

        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

        self.voice: VoiceEngine | None = None
        self.video: VideoEngine | None = None
        self._stop = asyncio.Event()
        self._print_lock = threading.Lock()
        self.voice_active_peers: dict[str, bool] = {}
        self.voice_is_active: bool = False
        self._gui_queue: queue.Queue | None = None  # set by GUI
        self._gui_mode: bool = False

    # --- UI helpers ----------------------------------------------------------

    def ui(self, msg: str) -> None:
        if self._gui_queue is not None:
            self._gui_queue.put(("ui", (msg,), {}))
            return
        with self._print_lock:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()

    def ui_status(self, msg: str) -> None:
        if self._gui_queue is not None:
            self._gui_queue.put(("ui_status", (msg,), {}))
            return
        self.ui(f"\033[90m* {msg}\033[0m")

    def ui_sys(self, msg: str) -> None:
        if self._gui_queue is not None:
            self._gui_queue.put(("ui_sys", (msg,), {}))
            return
        self.ui(f"\033[36m* {msg}\033[0m")

    def ui_chat(self, who: str, text: str) -> None:
        if self._gui_queue is not None:
            self._gui_queue.put(("ui_chat", (who, text), {}))
            return
        self.ui(f"\033[1m<{who}>\033[0m {text}")

    def ui_video_jpeg(self, jpeg_bytes: bytes, source: str) -> None:
        """Push a raw JPEG frame to the GUI (if active)."""
        if self._gui_queue is not None:
            self._gui_queue.put(("ui_video_jpeg", (jpeg_bytes, source), {}))

    def ui_image(self, image_id: str, webp_bytes: bytes, sender: str, name: str, width: int, height: int) -> None:
        """Push a received image to the GUI for pixel display."""
        if self._gui_queue is not None:
            self._gui_queue.put(("ui_image", (image_id, webp_bytes, sender, name, width, height), {}))

    def ui_file(self, file_id: str, file_bytes: bytes, sender: str, name: str, mime_type: str, size: int) -> None:
        """Push a received file to the GUI for display."""
        if self._gui_queue is not None:
            self._gui_queue.put(("ui_file", (file_id, file_bytes, sender, name, mime_type, size), {}))

    def ui_video_frame(self, text: str, label: str = "ASCIILINE") -> None:
        lines = text.splitlines()
        if not lines:
            return
        n = len(lines)
        with self._print_lock:
            # Move cursor up to overwrite previous frame if we printed one
            if self._frame_lines > 0:
                sys.stdout.write(f"\033[{self._frame_lines + 1}A")
            # Header line
            sys.stdout.write(f"\033[33m── {label} ({n} rows) ──\033[0m\033[K\n")
            for line in lines:
                sys.stdout.write(line + "\033[K\n")
            sys.stdout.flush()
            self._frame_lines = n + 1  # header + frame rows

    # --- networking ----------------------------------------------------------

    async def connect(self) -> None:
        self.loop = asyncio.get_running_loop()
        if self.tor_proxy:
            try:
                from python_socks.async_.asyncio import Proxy
            except ImportError:
                self.ui_status("python-socks not installed. Run: pip install python-socks[asyncio]")
                raise SystemExit(1)
            proxy = Proxy.from_url(self.tor_proxy)
            sock = await proxy.connect(dest_host=self.host, dest_port=self.port)
            self.reader, self.writer = await asyncio.open_connection(sock=sock)
        else:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        hello = pack_json(
            MsgType.HELLO,
            {
                "user_id": self.user_id,
                "display": self.display,
                "room": self.room,
                "identity_pub": b64(self.identity_pub),
            },
        )
        await self._send(hello)
        self.ui_sys(
            f"connected to {self.host}:{self.port} room={self.room!r} as {self.user_id}"
            + (" (via Tor)" if self.tor_proxy else "")
        )
        self.ui_sys(f"identity fingerprint: {self._fp(self.identity_pub)}")
        self.ui_sys(
            "commands: /voice on|off|listen  /video on|off  /screen on|off  "
            "/screen show on|off  /monitor N  /monitors  /region L T W H  "
            "/peers  /show [camera|screen]  /mic N  /speaker N  /devices  "
            "/viewer [off]  /sendimage <path>  /sendfile <path>  /images  /files  /download <id>  /help  /quit"
        )

    async def _send(self, pkt: Packet) -> None:
        assert self.writer is not None
        self.writer.write(pkt.encode())
        await self.writer.drain()

    def _fp(self, pub: bytes) -> str:
        import hashlib

        return hashlib.sha256(pub).hexdigest()[:16]

    def _i_am_initiator(self, peer_id: str, peer_pub: bytes) -> bool:
        # Deterministic: lower identity fingerprint initiates
        return self.identity_pub < peer_pub or (
            self.identity_pub == peer_pub and self.user_id < peer_id
        )

    async def _ensure_session(self, peer_id: str) -> SessionKeys | None:
        if peer_id in self.sessions:
            return self.sessions[peer_id]
        peer_pub = self.peer_identity.get(peer_id)
        if not peer_pub:
            return None
        # Start key exchange if we don't have one in flight
        if self.eph_priv is None:
            self.eph_priv, self.eph_pub = new_ephemeral()
        await self._send(
            pack_json(
                MsgType.KEY_EXCHANGE,
                {
                    "from": self.user_id,
                    "to": peer_id,  # advisory; room-broadcast
                    "identity_pub": b64(self.identity_pub),
                    "ephemeral_pub": b64(self.eph_pub),
                },
            )
        )
        return None

    async def _complete_session(self, peer_id: str, peer_eph: bytes) -> None:
        peer_pub = self.peer_identity.get(peer_id)
        if not peer_pub:
            return
        if self.eph_priv is None:
            self.eph_priv, self.eph_pub = new_ephemeral()
            # send our eph so peer can finish too
            await self._send(
                pack_json(
                    MsgType.KEY_EXCHANGE,
                    {
                        "from": self.user_id,
                        "to": peer_id,
                        "identity_pub": b64(self.identity_pub),
                        "ephemeral_pub": b64(self.eph_pub),
                    },
                )
            )
        initiator = self._i_am_initiator(peer_id, peer_pub)
        try:
            sess = derive_session(
                self.identity_priv,
                self.eph_priv,
                peer_pub,
                peer_eph,
                i_am_initiator=initiator,
            )
        except Exception as exc:
            self.ui_status(f"key exchange failed with {peer_id}: {exc}")
            return
        self.sessions[peer_id] = sess
        self.ui_sys(
            f"E2E session established with {self.peer_display.get(peer_id, peer_id)} "
            f"[{self._fp(peer_pub)}] initiator={initiator}"
        )

    async def _encrypt_to_all(self, msg_type: MsgType, plaintext: bytes, meta: dict | None = None) -> None:
        """Encrypt the same plaintext under each peer session and send envelopes."""
        if not self.sessions:
            return
        for peer_id, sess in list(self.sessions.items()):
            try:
                aad = f"{self.user_id}|{peer_id}|{int(msg_type)}".encode()
                ct = sess.encrypt(plaintext, aad=aad)
                body = {
                    "from": self.user_id,
                    "to": peer_id,
                    "ct": b64(ct),
                }
                if meta:
                    body.update(meta)
                await self._send(pack_json(msg_type, body))
            except Exception as exc:
                self.ui_status(f"encrypt error → {peer_id}: {exc}")

    async def send_chat(self, text: str) -> None:
        if not self.sessions:
            self.ui_status("no E2E sessions yet — wait for a peer")
            return
        payload = json.dumps({"text": text}, separators=(",", ":")).encode()
        await self._encrypt_to_all(MsgType.CHAT, payload)
        self.ui_chat(self.display, text)

    async def send_image(self, path: str, orig_name: str = "") -> None:
        if not self.sessions:
            self.ui_status("no E2E sessions yet — wait for a peer")
            return
        try:
            meta, webp_bytes, preview = load_and_convert(path)
        except Exception as exc:
            self.ui_status(f"image load failed: {exc}")
            return
        if orig_name:
            meta.name = orig_name
        payload = pack_image_payload(meta, webp_bytes, preview)
        if len(payload) > 1 << 20:
            self.ui_status(f"image too large after WebP ({len(payload)} bytes)")
            return
        await self._encrypt_to_all(MsgType.IMAGE, payload)
        size_kb = meta.webp_size / 1024
        self.ui_sys(
            f"sent image {meta.name} ({meta.width}x{meta.height}, "
            f"WebP {size_kb:.1f} KB, id={meta.id})"
        )

    async def send_file(self, path: str, orig_name: str = "") -> None:
        if not self.sessions:
            self.ui_status("no E2E sessions yet — wait for a peer")
            return
        import hashlib as _hl
        from pathlib import Path as _P
        p = _P(path)
        if not p.is_file():
            self.ui_status(f"file not found: {path}")
            return
        file_bytes = p.read_bytes()
        if len(file_bytes) > MAX_FILE_SIZE:
            self.ui_status(f"file too large ({len(file_bytes)} bytes, max {MAX_FILE_SIZE})")
            return
        mime = mimetypes.guess_type(orig_name or path)[0] or "application/octet-stream"
        meta = FileMessage(
            id=make_file_id(file_bytes),
            name=orig_name or p.name,
            mime_type=mime,
            size=len(file_bytes),
            sha256=_hl.sha256(file_bytes).hexdigest(),
        )
        payload = pack_file_payload(meta, file_bytes)
        await self._encrypt_to_all(MsgType.FILE, payload)
        size_kb = len(file_bytes) / 1024
        self.ui_sys(
            f"sent file {meta.name} ({mime}, {size_kb:.1f} KB, id={meta.id})"
        )

    # --- media hooks (called from other threads) -----------------------------

    def _voice_frame_cb(self, blob: bytes, track: str = "mic") -> None:
        if not self.loop or not self.sessions:
            return
        meta = {"codec": "ADPCM/IMA", "sr": SAMPLE_RATE, "ptime": 20}
        asyncio.run_coroutine_threadsafe(
            self._encrypt_to_all(MsgType.VOICE, blob, meta=meta),
            self.loop,
        )

    def _video_frame_cb(self, blob: bytes, source: str) -> None:
        if not self.loop or not self.sessions:
            return
        meta = {"codec": "ASCIILINE/1.0", "source": source}
        asyncio.run_coroutine_threadsafe(
            self._encrypt_to_all(MsgType.VIDEO, blob, meta=meta),
            self.loop,
        )

    def _ensure_video_engine(self) -> "VideoEngine":
        from client.video_io import VideoEngine
        if self.video is None:
            self.video = VideoEngine(
                self._video_frame_cb,
                width=self.ascii_w,
                height=self.ascii_h,
                fps=self.ascii_fps,
                camera_index=self.cam,
                monitor=self.monitor,
                screen_width=self.screen_w,
                screen_height=self.screen_h,
                screen_fps=self.screen_fps,
                mode=self.mode,
                pixel=self.pixel,
            )
        return self.video

    def start_voice(self, listen_only: bool = False) -> None:
        if self.voice is not None:
            return
        from client.audio_io import VoiceEngine
        if listen_only:
            self.voice = VoiceEngine(
                self._voice_frame_cb,
                input_device=None,
                output_device=self._output_device,
            )
            try:
                self.voice.start_listen()
                self.ui_sys("voice LISTEN — speaker output only (no mic)")
            except Exception as exc:
                self.voice = None
                self.ui_status(f"voice listen failed: {exc}")
                return
        else:
            self.voice = VoiceEngine(
                self._voice_frame_cb,
                input_device=self._input_device,
                output_device=self._output_device,
            )
            try:
                self.voice.start()
                in_dev = self._input_device if self._input_device is not None else "default"
                out_dev = self._output_device if self._output_device is not None else "default"
                self.ui_sys(f"voice ON — ADPCM mic={in_dev} speaker={out_dev}")
            except Exception as exc:
                self.voice = None
                self.ui_status(f"voice failed: {exc}")
                return
        if not self.voice:
            return
        self.voice_is_active = True
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._send_voice_presence(self.user_id, True), self.loop
            )

    def stop_voice(self) -> None:
        if self.voice:
            self.voice.stop()
            self.voice = None
            self.voice_is_active = False
            if self.loop:
                asyncio.run_coroutine_threadsafe(
                    self._send_voice_presence(self.user_id, False), self.loop
                )
            self.ui_sys("voice OFF")

    async def _send_voice_presence(self, who: str, active: bool) -> None:
        """Broadcast voice presence to all peers."""
        if not self.sessions:
            return
        for peer_id, sess in list(self.sessions.items()):
            plaintext = f'{{"voice_active":{str(active).lower()},"user":"{who}"}}'.encode()
            aad = f"{self.user_id}|{peer_id}|{int(MsgType.CONTROL)}".encode()
            ct = sess.encrypt(plaintext, aad=aad)
            body = {"from": self.user_id, "to": peer_id, "ct": b64(ct)}
            try:
                await self._send(pack_json(MsgType.CONTROL, body))
            except Exception:
                pass

    async def _send_media_presence(self, who: str, media_type: str, active: bool) -> None:
        """Broadcast screen/camera presence to all peers."""
        if not self.sessions:
            return
        for peer_id, sess in list(self.sessions.items()):
            plaintext = f'{{"media_type":"{media_type}","media_active":{str(active).lower()},"user":"{who}"}}'.encode()
            aad = f"{self.user_id}|{peer_id}|{int(MsgType.CONTROL)}".encode()
            ct = sess.encrypt(plaintext, aad=aad)
            body = {"from": self.user_id, "to": peer_id, "ct": b64(ct)}
            try:
                await self._send(pack_json(MsgType.CONTROL, body))
            except Exception:
                pass

    def start_video(self) -> None:
        eng = self._ensure_video_engine()
        if eng.camera_active:
            return
        eng.start_camera()
        note = "camera" if eng._cap is not None else "test-pattern (no camera)"
        self.ui_sys(
            f"camera ON — ASCIILINE {self.ascii_w}x{self.ascii_h} "
            f"@ {self.ascii_fps} fps ({note})"
        )
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._send_media_presence(self.user_id, "camera", True), self.loop
            )

    def stop_video(self) -> None:
        if not self.video:
            return
        self.video.stop_camera()
        self.ui_sys("camera OFF")
        if not self.video.screen_active:
            self.video = None
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._send_media_presence(self.user_id, "camera", False), self.loop
            )

    def start_screen(self) -> None:
        eng = self._ensure_video_engine()
        if eng.screen_active:
            return
        try:
            eng.monitor = self.monitor
            eng.start_screen()
        except Exception as exc:
            self.ui_status(f"screen share failed: {exc}")
            if not eng.camera_active:
                self.video = None
            return
        region = eng.region
        if region:
            where = f"region {region.left},{region.top} {region.width}x{region.height}"
        else:
            where = f"monitor {eng.monitor}"
        backend = eng.screen_backend_name or "?"
        fps = eng._screen.fps if eng._screen else eng.screen_fps
        self.ui_sys(
            f"screen ON — ASCIILINE {eng.screen_width}x{eng.screen_height} "
            f"@ {fps} fps ({where}, backend={backend})"
        )
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._send_media_presence(self.user_id, "screen", True), self.loop
            )

    def stop_screen(self) -> None:
        if not self.video:
            return
        self.video.stop_screen()
        self._frame_lines = 0
        self.ui_sys("screen OFF")
        if not self.video.camera_active:
            self.video = None
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._send_media_presence(self.user_id, "screen", False), self.loop
            )

    # --- receive path --------------------------------------------------------

    async def recv_loop(self) -> None:
        assert self.reader is not None
        fr = FrameReader()
        try:
            while not self._stop.is_set():
                data = await self.reader.read(65536)
                if not data:
                    self.ui_status("server closed connection")
                    break
                for pkt in fr.feed(data):
                    await self._on_packet(pkt)
        except Exception as exc:
            self.ui_status(f"recv error: {exc}")
        finally:
            self._stop.set()

    async def _on_packet(self, pkt: Packet) -> None:
        if pkt.type == MsgType.WELCOME:
            body = unpack_json(pkt.payload)
            for p in body.get("peers", []):
                await self._register_peer(p)
            self.ui_sys(f"room peers: {len(body.get('peers', []))}")
            return
        if pkt.type == MsgType.PEER_JOIN:
            body = unpack_json(pkt.payload)
            if body.get("user_id") == self.user_id:
                return
            await self._register_peer(body)
            return
        if pkt.type == MsgType.PEER_LEAVE:
            body = unpack_json(pkt.payload)
            uid = body.get("user_id", "")
            self.sessions.pop(uid, None)
            self.peer_identity.pop(uid, None)
            name = self.peer_display.pop(uid, uid)
            self.ui_sys(f"{name} left")
            return
        if pkt.type == MsgType.KEY_EXCHANGE:
            body = unpack_json(pkt.payload)
            src = body.get("from", "")
            if src == self.user_id:
                return
            if body.get("to") not in (None, "", self.user_id):
                return
            try:
                ident = b64d(body["identity_pub"])
                eph = b64d(body["ephemeral_pub"])
            except Exception:
                return
            self.peer_identity[src] = ident
            await self._complete_session(src, eph)
            return
        if pkt.type in (MsgType.CHAT, MsgType.VOICE, MsgType.VIDEO, MsgType.IMAGE, MsgType.FILE, MsgType.CONTROL):
            await self._on_encrypted(pkt)
            return
        if pkt.type == MsgType.ERROR:
            body = unpack_json(pkt.payload)
            self.ui_status(f"server error: {body.get('error')}")
            return

    async def _register_peer(self, p: dict) -> None:
        uid = p.get("user_id", "")
        if not uid or uid == self.user_id:
            return
        try:
            ident = b64d(p["identity_pub"])
        except Exception:
            return
        self.peer_identity[uid] = ident
        self.peer_display[uid] = p.get("display", uid)
        self.ui_sys(
            f"peer {self.peer_display[uid]} joined  fp={self._fp(ident)}"
        )
        # Kick off key exchange
        if self.eph_priv is None:
            self.eph_priv, self.eph_pub = new_ephemeral()
        await self._send(
            pack_json(
                MsgType.KEY_EXCHANGE,
                {
                    "from": self.user_id,
                    "to": uid,
                    "identity_pub": b64(self.identity_pub),
                    "ephemeral_pub": b64(self.eph_pub),
                },
            )
        )
        # Notify new peer of our voice status
        if self.voice_is_active:
            await self._send_voice_presence(self.user_id, True)

    async def _on_encrypted(self, pkt: Packet) -> None:
        body = unpack_json(pkt.payload)
        src = body.get("from", "")
        dst = body.get("to", "")
        if dst and dst != self.user_id:
            return
        if src == self.user_id:
            return
        sess = self.sessions.get(src)
        if not sess:
            # maybe we can still establish
            await self._ensure_session(src)
            sess = self.sessions.get(src)
            if not sess:
                return
        try:
            aad = f"{src}|{self.user_id}|{int(pkt.type)}".encode()
            pt = sess.decrypt(b64d(body["ct"]), aad=aad)
        except Exception as exc:
            self.ui_status(f"decrypt fail from {src}: {exc}")
            return

        if pkt.type == MsgType.CHAT:
            try:
                msg = json.loads(pt.decode())
                text = msg.get("text", "")
            except Exception:
                text = pt.decode("utf-8", errors="replace")
            who = self.peer_display.get(src, src)
            self.ui_chat(who, text)
        elif pkt.type == MsgType.VOICE:
            if self.voice:
                self.voice.push_remote_frame(pt)
        elif pkt.type == MsgType.VIDEO:
            source_hint = body.get("source")
            try:
                try:
                    eng = self._ensure_video_engine()
                    src = eng.push_remote_frame(pt, source_hint=source_hint)
                    # Push JPEG to GUI if active
                    if self._gui_queue is not None and src in ("screen", "camera"):
                        fr = eng.decoder.decode(pt)
                        if fr and fr.img_b64:
                            import base64 as _b64
                            jpg = _b64.b64decode(fr.img_b64)
                            self._gui_queue.put(("ui_video_jpeg", (jpg, src), {}))
                    # Show screen frames in terminal only when Canvas viewer has never been active
                    if src == "screen" and self.auto_show_screen:
                        from client.web_viewer import _viewer_ever_active
                        if not _viewer_ever_active:
                            meta = eng._latest_meta.get(src, {})
                            seq = int(meta.get("seq", 0))
                            last = self._last_shown_seq.get(src, -1)
                            if seq - last >= max(1, eng.screen_fps):
                                self._last_shown_seq[src] = seq
                                view = eng.get_remote_view("screen")
                                if view:
                                    who = self.peer_display.get(
                                        body.get("from", ""), body.get("from", "?")
                                    )
                                    self.ui_video_frame(view, label=f"ASCIILINE screen from {who}")
                except Exception:
                    # Android / headless: VideoEngine unavailable — decode ASCIILINE directly
                    from shared.asciline import AsciiLineDecoder
                    decoder = AsciiLineDecoder()
                    fr = decoder.decode(pt)
                    src = source_hint or (fr.source if fr else None) or "screen"
                    if fr and fr.img_b64 and self._gui_queue is not None:
                        import base64 as _b64
                        jpg = _b64.b64decode(fr.img_b64)
                        self._gui_queue.put(("ui_video_jpeg", (jpg, src), {}))
            except Exception as exc:
                self.ui_status(f"video decode fail: {exc}")
        elif pkt.type == MsgType.IMAGE:
            who = self.peer_display.get(src, src)
            try:
                meta, webp_bytes, preview = unpack_image_payload(pt)
                self._received_images[meta.id] = (meta, webp_bytes, preview)
                self.ui(format_image_info(meta, who))
                if self._gui_queue is not None:
                    self.ui_image(meta.id, webp_bytes, who, meta.name, meta.width, meta.height)
                elif preview:
                    self.ui(format_image_preview(meta, preview, who))
            except Exception as exc:
                self.ui_status(f"image decode fail: {exc}")
        elif pkt.type == MsgType.FILE:
            who = self.peer_display.get(src, src)
            try:
                meta, file_bytes = unpack_file_payload(pt)
                self._received_files[meta.id] = (meta, file_bytes)
                self.ui(format_file_info(meta, who))
                if self._gui_queue is not None:
                    self.ui_file(meta.id, file_bytes, who, meta.name, meta.mime_type, meta.size)
            except Exception as exc:
                self.ui_status(f"file decode fail: {exc}")
        elif pkt.type == MsgType.CONTROL:
            await self._on_control_decrypted(pt, src)

    async def _on_control_decrypted(self, pt: bytes, src: str):
        try:
            msg = json.loads(pt.decode())
        except Exception:
            return
        if "voice_active" in msg:
            self.voice_active_peers[src] = msg["voice_active"]
            who = self.peer_display.get(src, src)
            status = "joined voice" if msg["voice_active"] else "left voice"
            self.ui_sys(f"{who} {status}")
        elif "media_type" in msg:
            who = self.peer_display.get(src, src)
            media = msg["media_type"]
            active = msg.get("media_active", False)
            if active:
                self.ui_sys(f"{who} sharing {media}")
            else:
                self.ui_sys(f"{who} stopped sharing {media}")

    # --- stdin commands ------------------------------------------------------

    async def input_loop(self) -> None:
        if self._gui_mode:
            return  # GUI handles input directly
        # Run blocking stdin in a thread
        while not self._stop.is_set():
            line = await asyncio.to_thread(sys.stdin.readline)
            if line == "":
                self._stop.set()
                break
            line = line.rstrip("\n")
            if not line:
                continue
            if line.startswith("/"):
                await self._command(line)
            else:
                await self.send_chat(line)

    async def _command(self, line: str) -> None:
        parts = line.split()
        cmd = parts[0].lower()
        arg = parts[1].lower() if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit", "/q"):
            self._stop.set()
            return
        if cmd == "/help":
            self.ui_sys("available commands:")
            self.ui_sys("  /voice on|off|listen        — toggle voice chat")
            self.ui_sys("  /video on|off               — toggle camera")
            self.ui_sys("  /screen on|off [mode] [px]  — toggle screen share")
            self.ui_sys("  /screen show on|off         — toggle remote screen in terminal")
            self.ui_sys("  /show [camera|screen]       — show latest remote frame")
            self.ui_sys("  /monitor N                 — set screen capture monitor")
            self.ui_sys("  /monitors                  — list available monitors")
            self.ui_sys("  /region L T W H | clear     — set screen capture region")
            self.ui_sys("  /peers                     — list connected peers")
            self.ui_sys("  /devices                   — list audio devices")
            self.ui_sys("  /mic N                     — set mic input device")
            self.ui_sys("  /speaker N                 — set speaker output device")
            self.ui_sys("  /viewer [off]              — toggle browser canvas viewer")
            self.ui_sys("  /sendimage <path>          — send an image")
            self.ui_sys("  /sendfile <path>           — send a file")
            self.ui_sys("  /images                    — list received images")
            self.ui_sys("  /files                     — list received files")
            self.ui_sys("  /download <id>             — re-save a received image")
            self.ui_sys("  /quit                      — disconnect and exit")
            return
        if cmd == "/voice":
            if arg in ("on", "1", "start"):
                self.start_voice()
            elif arg in ("off", "0", "stop"):
                self.stop_voice()
            elif arg in ("listen", "rx", "only"):
                self.start_voice(listen_only=True)
            else:
                self.ui_status("usage: /voice on|off|listen")
            return
        if cmd == "/video":
            if arg in ("on", "1", "start", "camera"):
                self.start_video()
            elif arg in ("off", "0", "stop"):
                self.stop_video()
            else:
                self.ui_status("usage: /video on|off  (camera track)")
            return
        if cmd in ("/screen", "/screenshare", "/share"):
            if arg in ("on", "1", "start"):
                # Parse additional arguments: /screen on [mode] [pixel]
                mode = int(parts[2]) if len(parts) > 2 else 5
                pixel = parts[3].lower() not in ("off", "false", "0") if len(parts) > 3 else (mode == 5)

                # 1. Store them in the correct variables
                self.mode = mode
                self.pixel = pixel

                # 2. If the video engine is already running, update it instantly
                if self.video:
                    self.video.mode = self.mode
                    self.video.pixel = self.pixel

                self.start_screen()
            elif arg in ("off", "0", "stop"):
                self.stop_screen()
            elif parts[1].lower() == "show" if len(parts) > 1 else False:
                sub = parts[2].lower() if len(parts) > 2 else ""
                if sub in ("on", "1", "true"):
                    self.auto_show_screen = True
                    self.ui_status("terminal screen display ON")
                elif sub in ("off", "0", "false"):
                    self.auto_show_screen = False
                    self.ui_status("terminal screen display OFF")
                else:
                    self.ui_status(f"terminal screen display: {'ON' if self.auto_show_screen else 'OFF'}")
            else:
                self.ui_status("usage: /screen on|off [mode] [pixel]  |  /screen show on|off")
            return
        if cmd in ("/video-show", "/show"):
            which = arg if arg in ("camera", "screen", "video") else (
                parts[1].lower() if len(parts) > 1 else "screen"
            )
            if which not in ("camera", "screen", "video"):
                which = "screen"
            eng = self._ensure_video_engine()
            view = eng.get_remote_view(which)
            if view:
                self.ui_video_frame(view, label=f"ASCIILINE {which}")
            else:
                avail = eng.remote_sources()
                self.ui_status(
                    f"no remote {which} frame yet"
                    + (f" (have: {', '.join(avail)})" if avail else "")
                )
            return
        if cmd == "/monitor":
            if len(parts) < 2:
                self.ui_status("usage: /monitor <index>  (see /monitors)")
                return
            try:
                idx = int(parts[1])
            except ValueError:
                self.ui_status("monitor index must be int")
                return
            self.monitor = idx
            eng = self._ensure_video_engine()
            eng.set_monitor(idx)
            self.ui_sys(f"screen capture monitor → {idx}")
            return
        if cmd == "/region":
            if len(parts) == 2 and parts[1].lower() in ("clear", "off", "full"):
                eng = self._ensure_video_engine()
                eng.clear_region()
                self.ui_sys("screen region cleared (full monitor)")
                return
            if len(parts) < 5:
                self.ui_status("usage: /region <left> <top> <width> <height>  |  /region clear")
                return
            try:
                left, top, width, height = map(int, parts[1:5])
            except ValueError:
                self.ui_status("region values must be integers")
                return
            eng = self._ensure_video_engine()
            try:
                eng.set_region(left, top, width, height)
            except ValueError as exc:
                self.ui_status(str(exc))
                return
            self.ui_sys(f"screen region → {left},{top} {width}x{height}")
            return
        if cmd == "/monitors":
            from client.video_io import list_monitors, backend_status
            try:
                mons = list_monitors()
            except Exception as exc:
                self.ui_status(f"cannot list monitors: {exc}")
                return
            for m in mons:
                prim = " (primary)" if m.get("primary") else ""
                self.ui(
                    f"  [{m['index']}] {m.get('label', '?')}  "
                    f"{m['width']}x{m['height']} @ {m['left']},{m['top']}{prim}"
                )
            self.ui_sys(backend_status())
            return
        if cmd == "/peers":
            if not self.peer_identity:
                self.ui_status("no peers")
                return
            for uid, pub in self.peer_identity.items():
                ok = "E2E" if uid in self.sessions else "no-session"
                voice = " VOICE" if self.voice_active_peers.get(uid) else ""
                self.ui(f"  {self.peer_display.get(uid, uid)}  {ok}{voice}  fp={self._fp(pub)}")
            return
        if cmd == "/devices":
            from client.audio_io import list_devices
            self.ui(list_devices())
            return
        if cmd == "/viewer":
            from client.web_viewer import start_viewer, stop_viewer
            if arg in ("off", "0", "stop"):
                stop_viewer()
                self.ui_sys("canvas viewer stopped")
            else:
                try:
                    port = start_viewer()
                except Exception as exc:
                    self.ui_status(f"viewer failed: {exc}")
                    return
                self.ui_sys(f"canvas viewer open at http://127.0.0.1:{port}")
            return
        if cmd == "/mic":
            if arg in ("list", ""):
                from client.audio_io import list_devices
                self.ui(list_devices())
                return
            try:
                idx = int(arg)
            except ValueError:
                self.ui_status("usage: /mic <device-index>  (see /devices)")
                return
            self._input_device = idx
            was_running = self.voice is not None
            if was_running:
                self.stop_voice()
            if was_running:
                self.start_voice()
            else:
                self.ui_sys(f"mic input set to device {idx}")
            return
        if cmd in ("/speaker", "/spk"):
            if arg in ("list", ""):
                from client.audio_io import list_devices
                self.ui(list_devices())
                return
            try:
                idx = int(arg)
            except ValueError:
                self.ui_status("usage: /speaker <device-index>  (see /devices)")
                return
            self._output_device = idx
            was_running = self.voice is not None
            if was_running:
                self.stop_voice()
            if was_running:
                self.start_voice()
            else:
                self.ui_sys(f"speaker output set to device {idx}")
            return
        if cmd in ("/sendimage", "/image", "/img"):
            if len(parts) < 2:
                self.ui_status("usage: /sendimage <path>")
                return
            path = " ".join(parts[1:])
            await self.send_image(path)
            return
        if cmd in ("/sendfile", "/file"):
            if len(parts) < 2:
                self.ui_status("usage: /sendfile <path>")
                return
            path = " ".join(parts[1:])
            await self.send_file(path)
            return
        if cmd == "/download":
            if len(parts) < 2:
                self.ui_status("usage: /download <id>  (see /images or /files for IDs)")
                return
            dl_id = parts[1]
            if dl_id in self._received_images:
                meta, webp_bytes, preview = self._received_images[dl_id]
                saved = save_received_image(meta, webp_bytes)
                self.ui_sys(f"saved {meta.name} → {saved}")
            elif dl_id in self._received_files:
                meta, file_bytes = self._received_files[dl_id]
                saved = save_received_file(meta, file_bytes)
                self.ui_sys(f"saved {meta.name} → {saved}")
            else:
                self.ui_status(f"unknown id: {dl_id}  (try /images or /files)")
            return
        if cmd == "/images":
            if not self._received_images:
                self.ui_status("no images received yet")
                return
            for img_id, (meta, webp, _) in self._received_images.items():
                size_kb = meta.webp_size / 1024
                self.ui(
                    f"  [{img_id}] {meta.name}  {meta.width}x{meta.height}  "
                    f"WebP {size_kb:.1f} KB"
                )
            self.ui_sys("use /download <id> to save, or /preview <id> to show again")
            return
        if cmd == "/files":
            if not self._received_files:
                self.ui_status("no files received yet")
                return
            for fid, (meta, _) in self._received_files.items():
                size_kb = meta.size / 1024
                self.ui(
                    f"  [{fid}] {meta.name}  {meta.mime_type}  {size_kb:.1f} KB"
                )
            self.ui_sys("use /download <id> to save")
            return
        if cmd == "/preview":
            if len(parts) < 2:
                self.ui_status("usage: /preview <image-id>")
                return
            img_id = parts[1]
            if img_id not in self._received_images:
                self.ui_status(f"unknown image id: {img_id}")
                return
            meta, webp_bytes, preview = self._received_images[img_id]
            if not preview:
                self.ui_status("no preview available for this image")
                return
            self.ui(format_image_preview(meta, preview, "cached"))
            return
        if cmd == "/help":
            self.ui_sys(
                "/voice on|off|listen  /video on|off  /screen on|off  "
                "/monitor N  /region L T W H  /monitors  "
                "/viewer [off]  "
                "/show [camera|screen]  /peers  /devices  "
                "/mic N  /speaker N  "
                "/sendimage <path>  /images  /download <id>  /preview <id>  /quit"
            )
            return
        self.ui_status(f"unknown command {cmd} — try /help")

    async def run(self) -> None:
        await self.connect()
        if self.want_voice:
            self.start_voice()
        if self.want_video:
            self.start_video()
        if self.want_viewer:
            from client.web_viewer import start_viewer
            try:
                port = start_viewer()
                self.ui_sys(f"canvas viewer open at http://127.0.0.1:{port}")
                if self.upnp:
                    from shared.upnp import setup_port_mapping
                    self._upnp_mapping = setup_port_mapping(
                        port, description="Asciline Viewer",
                    )
                    if self._upnp_mapping:
                        ext_ip = self._upnp_mapping.external_ip or "?"
                        self.ui_sys(f"UPnP: viewer reachable at http://{ext_ip}:{port}")
            except Exception as exc:
                self.ui_status(f"viewer failed: {exc}")
        if self.want_screen:
            self.start_screen()
        recv_task = asyncio.create_task(self.recv_loop())
        input_task = asyncio.create_task(self.input_loop())
        await self._stop.wait()
        self.stop_voice()
        self.stop_video()
        self.stop_screen()
        if self._upnp_mapping:
            self._upnp_mapping.cleanup()
            self._upnp_mapping = None
        recv_task.cancel()
        input_task.cancel()
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
        self.ui_sys("bye")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="E2E chat -- ASCIILINE camera/screen + ADPCM voice"
    )
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9473)
    ap.add_argument("--room", default="lobby")
    ap.add_argument("--user", default="", help="user id (default: random)")
    ap.add_argument("--display", default="", help="display name")
    ap.add_argument("--voice", action="store_true", help="start voice on connect")
    ap.add_argument("--video", action="store_true", help="start ASCIILINE camera on connect")
    ap.add_argument("--screen", action="store_true", help="start ASCIILINE screen share on connect")
    ap.add_argument("--viewer", action="store_true", help="open Canvas viewer in browser on connect")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--monitor", type=int, default=1, help="mss monitor index (1=primary usually)")
    ap.add_argument("--ascii-w", type=int, default=120, help="camera ASCII width")
    ap.add_argument("--ascii-h", type=int, default=40, help="camera ASCII height")
    ap.add_argument("--ascii-fps", type=int, default=30, help="camera ASCII fps")
    ap.add_argument("--screen-w", type=int, default=120, help="screen share ASCII width")
    ap.add_argument("--screen-h", type=int, default=40, help="screen share ASCII height")
    ap.add_argument("--screen-fps", type=int, default=30, help="screen share ASCII fps")
    ap.add_argument("--mode", type=int, default=5, help="Rendering mode (1-5)")
    ap.add_argument("--no-pixel", dest="pixel", action="store_false", help="Disable PIXEL mode (on by default)")
    ap.set_defaults(pixel=True)
    ap.add_argument("--tor", action="store_true", help="route through Tor SOCKS5 proxy (default: socks5://127.0.0.1:9050)")
    ap.add_argument("--tor-proxy", default="", help="SOCKS5 proxy URL (default: socks5://127.0.0.1:9050 when --tor is set)")
    ap.add_argument("--upnp", action="store_true", help="map viewer port via UPnP IGD")
    ap.add_argument("--gui", action="store_true", help="launch tkinter GUI")
    ap.add_argument("--no-gui", action="store_true", help="force terminal mode")
    args = ap.parse_args()

    user = args.user or f"user-{os.getpid()}"
    display = args.display or user

    client = ChatClient(
        host=args.host,
        port=args.port,
        room=args.room,
        user_id=user,
        display=display,
        voice=args.voice,
        video=args.video,
        screen=args.screen,
        cam=args.camera,
        monitor=args.monitor,
        ascii_w=args.ascii_w,
        ascii_h=args.ascii_h,
        ascii_fps=args.ascii_fps,
        screen_w=args.screen_w,
        screen_h=args.screen_h,
        screen_fps=args.screen_fps,
        mode=args.mode,
        pixel=args.pixel,
        want_viewer=args.viewer,
        tor_proxy=args.tor_proxy or ("socks5://127.0.0.1:9050" if args.tor else ""),
        upnp=args.upnp,
    )

    use_gui = args.gui
    if not args.no_gui and not args.gui:
        use_gui = not sys.stdin.isatty()

    if use_gui:
        try:
            from client.gui import ChatGUI
        except ImportError as exc:
            print(f"GUI requires tkinter: {exc}", file=sys.stderr)
            raise SystemExit(1)
        gui = ChatGUI(client)
        gui.run()
    else:
        try:
            asyncio.run(client.run())
        except KeyboardInterrupt:
            print()


if __name__ == "__main__":
    main()
