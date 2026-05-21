"""Tests for tango_note.core.analytics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tango_note.core.analytics import (
    FRESHNESS_NEVER,
    FRESHNESS_STALE,
    FRESHNESS_WITHIN_MONTH,
    FRESHNESS_WITHIN_WEEK,
    count_by_review_freshness,
    list_stale_cards,
)
from tango_note.core.models import Card, CardStats, Deck, DeckMeta

_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _card(cid: str, last: datetime | None) -> Card:
    return Card(
        id=cid,
        term=cid,
        definition=cid,
        stats=CardStats(last_reviewed=last),
    )


def _deck(*cards: Card) -> Deck:
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


# ===== count_by_review_freshness ============================================


def test_count_freshness_classifies_each_bucket() -> None:
    deck = _deck(
        _card("never", None),
        _card("recent", _NOW - timedelta(days=2)),
        _card("midold", _NOW - timedelta(days=15)),
        _card("stale", _NOW - timedelta(days=90)),
    )
    counts = count_by_review_freshness(deck, now=_NOW)
    assert counts == {
        FRESHNESS_NEVER: 1,
        FRESHNESS_WITHIN_WEEK: 1,
        FRESHNESS_WITHIN_MONTH: 1,
        FRESHNESS_STALE: 1,
    }


def test_count_freshness_boundary_exactly_seven_days() -> None:
    """Exactly 7 days ago counts as 'within a week' (inclusive)."""
    deck = _deck(_card("edge", _NOW - timedelta(days=7)))
    counts = count_by_review_freshness(deck, now=_NOW)
    assert counts[FRESHNESS_WITHIN_WEEK] == 1
    assert counts[FRESHNESS_WITHIN_MONTH] == 0


def test_count_freshness_boundary_exactly_thirty_days() -> None:
    """Exactly 30 days ago counts as 'within a month' (inclusive)."""
    deck = _deck(_card("edge", _NOW - timedelta(days=30)))
    counts = count_by_review_freshness(deck, now=_NOW)
    assert counts[FRESHNESS_WITHIN_MONTH] == 1
    assert counts[FRESHNESS_STALE] == 0


def test_count_freshness_just_over_thirty_is_stale() -> None:
    deck = _deck(_card("edge", _NOW - timedelta(days=31)))
    counts = count_by_review_freshness(deck, now=_NOW)
    assert counts[FRESHNESS_STALE] == 1


def test_count_freshness_empty_deck_all_zero() -> None:
    counts = count_by_review_freshness(_deck(), now=_NOW)
    assert counts == {
        FRESHNESS_NEVER: 0,
        FRESHNESS_WITHIN_WEEK: 0,
        FRESHNESS_WITHIN_MONTH: 0,
        FRESHNESS_STALE: 0,
    }


def test_count_freshness_sums_to_card_count() -> None:
    deck = _deck(
        _card("a", None),
        _card("b", _NOW - timedelta(days=1)),
        _card("c", _NOW - timedelta(days=100)),
    )
    counts = count_by_review_freshness(deck, now=_NOW)
    assert sum(counts.values()) == len(deck.cards)


# ===== list_stale_cards =====================================================


def test_list_stale_returns_cards_past_threshold() -> None:
    deck = _deck(
        _card("recent", _NOW - timedelta(days=5)),
        _card("old", _NOW - timedelta(days=45)),
    )
    stale = list_stale_cards(deck, days_threshold=30, now=_NOW)
    assert [c.id for c in stale] == ["old"]


def test_list_stale_include_never_true() -> None:
    deck = _deck(_card("never", None), _card("recent", _NOW))
    stale = list_stale_cards(
        deck, days_threshold=30, include_never=True, now=_NOW
    )
    assert [c.id for c in stale] == ["never"]


def test_list_stale_include_never_false() -> None:
    deck = _deck(_card("never", None))
    stale = list_stale_cards(
        deck, days_threshold=30, include_never=False, now=_NOW
    )
    assert stale == []


def test_list_stale_preserves_deck_order() -> None:
    deck = _deck(
        _card("c1", _NOW - timedelta(days=100)),
        _card("c2", _NOW - timedelta(days=5)),    # excluded
        _card("c3", None),
        _card("c4", _NOW - timedelta(days=40)),
    )
    stale = list_stale_cards(deck, days_threshold=30, now=_NOW)
    assert [c.id for c in stale] == ["c1", "c3", "c4"]


def test_list_stale_boundary_exactly_threshold() -> None:
    deck = _deck(_card("edge", _NOW - timedelta(days=30)))
    stale = list_stale_cards(deck, days_threshold=30, now=_NOW)
    assert [c.id for c in stale] == ["edge"]


def test_list_stale_empty_deck() -> None:
    assert list_stale_cards(_deck(), days_threshold=30, now=_NOW) == []
