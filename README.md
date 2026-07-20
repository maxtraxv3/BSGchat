# E2E ASCILINE Chat

End-to-end encrypted chat with:

- **Text chat** — ChaCha20-Poly1305 over X25519 session keys
- **ASCIILINE video** — terminal ASCII frames from **camera** and/or **screen share**
- **Canvas viewer** — browser-based JPEG viewer with system audio playback
- **ADPCM voice** — IMA/DVI ADPCM @ 32 kb/s (free, public-domain, ultra-low CPU)
- **Image sharing** — any image format → WebP with ASCII preview

The relay is **untrusted**: it only routes opaque ciphertext between room members.

## Quick start

```bash
cd ~/Projects/e2e-asciline-chat2
python3 -m venv .venv
source .venv/bin/activate   # or: .venv/bin/activate.fish
pip install -r requirements.txt

# Terminal 1 — relay
python server/relay.py --port 9473

# Terminal 2 — Alice (camera + screen share + viewer)
python client/main.py --user alice --room demo --voice --video --screen --viewer

# Terminal 3 — Bob
python client/main.py --user bob --room demo --voice --video
```

Type messages normally. Commands:

| Command | Action |
|--------|--------|
| `/voice on\|off` | ADPCM voice chat |
| `/video on\|off` | ASCIILINE **camera** track |
| `/screen on\|off` | ASCIILINE **desktop screen share** |
| `/screen show on\|off` | toggle remote screen frames in terminal (default: off) |
| `/viewer [off]` | open/close Canvas viewer in browser |
| `/monitors` | list displays |
| `/monitor N` | pick monitor for screen share (0 = all) |
| `/region L T W H` | crop screen share to a pixel region |
| `/region clear` | full monitor again |
| `/show [camera\|screen]` | redraw last remote ASCII frame |
| `/sendimage <path>` | send an image (auto-converted to WebP) |
| `/images` | list received images |
| `/download <id>` | save a received image to disk |
| `/preview <id>` | re-show ASCII preview of a received image |
| `/peers` | list peers + fingerprints |
| `/devices` | list audio devices |
| `/quit` | exit |

### CLI flags

| Flag | Description |
|------|-------------|
| `--screen` | start screen share on connect |
| `--viewer` | open Canvas viewer in browser on connect |
| `--voice` | start voice chat on connect |
| `--video` | start camera on connect |
| `--monitor N` | select monitor for screen share |

## Canvas viewer

The Canvas viewer renders screen share as JPEG in a browser with system audio playback.

```bash
# Start with viewer
python client/main.py --user alice --room demo --screen --viewer

# Or open viewer later
/viewer
/viewer off
```

The viewer captures system audio (what plays through your speakers) from the sharing PC via PipeWire/PulseAudio monitor source and streams it to the browser. Click **Enable Sound** in the browser to start audio playback (required by browser autoplay policy).

**System dependencies for audio capture** (Linux only):
- `pactl` (PulseAudio/PipeWire) — for finding the audio monitor source
- `pw-record` (PipeWire) — for capturing system audio

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
      ├─ Voice: ADPCM/ima-v1 frames (20 ms, 8 kHz)                  │
      ├─ Video: ASCIINE/1.0 frames                                   │
      └─ Image: WebP + ASCII preview                                 │
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
W:120 H:40 FPS:4 SEQ:42 TS:… FLAGS:2 SRC:screen IMG:<base64_jpeg>
....:::---===+++***###
...
.
```

| Track | Source | Default size | Notes |
|-------|--------|--------------|--------|
| `camera` | webcam (OpenCV) or test pattern | 80×28 @ 6 fps | `FLAGS` bit `0x1` |
| `screen` | desktop (auto backend) | 120×40 @ 30 fps | `FLAGS` bit `0x2`, denser glyph ramp |

Camera and screen are **independent tracks** — both can run at once. Receivers cache the latest frame per source (`/show camera`, `/show screen`).

The `IMG:` field carries a base64-encoded JPEG thumbnail (640×360, quality 60) embedded in each screen frame. The Canvas viewer decodes this directly — no ASCII conversion needed on the viewer side.

#### Screen capture backends (Wayland-safe)

`mss` often returns **black frames on Wayland**. The client probes backends in order and keeps the first that yields a real image:

| Backend | When it works | FPS |
|---------|---------------|-----|
| **gpu-screen-recorder** | Wayland (GPU-accelerated, persistent pipe mode) | ~27 |
| **grim** | wlroots (Sway, Hyprland, …) | ~15 |
| **spectacle** | KDE Plasma / kwin_wayland | ~2 |
| **mss** | X11 (fast) | ~30 |
| **ImageMagick** | `magick import` / `import` fallback | ~3 |

`gpu-screen-recorder` uses a **persistent streaming mode**: one long-lived process encodes H264/MPEG-TS to a pipe, decoded in real-time by ffmpeg. This achieves ~27 fps vs ~2 fps with per-frame subprocess spawning.

`/monitors` prints the active backend and a grab timing sample.

```bash
# share primary monitor only
/screen on
/monitors
/monitor 1

# share a window-ish crop (global pixel coords)
/region 100 100 1280 720

# toggle remote screen display in terminal
/screen show off
```

### ADPCM voice

| Property | Value |
|----------|--------|
| Sample rate | 8 kHz mono |
| Frame | 20 ms (160 samples) |
| Bitrate | 32 kb/s active |
| DTX | silence suppression with SID frames |
| Payload tag | `ADPCM/ima-v1` |

IMA/DVI ADPCM is a public-domain algorithm with no patents. Ultra-low CPU cost.

### System audio (viewer)

The Canvas viewer captures system audio from the screen-sharing PC via PipeWire/PulseAudio's monitor source:

- Uses `pactl info` to find the default output sink
- Constructs `<sink>.monitor` source name
- Captures via `pw-record` at 8 kHz mono
- Streams to browser via HTTP polling (`GET /audio`)
- Browser decodes PCM and plays via Web Audio API

This captures everything playing through the speakers (browser audio, videos, music, games, system sounds).

### Image sharing

Images are converted to WebP on send (quality 80) to save bandwidth. A small ASCII preview is included in the payload so receivers can display it without decoding the full image. Received images are saved to `~/.local/share/asciline/images/`.

## Tests

```bash
.venv/bin/python tests/test_codecs_crypto.py
```

## Layout

```
e2e-asciline-chat2/
  server/relay.py          # blind room relay
  client/main.py           # interactive client
  client/audio_io.py       # mic/speaker + ADPCM
  client/video_io.py       # camera + ASCIILINE + screen loop
  client/screencap.py      # desktop capture backends + persistent GSR
  client/web_viewer.py     # Canvas viewer HTTP server + audio capture
  shared/crypto.py         # X25519 + ChaCha20-Poly1305
  shared/protocol.py       # length-prefixed packets
  shared/adpcm.py          # IMA/DVI ADPCM voice codec
  shared/asciline.py       # ASCIILINE codec
  shared/image_share.py    # WebP image sharing
  tests/
  requirements.txt
```

## Notes

- **Security**: No forward secrecy ratchet beyond the ephemeral exchange; no authentication of identity keys out-of-band beyond fingerprint display. Compare `/peers` fingerprints on a second channel for MITM resistance.
- **Headless**: Without a camera, video still streams an animated ASCII test pattern. Without a mic/speaker, `/voice on` will error with a sounddevice message.
- **Audio capture**: System audio in the viewer requires PipeWire or PulseAudio with monitor/loopback support. On PipeWire, `pw-record` and `pactl` must be installed. On PulseAudio, `parec` may be used instead.
