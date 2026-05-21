"""Card search and duplicate detection.

Pure, in-memory query helpers over a :class:`~tango_note.core.models.Deck`.
No I/O and no user-facing strings — callers in ``cli/`` and ``gui/``
format and translate the results.
"""

from __future__ import annotations

from tango_note.core.models import Card, Deck

#: Fields that may be targeted by :func:`search_cards`.
SEARCHABLE_FIELDS = ("term", "definition", "notes")


def search_cards(
    deck: Deck,
    query: str,
    fields: list[str] | None = None,
    case_sensitive: bool = False,
) -> list[Card]:
    """Find cards whose chosen fields contain ``query`` as a substring.

    Args:
        deck: The deck to search.
        query: The substring to look for.
        fields: Field names to search. ``None`` searches all of
            ``("term", "definition", "notes")``. Passing an unknown
            field name raises ``ValueError``.
        case_sensitive: When ``True``, match case exactly. Default
            ``False`` (case-insensitive).

    Returns:
        Matching cards in their original deck order. Each card appears
        at most once even if several fields match.

    Raises:
        ValueError: If ``fields`` contains an unknown field name.

    Notes:
        An empty or whitespace-only ``query`` returns an empty list.
        Because ``notes`` may contain newlines and matching uses plain
        substring containment, a query can match across a line break.
    """
    if fields is None:
        target_fields = list(SEARCHABLE_FIELDS)
    else:
        invalid = [f for f in fields if f not in SEARCHABLE_FIELDS]
        if invalid:
            raise ValueError(
                f"Invalid search field(s): {invalid}. "
                f"Valid fields: {list(SEARCHABLE_FIELDS)}"
            )
        target_fields = list(fields)

    if not query.strip():
        return []

    needle = query if case_sensitive else query.lower()

    results: list[Card] = []
    for card in deck.cards:
        for field in target_fields:
            value: str = getattr(card, field)
            haystack = value if case_sensitive else value.lower()
            if needle in haystack:
                results.append(card)
                break  # one matching field is enough; keep order, no dupes
    return results


def find_duplicates(
    deck: Deck,
    case_sensitive: bool = False,
) -> list[list[Card]]:
    """Group cards that share the same ``term``.

    Args:
        deck: The deck to inspect.
        case_sensitive: When ``True``, ``"Apple"`` and ``"apple"`` are
            treated as distinct terms. Default ``False``.

    Returns:
        A list of duplicate groups; each group holds two or more cards
        with the same term. Groups are ordered by the deck position of
        their first card. Returns an empty list when there are no
        duplicates.

    Notes:
        Only ``term`` is used as the comparison key — ``definition``
        and ``notes`` are not considered.
    """
    groups: dict[str, list[Card]] = {}
    order: list[str] = []  # first-appearance order of keys
    for card in deck.cards:
        key = card.term if case_sensitive else card.term.lower()
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(card)

    return [groups[key] for key in order if len(groups[key]) >= 2]
