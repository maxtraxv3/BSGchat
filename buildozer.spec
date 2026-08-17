[app]

# ── Basic info ──────────────────────────────────────────────────────
title = Asciline Chat
package.name = asciline
package.domain = org.asciline
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,java
source.include_patterns = shared/*,client/*
source.exclude_dirs = server,tests,bin,.buildozer,.git,.venv,node_modules
source.exclude_patterns = -,*-*,*.mkv,*.mp4,*.avi,*.mov,*.webm,*.iso,*.img

# ── Version ─────────────────────────────────────────────────────────
version = 0.3.0

# Entry point: main.py at project root

# ── Requirements ────────────────────────────────────────────────────
# No opencv — Android doesn't need it (camera uses pyjnius Camera1 API,
# screen uses MediaProjection). numpy is needed for ADPCM voice codec.
# ── Requirements ────────────────────────────────────────────────────
requirements =
    python3,
    hostpython3,
    kivy,
    pillow,
    numpy,
    pyjnius,
    plyer,
    openssl,
    cryptography==42.0.5,
    cffi,
    charset-normalizer

# ── Android-specific ────────────────────────────────────────────────
android.permissions =
    INTERNET,
    RECORD_AUDIO,
    CAMERA,
    MANAGE_EXTERNAL_STORAGE,
    FOREGROUND_SERVICE,
    FOREGROUND_SERVICE_MICROPHONE,
    FOREGROUND_SERVICE_MEDIA_PROJECTION,
    POST_NOTIFICATIONS,
    ACCESS_NETWORK_STATE

android.api = 35
android.minapi = 24
android.ndk = 26b
android.sdk = 35
android.accept_sdk_license = True
android.arch = arm64-v8a
android.archs = arm64-v8a

# Use fullscreen with action bar
android.fullscreen = 1
android.orientation = portrait

# Custom Java source — Gradle compiles src/org/asciline/*.java into the APK.
# This provides MediaProjectionService, a foreground service required for
# screen capture on Android 14+. Must run in main process (not :python_service).
android.add_src = src

# ── Presplash ───────────────────────────────────────────────────────
# presplash.filename = %(source.dir)s/assets/presplash.png
# icon.filename = %(source.dir)s/assets/icon.png

# ── Build ───────────────────────────────────────────────────────────
# log_level = 2
# warn_on_root = 1

# ── P4A (python-for-android) recipes ───────────────────────────────
p4a.branch = develop

# Force pip to respect p4a cross-compilation flags
p4a.pip_build_options = --no-build-isolation

# Manifest additions required for Foreground Service types on Android 14+ (API 35)
android.manifest.application_manifest_xml = <service android:name="org.asciline.MediaProjectionService" android:foregroundServiceType="mediaProjection|microphone" android:exported="false" />
