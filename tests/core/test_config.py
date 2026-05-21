"""Tests for tango_note.core.config."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from tango_note.core.config import (
    DEFAULT_UNREVIEWED_DAYS,
    DEFAULT_WEAK_THRESHOLD,
    EXPORT_DEFAULT_ASK,
    EXPORT_DEFAULT_INCLUDE,
    EXPORT_DEFAULT_STRIP,
    QUIZ_MODE_RANDOM,
    QUIZ_MODE_UNREVIEWED,
    QUIZ_MODE_WEAK,
    AppConfig,
    config_path,
    decks_dir,
    home_dir,
    load_config,
    save_config,
)
from tango_note.core.exceptions import InvalidConfigError


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the app home directory to a tmp path for the test."""
    monkeypatch.setenv("TANGO_NOTE_HOME", str(tmp_path))
    return tmp_path


# ----- env-var override / path helpers ---------------------------------------


def test_home_dir_honors_env_var(tmp_home: Path) -> None:
    assert home_dir() == tmp_home


def test_config_path_lives_under_home(tmp_home: Path) -> None:
    assert config_path() == tmp_home / "config.json"


def test_decks_dir_lives_under_home(tmp_home: Path) -> None:
    assert decks_dir() == tmp_home / "decks"


# ----- defaults / load -------------------------------------------------------


def test_default_config_when_file_missing(tmp_home: Path) -> None:
    cfg = load_config()
    assert cfg.lang == "ja"
    assert cfg.current_deck is None


def test_save_and_load_roundtrip(tmp_home: Path) -> None:
    save_config(AppConfig(lang="en", current_deck="/path/to/deck.json"))
    loaded = load_config()
    assert loaded.lang == "en"
    assert loaded.current_deck == "/path/to/deck.json"


def test_save_creates_parent_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Saving a config must create the home dir if it does not yet exist."""
    nested_home = tmp_path / "fresh" / "tango-note"
    monkeypatch.setenv("TANGO_NOTE_HOME", str(nested_home))
    assert not nested_home.exists()
    save_config(AppConfig())
    assert (nested_home / "config.json").exists()


def test_save_writes_utf8_not_ascii(tmp_home: Path) -> None:
    """Deck paths with non-ASCII characters must be preserved as UTF-8."""
    save_config(AppConfig(current_deck=str(tmp_home / "日本語デッキ.json")))
    raw = config_path().read_text(encoding="utf-8")
    assert "日本語デッキ.json" in raw
    assert "\\u" not in raw


def test_save_leaves_no_temp_files(tmp_home: Path) -> None:
    """The .tmp file used for atomic write must not linger."""
    save_config(AppConfig())
    assert not list(tmp_home.glob("*.tmp"))


# ----- error paths -----------------------------------------------------------


def test_load_invalid_json_raises(tmp_home: Path) -> None:
    config_path().write_text("not valid json{", encoding="utf-8")
    with pytest.raises(InvalidConfigError):
        load_config()


def test_load_non_object_json_raises(tmp_home: Path) -> None:
    config_path().write_text('"just a string"', encoding="utf-8")
    with pytest.raises(InvalidConfigError):
        load_config()


def test_load_extra_fields_are_ignored(tmp_home: Path) -> None:
    """Unknown fields should not break loading (forward-compat)."""
    config_path().write_text(
        json.dumps({"lang": "fr", "current_deck": None, "future_field": 42}),
        encoding="utf-8",
    )
    cfg = load_config()
    assert cfg.lang == "fr"
    assert cfg.current_deck is None


# ----- export_default --------------------------------------------------------


def test_export_default_defaults_to_ask_when_file_missing(tmp_home: Path) -> None:
    assert load_config().export_default == EXPORT_DEFAULT_ASK


def test_export_default_absent_field_defaults_silently(
    tmp_home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An old config without the field defaults to 'ask' with no warning."""
    config_path().write_text(
        json.dumps({"lang": "ja", "current_deck": None}), encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING, logger="tango_note.core.config"):
        cfg = load_config()
    assert cfg.export_default == EXPORT_DEFAULT_ASK
    assert caplog.records == []


@pytest.mark.parametrize(
    "value", [EXPORT_DEFAULT_ASK, EXPORT_DEFAULT_STRIP, EXPORT_DEFAULT_INCLUDE]
)
def test_export_default_roundtrip(tmp_home: Path, value: str) -> None:
    save_config(AppConfig(export_default=value))
    assert load_config().export_default == value


def test_export_default_invalid_value_warns_and_falls_back(
    tmp_home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config_path().write_text(
        json.dumps({"export_default": "bogus"}), encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING, logger="tango_note.core.config"):
        cfg = load_config()
    assert cfg.export_default == EXPORT_DEFAULT_ASK
    assert any(
        "export_default" in record.message for record in caplog.records
    ), f"expected an export_default warning, got: {[r.message for r in caplog.records]}"


def test_save_includes_export_default_in_json(tmp_home: Path) -> None:
    save_config(AppConfig())
    data = json.loads(config_path().read_text(encoding="utf-8"))
    assert data["export_default"] == EXPORT_DEFAULT_ASK


# ----- quiz_mode / weak_threshold / unreviewed_days --------------------------


def test_quiz_tuning_defaults_when_file_missing(tmp_home: Path) -> None:
    cfg = load_config()
    assert cfg.quiz_mode == QUIZ_MODE_RANDOM
    assert cfg.weak_threshold == DEFAULT_WEAK_THRESHOLD
    assert cfg.unreviewed_days == DEFAULT_UNREVIEWED_DAYS


def test_quiz_tuning_defaults_for_old_config(
    tmp_home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An old config without these fields defaults silently (no warning)."""
    config_path().write_text(
        json.dumps({"lang": "ja", "current_deck": None}), encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING, logger="tango_note.core.config"):
        cfg = load_config()
    assert cfg.quiz_mode == QUIZ_MODE_RANDOM
    assert cfg.weak_threshold == DEFAULT_WEAK_THRESHOLD
    assert cfg.unreviewed_days == DEFAULT_UNREVIEWED_DAYS
    assert caplog.records == []


@pytest.mark.parametrize(
    "mode", [QUIZ_MODE_RANDOM, QUIZ_MODE_WEAK, QUIZ_MODE_UNREVIEWED]
)
def test_quiz_mode_roundtrip(tmp_home: Path, mode: str) -> None:
    save_config(AppConfig(quiz_mode=mode))
    assert load_config().quiz_mode == mode


@pytest.mark.parametrize("threshold", [0.0, 0.5, 0.85, 1.0])
def test_weak_threshold_roundtrip(tmp_home: Path, threshold: float) -> None:
    save_config(AppConfig(weak_threshold=threshold))
    assert load_config().weak_threshold == threshold


@pytest.mark.parametrize("days", [1, 7, 30, 365])
def test_unreviewed_days_roundtrip(tmp_home: Path, days: int) -> None:
    save_config(AppConfig(unreviewed_days=days))
    assert load_config().unreviewed_days == days


def test_quiz_mode_invalid_value_warns_and_falls_back(
    tmp_home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config_path().write_text(
        json.dumps({"quiz_mode": "bogus"}), encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING, logger="tango_note.core.config"):
        cfg = load_config()
    assert cfg.quiz_mode == QUIZ_MODE_RANDOM
    assert any("quiz_mode" in r.message for r in caplog.records)


@pytest.mark.parametrize("bad", [-0.5, 1.5, "high", True])
def test_weak_threshold_invalid_warns_and_falls_back(
    tmp_home: Path, caplog: pytest.LogCaptureFixture, bad: object
) -> None:
    config_path().write_text(
        json.dumps({"weak_threshold": bad}), encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING, logger="tango_note.core.config"):
        cfg = load_config()
    assert cfg.weak_threshold == DEFAULT_WEAK_THRESHOLD
    assert any("weak_threshold" in r.message for r in caplog.records)


@pytest.mark.parametrize("bad", [0, -3, 2.5, "ten", True])
def test_unreviewed_days_invalid_warns_and_falls_back(
    tmp_home: Path, caplog: pytest.LogCaptureFixture, bad: object
) -> None:
    config_path().write_text(
        json.dumps({"unreviewed_days": bad}), encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING, logger="tango_note.core.config"):
        cfg = load_config()
    assert cfg.unreviewed_days == DEFAULT_UNREVIEWED_DAYS
    assert any("unreviewed_days" in r.message for r in caplog.records)
