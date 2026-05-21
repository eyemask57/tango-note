"""Small, dependency-free Tkinter helpers shared across GUI screens.

This module must not import from ``tango_note.gui.screens`` or
``tango_note.gui.app`` — keeping it leaf-level avoids any circular-import
risk when screens import it.
"""

from __future__ import annotations

import tkinter as tk


def center_on_parent(dialog: tk.Toplevel, parent: tk.Misc) -> None:
    """Position ``dialog`` centered over ``parent``.

    Both widgets are flushed with ``update_idletasks()`` first so the
    geometry queries below return real, settled values rather than the
    placeholder sizes a freshly built (not yet mapped) widget reports.

    Args:
        dialog: The ``Toplevel`` to move.
        parent: The window to center over. Should be a top-level window
            (``Tk`` or ``Toplevel``) so ``winfo_x`` / ``winfo_y`` are
            absolute screen coordinates.

    Notes:
        The final position is clamped with ``max(0, ...)`` so the dialog
        never lands at negative coordinates (partly off the top/left of
        the screen) when the parent is small or near a screen edge.
    """
    parent.update_idletasks()
    dialog.update_idletasks()
    px = parent.winfo_x()
    py = parent.winfo_y()
    pw = parent.winfo_width()
    ph = parent.winfo_height()
    dw = dialog.winfo_reqwidth()
    dh = dialog.winfo_reqheight()
    x = px + (pw - dw) // 2
    y = py + (ph - dh) // 2
    dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
