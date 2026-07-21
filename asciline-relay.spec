# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Asciline relay server."""

import os
ROOT = os.path.dirname(os.path.abspath(SPECPATH))

a = Analysis(
    [os.path.join(ROOT, "server", "relay.py")],
    pathex=[ROOT],
    datas=[],
    hiddenimports=[
        "shared",
        "shared.protocol",
        "shared.crypto",
        "shared.upnp",
        "miniupnpc",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PIL", "cv2", "numpy", "sounddevice", "mss"],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="asciline-relay",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
)
