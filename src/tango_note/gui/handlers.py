"""GUI handler layer.

Thin wrappers that screens call to drive ``core`` and ``storage``. Each
function accepts only plain values (paths, strings, ``Deck``/``Card``
objects) and never touches Tkinter widgets — that is the screens'
job. Exceptions from ``core`` propagate untouched so screens can decide
how to render them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tango_note.core import analytics as _analytics
from tango_note.core import config as _config
from tango_note.core import quiz as _quiz
from tango_note.core import search as _search
from tango_note.core import stats as _stats
from tango_note.core import storage as _storage
from tango_note.core.exceptions import (
    CardNotFoundError,
    DeckNotFoundError,
    InvalidDeckSchemaError,
)
from tango_note.core.models import Card, Deck, DeckMeta


@dataclass
class DeckEntry:
    """Lightweight summary of a deck for the deck-list screen.

    Attributes:
        path: Filesystem path of the deck JSON file.
        name: ``DeckMeta.name`` if the deck loads cleanly, else the file
            stem as a fallback so unloadable decks still appear.
        is_current: ``True`` if this is the deck currently marked as
            active in the user config.
        card_count: Number of cards in the deck, or ``0`` when the deck
            file could not be loaded.
    """

    path: Path
    name: str
    is_current: bool
    card_count: int


def list_known_decks() -> list[DeckEntry]:
    """Enumerate decks in ``<home>/decks/`` plus the current deck.

    Decks whose JSON cannot be parsed are still listed (with their
    file stem as the name) so the user can re-open and inspect them.
    """
    entries: list[DeckEntry] = []
    seen: set[Path] = set()

    cfg = _config.load_config()
    current = Path(cfg.current_deck) if cfg.current_deck else None

    dd = _config.decks_dir()
    if dd.is_dir():
        for p in sorted(dd.glob("*.json")):
            entries.append(_make_entry(p, current))
            seen.add(p)

    if current is not None and current not in seen and current.exists():
        entries.append(_make_entry(current, current))

    return entries


def _make_entry(path: Path, current: Optional[Path]) -> DeckEntry:
    try:
        deck = _storage.load_deck(path)
        name = deck.meta.name
        card_count = len(deck.cards)
    except (InvalidDeckSchemaError, DeckNotFoundError):
        name = path.stem
        card_count = 0
    return DeckEntry(
        path=path,
        name=name,
        is_current=(path == current),
        card_count=card_count,
    )


def load_deck(path: Path) -> Deck:
    """Load a deck from disk (passthrough to ``storage.load_deck``)."""
    return _storage.load_deck(path)


def save_deck(deck: Deck, path: Path) -> None:
    """Persist a deck atomically (passthrough to ``storage.save_deck``)."""
    _storage.save_deck(deck, path)


def create_deck(
    name: str,
    source_lang: str = "en",
    target_lang: str = "ja",
    path: Optional[Path] = None,
) -> tuple[Deck, Path]:
    """Create and persist a new deck; mark it as the current deck.

    Args:
        name: User-facing deck name.
        source_lang: ISO 639-1 code for the term language.
        target_lang: ISO 639-1 code for the definition language.
        path: Custom destination path. Default:
            ``<home>/decks/<uuid>.json``.

    Returns:
        ``(deck, path)`` for the newly created deck.
    """
    deck_id = str(uuid.uuid4())
    target_path = path if path is not None else _config.decks_dir() / f"{deck_id}.json"
    deck = Deck(
        meta=DeckMeta(
            id=deck_id,
            name=name,
            source_lang=source_lang,
            target_lang=target_lang,
            created_at=datetime.now(timezone.utc),
        )
    )
    _storage.save_deck(deck, target_path)
    set_current_deck(target_path)
    return deck, target_path


def add_card_to_deck(
    deck: Deck,
    term: str,
    definition: str,
    notes: str = "",
) -> Card:
    """Append a new card to an in-memory deck and return it."""
    card = Card(
        id=str(uuid.uuid4()),
        term=term,
        definition=definition,
        notes=notes,
    )
    deck.cards.append(card)
    return card


def delete_card_from_deck(deck: Deck, card_id: str) -> None:
    """Remove a card from an in-memory deck. No-op if the id is unknown."""
    deck.cards = [c for c in deck.cards if c.id != card_id]


def update_card_in_deck(
    deck: Deck,
    card_id: str,
    term: str,
    definition: str,
    notes: str,
) -> Card:
    """Mutate fields of an existing card in an in-memory deck.

    Raises:
        CardNotFoundError: If ``card_id`` is not present in the deck.
    """
    for c in deck.cards:
        if c.id == card_id:
            c.term = term
            c.definition = definition
            c.notes = notes
            return c
    raise CardNotFoundError(card_id)


def import_deck(source_path: Path, force: bool = False) -> Path:
    """Copy a deck file into ``<home>/decks/<deck-id>.json``.

    Args:
        source_path: Path to the source deck file.
        force: Overwrite an existing destination file when ``True``.

    Returns:
        The destination path on success.

    Raises:
        FileExistsError: If a destination file already exists and
            ``force`` is False.
        DeckNotFoundError / InvalidDeckSchemaError: From ``storage``.
    """
    deck = _storage.load_deck(source_path)
    dest = _config.decks_dir() / f"{deck.meta.id}.json"
    if dest.exists() and not force:
        raise FileExistsError(str(dest))
    _storage.save_deck(deck, dest)
    return dest


def export_deck(deck: Deck, destination: Path) -> None:
    """Save the in-memory deck to ``destination``."""
    _storage.save_deck(deck, destination)


def export_deck_to_path(
    source_path: Path,
    dest_path: Path,
    strip_stats: bool = False,
) -> None:
    """Export a deck file to ``dest_path``, optionally stripping stats.

    Thin delegate to ``core.storage.export_deck``. The load-transform-
    save logic lives in core so the CLI ``export`` command and this GUI
    handler do not duplicate it; see ``core.storage.export_deck`` for
    full behavior and the exceptions it may raise.

    Args:
        source_path: Path of the deck to export.
        dest_path: Destination file path.
        strip_stats: Reset every card's stats in the export when True.
    """
    _storage.export_deck(source_path, dest_path, strip_stats=strip_stats)


def delete_deck(path: Path) -> None:
    """Permanently delete a deck file (passthrough to ``storage.delete_deck``).

    Propagates ``DeckNotFoundError`` / ``StorageError`` from ``storage``
    so the calling screen can render the failure.
    """
    _storage.delete_deck(path)


def set_current_deck(path: Path) -> None:
    """Set ``current_deck`` in the user config."""
    cfg = _config.load_config()
    cfg.current_deck = str(path)
    _config.save_config(cfg)


def get_current_deck() -> Optional[Path]:
    """Return the current deck path, or ``None``."""
    cfg = _config.load_config()
    return Path(cfg.current_deck) if cfg.current_deck else None


def set_quiz_mode(mode: str) -> None:
    """Persist the default ``quiz_mode`` in the user config."""
    cfg = _config.load_config()
    cfg.quiz_mode = mode
    _config.save_config(cfg)


def pick_next_card(deck: Deck) -> Card:
    """Pick the next quiz card (passthrough to ``quiz.pick_next``)."""
    return _quiz.pick_next(deck)


def pick_next_card_by_mode(
    deck: Deck, mode: str, config: _config.AppConfig
) -> Card:
    """Pick the next quiz card according to ``mode``.

    Dispatches to the right ``core.quiz`` picker, drawing the weak /
    unreviewed thresholds from ``config``.

    Takes the in-memory ``Deck`` (not a path) on purpose: the quiz tab
    grades and auto-saves the very object it picks from, so picking from
    a freshly reloaded copy would drop grades. Raises ``EmptyDeckError``
    when no card is eligible for the chosen mode.
    """
    if mode == _config.QUIZ_MODE_WEAK:
        return _quiz.pick_next_weak(
            deck, threshold_accuracy=config.weak_threshold
        )
    if mode == _config.QUIZ_MODE_UNREVIEWED:
        return _quiz.pick_next_unreviewed(
            deck, days_threshold=config.unreviewed_days
        )
    return _quiz.pick_next(deck)


def count_freshness_in_deck(deck: Deck) -> dict[str, int]:
    """Bucket the deck's cards by last-review age (passthrough to analytics).

    Operates on the in-memory ``Deck`` so the breakdown reflects any
    unsaved edits the stats tab is showing.
    """
    return _analytics.count_by_review_freshness(deck)


def list_stale_cards_in_deck(deck: Deck, days_threshold: int) -> list[Card]:
    """List cards not reviewed for ``days_threshold`` days (analytics)."""
    return _analytics.list_stale_cards(deck, days_threshold=days_threshold)


def record_correct(card: Card, now: Optional[datetime] = None) -> None:
    """Record a correct answer (passthrough to ``stats.record_correct``)."""
    _stats.record_correct(card, now=now)


def record_wrong(card: Card, now: Optional[datetime] = None) -> None:
    """Record a wrong answer (passthrough to ``stats.record_wrong``)."""
    _stats.record_wrong(card, now=now)


def deck_summary(deck: Deck) -> _stats.DeckSummary:
    """Compute aggregate deck statistics."""
    return _stats.deck_summary(deck)


def card_accuracy(card: Card) -> Optional[float]:
    """Per-card accuracy in [0, 1], or ``None`` if never reviewed."""
    return _stats.accuracy(card)


def search_cards_in_deck(
    deck_path: Path,
    query: str,
    fields: Optional[list[str]] = None,
    case_sensitive: bool = False,
) -> list[Card]:
    """Load the deck at ``deck_path`` and return cards matching ``query``.

    This loads from disk; callers that already hold an in-memory
    ``Deck`` (and may have unsaved edits) should call
    ``tango_note.core.search.search_cards`` directly instead.
    """
    deck = _storage.load_deck(deck_path)
    return _search.search_cards(
        deck, query, fields=fields, case_sensitive=case_sensitive
    )


def find_duplicates_in_deck(
    deck_path: Path,
    case_sensitive: bool = False,
) -> list[list[Card]]:
    """Load the deck at ``deck_path`` and return its duplicate-term groups.

    Loads from disk; see :func:`search_cards_in_deck` for the in-memory
    caveat.
    """
    deck = _storage.load_deck(deck_path)
    return _search.find_duplicates(deck, case_sensitive=case_sensitive)
