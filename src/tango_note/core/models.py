"""Core data models for tango-note.

All dataclasses here are mutable (``frozen=False``). Datetimes are held as
``datetime`` instances; conversion to/from ISO 8601 strings happens in
``tango_note.core.storage``, never in the models themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CardStats:
    """Per-card review statistics.

    Attributes:
        correct: Number of times the card has been answered correctly.
        wrong: Number of times the card has been answered incorrectly.
        last_reviewed: Timestamp of the most recent review, or ``None`` if
            the card has never been reviewed.
    """

    correct: int = 0
    wrong: int = 0
    last_reviewed: Optional[datetime] = None


@dataclass
class Card:
    """A single flashcard entry within a deck.

    Attributes:
        id: Stable identifier (unique within the deck).
        term: The prompt side of the card (e.g., "bonjour").
        definition: The answer side of the card (e.g., "こんにちは").
        notes: Optional free-form annotation shown alongside the card.
        stats: Review statistics — see the per-field invariant below.
    """

    id: str
    term: str
    definition: str
    notes: str = ""
    stats: CardStats = field(default_factory=CardStats)
    """Review statistics for this card.

    INVARIANT: ``stats`` must be mutated **only** through helpers in
    ``tango_note.core.stats`` (e.g. ``record_correct``, ``record_wrong``).
    Callers in ``cli/``, ``gui/``, and ``storage`` MUST NOT write to
    ``stats.correct``, ``stats.wrong``, or ``stats.last_reviewed``
    directly. This keeps review bookkeeping (counter increments,
    timestamp updates) in a single, testable code path.
    """


@dataclass
class DeckMeta:
    """Deck-level metadata.

    Attributes:
        id: Stable identifier for the deck (typically a UUID).
        name: Human-readable deck name.
        source_lang: ISO 639-1 code of the term language (e.g. ``"fr"``).
        target_lang: ISO 639-1 code of the definition language
            (e.g. ``"ja"``).
        created_at: Creation timestamp.
    """

    id: str
    name: str
    source_lang: str
    target_lang: str
    created_at: datetime


@dataclass
class Deck:
    """A deck of flashcards.

    One deck corresponds to one JSON file on disk. Persistence is handled
    by ``tango_note.core.storage``.

    Attributes:
        meta: Deck-level metadata.
        cards: The list of cards in this deck. May be empty.
    """

    meta: DeckMeta
    cards: list[Card] = field(default_factory=list)
