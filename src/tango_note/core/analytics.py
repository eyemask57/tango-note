"""Review-frequency analytics for decks.

Kept separate from ``core.stats`` on purpose: ``stats`` owns per-card
*correctness* bookkeeping (the only place allowed to mutate ``Card.stats``
— see the ``Card.stats`` invariant), whereas this module is read-only
*analysis* over review timing. Mixing the two would blur that boundary,
and the analysis side is expected to grow (histograms, streaks, …), so
it gets its own home.

All functions here are pure: no I/O, no display strings, no mutation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tango_note.core.models import Card, Deck

# Freshness bucket keys returned by ``count_by_review_freshness``.
FRESHNESS_NEVER = "never"
FRESHNESS_WITHIN_WEEK = "within_week"
FRESHNESS_WITHIN_MONTH = "within_month"
FRESHNESS_STALE = "stale"


def count_by_review_freshness(
    deck: Deck,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Bucket cards by how long ago they were last reviewed.

    Buckets (boundaries inclusive on the *recent* side):

    * ``never`` — never reviewed (``last_reviewed`` is ``None``).
    * ``within_week`` — reviewed within the last 7 days.
    * ``within_month`` — reviewed 7+ to 30 days ago.
    * ``stale`` — reviewed 30 or more days ago.

    Args:
        deck: The deck to analyze.
        now: Reference time; defaults to ``datetime.now(timezone.utc)``.

    Returns:
        A dict with all four keys present, summing to ``len(deck.cards)``.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    week_cutoff = now - timedelta(days=7)
    month_cutoff = now - timedelta(days=30)

    counts = {
        FRESHNESS_NEVER: 0,
        FRESHNESS_WITHIN_WEEK: 0,
        FRESHNESS_WITHIN_MONTH: 0,
        FRESHNESS_STALE: 0,
    }
    for card in deck.cards:
        last = card.stats.last_reviewed
        if last is None:
            counts[FRESHNESS_NEVER] += 1
        elif last >= week_cutoff:
            counts[FRESHNESS_WITHIN_WEEK] += 1
        elif last >= month_cutoff:
            counts[FRESHNESS_WITHIN_MONTH] += 1
        else:
            counts[FRESHNESS_STALE] += 1
    return counts


def list_stale_cards(
    deck: Deck,
    *,
    days_threshold: int = 30,
    include_never: bool = True,
    now: datetime | None = None,
) -> list[Card]:
    """List cards not reviewed for at least ``days_threshold`` days.

    A card qualifies when its ``last_reviewed`` is at or before
    ``now - days_threshold``. Never-reviewed cards qualify when
    ``include_never`` is True.

    Args:
        deck: The deck to analyze.
        days_threshold: Minimum age, in days, of the last review.
        include_never: Whether never-reviewed cards are included.
        now: Reference time; defaults to ``datetime.now(timezone.utc)``.

    Returns:
        Matching cards in their original deck order.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_threshold)
    result: list[Card] = []
    for card in deck.cards:
        last = card.stats.last_reviewed
        if last is None:
            if include_never:
                result.append(card)
        elif last <= cutoff:
            result.append(card)
    return result
