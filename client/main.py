#!/usr/bin/env python3
"""E2E encrypted chat client with ASCIILINE video and G.729.1 (G.729EV) voice."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from client.audio_io import VoiceEngine, list_devices
from client.video_io import VideoEngine, list_monitors
from shared.crypto import (
    SessionKeys,
    b64,
    b64d,
    derive_session,
    generate_identity,
    new_ephemeral,
)
from shared.protocol import FrameReader, MsgType, Packet, pack_json, unpack_json


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
        bitrate: int,
        cam: int,
        monitor: int,
        ascii_w: int,
        ascii_h: int,
        ascii_fps: int,
        screen_w: int,
        screen_h: int,
        screen_fps: int,
        auto_show_screen: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.room = room
        self.user_id = user_id
        self.display = display
        self.want_voice = voice
        self.want_video = video
        self.want_screen = screen
        self.bitrate = bitrate
        self.cam = cam
        self.monitor = monitor
        self.ascii_w = ascii_w
        self.ascii_h = ascii_h
        self.ascii_fps = ascii_fps
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.screen_fps = screen_fps
        self.auto_show_screen = auto_show_screen
        self._last_shown_seq: dict[str, int] = {}

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

    # --- UI helpers ----------------------------------------------------------

    def ui(self, msg: str) -> None:
        with self._print_lock:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()

    def ui_status(self, msg: str) -> None:
        self.ui(f"\033[90m* {msg}\033[0m")

    def ui_sys(self, msg: str) -> None:
        self.ui(f"\033[36m* {msg}\033[0m")

    def ui_chat(self, who: str, text: str) -> None:
        self.ui(f"\033[1m<{who}>\033[0m {text}")

    def ui_video_frame(self, text: str, label: str = "ASCIILINE") -> None:
        # Draw remote ASCIILINE in a boxed region above the prompt area
        lines = text.splitlines()
        if not lines:
            return
        w = max(len(l) for l in lines)
        border = "┌" + "─" * w + "┐"
        bottom = "└" + "─" * w + "┘"
        body = "\n".join("│" + l.ljust(w) + "│" for l in lines)
        with self._print_lock:
            sys.stdout.write(
                f"\n\033[33m── {label} remote ({len(lines)}x{w}) ──\033[0m\n"
                f"{border}\n{body}\n{bottom}\n"
            )
            sys.stdout.flush()

    # --- networking ----------------------------------------------------------

    async def connect(self) -> None:
        self.loop = asyncio.get_running_loop()
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
        )
        self.ui_sys(f"identity fingerprint: {self._fp(self.identity_pub)}")
        self.ui_sys(
            "commands: /voice on|off  /video on|off  /screen on|off  "
            "/monitor N  /region L T W H  /bitrate N  /peers  "
            "/show [camera|screen]  /monitors  /devices  /quit"
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

    # --- media hooks (called from other threads) -----------------------------

    def _voice_frame_cb(self, blob: bytes) -> None:
        if not self.loop or not self.sessions:
            return
        meta = {"codec": "G729EV/open-v1", "sr": 16000, "ptime": 20}
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

    def _ensure_video_engine(self) -> VideoEngine:
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
            )
        return self.video

    def start_voice(self) -> None:
        if self.voice is not None:
            return
        self.voice = VoiceEngine(self._voice_frame_cb, bitrate_kbps=self.bitrate)
        try:
            self.voice.start()
            self.ui_sys(f"voice ON — G.729.1/G.729EV open-v1 @ {self.voice.codec_tx.bitrate} kb/s")
        except Exception as exc:
            self.voice = None
            self.ui_status(f"voice failed: {exc}")

    def stop_voice(self) -> None:
        if self.voice:
            self.voice.stop()
            self.voice = None
            self.ui_sys("voice OFF")

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

    def stop_video(self) -> None:
        if not self.video:
            return
        self.video.stop_camera()
        self.ui_sys("camera OFF")
        if not self.video.screen_active:
            self.video = None

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
        self.ui_sys(
            f"screen ON — ASCIILINE {eng.screen_width}x{eng.screen_height} "
            f"@ {eng.screen_fps} fps ({where})"
        )

    def stop_screen(self) -> None:
        if not self.video:
            return
        self.video.stop_screen()
        self.ui_sys("screen OFF")
        if not self.video.camera_active:
            self.video = None

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
        if pkt.type in (MsgType.CHAT, MsgType.VOICE, MsgType.VIDEO):
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
                eng = self._ensure_video_engine()
                src = eng.push_remote_frame(pt, source_hint=source_hint)
                # Periodically surface screen frames so share is visible without a command
                if src == "screen" and self.auto_show_screen:
                    meta = eng._latest_meta.get(src, {})
                    seq = int(meta.get("seq", 0))
                    last = self._last_shown_seq.get(src, -1)
                    # show ~1 frame/sec to avoid flooding the terminal
                    if seq - last >= max(1, eng.screen_fps):
                        self._last_shown_seq[src] = seq
                        view = eng.get_remote_view("screen")
                        if view:
                            who = self.peer_display.get(
                                body.get("from", ""), body.get("from", "?")
                            )
                            self.ui_video_frame(view, label=f"ASCIILINE screen from {who}")
            except Exception as exc:
                self.ui_status(f"video decode fail: {exc}")

    # --- stdin commands ------------------------------------------------------

    async def input_loop(self) -> None:
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
        if cmd == "/voice":
            if arg in ("on", "1", "start"):
                self.start_voice()
            elif arg in ("off", "0", "stop"):
                self.stop_voice()
            else:
                self.ui_status("usage: /voice on|off")
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
                self.start_screen()
            elif arg in ("off", "0", "stop"):
                self.stop_screen()
            else:
                self.ui_status("usage: /screen on|off")
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
            return
        if cmd == "/bitrate":
            if len(parts) < 2:
                self.ui_status("usage: /bitrate <8-32>")
                return
            try:
                br = int(parts[1])
            except ValueError:
                self.ui_status("bitrate must be integer kb/s")
                return
            self.bitrate = br
            if self.voice:
                self.voice.set_bitrate(br)
                self.ui_sys(f"G.729EV bitrate → {self.voice.codec_tx.bitrate} kb/s "
                            f"({self.voice.codec_tx.layers} layers)")
            else:
                self.ui_sys(f"bitrate set to {br} (applies when voice starts)")
            return
        if cmd == "/peers":
            if not self.peer_identity:
                self.ui_status("no peers")
                return
            for uid, pub in self.peer_identity.items():
                ok = "E2E" if uid in self.sessions else "no-session"
                self.ui(f"  {self.peer_display.get(uid, uid)}  {ok}  fp={self._fp(pub)}")
            return
        if cmd == "/devices":
            self.ui(list_devices())
            return
        if cmd == "/help":
            self.ui_sys(
                "/voice on|off  /video on|off  /screen on|off  "
                "/monitor N  /region L T W H  /monitors  "
                "/show [camera|screen]  /bitrate N  /peers  /devices  /quit"
            )
            return
        self.ui_status(f"unknown command {cmd} — try /help")

    async def run(self) -> None:
        await self.connect()
        if self.want_voice:
            self.start_voice()
        if self.want_video:
            self.start_video()
        if self.want_screen:
            self.start_screen()
        recv_task = asyncio.create_task(self.recv_loop())
        input_task = asyncio.create_task(self.input_loop())
        await self._stop.wait()
        self.stop_voice()
        self.stop_video()
        self.stop_screen()
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
        description="E2E chat — ASCIILINE camera/screen + G.729.1/G.729EV voice"
    )
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9473)
    ap.add_argument("--room", default="lobby")
    ap.add_argument("--user", default="", help="user id (default: random)")
    ap.add_argument("--display", default="", help="display name")
    ap.add_argument("--voice", action="store_true", help="start voice on connect")
    ap.add_argument("--video", action="store_true", help="start ASCIILINE camera on connect")
    ap.add_argument("--screen", action="store_true", help="start ASCIILINE screen share on connect")
    ap.add_argument("--bitrate", type=int, default=24, help="G.729EV kb/s (8-32)")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--monitor", type=int, default=1, help="mss monitor index (1=primary usually)")
    ap.add_argument("--ascii-w", type=int, default=80, help="camera ASCII width")
    ap.add_argument("--ascii-h", type=int, default=28, help="camera ASCII height")
    ap.add_argument("--ascii-fps", type=int, default=6, help="camera ASCII fps")
    ap.add_argument("--screen-w", type=int, default=120, help="screen share ASCII width")
    ap.add_argument("--screen-h", type=int, default=40, help="screen share ASCII height")
    ap.add_argument("--screen-fps", type=int, default=4, help="screen share ASCII fps")
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
        bitrate=args.bitrate,
        cam=args.camera,
        monitor=args.monitor,
        ascii_w=args.ascii_w,
        ascii_h=args.ascii_h,
        ascii_fps=args.ascii_fps,
        screen_w=args.screen_w,
        screen_h=args.screen_h,
        screen_fps=args.screen_fps,
    )
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
