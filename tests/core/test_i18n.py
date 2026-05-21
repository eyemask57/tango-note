"""Tests for tango_note.core.i18n."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tango_note.core.i18n import _locate_localedir, setup_i18n


def test_japanese_translation_for_known_string() -> None:
    _ = setup_i18n("ja")
    assert _("Hello") == "こんにちは"


def test_untranslated_string_falls_back_to_source() -> None:
    """Strings without a translation entry must come back unchanged."""
    _ = setup_i18n("ja")
    assert _("NonExistentString") == "NonExistentString"


def test_unknown_language_falls_back_to_source() -> None:
    """Asking for an unsupported language must not raise — fallback to identity."""
    _ = setup_i18n("xx")
    assert _("Hello") == "Hello"
    assert _("Anything else") == "Anything else"


def test_translator_is_callable_with_str_return() -> None:
    _ = setup_i18n("ja")
    result = _("Hello")
    assert isinstance(result, str)


def test_setup_i18n_can_be_called_multiple_times_independently() -> None:
    """Two calls produce independent translators; one does not affect the other."""
    ja = setup_i18n("ja")
    xx = setup_i18n("xx")
    assert ja("Hello") == "こんにちは"
    assert xx("Hello") == "Hello"


# ----- locale-directory resolution ------------------------------------------


def test_locate_localedir_uses_meipass_when_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In a PyInstaller bundle, locales live under sys._MEIPASS."""
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert _locate_localedir() == tmp_path / "locales"


def test_locate_localedir_normal_run_ignores_meipass(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without _MEIPASS (normal run), the resolved dir holds the real .mo."""
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    localedir = _locate_localedir()
    assert localedir.name == "locales"
    # The real catalog is reachable, so translation still works.
    assert setup_i18n("ja")("Hello") == "こんにちは"
