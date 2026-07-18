#!/usr/bin/env python3
"""Smoke tests for crypto, G.729EV, ASCIILINE, and framing."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.asciline import AsciiLineDecoder, AsciiLineEncoder, AsciiLineFrame
from shared.crypto import derive_session, generate_identity, new_ephemeral
from shared.g729ev import (
    FRAME_SAMPLES,
    LAYER_RATES_KBPS,
    G729EVCodec,
    G729EVFrame,
    layers_to_bytes,
    rate_to_layers,
)
from shared.protocol import FrameReader, MsgType, Packet, pack_json


def test_frame_reader() -> None:
    p1 = pack_json(MsgType.CHAT, {"a": 1})
    p2 = Packet(MsgType.VOICE, b"\x00\x01\x02")
    blob = p1.encode() + p2.encode()
    # split arbitrarily
    fr = FrameReader()
    mid = len(blob) // 3
    out = fr.feed(blob[:mid]) + fr.feed(blob[mid:])
    assert len(out) == 2
    assert out[0].type == MsgType.CHAT
    assert out[1].payload == b"\x00\x01\x02"
    print("OK frame_reader")


def test_e2e_crypto() -> None:
    id_a, pub_a = generate_identity()
    id_b, pub_b = generate_identity()
    eph_a, epub_a = new_ephemeral()
    eph_b, epub_b = new_ephemeral()

    # A is initiator if pub_a < pub_b
    a_init = pub_a < pub_b
    sess_a = derive_session(id_a, eph_a, pub_b, epub_b, i_am_initiator=a_init)
    sess_b = derive_session(id_b, eph_b, pub_a, epub_a, i_am_initiator=not a_init)

    aad = b"test-aad"
    ct = sess_a.encrypt(b"hello e2e", aad=aad)
    pt = sess_b.decrypt(ct, aad=aad)
    assert pt == b"hello e2e"

    ct2 = sess_b.encrypt(b"reply", aad=aad)
    assert sess_a.decrypt(ct2, aad=aad) == b"reply"
    print("OK e2e_crypto")


def test_g729ev_roundtrip() -> None:
    for kbps in LAYER_RATES_KBPS:
        enc = G729EVCodec(kbps)
        dec = G729EVCodec(kbps)
        # 440 Hz tone
        t = np.arange(FRAME_SAMPLES) / 16000.0
        pcm = (0.4 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
        blob = enc.encode(pcm)
        fr = G729EVFrame.unpack(blob)
        assert fr.layers == rate_to_layers(kbps)
        assert len(fr.data) == layers_to_bytes(fr.layers)
        out = dec.decode(blob)
        assert out.dtype == np.int16
        assert len(out) == FRAME_SAMPLES
        # should not be pure silence for a tone at higher rates
        if kbps >= 14:
            assert float(np.max(np.abs(out))) > 100
    print("OK g729ev_roundtrip")


def test_asciline_roundtrip() -> None:
    from shared.asciline import FLAG_CAMERA, FLAG_SCREEN

    enc = AsciiLineEncoder(width=40, height=12, fps=5, flags=FLAG_CAMERA)
    img = np.linspace(0, 255, 40 * 12, dtype=np.uint8).reshape(12, 40)
    blob = enc.encode_gray(img)
    fr = AsciiLineFrame.decode(blob)
    assert fr.width == 40 and fr.height == 12
    assert len(fr.rows) == 12
    assert all(len(r) == 40 for r in fr.rows)
    assert fr.source == "camera"
    assert fr.flags & FLAG_CAMERA
    fr2 = AsciiLineDecoder().decode(blob)
    assert fr2.rows == fr.rows

    enc_s = AsciiLineEncoder(width=60, height=20, fps=4, flags=FLAG_SCREEN)
    blob_s = enc_s.encode_gray(img)
    fr_s = AsciiLineFrame.decode(blob_s)
    assert fr_s.source == "screen"
    assert fr_s.flags & FLAG_SCREEN
    print("OK asciline_roundtrip")


if __name__ == "__main__":
    test_frame_reader()
    test_e2e_crypto()
    test_g729ev_roundtrip()
    test_asciline_roundtrip()
    print("\nAll smoke tests passed.")
