"""Tests for tango_note.core.storage."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tango_note.core.exceptions import DeckNotFoundError, InvalidDeckSchemaError
from tango_note.core.models import Card, CardStats, Deck, DeckMeta
from tango_note.core.storage import (
    SUPPORTED_VERSION,
    deck_from_dict,
    deck_to_dict,
    delete_deck,
    load_deck,
    save_deck,
)


@pytest.fixture
def sample_deck() -> Deck:
    return Deck(
        meta=DeckMeta(
            id="deck-uuid-1",
            name="French Basics",
            source_lang="fr",
            target_lang="ja",
            created_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc),
        ),
        cards=[
            Card(
                id="card-001",
                term="bonjour",
                definition="こんにちは",
                notes="朝〜昼の挨拶",
                stats=CardStats(
                    correct=3,
                    wrong=1,
                    last_reviewed=datetime(2026, 5, 10, 8, 0, 0, tzinfo=timezone.utc),
                ),
            ),
        ],
    )


def _minimal_deck_dict(version: str = SUPPORTED_VERSION) -> dict:
    return {
        "version": version,
        "deck": {
            "id": "d",
            "name": "n",
            "source_lang": "fr",
            "target_lang": "ja",
            "created_at": "2026-05-12T10:00:00Z",
        },
        "cards": [],
    }


# ----- to_dict / from_dict roundtrip -----------------------------------------


def test_deck_to_dict_uses_supported_version(sample_deck: Deck) -> None:
    data = deck_to_dict(sample_deck)
    assert data["version"] == SUPPORTED_VERSION


def test_dict_roundtrip_preserves_all_fields(sample_deck: Deck) -> None:
    data = deck_to_dict(sample_deck)
    restored = deck_from_dict(data)

    assert restored.meta.id == sample_deck.meta.id
    assert restored.meta.name == sample_deck.meta.name
    assert restored.meta.source_lang == "fr"
    assert restored.meta.target_lang == "ja"
    assert restored.meta.created_at == sample_deck.meta.created_at

    assert len(restored.cards) == 1
    c = restored.cards[0]
    assert c.id == "card-001"
    assert c.term == "bonjour"
    assert c.definition == "こんにちは"
    assert c.notes == "朝〜昼の挨拶"
    assert c.stats.correct == 3
    assert c.stats.wrong == 1
    assert c.stats.last_reviewed == datetime(2026, 5, 10, 8, 0, 0, tzinfo=timezone.utc)


def test_datetime_serialized_as_iso8601_with_z(sample_deck: Deck) -> None:
    data = deck_to_dict(sample_deck)
    assert data["deck"]["created_at"] == "2026-05-12T10:00:00Z"
    assert data["cards"][0]["stats"]["last_reviewed"] == "2026-05-10T08:00:00Z"


def test_last_reviewed_none_roundtrips(sample_deck: Deck) -> None:
    sample_deck.cards[0].stats.last_reviewed = None
    data = deck_to_dict(sample_deck)
    assert data["cards"][0]["stats"]["last_reviewed"] is None
    restored = deck_from_dict(data)
    assert restored.cards[0].stats.last_reviewed is None


# ----- file save/load --------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path: Path, sample_deck: Deck) -> None:
    p = tmp_path / "deck.json"
    save_deck(sample_deck, p)
    assert p.exists()

    loaded = load_deck(p)
    assert loaded.meta.id == sample_deck.meta.id
    assert len(loaded.cards) == 1
    assert loaded.cards[0].definition == "こんにちは"


def test_save_writes_utf8_not_ascii_escapes(tmp_path: Path, sample_deck: Deck) -> None:
    """Non-ASCII content must be preserved as literal UTF-8."""
    p = tmp_path / "deck.json"
    save_deck(sample_deck, p)
    raw_text = p.read_text(encoding="utf-8")
    assert "こんにちは" in raw_text
    assert "朝〜昼の挨拶" in raw_text
    assert "\\u" not in raw_text


def test_save_creates_parent_directories(tmp_path: Path, sample_deck: Deck) -> None:
    p = tmp_path / "nested" / "deeper" / "deck.json"
    save_deck(sample_deck, p)
    assert p.exists()


def test_save_overwrites_existing(tmp_path: Path, sample_deck: Deck) -> None:
    p = tmp_path / "deck.json"
    save_deck(sample_deck, p)

    sample_deck.meta.name = "Renamed Deck"
    save_deck(sample_deck, p)

    loaded = load_deck(p)
    assert loaded.meta.name == "Renamed Deck"


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(DeckNotFoundError):
        load_deck(tmp_path / "missing.json")


def test_save_produces_valid_json(tmp_path: Path, sample_deck: Deck) -> None:
    p = tmp_path / "deck.json"
    save_deck(sample_deck, p)
    parsed = json.loads(p.read_text(encoding="utf-8"))
    assert parsed["version"] == SUPPORTED_VERSION
    assert parsed["deck"]["name"] == "French Basics"


# ----- delete_deck -----------------------------------------------------------


def test_delete_deck_removes_file(tmp_path: Path, sample_deck: Deck) -> None:
    p = tmp_path / "deck.json"
    save_deck(sample_deck, p)
    assert p.exists()
    delete_deck(p)
    assert not p.exists()


def test_delete_deck_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(DeckNotFoundError):
        delete_deck(tmp_path / "missing.json")


# ----- version validation ----------------------------------------------------


def test_missing_version_rejected() -> None:
    data = _minimal_deck_dict()
    del data["version"]
    with pytest.raises(InvalidDeckSchemaError):
        deck_from_dict(data)


def test_empty_version_rejected() -> None:
    with pytest.raises(InvalidDeckSchemaError):
        deck_from_dict(_minimal_deck_dict(version=""))


def test_malformed_version_rejected() -> None:
    with pytest.raises(InvalidDeckSchemaError):
        deck_from_dict(_minimal_deck_dict(version="1"))


def test_wrong_major_version_rejected() -> None:
    with pytest.raises(InvalidDeckSchemaError):
        deck_from_dict(_minimal_deck_dict(version="2.0"))


def test_minor_version_difference_warns_and_loads(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="tango_note.core.storage"):
        deck = deck_from_dict(_minimal_deck_dict(version="1.5"))

    assert deck.meta.id == "d"
    assert any(
        "minor version" in record.message.lower() for record in caplog.records
    ), f"expected a minor-version warning, got: {[r.message for r in caplog.records]}"


# ----- required-field checks -------------------------------------------------


def test_missing_required_deck_field_raises() -> None:
    data = _minimal_deck_dict()
    del data["deck"]["id"]
    with pytest.raises(InvalidDeckSchemaError):
        deck_from_dict(data)


def test_missing_required_card_field_raises() -> None:
    data = _minimal_deck_dict()
    data["cards"] = [{"id": "c1", "term": "a"}]  # missing definition
    with pytest.raises(InvalidDeckSchemaError):
        deck_from_dict(data)


def test_card_with_no_stats_defaults_to_zero() -> None:
    data = _minimal_deck_dict()
    data["cards"] = [{"id": "c1", "term": "a", "definition": "α"}]
    deck = deck_from_dict(data)
    assert deck.cards[0].notes == ""
    assert deck.cards[0].stats.correct == 0
    assert deck.cards[0].stats.wrong == 0
    assert deck.cards[0].stats.last_reviewed is None


def test_top_level_must_be_object() -> None:
    with pytest.raises(InvalidDeckSchemaError):
        deck_from_dict("not a dict")  # type: ignore[arg-type]


def test_malformed_json_file_raises_schema_error(tmp_path: Path) -> None:
    """Raw JSON syntax errors are normalized to InvalidDeckSchemaError."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(InvalidDeckSchemaError):
        load_deck(bad)


# ----- multi-line notes round-trip ------------------------------------------


def _deck_with_notes(notes: str) -> Deck:
    return Deck(
        meta=DeckMeta(
            id="d",
            name="n",
            source_lang="en",
            target_lang="ja",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        cards=[Card(id="c1", term="t", definition="d", notes=notes)],
    )


def test_multiline_notes_survive_dict_roundtrip() -> None:
    notes = "first line\nsecond line\nthird line"
    restored = deck_from_dict(deck_to_dict(_deck_with_notes(notes)))
    assert restored.cards[0].notes == notes


def test_multiline_notes_survive_file_roundtrip(tmp_path: Path) -> None:
    notes = "line A\nline B\n\nline D (after blank line)"
    p = tmp_path / "deck.json"
    save_deck(_deck_with_notes(notes), p)
    loaded = load_deck(p)
    assert loaded.cards[0].notes == notes


def test_notes_with_leading_newline_preserved(tmp_path: Path) -> None:
    notes = "\nstarts with a blank line"
    p = tmp_path / "deck.json"
    save_deck(_deck_with_notes(notes), p)
    assert load_deck(p).cards[0].notes == notes


def test_notes_with_trailing_newline_preserved(tmp_path: Path) -> None:
    notes = "ends with a blank line\n"
    p = tmp_path / "deck.json"
    save_deck(_deck_with_notes(notes), p)
    assert load_deck(p).cards[0].notes == notes


def test_notes_that_are_only_newlines_preserved(tmp_path: Path) -> None:
    notes = "\n\n\n"
    p = tmp_path / "deck.json"
    save_deck(_deck_with_notes(notes), p)
    assert load_deck(p).cards[0].notes == notes
