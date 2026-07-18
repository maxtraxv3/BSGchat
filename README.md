# E2E ASCILINE Chat

End-to-end encrypted chat with:

- **Text chat** — ChaCha20-Poly1305 over X25519 session keys
- **ASCIILINE video** — terminal ASCII frames from **camera** and/or **screen share**
- **G.729.1 / G.729EV (Annex J) voice** — multi-layer embedded wideband speech @ 8–32 kb/s

The relay is **untrusted**: it only routes opaque ciphertext between room members.

## Quick start

```bash
cd ~/Projects/e2e-asciline-chat
python3 -m venv .venv
source .venv/bin/activate   # or: .venv/bin/activate.fish
pip install -r requirements.txt

# Terminal 1 — relay
python server/relay.py --port 9473

# Terminal 2 — Alice (camera + screen share)
python client/main.py --user alice --room demo --voice --video --screen

# Terminal 3 — Bob
python client/main.py --user bob --room demo --voice --video
```

Type messages normally. Commands:

| Command | Action |
|--------|--------|
| `/voice on\|off` | G.729EV voice chat |
| `/video on\|off` | ASCIILINE **camera** track |
| `/screen on\|off` | ASCIILINE **desktop screen share** |
| `/monitors` | list displays (mss indices) |
| `/monitor N` | pick monitor for screen share (0 = all) |
| `/region L T W H` | crop screen share to a pixel region |
| `/region clear` | full monitor again |
| `/show [camera\|screen]` | redraw last remote ASCII frame |
| `/bitrate N` | G.729EV rate 8–32 kb/s |
| `/peers` | list peers + fingerprints |
| `/devices` | list audio devices |
| `/quit` | exit |

## Architecture

```
┌────────────┐   ciphertext    ┌─────────────┐   ciphertext    ┌────────────┐
│  Client A  │ ───────────────►│ Blind relay │───────────────►│  Client B  │
│            │◄─────────────── │  (no keys)  │◄───────────────│            │
└─────┬──────┘                 └─────────────┘                 └─────┬──────┘
      │                                                              │
      ├─ X25519 identity + ephemeral (triple-DH style)               │
      ├─ HKDF-SHA256 → directional ChaCha20-Poly1305                 │
      ├─ Chat: JSON text                                             │
      ├─ Voice: G729EV/open-v1 frames (20 ms, 16 kHz)                │
      └─ Video: ASCIILINE/1.0 frames                                 │
```

### E2E crypto

1. Each client has a long-term **X25519 identity** key.
2. On peer join, both send **ephemeral** public keys.
3. Session material = `ECDH(eph,peer_eph) || ECDH(id,peer_eph) || ECDH(eph,peer_id)`.
4. HKDF derives two directional AEAD keys (initiator/responder ordered by identity).
5. Nonces are counters with replay detection. AAD binds `from|to|msg_type`.

### ASCIILINE video + screen share

UTF-8 line protocol inside the encrypted VIDEO payload:

```
ASCIILINE/1.0
W:120 H:40 FPS:4 SEQ:42 TS:… FLAGS:2 SRC:screen
....:::---===+++***###
...
.
```

| Track | Source | Default size | Notes |
|-------|--------|--------------|--------|
| `camera` | webcam (OpenCV) or test pattern | 80×28 @ 6 fps | `FLAGS` bit `0x1` |
| `screen` | desktop via **mss** | 120×40 @ 4 fps | `FLAGS` bit `0x2`, denser glyph ramp |

Camera and screen are **independent tracks** — both can run at once. Receivers cache the latest frame per source (`/show camera`, `/show screen`). Incoming screen frames are also printed about once per second so share is visible without a command.

```bash
# share primary monitor only
/screen on
/monitors
/monitor 1

# share a window-ish crop (global pixel coords)
/region 100 100 1280 720
```

### G.729.1 / G.729EV voice

| Property | Value |
|----------|--------|
| Sample rate | 16 kHz wideband |
| Frame | 20 ms (320 samples) |
| Rates | 8, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32 kb/s |
| Layers | L1 core → L2 NB enh. → L3 TDBWE-like → L4+ MDCT enh. |
| Payload tag | `G729EV/open-v1` |

Layer byte budgets match ITU-T G.729.1. The signal path is an **open reimplementation** of the embedded multi-layer architecture (LPC core + spectral enhancement), **not** bit-exact with the patent-encumbered ITU reference. Swap `shared/g729ev.py`’s `G729EVCodec` for a licensed ITU binary if you need bit-exact interoperability.

## Tests

```bash
.venv/bin/python tests/test_codecs_crypto.py
```

## Layout

```
e2e-asciline-chat/
  server/relay.py          # blind room relay
  client/main.py           # interactive client
  client/audio_io.py       # mic/speaker + G.729EV
  client/video_io.py       # camera + ASCIILINE
  shared/crypto.py         # X25519 + ChaCha20-Poly1305
  shared/protocol.py       # length-prefixed packets
  shared/g729ev.py         # G.729.1 layer codec
  shared/asciline.py       # ASCIILINE codec
  tests/
  requirements.txt
```

## Notes

- **Patents**: Commercial G.729 / G.729.1 may require royalty licenses from the patent pool. This project ships an open architectural codec for research/demo use.
- **Security**: No forward secrecy ratchet beyond the ephemeral exchange; no authentication of identity keys out-of-band beyond fingerprint display. Compare `/peers` fingerprints on a second channel for MITM resistance.
- **Headless**: Without a camera, video still streams an animated ASCII test pattern. Without a mic/speaker, `/voice on` will error with a sounddevice message.
