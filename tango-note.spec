# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for tango-note.

Produces a single-file, windowed (no console) Windows executable for the
Tkinter GUI. The compiled translation catalogs under ``locales/`` are
bundled as data; at runtime PyInstaller unpacks them to ``sys._MEIPASS``
and ``core.i18n._locate_localedir`` finds them there.

Build with::

    pyinstaller --clean --noconfirm tango-note.spec
"""

import pathlib

# SPECPATH is injected by PyInstaller — the directory of this spec file,
# which is the repository root.
repo_root = pathlib.Path(SPECPATH).resolve()

a = Analysis(
    [str(repo_root / "src" / "tango_note" / "gui" / "main.py")],
    pathex=[str(repo_root / "src")],
    binaries=[],
    datas=[
        (str(repo_root / "locales"), "locales"),
        # The app icon — unpacked to ``sys._MEIPASS/assets`` at runtime
        # so ``tango_note.gui.app._locate_icon`` can find it in the
        # frozen build.
        (str(repo_root / "installer" / "tango-note_source.png"), "assets"),
    ],
    hiddenimports=[
        "tkinter",
        "tkinter.ttk",
        "tkinter.messagebox",
        "tkinter.filedialog",
        "gettext",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "pytest_cov",
        "_pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="tango-note",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(repo_root / "installer" / "tango-note.ico"),
)
