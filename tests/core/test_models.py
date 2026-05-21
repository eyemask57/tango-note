"""Tests for tango_note.core.models."""

from __future__ import annotations

from dataclasses import is_dataclass
from datetime import datetime, timezone

from tango_note.core.models import Card, CardStats, Deck, DeckMeta


def test_card_stats_defaults() -> None:
    s = CardStats()
    assert s.correct == 0
    assert s.wrong == 0
    assert s.last_reviewed is None


def test_card_defaults() -> None:
    c = Card(id="c1", term="bonjour", definition="こんにちは")
    assert c.notes == ""
    assert isinstance(c.stats, CardStats)
    assert c.stats.correct == 0
    assert c.stats.wrong == 0
    assert c.stats.last_reviewed is None


def test_card_default_stats_not_shared_between_instances() -> None:
    """Default ``stats`` must be a fresh instance per Card."""
    c1 = Card(id="c1", term="a", definition="α")
    c2 = Card(id="c2", term="b", definition="β")
    c1.stats.correct = 5
    assert c2.stats.correct == 0
    assert c1.stats is not c2.stats


def test_dataclasses_are_mutable() -> None:
    """All core dataclasses are intentionally not frozen."""
    for cls in (Card, CardStats, Deck, DeckMeta):
        assert is_dataclass(cls)

    c = Card(id="c1", term="a", definition="b")
    c.notes = "updated"
    c.term = "renamed"
    assert c.notes == "updated"
    assert c.term == "renamed"

    s = CardStats()
    s.correct = 9
    assert s.correct == 9


def test_deck_construction_and_appending() -> None:
    meta = DeckMeta(
        id="d1",
        name="French Basics",
        source_lang="fr",
        target_lang="ja",
        created_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc),
    )
    deck = Deck(meta=meta)
    assert deck.cards == []

    deck.cards.append(Card(id="c1", term="bonjour", definition="こんにちは"))
    assert len(deck.cards) == 1
    assert deck.cards[0].term == "bonjour"


def test_deck_meta_holds_iso_lang_codes_as_strings() -> None:
    """Language codes are not enforced beyond being strings at the model level."""
    meta = DeckMeta(
        id="d1",
        name="多言語",
        source_lang="zh",
        target_lang="ja",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert meta.source_lang == "zh"
    assert meta.target_lang == "ja"
