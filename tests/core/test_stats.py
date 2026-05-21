"""Tests for tango_note.core.stats."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tango_note.core.models import Card, CardStats, Deck, DeckMeta
from tango_note.core.stats import (
    DeckSummary,
    accuracy,
    deck_summary,
    record_correct,
    record_wrong,
)


def _make_card(
    cid: str = "c1",
    *,
    correct: int = 0,
    wrong: int = 0,
    last: datetime | None = None,
) -> Card:
    return Card(
        id=cid,
        term="t",
        definition="d",
        stats=CardStats(correct=correct, wrong=wrong, last_reviewed=last),
    )


def _make_deck(*cards: Card) -> Deck:
    deck = Deck(
        meta=DeckMeta(
            id="d",
            name="n",
            source_lang="fr",
            target_lang="ja",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    deck.cards = list(cards)
    return deck


# ----- record_correct / record_wrong -----------------------------------------


def test_record_correct_increments_and_stamps() -> None:
    c = _make_card()
    now = datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc)
    record_correct(c, now=now)
    assert c.stats.correct == 1
    assert c.stats.wrong == 0
    assert c.stats.last_reviewed == now


def test_record_wrong_increments_and_stamps() -> None:
    c = _make_card()
    now = datetime(2026, 5, 12, 11, 0, 0, tzinfo=timezone.utc)
    record_wrong(c, now=now)
    assert c.stats.correct == 0
    assert c.stats.wrong == 1
    assert c.stats.last_reviewed == now


def test_record_correct_default_now_is_utc_aware() -> None:
    """When ``now`` is omitted, the stamp must be a tz-aware UTC datetime."""
    c = _make_card()
    record_correct(c)
    assert c.stats.last_reviewed is not None
    assert c.stats.last_reviewed.tzinfo is not None
    assert c.stats.last_reviewed.utcoffset().total_seconds() == 0


def test_record_wrong_default_now_is_utc_aware() -> None:
    c = _make_card()
    record_wrong(c)
    assert c.stats.last_reviewed is not None
    assert c.stats.last_reviewed.tzinfo is not None
    assert c.stats.last_reviewed.utcoffset().total_seconds() == 0


def test_record_multiple_keeps_latest_timestamp() -> None:
    c = _make_card()
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    t3 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    record_correct(c, now=t1)
    record_correct(c, now=t2)
    record_wrong(c, now=t3)
    assert c.stats.correct == 2
    assert c.stats.wrong == 1
    assert c.stats.last_reviewed == t3


def test_record_does_not_touch_other_card_fields() -> None:
    c = _make_card()
    c.term = "term-before"
    c.definition = "def-before"
    c.notes = "notes-before"
    record_correct(c, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert c.term == "term-before"
    assert c.definition == "def-before"
    assert c.notes == "notes-before"


# ----- accuracy --------------------------------------------------------------


def test_accuracy_none_when_no_attempts() -> None:
    assert accuracy(_make_card()) is None


def test_accuracy_all_correct() -> None:
    assert accuracy(_make_card(correct=4, wrong=0)) == pytest.approx(1.0)


def test_accuracy_all_wrong() -> None:
    """Zero accuracy is distinct from 'never attempted' (None)."""
    result = accuracy(_make_card(correct=0, wrong=5))
    assert result == 0.0
    assert result is not None


def test_accuracy_mixed() -> None:
    assert accuracy(_make_card(correct=3, wrong=1)) == pytest.approx(0.75)


# ----- deck_summary ----------------------------------------------------------


def test_deck_summary_empty_deck() -> None:
    s = deck_summary(_make_deck())
    assert isinstance(s, DeckSummary)
    assert s.total_cards == 0
    assert s.reviewed_cards == 0
    assert s.total_correct == 0
    assert s.total_wrong == 0
    assert s.accuracy is None


def test_deck_summary_all_unreviewed_cards() -> None:
    deck = _make_deck(_make_card("c1"), _make_card("c2"))
    s = deck_summary(deck)
    assert s.total_cards == 2
    assert s.reviewed_cards == 0
    assert s.accuracy is None


def test_deck_summary_mixed_review_states() -> None:
    deck = _make_deck(
        _make_card("c1", correct=3, wrong=1),
        _make_card("c2", correct=0, wrong=2),
        _make_card("c3"),  # never reviewed
    )
    s = deck_summary(deck)
    assert s.total_cards == 3
    assert s.reviewed_cards == 2
    assert s.total_correct == 3
    assert s.total_wrong == 3
    assert s.accuracy == pytest.approx(0.5)
