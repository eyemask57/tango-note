"""Tests for tango_note.gui.utils.

These mock the Tkinter widgets so they run headless — no display is
needed and no GUI skip marker applies.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from tango_note.gui.utils import center_on_parent


def _parent(x: int, y: int, w: int, h: int) -> MagicMock:
    p = MagicMock()
    p.winfo_x.return_value = x
    p.winfo_y.return_value = y
    p.winfo_width.return_value = w
    p.winfo_height.return_value = h
    return p


def _dialog(req_w: int, req_h: int) -> MagicMock:
    d = MagicMock()
    d.winfo_reqwidth.return_value = req_w
    d.winfo_reqheight.return_value = req_h
    return d


def test_center_computes_centered_offset() -> None:
    parent = _parent(100, 100, 800, 600)
    dialog = _dialog(200, 100)
    center_on_parent(dialog, parent)
    # x = 100 + (800 - 200)//2 = 400 ; y = 100 + (600 - 100)//2 = 350
    dialog.geometry.assert_called_once_with("+400+350")


def test_center_clamps_negative_x_and_y_to_zero() -> None:
    """A dialog larger than its parent must not land off-screen."""
    parent = _parent(0, 0, 100, 100)
    dialog = _dialog(400, 300)
    center_on_parent(dialog, parent)
    # x = 0 + (100-400)//2 = -150 -> 0 ; y = 0 + (100-300)//2 = -100 -> 0
    dialog.geometry.assert_called_once_with("+0+0")


def test_center_clamps_only_the_offending_axis() -> None:
    parent = _parent(0, 500, 1000, 100)
    dialog = _dialog(200, 400)
    center_on_parent(dialog, parent)
    # x = 0 + (1000-200)//2 = 400 (ok) ; y = 500 + (100-400)//2 = 350 (ok)
    dialog.geometry.assert_called_once_with("+400+350")


def test_center_flushes_pending_geometry_first() -> None:
    """Both widgets must be settled with update_idletasks before measuring."""
    parent = _parent(10, 10, 200, 200)
    dialog = _dialog(50, 50)
    center_on_parent(dialog, parent)
    parent.update_idletasks.assert_called_once()
    dialog.update_idletasks.assert_called_once()


def test_center_geometry_string_is_offset_only() -> None:
    """The geometry string sets position only (``+x+y``), not size."""
    parent = _parent(0, 0, 400, 400)
    dialog = _dialog(100, 100)
    center_on_parent(dialog, parent)
    arg = dialog.geometry.call_args[0][0]
    assert arg.startswith("+")
    assert "x" not in arg  # no WxH component
