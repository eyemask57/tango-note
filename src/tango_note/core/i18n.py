"""i18n setup for tango-note.

Display layers obtain a translator function via :func:`setup_i18n` and
use it to wrap all user-facing strings::

    _ = setup_i18n("ja")
    print(_("Hello"))    # -> "こんにちは"

``gettext.install()`` is intentionally avoided so the global ``builtins``
namespace stays clean — each module that needs translations binds its
own local ``_``.

Locale directory layout (gettext convention)::

    locales/<lang>/LC_MESSAGES/tango_note.mo

The directory is located, in priority order, for a PyInstaller bundle,
then a wheel install, then an editable (``pip install -e .``) checkout.
"""

from __future__ import annotations

import gettext
import sys
from importlib.resources import files
from pathlib import Path
from typing import Callable

DOMAIN = "tango_note"


def _locate_localedir() -> Path:
    """Resolve the locale directory across all three deployment modes.

    Priority:

    1. **PyInstaller bundle** — when frozen, PyInstaller unpacks bundled
       data to ``sys._MEIPASS``; the spec file ships ``locales`` there,
       so ``<_MEIPASS>/locales`` is used.
    2. **Wheel install** — hatch ``force-include`` places ``locales``
       inside the installed ``tango_note`` package.
    3. **Editable install** — ``locales`` sits at the repo root, two
       directories above ``src/tango_note/``.

    Returns:
        Path to the ``locales`` directory. If no candidate directory
        exists (e.g., before any ``.mo`` has been generated), the
        editable-layout candidate is returned anyway; :func:`gettext.
        translation` with ``fallback=True`` then yields a
        ``NullTranslations`` that passes message ids through unchanged.
    """
    # 1. PyInstaller one-file/one-dir bundle.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        return Path(meipass) / "locales"

    pkg_root = Path(str(files("tango_note")))

    # 2. Wheel install (hatch ``force-include``): locales/ is inside the
    # tango_note package.
    bundled = pkg_root / "locales"
    if bundled.is_dir():
        return bundled

    # 3. Editable install with src layout: locales/ sits at the repo
    # root, which is two directories above ``src/tango_note/``.
    repo_root_candidate = pkg_root.parent.parent / "locales"
    return repo_root_candidate


def setup_i18n(lang: str) -> Callable[[str], str]:
    """Return a translator function ``_`` for the given language.

    Args:
        lang: ISO 639-1 language code (e.g., ``"ja"``, ``"en"``,
            ``"fr"``). Unknown codes silently fall back to identity —
            i.e., the source English string is returned unchanged.

    Returns:
        A callable ``_(msgid) -> str``. Untranslated message ids are
        returned as-is.
    """
    translation = gettext.translation(
        domain=DOMAIN,
        localedir=str(_locate_localedir()),
        languages=[lang],
        fallback=True,
    )
    return translation.gettext
