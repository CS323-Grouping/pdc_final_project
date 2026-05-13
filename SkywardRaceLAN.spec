# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: onedir build with bundled assets (pygame-ce).
#
# The spec walks ``assets/`` (``datas``), so ``assets/font/`` (see ``app/fonts.py``)
# ships bundled TTF files with the build automatically.
#
# Release semver and build number: edit app/version.py (VERSION_* and BUILD_NUMBER).
# Distribute the whole built folder under dist/ (application + _internal), not a lone .exe.
# For Windows File Properties version info, you can generate a VSVersionInfo block
# from app.version.windows_file_version_quad() when you add a version resource.
import os

spec_root = os.path.dirname(os.path.abspath(SPEC))

block_cipher = None

datas = []
_assets = os.path.join(spec_root, "assets")
if os.path.isdir(_assets):
    for root, _dirs, files in os.walk(_assets):
        for fname in files:
            src_path = os.path.join(root, fname)
            rel = os.path.relpath(src_path, _assets)
            parent = os.path.dirname(rel)
            if parent in ("", "."):
                dst = "assets"
            else:
                dst = os.path.join("assets", parent).replace("\\", "/")
            datas.append((src_path, dst))

hiddenimports = [
    "network.beacon",
    "network.cooldown",
    "network.end_policy",
    "network.protocol",
    "network.discovery",
    "network.network_handler",
    "pygame",
]

a = Analysis(
    [os.path.join(spec_root, "main.py")],
    pathex=[spec_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SkywardRaceLAN",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SkywardRaceLAN",
)
