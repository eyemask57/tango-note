"""Tests for pure (non-Tk) helpers in tango_note.gui.screens.card_edit.

These cover module-level functions that need no ``Tk`` instance, so they
run headless and carry no GUI skip marker. (Importing the module only
needs ``import tkinter``, which works without a display; a display is
only required to actually instantiate widgets.)
"""

from __future__ import annotations

import pytest

from tango_note.core.config import (
    EXPORT_DEFAULT_ASK,
    EXPORT_DEFAULT_INCLUDE,
    EXPORT_DEFAULT_STRIP,
)
from tango_note.gui.screens.card_edit import (
    _format_notes_for_treeview,
    _resolve_strip_stats,
    _sanitize_filename,
)


# ----- _sanitize_filename ---------------------------------------------------


def test_sanitize_replaces_each_illegal_char() -> None:
    for ch in '<>:"/\\|?*':
        assert _sanitize_filename(f"a{ch}b") == "a_b", ch


def test_sanitize_slash_example() -> None:
    # The example from the spec.
    assert _sanitize_filename("My/Deck") == "My_Deck"


def test_sanitize_multiple_illegal_chars() -> None:
    assert _sanitize_filename('a<b>c:d"e') == "a_b_c_d_e"


def test_sanitize_trims_surrounding_whitespace() -> None:
    assert _sanitize_filename("  French Basics  ") == "French Basics"


def test_sanitize_safe_name_unchanged() -> None:
    assert _sanitize_filename("French Basics") == "French Basics"


def test_sanitize_non_ascii_name_preserved() -> None:
    assert _sanitize_filename("フランス語 入門") == "フランス語 入門"


def test_sanitize_empty_or_blank_falls_back_to_deck() -> None:
    assert _sanitize_filename("") == "deck"
    assert _sanitize_filename("   ") == "deck"


def test_sanitize_all_illegal_becomes_underscores() -> None:
    # "///" -> "___" is non-empty, so it is kept (no "deck" fallback).
    assert _sanitize_filename("///") == "___"


# ----- _format_notes_for_treeview -------------------------------------------


def test_format_notes_collapses_multiline() -> None:
    assert _format_notes_for_treeview("first\nsecond") == "first ..."


def test_format_notes_single_line_unchanged() -> None:
    assert _format_notes_for_treeview("single line") == "single line"
    assert _format_notes_for_treeview("") == ""


# ----- _resolve_strip_stats -------------------------------------------------


def _exploding_callback() -> bool:
    raise AssertionError("ask_callback must not be invoked for this setting")


def test_resolve_strip_returns_true_without_asking() -> None:
    assert _resolve_strip_stats(EXPORT_DEFAULT_STRIP, _exploding_callback) is True


def test_resolve_include_returns_false_without_asking() -> None:
    assert _resolve_strip_stats(EXPORT_DEFAULT_INCLUDE, _exploding_callback) is False


@pytest.mark.parametrize("answer", [True, False, None])
def test_resolve_ask_delegates_to_callback(answer) -> None:
    assert _resolve_strip_stats(EXPORT_DEFAULT_ASK, lambda: answer) is answer


def test_resolve_unknown_value_delegates_to_callback() -> None:
    """An unrecognized setting falls back to asking, never silently exports."""
    assert _resolve_strip_stats("bogus", lambda: True) is True
