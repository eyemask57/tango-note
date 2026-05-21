"""Tests for tango_note.core.search."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tango_note.core.models import Card, Deck, DeckMeta
from tango_note.core.search import find_duplicates, search_cards


def _deck(*cards: Card) -> Deck:
    deck = Deck(
        meta=DeckMeta(
            id="d",
            name="n",
            source_lang="en",
            target_lang="ja",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    deck.cards = list(cards)
    return deck


def _card(cid: str, term: str, definition: str = "", notes: str = "") -> Card:
    return Card(id=cid, term=term, definition=definition, notes=notes)


# ===== search_cards =========================================================


def test_search_matches_term_substring() -> None:
    deck = _deck(
        _card("c1", "bonjour", "こんにちは"),
        _card("c2", "merci", "ありがとう"),
    )
    result = search_cards(deck, "bon")
    assert [c.id for c in result] == ["c1"]


def test_search_matches_definition_substring() -> None:
    deck = _deck(
        _card("c1", "bonjour", "こんにちは"),
        _card("c2", "merci", "ありがとう"),
    )
    result = search_cards(deck, "ありがと")
    assert [c.id for c in result] == ["c2"]


def test_search_matches_notes_substring() -> None:
    deck = _deck(
        _card("c1", "bonjour", "こんにちは", notes="朝の挨拶"),
        _card("c2", "merci", "ありがとう", notes="感謝"),
    )
    result = search_cards(deck, "挨拶")
    assert [c.id for c in result] == ["c1"]


def test_search_matches_across_newline_in_notes() -> None:
    """A query may span a line break inside multi-line notes."""
    deck = _deck(
        _card("c1", "term", "def", notes="line one\nline two\nline three"),
    )
    # Word that only exists on the second line.
    assert [c.id for c in search_cards(deck, "two")] == ["c1"]
    # Substring straddling the newline between line one and line two.
    assert [c.id for c in search_cards(deck, "one\nline")] == ["c1"]


def test_search_fields_restricts_to_term_only() -> None:
    deck = _deck(
        _card("c1", "apple", "りんご"),
        _card("c2", "fruit", "apple pie"),  # "apple" only in definition
    )
    result = search_cards(deck, "apple", fields=["term"])
    assert [c.id for c in result] == ["c1"]


def test_search_fields_multiple_fields() -> None:
    deck = _deck(
        _card("c1", "cat", "猫", notes="pet"),
        _card("c2", "dog", "犬", notes="cat-like? no"),  # "cat" in notes
        _card("c3", "bird", "鳥", notes="flies"),
    )
    result = search_cards(deck, "cat", fields=["definition", "notes"])
    # c1 term has "cat" but term is excluded; c2 notes has "cat".
    assert [c.id for c in result] == ["c2"]


def test_search_case_insensitive_by_default() -> None:
    deck = _deck(_card("c1", "Apple", "りんご"))
    assert [c.id for c in search_cards(deck, "apple")] == ["c1"]
    assert [c.id for c in search_cards(deck, "APPLE")] == ["c1"]


def test_search_case_sensitive_distinguishes_case() -> None:
    deck = _deck(_card("c1", "Apple", "りんご"))
    assert search_cards(deck, "apple", case_sensitive=True) == []
    assert [c.id for c in search_cards(deck, "Apple", case_sensitive=True)] == ["c1"]


def test_search_empty_query_returns_empty() -> None:
    deck = _deck(_card("c1", "anything", "何でも"))
    assert search_cards(deck, "") == []


def test_search_whitespace_only_query_returns_empty() -> None:
    deck = _deck(_card("c1", "anything", "何でも"))
    assert search_cards(deck, "   ") == []
    assert search_cards(deck, "\t\n ") == []


def test_search_preserves_deck_order() -> None:
    deck = _deck(
        _card("c1", "alpha"),
        _card("c2", "beta"),
        _card("c3", "alphabet"),
        _card("c4", "gamma"),
        _card("c5", "alpine"),
    )
    result = search_cards(deck, "al")
    assert [c.id for c in result] == ["c1", "c3", "c5"]


def test_search_invalid_field_raises_value_error() -> None:
    deck = _deck(_card("c1", "x", "y"))
    with pytest.raises(ValueError):
        search_cards(deck, "x", fields=["term", "bogus"])


def test_search_empty_deck_returns_empty() -> None:
    assert search_cards(_deck(), "anything") == []


def test_search_card_with_multiple_matching_fields_appears_once() -> None:
    deck = _deck(_card("c1", "echo", "echo", notes="echo echo"))
    result = search_cards(deck, "echo")
    assert [c.id for c in result] == ["c1"]


# ===== find_duplicates ======================================================


def test_duplicates_none_returns_empty() -> None:
    deck = _deck(
        _card("c1", "apple"),
        _card("c2", "banana"),
        _card("c3", "cherry"),
    )
    assert find_duplicates(deck) == []


def test_duplicates_simple_pair() -> None:
    deck = _deck(
        _card("c1", "apple", "りんご"),
        _card("c2", "banana", "バナナ"),
        _card("c3", "apple", "アップル"),
    )
    groups = find_duplicates(deck)
    assert len(groups) == 1
    assert [c.id for c in groups[0]] == ["c1", "c3"]


def test_duplicates_three_or_more_in_one_group() -> None:
    deck = _deck(
        _card("c1", "apple"),
        _card("c2", "apple"),
        _card("c3", "apple"),
    )
    groups = find_duplicates(deck)
    assert len(groups) == 1
    assert [c.id for c in groups[0]] == ["c1", "c2", "c3"]


def test_duplicates_multiple_independent_groups() -> None:
    deck = _deck(
        _card("c1", "apple"),
        _card("c2", "cat"),
        _card("c3", "apple"),
        _card("c4", "cat"),
        _card("c5", "unique"),
    )
    groups = find_duplicates(deck)
    assert len(groups) == 2
    assert [c.id for c in groups[0]] == ["c1", "c3"]
    assert [c.id for c in groups[1]] == ["c2", "c4"]


def test_duplicates_case_insensitive_by_default() -> None:
    deck = _deck(
        _card("c1", "Apple"),
        _card("c2", "apple"),
    )
    groups = find_duplicates(deck)
    assert len(groups) == 1
    assert [c.id for c in groups[0]] == ["c1", "c2"]


def test_duplicates_case_sensitive_separates_case() -> None:
    deck = _deck(
        _card("c1", "Apple"),
        _card("c2", "apple"),
    )
    assert find_duplicates(deck, case_sensitive=True) == []


def test_duplicates_group_order_follows_deck_position() -> None:
    """Groups appear in the order their first card appears in the deck."""
    deck = _deck(
        _card("c1", "zebra"),
        _card("c2", "apple"),
        _card("c3", "zebra"),
        _card("c4", "apple"),
    )
    groups = find_duplicates(deck)
    # "zebra" first appears before "apple" → zebra group is group 0.
    assert [c.id for c in groups[0]] == ["c1", "c3"]
    assert [c.id for c in groups[1]] == ["c2", "c4"]


def test_duplicates_empty_deck_returns_empty() -> None:
    assert find_duplicates(_deck()) == []
