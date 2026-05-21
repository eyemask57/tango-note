"""Per-card and deck-level review statistics helpers.

This module is the **only** place that should mutate ``Card.stats``.
Callers in ``cli/``, ``gui/``, and elsewhere should go through these
functions rather than writing to ``card.stats.correct`` etc. directly
(see the invariant docstring on ``Card.stats``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from tango_note.core.models import Card, CardStats, Deck


def record_correct(card: Card, now: datetime | None = None) -> None:
    """Record a correct answer for ``card``.

    Increments ``card.stats.correct`` by one and updates
    ``card.stats.last_reviewed``.

    Args:
        card: The card that was just reviewed.
        now: Timestamp to stamp on the review. If ``None``, uses
            ``datetime.now(timezone.utc)``. Passing an explicit value is
            useful for deterministic tests.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    card.stats.correct += 1
    card.stats.last_reviewed = now


def record_wrong(card: Card, now: datetime | None = None) -> None:
    """Record a wrong answer for ``card``.

    Increments ``card.stats.wrong`` by one and updates
    ``card.stats.last_reviewed``.

    Args:
        card: The card that was just reviewed.
        now: Timestamp to stamp on the review. If ``None``, uses
            ``datetime.now(timezone.utc)``.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    card.stats.wrong += 1
    card.stats.last_reviewed = now


def reset_stats(card: Card) -> None:
    """Reset a card's review statistics to their initial, zeroed state.

    Replaces ``card.stats`` with a fresh ``CardStats`` (``correct=0``,
    ``wrong=0``, ``last_reviewed=None``).

    This lives in ``core.stats`` rather than the export caller because
    "what resetting stats means" is a statistics-domain concern, and the
    ``Card.stats`` invariant says ``stats`` must only be changed through
    ``core.stats`` helpers. Used by deck export when the caller wants to
    strip learning history before sharing.
    """
    card.stats = CardStats()


def accuracy(card: Card) -> Optional[float]:
    """Correct ratio for ``card``.

    Returns:
        ``card.stats.correct / (correct + wrong)`` in [0.0, 1.0], or
        ``None`` if the card has never been reviewed. Returning ``None``
        (rather than e.g. 0.0) lets the display layer distinguish
        "never attempted" from "all wrong".
    """
    total = card.stats.correct + card.stats.wrong
    if total == 0:
        return None
    return card.stats.correct / total


@dataclass
class DeckSummary:
    """Aggregate review statistics for a deck.

    Attributes:
        total_cards: Total number of cards in the deck.
        reviewed_cards: Number of cards with at least one recorded attempt.
        total_correct: Sum of correct counts across all cards.
        total_wrong: Sum of wrong counts across all cards.
        accuracy: Overall accuracy as a **micro-average** in [0.0, 1.0],
            or ``None`` if no card has been attempted. See
            :func:`deck_summary` for the precise definition.
    """

    total_cards: int
    reviewed_cards: int
    total_correct: int
    total_wrong: int
    accuracy: Optional[float]


def deck_summary(deck: Deck) -> DeckSummary:
    """Compute aggregate review statistics for an entire deck.

    The reported ``accuracy`` is a **micro-average** — it pools every
    attempt across every card and divides total correct by total
    attempts::

        accuracy = sum(card.stats.correct for card in deck.cards)
                 / sum(card.stats.correct + card.stats.wrong
                       for card in deck.cards)

    Consequences of this choice:

    - Cards reviewed many times have proportionally more influence on
      the headline number — a card with 100 attempts moves the score
      far more than a card with 5 attempts.
    - This is *not* a macro-average. A macro-average would compute
      ``accuracy(card)`` per card and then take the unweighted mean,
      treating every card as equally important regardless of attempt
      count. The two metrics can differ substantially on decks where
      attempt counts are uneven.

    Micro-average is chosen here because it answers the question users
    typically ask ("what fraction of all my answers were right?")
    rather than "what is my average accuracy per card?". Per-card
    accuracy is available via :func:`accuracy` for callers that need
    the macro view.

    Args:
        deck: The deck to summarize.

    Returns:
        A ``DeckSummary`` value object. Display formatting is left to
        the caller (``cli/`` or ``gui/``).
    """
    total_correct = sum(c.stats.correct for c in deck.cards)
    total_wrong = sum(c.stats.wrong for c in deck.cards)
    reviewed = sum(1 for c in deck.cards if c.stats.correct + c.stats.wrong > 0)
    total_attempts = total_correct + total_wrong
    overall = total_correct / total_attempts if total_attempts > 0 else None
    return DeckSummary(
        total_cards=len(deck.cards),
        reviewed_cards=reviewed,
        total_correct=total_correct,
        total_wrong=total_wrong,
        accuracy=overall,
    )
