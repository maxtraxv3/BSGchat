"""Wire protocol for the untrusted relay.

All application payloads (chat, voice, video) are opaque ciphertext to the
server. Only routing metadata is plaintext.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class MsgType(IntEnum):
    HELLO = 0x01
    WELCOME = 0x02
    PEER_JOIN = 0x03
    PEER_LEAVE = 0x04
    KEY_EXCHANGE = 0x10
    CHAT = 0x20
    VOICE = 0x30
    VIDEO = 0x40
    IMAGE = 0x45
    CONTROL = 0x50
    ERROR = 0x7F


HEADER = struct.Struct("!IB")  # length (payload only), type
MAX_PAYLOAD = 1 << 20  # 1 MiB


@dataclass
class Packet:
    type: MsgType
    payload: bytes

    def encode(self) -> bytes:
        if len(self.payload) > MAX_PAYLOAD:
            raise ValueError("payload too large")
        return HEADER.pack(len(self.payload), int(self.type)) + self.payload


def pack_json(msg_type: MsgType, obj: dict[str, Any]) -> Packet:
    return Packet(msg_type, json.dumps(obj, separators=(",", ":")).encode("utf-8"))


def unpack_json(payload: bytes) -> dict[str, Any]:
    return json.loads(payload.decode("utf-8"))


class FrameReader:
    """Incremental length-prefixed frame parser."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Packet]:
        self._buf.extend(data)
        out: list[Packet] = []
        while True:
            if len(self._buf) < HEADER.size:
                break
            length, mtype = HEADER.unpack_from(self._buf, 0)
            if length > MAX_PAYLOAD:
                raise ValueError(f"frame too large: {length}")
            total = HEADER.size + length
            if len(self._buf) < total:
                break
            payload = bytes(self._buf[HEADER.size:total])
            del self._buf[:total]
            try:
                out.append(Packet(MsgType(mtype), payload))
            except ValueError as exc:
                raise ValueError(f"unknown message type {mtype}") from exc
        return out
