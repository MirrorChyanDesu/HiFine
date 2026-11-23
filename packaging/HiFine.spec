# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os
import plistlib
import sys

from PyInstaller.utils.hooks import copy_metadata

packaging = Path(SPECPATH)
root = packaging.parent
if sys.platform == "win32":
    # Qt imports Windows' ICU ABI. Unrelated ICU/OpenSSL builds on a developer's
    # PATH can have the same DLL names but export different functions.
    windows = Path(os.environ["SystemRoot"])
    os.environ["PATH"] = os.pathsep.join(map(str, (
        Path(sys.executable).parent, Path(sys.base_prefix), windows / "System32", windows,
    )))
assets = root / "src" / "hifine" / "assets"
data = [(str(assets), "hifine/assets"), (str(packaging / "licenses"), "licenses")]
for dependency in ("Pillow", "pillow-heif", "PySide6-Essentials", "shiboken6"):
    data.extend(copy_metadata(dependency))

analysis = Analysis(
    [str(root / "src/hifine/__main__.py")],
    pathex=[str(root / "src")],
    datas=data,
    excludes=["tkinter", "unittest", "pytest", "numpy", "matplotlib", "IPython"],
)
pyz = PYZ(analysis.pure)
app_icon = packaging / ("macos/HiFine.icns" if sys.platform == "darwin" else "HiFine.ico")
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="HiFine",
          console=False, icon=str(app_icon), upx=False)
coll = COLLECT(exe, analysis.binaries, analysis.datas, name="HiFine", upx=False)

if sys.platform == "darwin":
    with (packaging / "macos/Documents.plist").open("rb") as stream:
        document_types = plistlib.load(stream)
    app = BUNDLE(coll, name="HiFine.app", icon=str(app_icon),
                 bundle_identifier="io.github.hifine.HiFine", version="0.1.0",
                 info_plist=document_types)
