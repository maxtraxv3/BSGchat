#!/usr/bin/env python3
"""Untrusted room relay.

The server routes packets between peers in a room. It never has session keys
and cannot read chat, voice, or ASCIILINE video payloads.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow running as script without install
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.crypto import b64, b64d  # noqa: E402
from shared.protocol import FrameReader, MsgType, Packet, pack_json, unpack_json  # noqa: E402

log = logging.getLogger("relay")


class Peer:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer
        self.user_id: str = ""
        self.display: str = ""
        self.identity_pub: bytes = b""
        self.room: str = ""
        self.addr = writer.get_extra_info("peername")

    async def send(self, packet: Packet) -> None:
        self.writer.write(packet.encode())
        await self.writer.drain()


class Relay:
    def __init__(self) -> None:
        self.rooms: dict[str, dict[str, Peer]] = {}
        self.lock = asyncio.Lock()

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = Peer(reader, writer)
        fr = FrameReader()
        log.info("connect %s", peer.addr)
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                for pkt in fr.feed(data):
                    await self._dispatch(peer, pkt)
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception:
            log.exception("peer error %s", peer.addr)
        finally:
            await self._leave(peer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            log.info("disconnect %s (%s)", peer.addr, peer.user_id or "?")

    async def _dispatch(self, peer: Peer, pkt: Packet) -> None:
        if pkt.type == MsgType.HELLO:
            await self._hello(peer, unpack_json(pkt.payload))
            return
        if not peer.user_id:
            await peer.send(pack_json(MsgType.ERROR, {"error": "send HELLO first"}))
            return

        # Forward end-to-end payloads as-is (server is blind)
        if pkt.type in (
            MsgType.KEY_EXCHANGE,
            MsgType.CHAT,
            MsgType.VOICE,
            MsgType.VIDEO,
            MsgType.IMAGE,
            MsgType.FILE,
            MsgType.CONTROL,
        ):
            await self._broadcast(peer, pkt)
            return

        await peer.send(pack_json(MsgType.ERROR, {"error": f"unsupported type {pkt.type}"}))

    async def _hello(self, peer: Peer, body: dict) -> None:
        user_id = str(body.get("user_id", "")).strip()
        room = str(body.get("room", "lobby")).strip() or "lobby"
        display = str(body.get("display", user_id)).strip() or user_id
        ident_b64 = body.get("identity_pub", "")
        if not user_id or not ident_b64:
            await peer.send(pack_json(MsgType.ERROR, {"error": "user_id and identity_pub required"}))
            return
        try:
            identity = b64d(ident_b64)
            if len(identity) != 32:
                raise ValueError("bad key length")
        except Exception:
            await peer.send(pack_json(MsgType.ERROR, {"error": "invalid identity_pub"}))
            return

        async with self.lock:
            room_peers = self.rooms.setdefault(room, {})
            if user_id in room_peers:
                await peer.send(pack_json(MsgType.ERROR, {"error": "user_id already in room"}))
                return
            peer.user_id = user_id
            peer.display = display
            peer.identity_pub = identity
            peer.room = room
            # Introduce existing peers
            others = [
                {
                    "user_id": p.user_id,
                    "display": p.display,
                    "identity_pub": b64(p.identity_pub),
                }
                for p in room_peers.values()
            ]
            room_peers[user_id] = peer

        await peer.send(
            pack_json(
                MsgType.WELCOME,
                {"user_id": user_id, "room": room, "peers": others},
            )
        )
        join = pack_json(
            MsgType.PEER_JOIN,
            {
                "user_id": user_id,
                "display": display,
                "identity_pub": b64(identity),
            },
        )
        await self._broadcast(peer, join, include_self=False)
        log.info("%s joined room %s (%d peers)", user_id, room, len(self.rooms.get(room, {})))

    async def _leave(self, peer: Peer) -> None:
        if not peer.user_id or not peer.room:
            return
        async with self.lock:
            room_peers = self.rooms.get(peer.room, {})
            if room_peers.get(peer.user_id) is peer:
                del room_peers[peer.user_id]
            if peer.room in self.rooms and not self.rooms[peer.room]:
                del self.rooms[peer.room]
        leave = pack_json(MsgType.PEER_LEAVE, {"user_id": peer.user_id})
        # broadcast without requiring peer still in map
        await self._broadcast_room(peer.room, leave, exclude=peer.user_id)

    async def _broadcast(self, sender: Peer, pkt: Packet, include_self: bool = False) -> None:
        # Stamp from on encrypted envelope if JSON-capable types already have it
        await self._broadcast_room(
            sender.room,
            pkt,
            exclude=None if include_self else sender.user_id,
        )

    async def _broadcast_room(
        self, room: str, pkt: Packet, exclude: str | None
    ) -> None:
        async with self.lock:
            targets = list(self.rooms.get(room, {}).values())
        dead: list[Peer] = []
        for p in targets:
            if exclude and p.user_id == exclude:
                continue
            try:
                await p.send(pkt)
            except Exception:
                dead.append(p)
        for p in dead:
            await self._leave(p)


async def main_async(host: str, port: int) -> None:
    relay = Relay()
    server = await asyncio.start_server(relay.handle, host, port)
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    log.info("relay listening on %s (blind E2E media relay)", addrs)
    async with server:
        await server.serve_forever()


def _setup_hidden_service(port: int, control_port: int, control_host: str) -> str | None:
    """Create an ephemeral Tor hidden service via stem. Returns the .onion address."""
    try:
        from stem.control import Controller
    except ImportError:
        print("[tor] stem library not installed. Install with: pip install stem", file=sys.stderr)
        print("[tor] Manual setup: add to /etc/tor/torrc:", file=sys.stderr)
        print(f"[tor]   HiddenServiceDir /var/lib/tor/chat-relay/", file=sys.stderr)
        print(f"[tor]   HiddenServicePort 80 127.0.0.1:{port}", file=sys.stderr)
        return None

    try:
        controller = Controller.from_port(address=control_host, port=control_port)
        controller.authenticate()
    except Exception as exc:
        print(f"[tor] cannot connect to Tor ControlPort ({control_host}:{control_port}): {exc}", file=sys.stderr)
        print("[tor] Ensure Tor is running with ControlPort enabled in torrc:", file=sys.stderr)
        print(f"[tor]   ControlPort {control_port}", file=sys.stderr)
        print(f"[tor]   CookieAuthentication 1", file=sys.stderr)
        return None

    try:
        response = controller.create_ephemeral_hidden_service(
            f"80:127.0.0.1:{port}",
            detached=True,
        )
        onion = response.service_id + ".onion"
        log.info("tor hidden service: %s", onion)
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"  Tor hidden service active: {onion}", file=sys.stderr)
        print(f"  Clients can connect with: --tor --host {onion}", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        return onion
    except Exception as exc:
        print(f"[tor] failed to create hidden service: {exc}", file=sys.stderr)
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="E2E ASCILINE chat relay (untrusted)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=9473)
    ap.add_argument("--tor", action="store_true", help="create a Tor hidden service")
    ap.add_argument("--tor-control-port", type=int, default=9051, help="Tor ControlPort (default: 9051)")
    ap.add_argument("--tor-control-host", default="127.0.0.1", help="Tor ControlPort host")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.tor:
        _setup_hidden_service(args.port, args.tor_control_port, args.tor_control_host)

    try:
        asyncio.run(main_async(args.host, args.port))
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
