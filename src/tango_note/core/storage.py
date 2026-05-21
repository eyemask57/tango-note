"""JSON persistence for decks.

Handles:

- atomic file save (write-temp-then-rename),
- UTF-8 output with non-ASCII preserved verbatim (``ensure_ascii=False``),
- ISO 8601 ↔ ``datetime`` conversion at the storage boundary,
- schema-version validation (see ``deck_from_dict``),
- file-to-file export (see ``export_deck``).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tango_note.core.exceptions import (
    DeckNotFoundError,
    InvalidDeckSchemaError,
    StorageError,
)
from tango_note.core.models import Card, CardStats, Deck, DeckMeta
from tango_note.core.stats import reset_stats

logger = logging.getLogger(__name__)

SUPPORTED_VERSION = "1.0"


def _to_iso(dt: datetime | None) -> str | None:
    """Convert a ``datetime`` to a UTC ISO 8601 string (``Z`` suffix).

    Naive datetimes are assumed to be UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _from_iso(s: str | None) -> datetime | None:
    """Parse a ``Z``-suffixed (or offset-suffixed) ISO 8601 string."""
    if s is None:
        return None
    text = s[:-1] + "+00:00" if s.endswith("Z") else s
    return datetime.fromisoformat(text)


def deck_to_dict(deck: Deck) -> dict[str, Any]:
    """Serialize a ``Deck`` to a JSON-ready dict.

    Args:
        deck: The deck to serialize.

    Returns:
        A plain dict matching the on-disk schema, with the current
        ``SUPPORTED_VERSION``.
    """
    return {
        "version": SUPPORTED_VERSION,
        "deck": {
            "id": deck.meta.id,
            "name": deck.meta.name,
            "source_lang": deck.meta.source_lang,
            "target_lang": deck.meta.target_lang,
            "created_at": _to_iso(deck.meta.created_at),
        },
        "cards": [
            {
                "id": c.id,
                "term": c.term,
                "definition": c.definition,
                "notes": c.notes,
                "stats": {
                    "correct": c.stats.correct,
                    "wrong": c.stats.wrong,
                    "last_reviewed": _to_iso(c.stats.last_reviewed),
                },
            }
            for c in deck.cards
        ],
    }


def _validate_version(version: Any) -> None:
    """Apply the schema-version rule.

    - Missing or non-string ``version`` → ``InvalidDeckSchemaError``.
    - Major version mismatch → ``InvalidDeckSchemaError``.
    - Minor version mismatch → warning log, continue.
    """
    if not isinstance(version, str) or not version:
        raise InvalidDeckSchemaError(f"Missing or invalid 'version': {version!r}")

    parts = version.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise InvalidDeckSchemaError(f"Malformed version: {version!r}")
    major, minor = parts

    supported_major, supported_minor = SUPPORTED_VERSION.split(".", 1)
    if major != supported_major:
        raise InvalidDeckSchemaError(
            f"Unsupported major version: {version!r} "
            f"(supported: {SUPPORTED_VERSION!r})"
        )
    if minor != supported_minor:
        logger.warning(
            "Deck minor version %s differs from supported %s; loading anyway.",
            version,
            SUPPORTED_VERSION,
        )


def deck_from_dict(data: dict[str, Any]) -> Deck:
    """Parse a JSON-derived dict into a ``Deck``.

    Args:
        data: A dict matching the on-disk schema.

    Returns:
        The deserialized ``Deck``.

    Raises:
        InvalidDeckSchemaError: If the ``version`` is missing or
            unsupported, or if required fields are absent.
    """
    if not isinstance(data, dict):
        raise InvalidDeckSchemaError("Top-level deck data must be an object.")

    _validate_version(data.get("version"))

    try:
        deck_block = data["deck"]
        meta = DeckMeta(
            id=deck_block["id"],
            name=deck_block["name"],
            source_lang=deck_block["source_lang"],
            target_lang=deck_block["target_lang"],
            created_at=_from_iso(deck_block["created_at"]),
        )
        cards: list[Card] = []
        for raw_card in data.get("cards", []):
            stats_block = raw_card.get("stats") or {}
            cards.append(
                Card(
                    id=raw_card["id"],
                    term=raw_card["term"],
                    definition=raw_card["definition"],
                    notes=raw_card.get("notes", ""),
                    stats=CardStats(
                        correct=stats_block.get("correct", 0),
                        wrong=stats_block.get("wrong", 0),
                        last_reviewed=_from_iso(stats_block.get("last_reviewed")),
                    ),
                )
            )
    except KeyError as e:
        raise InvalidDeckSchemaError(f"Missing required field: {e.args[0]!r}") from e

    return Deck(meta=meta, cards=cards)


def load_deck(path: Path | str) -> Deck:
    """Load a deck from a JSON file on disk.

    Args:
        path: Path to the deck JSON file.

    Returns:
        The deserialized ``Deck``.

    Raises:
        DeckNotFoundError: If ``path`` does not exist.
        InvalidDeckSchemaError: If the file's schema is invalid.
    """
    p = Path(path)
    if not p.exists():
        raise DeckNotFoundError(str(p))
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        # Normalize raw JSON errors into our domain type so callers
        # only need to handle ``InvalidDeckSchemaError`` for any kind
        # of "the deck file is not loadable" condition.
        raise InvalidDeckSchemaError(f"Invalid JSON in {p}: {e}") from e
    return deck_from_dict(data)


def save_deck(deck: Deck, path: Path | str) -> None:
    """Atomically save a deck to a JSON file.

    Writes to a sibling ``*.tmp`` file first, then replaces the target,
    so a crash mid-write cannot corrupt the existing deck. Output is
    UTF-8 with ``ensure_ascii=False`` so non-Latin scripts (CJK, Cyrillic,
    etc.) are stored as their natural glyphs rather than ``\\uXXXX``
    escapes.

    Args:
        deck: The deck to persist.
        path: Destination file path. Parent directories are created if
            they do not already exist.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = deck_to_dict(deck)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(p)


def delete_deck(path: Path | str) -> None:
    """Permanently delete a deck file from disk.

    This is an unconditional, unrecoverable delete: there is no trash
    or undo. A trash / restore feature is deferred to a later version.

    Args:
        path: Path to the deck JSON file to delete.

    Raises:
        DeckNotFoundError: If no file exists at ``path``.
        StorageError: If the file exists but the OS refuses to remove
            it (a permission error, a lock, an I/O error, …).
    """
    p = Path(path)
    if not p.is_file():
        raise DeckNotFoundError(str(p))
    try:
        p.unlink()
    except OSError as e:
        raise StorageError(f"Failed to delete deck: {e}") from e


def export_deck(
    source_path: Path | str,
    dest_path: Path | str,
    strip_stats: bool = False,
) -> None:
    """Export a deck file to another location, optionally stripping stats.

    Loads the deck from ``source_path`` and writes it to ``dest_path``.
    When ``strip_stats`` is True, every card's review statistics are
    reset (via ``stats.reset_stats``) before writing, producing a clean
    copy suitable for sharing.

    This load-transform-save composition lives in the storage layer so
    the CLI ``export`` command and the GUI export handler share a single
    implementation instead of duplicating it. Resetting stats is
    delegated to ``core.stats`` to honor the ``Card.stats`` invariant.

    Args:
        source_path: Path of the deck to export.
        dest_path: Destination file path.
        strip_stats: Reset every card's stats when True; copy verbatim
            when False (default).

    Raises:
        DeckNotFoundError: If ``source_path`` does not exist.
        InvalidDeckSchemaError: If the source deck is malformed.
        OSError: If writing to ``dest_path`` fails.
    """
    deck = load_deck(source_path)
    if strip_stats:
        for card in deck.cards:
            reset_stats(card)
    save_deck(deck, dest_path)
