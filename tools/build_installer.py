#!/usr/bin/env python
"""Build the tango-note Windows executable and installer end to end.

Steps:

1. Generate ``installer/tango-note.ico`` from the source PNG.
2. Recompile the ``.mo`` translation catalog.
3. Build ``dist/tango-note.exe`` with PyInstaller (``tango-note.spec``).
4. Compile ``dist/tango-note-setup.exe`` with Inno Setup (``ISCC.exe``).

Requires the ``build`` extras (``pip install -e ".[build]"``) and Inno
Setup 6. ISCC.exe is located via ``INNO_SETUP_ISCC``, the standard
install paths, then ``PATH``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_iscc() -> Path | None:
    """Locate the Inno Setup compiler, or return None if not found."""
    candidates: list[Path] = []
    env_path = os.environ.get("INNO_SETUP_ISCC")
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(
        [
            Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
            Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        ]
    )
    for c in candidates:
        if c.is_file():
            return c
    which = shutil.which("ISCC.exe")
    if which:
        return Path(which)
    return None


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    iscc = find_iscc()
    if iscc is None:
        print("ERROR: ISCC.exe (Inno Setup) が見つかりません．", file=sys.stderr)
        print(
            "  Inno Setup 6 をインストールするか，環境変数 INNO_SETUP_ISCC で",
            file=sys.stderr,
        )
        print("  ISCC.exe のパスを指定してください．", file=sys.stderr)
        return 1

    # 1. Icon generation.
    print("Generating icon...")
    subprocess.run(
        [sys.executable, str(repo_root / "tools" / "gen_icon.py")], check=True
    )

    # 2. Recompile the .mo catalog.
    po = repo_root / "locales" / "ja" / "LC_MESSAGES" / "tango_note.po"
    print(f"Compiling {po.name}...")
    subprocess.run(
        [sys.executable, str(repo_root / "tools" / "msgfmt.py"), str(po)],
        check=True,
        cwd=str(repo_root),
    )

    # 3. PyInstaller (invoked via the module so PATH need not be set up).
    print("Running PyInstaller...")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "tango-note.spec",
        ],
        check=True,
        cwd=str(repo_root),
    )

    # 4. Inno Setup.
    print(f"Running Inno Setup: {iscc}")
    subprocess.run(
        [str(iscc), str(repo_root / "installer" / "installer.iss")],
        check=True,
        cwd=str(repo_root),
    )

    # Result summary.
    exe = repo_root / "dist" / "tango-note.exe"
    setup = repo_root / "dist" / "tango-note-setup.exe"
    if not exe.exists():
        print(f"ERROR: {exe} not found", file=sys.stderr)
        return 1
    if not setup.exists():
        print(f"ERROR: {setup} not found", file=sys.stderr)
        return 1
    print()
    print("Build complete:")
    print(f"  {exe} ({exe.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  {setup} ({setup.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
