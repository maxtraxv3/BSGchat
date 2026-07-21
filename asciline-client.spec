# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Asciline GUI client."""

import os
ROOT = os.path.dirname(os.path.abspath(SPECPATH))

a = Analysis(
    [os.path.join(ROOT, "client", "main.py")],
    pathex=[ROOT],
    datas=[],
    hiddenimports=[
        "client",
        "client.gui",
        "client.main",
        "client.audio_io",
        "client.video_io",
        "client.screencap",
        "client.web_viewer",
        "shared",
        "shared.protocol",
        "shared.crypto",
        "shared.asciline",
        "shared.adpcm",
        "shared.image_share",
        "shared.file_share",
        "shared.upnp",
        "miniupnpc",
        "sounddevice",
        "numpy",
        "cv2",
        "PIL",
        "mss",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="asciline-client",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
