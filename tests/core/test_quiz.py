"""Tests for tango_note.core.quiz."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from tango_note.core.exceptions import EmptyDeckError
from tango_note.core.models import Card, CardStats, Deck, DeckMeta
from tango_note.core.quiz import pick_next, pick_next_unreviewed, pick_next_weak


@pytest.fixture
def empty_deck() -> Deck:
    return Deck(
        meta=DeckMeta(
            id="d",
            name="n",
            source_lang="fr",
            target_lang="ja",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )


@pytest.fixture
def filled_deck(empty_deck: Deck) -> Deck:
    empty_deck.cards = [
        Card(id=f"c{i}", term=f"t{i}", definition=f"d{i}") for i in range(5)
    ]
    return empty_deck


def test_pick_next_empty_deck_raises(empty_deck: Deck) -> None:
    with pytest.raises(EmptyDeckError):
        pick_next(empty_deck)


def test_pick_next_empty_deck_raises_even_with_rng(empty_deck: Deck) -> None:
    with pytest.raises(EmptyDeckError):
        pick_next(empty_deck, rng=random.Random(0))


def test_pick_next_returns_card_from_deck(filled_deck: Deck) -> None:
    picked = pick_next(filled_deck, rng=random.Random(0))
    assert picked in filled_deck.cards


def test_pick_next_reproducible_with_same_seed(filled_deck: Deck) -> None:
    """Two RNGs seeded identically must yield the same sequence."""
    rng1 = random.Random(42)
    rng2 = random.Random(42)
    picks1 = [pick_next(filled_deck, rng=rng1).id for _ in range(10)]
    picks2 = [pick_next(filled_deck, rng=rng2).id for _ in range(10)]
    assert picks1 == picks2


def test_pick_next_distinct_seeds_diverge(filled_deck: Deck) -> None:
    """Different seeds produce different sequences (sanity check)."""
    picks_a = [pick_next(filled_deck, rng=random.Random(1)).id for _ in range(20)]
    picks_b = [pick_next(filled_deck, rng=random.Random(2)).id for _ in range(20)]
    assert picks_a != picks_b


def test_pick_next_covers_all_cards_over_many_picks(filled_deck: Deck) -> None:
    """Over 100 uniform draws from 5 cards, every card should appear."""
    rng = random.Random(0)
    ids = {pick_next(filled_deck, rng=rng).id for _ in range(100)}
    assert ids == {f"c{i}" for i in range(5)}


def test_pick_next_without_rng_uses_module_random(filled_deck: Deck) -> None:
    """When rng is None, the call should still succeed and return a deck card."""
    picked = pick_next(filled_deck)
    assert picked in filled_deck.cards


def test_pick_next_does_not_mutate_deck(filled_deck: Deck) -> None:
    """pick_next is a pure read — no side effects on the deck."""
    before_ids = [c.id for c in filled_deck.cards]
    pick_next(filled_deck, rng=random.Random(7))
    after_ids = [c.id for c in filled_deck.cards]
    assert before_ids == after_ids
    assert len(filled_deck.cards) == 5


# ===== pick_next_weak =======================================================


def _card(
    cid: str,
    *,
    correct: int = 0,
    wrong: int = 0,
    last: datetime | None = None,
) -> Card:
    return Card(
        id=cid,
        term=cid,
        definition=cid,
        stats=CardStats(correct=correct, wrong=wrong, last_reviewed=last),
    )


def _deck_of(*cards: Card) -> Deck:
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


def test_pick_next_weak_selects_only_low_accuracy() -> None:
    deck = _deck_of(
        _card("strong", correct=9, wrong=1),   # 0.9 — not weak
        _card("weak", correct=2, wrong=8),     # 0.2 — weak
    )
    picked = pick_next_weak(deck, threshold_accuracy=0.7, rng=random.Random(0))
    assert picked.id == "weak"


def test_pick_next_weak_excludes_below_min_attempts() -> None:
    """Cards with fewer than min_attempts attempts are not eligible."""
    deck = _deck_of(
        _card("untried"),                       # 0 attempts
        _card("once_wrong", correct=0, wrong=1),  # 1 attempt, 0.0
    )
    picked = pick_next_weak(deck, min_attempts=1, rng=random.Random(0))
    assert picked.id == "once_wrong"


def test_pick_next_weak_unattempted_never_eligible() -> None:
    """A deck of only never-attempted cards yields no weak card."""
    deck = _deck_of(_card("a"), _card("b"))
    with pytest.raises(EmptyDeckError):
        pick_next_weak(deck)


def test_pick_next_weak_reproducible_with_seed() -> None:
    deck = _deck_of(
        _card("w1", correct=1, wrong=9),
        _card("w2", correct=2, wrong=8),
        _card("w3", correct=0, wrong=5),
    )
    a = [pick_next_weak(deck, rng=random.Random(5)).id for _ in range(8)]
    b = [pick_next_weak(deck, rng=random.Random(5)).id for _ in range(8)]
    assert a == b


def test_pick_next_weak_no_eligible_raises() -> None:
    deck = _deck_of(_card("strong", correct=10, wrong=0))
    with pytest.raises(EmptyDeckError):
        pick_next_weak(deck, threshold_accuracy=0.7)


def test_pick_next_weak_threshold_one_includes_all_attempted() -> None:
    """threshold=1.0 makes every attempted card weak (accuracy < 1.0...)."""
    deck = _deck_of(
        _card("perfect", correct=5, wrong=0),   # accuracy 1.0 — NOT < 1.0
        _card("good", correct=9, wrong=1),       # 0.9 — < 1.0
        _card("untried"),                        # excluded (0 attempts)
    )
    ids = {pick_next_weak(deck, threshold_accuracy=1.0, rng=random.Random(i)).id
           for i in range(30)}
    assert ids == {"good"}  # perfect (==1.0) and untried excluded


def test_pick_next_weak_threshold_zero_excludes_everyone() -> None:
    deck = _deck_of(_card("any", correct=0, wrong=5))  # accuracy 0.0
    with pytest.raises(EmptyDeckError):
        pick_next_weak(deck, threshold_accuracy=0.0)


# ===== pick_next_unreviewed =================================================

_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_pick_next_unreviewed_selects_old_cards() -> None:
    deck = _deck_of(
        _card("fresh", last=_NOW - timedelta(days=2)),
        _card("stale", last=_NOW - timedelta(days=60)),
    )
    picked = pick_next_unreviewed(
        deck, days_threshold=30, now=_NOW, rng=random.Random(0)
    )
    assert picked.id == "stale"


def test_pick_next_unreviewed_include_never_true() -> None:
    deck = _deck_of(_card("never"))
    picked = pick_next_unreviewed(
        deck, days_threshold=30, include_never=True, now=_NOW
    )
    assert picked.id == "never"


def test_pick_next_unreviewed_include_never_false() -> None:
    deck = _deck_of(_card("never"))
    with pytest.raises(EmptyDeckError):
        pick_next_unreviewed(
            deck, days_threshold=30, include_never=False, now=_NOW
        )


def test_pick_next_unreviewed_boundary_exactly_threshold() -> None:
    """A card last reviewed exactly days_threshold ago is eligible."""
    deck = _deck_of(_card("edge", last=_NOW - timedelta(days=30)))
    picked = pick_next_unreviewed(deck, days_threshold=30, now=_NOW)
    assert picked.id == "edge"


def test_pick_next_unreviewed_no_eligible_raises() -> None:
    deck = _deck_of(
        _card("recent", last=_NOW - timedelta(days=1)),
    )
    with pytest.raises(EmptyDeckError):
        pick_next_unreviewed(
            deck, days_threshold=30, include_never=False, now=_NOW
        )


def test_pick_next_unreviewed_reproducible_with_seed() -> None:
    deck = _deck_of(
        _card("s1", last=_NOW - timedelta(days=40)),
        _card("s2", last=_NOW - timedelta(days=50)),
        _card("s3"),
    )
    a = [pick_next_unreviewed(deck, now=_NOW, rng=random.Random(3)).id
         for _ in range(8)]
    b = [pick_next_unreviewed(deck, now=_NOW, rng=random.Random(3)).id
         for _ in range(8)]
    assert a == b
