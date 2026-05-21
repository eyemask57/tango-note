"""tango-note GUI entry point.

Wires :func:`tango_note.core.i18n.setup_i18n` to the active language
from the user config, builds a :class:`tango_note.gui.app.MainWindow`,
and enters the Tk mainloop.
"""

from __future__ import annotations

import sys

# UTF-8 stdout/stderr — protects any print() / traceback path during
# development on legacy Windows code pages (e.g., cp932).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError, ValueError):
        pass

from tango_note.core.config import load_config  # noqa: E402
from tango_note.core.exceptions import InvalidConfigError  # noqa: E402
from tango_note.core.i18n import setup_i18n  # noqa: E402
from tango_note.gui.app import MainWindow  # noqa: E402


def main() -> None:
    """Launch the tango-note Tkinter GUI."""
    try:
        cfg = load_config()
        lang = cfg.lang
    except InvalidConfigError:
        lang = "ja"
    translator = setup_i18n(lang)
    window = MainWindow(translator=translator)
    window.run()


if __name__ == "__main__":
    main()
