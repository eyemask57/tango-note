"""Session-wide pytest setup.

Compiles any stale ``.po`` files to ``.mo`` before tests run so that
:mod:`tango_note.core.i18n` can load translations without requiring
developers to remember the manual ``python tools/msgfmt.py`` step
between edits.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def pytest_configure(config) -> None:  # noqa: ARG001 (pytest hook signature)
    locales_dir = REPO_ROOT / "locales"
    msgfmt = REPO_ROOT / "tools" / "msgfmt.py"
    if not locales_dir.exists() or not msgfmt.exists():
        return
    for po_file in locales_dir.rglob("*.po"):
        mo_file = po_file.with_suffix(".mo")
        if mo_file.exists() and mo_file.stat().st_mtime >= po_file.stat().st_mtime:
            continue
        subprocess.run(
            [sys.executable, str(msgfmt), str(po_file)],
            check=True,
        )
