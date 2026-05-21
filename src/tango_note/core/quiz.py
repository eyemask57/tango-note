"""Quiz selection logic.

Picks the next card to present to the user. Three strategies:

* :func:`pick_next` — uniformly random.
* :func:`pick_next_weak` — cards with a low correct ratio.
* :func:`pick_next_unreviewed` — cards not reviewed for a while.

All three raise :class:`EmptyDeckError` when no eligible card exists, so
display layers can surface a mode-appropriate message.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from tango_note.core.exceptions import EmptyDeckError
from tango_note.core.models import Card, Deck
from tango_note.core.stats import accuracy


def pick_next(deck: Deck, rng: random.Random | None = None) -> Card:
    """Pick the next card to quiz on, uniformly at random.

    Args:
        deck: The deck to pick from.
        rng: Optional ``random.Random`` instance. When ``None``, uses
            the module-level ``random`` PRNG. Tests should pass a seeded
            ``random.Random(seed)`` for reproducibility.

    Returns:
        A ``Card`` drawn uniformly at random from ``deck.cards``.

    Raises:
        EmptyDeckError: If the deck has no cards. Display layers should
            catch this and surface a translated "deck is empty" message.
    """
    if not deck.cards:
        raise EmptyDeckError("Deck contains no cards.")
    return _choose(deck.cards, rng)


def _choose(cards: list[Card], rng: random.Random | None) -> Card:
    """Pick one card uniformly at random from a non-empty list."""
    if rng is None:
        return random.choice(cards)
    return rng.choice(cards)


def pick_next_weak(
    deck: Deck,
    *,
    threshold_accuracy: float = 0.7,
    min_attempts: int = 1,
    rng: random.Random | None = None,
) -> Card:
    """Pick a card the learner is weak on, at random among eligible ones.

    A card is eligible when it has been attempted at least
    ``min_attempts`` times and its accuracy is strictly below
    ``threshold_accuracy``. Never-attempted cards are excluded (their
    accuracy is undefined).

    Args:
        deck: The deck to pick from.
        threshold_accuracy: Accuracy cutoff in [0.0, 1.0]; a card
            qualifies when ``accuracy(card) < threshold_accuracy``.
        min_attempts: Minimum ``correct + wrong`` for a card to count.
        rng: Optional seeded ``random.Random`` for reproducibility.

    Returns:
        A randomly chosen eligible (weak) card.

    Raises:
        EmptyDeckError: If no card is eligible.
    """
    eligible: list[Card] = []
    for card in deck.cards:
        attempts = card.stats.correct + card.stats.wrong
        if attempts < min_attempts:
            continue
        acc = accuracy(card)
        if acc is not None and acc < threshold_accuracy:
            eligible.append(card)
    if not eligible:
        raise EmptyDeckError("No weak cards match the criteria.")
    return _choose(eligible, rng)


def pick_next_unreviewed(
    deck: Deck,
    *,
    days_threshold: int = 30,
    include_never: bool = True,
    rng: random.Random | None = None,
    now: datetime | None = None,
) -> Card:
    """Pick a card not reviewed for a while, at random among eligible ones.

    A card is eligible when its ``last_reviewed`` is at or before
    ``now - days_threshold``. Never-reviewed cards (``last_reviewed`` is
    ``None``) are eligible when ``include_never`` is True.

    Args:
        deck: The deck to pick from.
        days_threshold: Minimum age, in days, of the last review.
        include_never: Whether never-reviewed cards count as eligible.
        rng: Optional seeded ``random.Random`` for reproducibility.
        now: Reference time; defaults to ``datetime.now(timezone.utc)``.

    Returns:
        A randomly chosen eligible (long-unreviewed) card.

    Raises:
        EmptyDeckError: If no card is eligible.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_threshold)
    eligible: list[Card] = []
    for card in deck.cards:
        last = card.stats.last_reviewed
        if last is None:
            if include_never:
                eligible.append(card)
        elif last <= cutoff:
            eligible.append(card)
    if not eligible:
        raise EmptyDeckError("No long-unreviewed cards match the criteria.")
    return _choose(eligible, rng)
