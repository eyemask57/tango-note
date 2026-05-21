"""Tests for tango_note.gui.handlers.

These exercise the real core layer; nothing is mocked. Each test gets
its own ``tmp_path``-backed ``TANGO_NOTE_HOME`` so the real user data
at ``~/.tango-note/`` is never touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tango_note.core.analytics import FRESHNESS_NEVER
from tango_note.core.config import (
    QUIZ_MODE_RANDOM,
    QUIZ_MODE_UNREVIEWED,
    QUIZ_MODE_WEAK,
    AppConfig,
    load_config,
)
from tango_note.core.exceptions import (
    CardNotFoundError,
    DeckNotFoundError,
    EmptyDeckError,
    InvalidDeckSchemaError,
)
from tango_note.gui import handlers


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TANGO_NOTE_HOME", str(tmp_path))
    return tmp_path


# ----- create / load / save -------------------------------------------------


def test_create_deck_writes_file_and_marks_current(tmp_home: Path) -> None:
    deck, path = handlers.create_deck("French", source_lang="fr", target_lang="ja")
    assert path.exists()
    assert path.parent == tmp_home / "decks"
    assert deck.meta.name == "French"
    assert deck.meta.source_lang == "fr"
    assert deck.meta.target_lang == "ja"
    assert handlers.get_current_deck() == path


def test_create_deck_with_explicit_path(tmp_home: Path, tmp_path: Path) -> None:
    target = tmp_path / "custom" / "deck.json"
    deck, path = handlers.create_deck("Custom", path=target)
    assert path == target
    assert target.exists()
    assert deck.meta.name == "Custom"


def test_load_deck_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(DeckNotFoundError):
        handlers.load_deck(tmp_path / "missing.json")


def test_load_deck_invalid_schema_raises(tmp_home: Path, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"version": "9.0", "deck": {}}', encoding="utf-8")
    with pytest.raises(InvalidDeckSchemaError):
        handlers.load_deck(bad)


def test_save_then_load_roundtrip(tmp_home: Path) -> None:
    deck, path = handlers.create_deck("Test")
    handlers.add_card_to_deck(deck, "bonjour", "こんにちは", notes="朝の挨拶")
    handlers.save_deck(deck, path)
    loaded = handlers.load_deck(path)
    assert len(loaded.cards) == 1
    assert loaded.cards[0].term == "bonjour"
    assert loaded.cards[0].definition == "こんにちは"
    assert loaded.cards[0].notes == "朝の挨拶"


# ----- card mutations -------------------------------------------------------


def test_add_card_returns_card_with_uuid(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("Test")
    c = handlers.add_card_to_deck(deck, "a", "α")
    assert c.term == "a"
    assert c.definition == "α"
    assert c.notes == ""
    assert c.id  # non-empty uuid
    assert c in deck.cards


def test_delete_card_removes_only_matching_id(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("Test")
    c1 = handlers.add_card_to_deck(deck, "a", "α")
    c2 = handlers.add_card_to_deck(deck, "b", "β")
    handlers.delete_card_from_deck(deck, c1.id)
    assert c1 not in deck.cards
    assert c2 in deck.cards


def test_delete_card_with_unknown_id_is_noop(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("Test")
    c = handlers.add_card_to_deck(deck, "a", "α")
    handlers.delete_card_from_deck(deck, "no-such-id")
    assert c in deck.cards
    assert len(deck.cards) == 1


def test_update_card_mutates_in_place(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("Test")
    c = handlers.add_card_to_deck(deck, "a", "α")
    handlers.update_card_in_deck(deck, c.id, "A", "Alpha", "first letter")
    assert c.term == "A"
    assert c.definition == "Alpha"
    assert c.notes == "first letter"


def test_update_card_unknown_id_raises(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("Test")
    with pytest.raises(CardNotFoundError):
        handlers.update_card_in_deck(deck, "nope", "x", "y", "")


# ----- deck listing ---------------------------------------------------------


def test_list_known_decks_includes_created(tmp_home: Path) -> None:
    handlers.create_deck("Alpha")
    handlers.create_deck("Beta")
    names = [e.name for e in handlers.list_known_decks()]
    assert names.count("Alpha") == 1
    assert names.count("Beta") == 1


def test_list_known_decks_marks_current(tmp_home: Path) -> None:
    handlers.create_deck("A")
    _, path_b = handlers.create_deck("B")
    entries = handlers.list_known_decks()
    current = [e for e in entries if e.is_current]
    assert len(current) == 1
    assert current[0].path == path_b


def test_list_known_decks_when_empty(tmp_home: Path) -> None:
    assert handlers.list_known_decks() == []


def test_list_known_decks_includes_current_outside_decks_dir(
    tmp_home: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside" / "deck.json"
    handlers.create_deck("Outsider", path=outside)
    entries = handlers.list_known_decks()
    paths = [e.path for e in entries]
    assert outside in paths


def test_list_known_decks_falls_back_to_stem_for_broken_files(
    tmp_home: Path,
) -> None:
    """Decks with bad JSON still appear so the user can see them."""
    decks_dir = tmp_home / "decks"
    decks_dir.mkdir(parents=True)
    (decks_dir / "broken.json").write_text("not json{", encoding="utf-8")
    entries = handlers.list_known_decks()
    names = [e.name for e in entries]
    assert "broken" in names


# ----- import / export ------------------------------------------------------


def test_import_clashes_then_force_overwrites(
    tmp_home: Path, tmp_path: Path
) -> None:
    deck, _ = handlers.create_deck("Imp")
    external = tmp_path / "external.json"
    handlers.export_deck(deck, external)
    # Same deck id -> destination already exists
    with pytest.raises(FileExistsError):
        handlers.import_deck(external)
    dest = handlers.import_deck(external, force=True)
    assert dest.exists()


def test_import_from_missing_source_raises(tmp_home: Path, tmp_path: Path) -> None:
    with pytest.raises(DeckNotFoundError):
        handlers.import_deck(tmp_path / "nope.json")


def test_export_writes_to_destination(tmp_home: Path, tmp_path: Path) -> None:
    deck, _ = handlers.create_deck("E")
    handlers.add_card_to_deck(deck, "x", "y")
    dest = tmp_path / "exported.json"
    handlers.export_deck(deck, dest)
    loaded = handlers.load_deck(dest)
    assert len(loaded.cards) == 1


# ----- current-deck helpers -------------------------------------------------


def test_get_current_deck_none_when_unset(tmp_home: Path) -> None:
    assert handlers.get_current_deck() is None


def test_set_then_get_current_deck(tmp_home: Path, tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    handlers.set_current_deck(path)
    assert handlers.get_current_deck() == path


# ----- quiz / stats helpers -------------------------------------------------


def test_pick_next_card_empty_raises(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("Empty")
    with pytest.raises(EmptyDeckError):
        handlers.pick_next_card(deck)


def test_pick_next_card_returns_member(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("T")
    c = handlers.add_card_to_deck(deck, "a", "α")
    picked = handlers.pick_next_card(deck)
    assert picked is c


def test_record_correct_increments_and_stamps(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("T")
    c = handlers.add_card_to_deck(deck, "a", "α")
    handlers.record_correct(c)
    assert c.stats.correct == 1
    assert c.stats.last_reviewed is not None


def test_record_wrong_increments_and_stamps(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("T")
    c = handlers.add_card_to_deck(deck, "a", "α")
    handlers.record_wrong(c)
    assert c.stats.wrong == 1
    assert c.stats.last_reviewed is not None


def test_card_accuracy(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("T")
    c = handlers.add_card_to_deck(deck, "a", "α")
    assert handlers.card_accuracy(c) is None
    handlers.record_correct(c)
    handlers.record_wrong(c)
    assert handlers.card_accuracy(c) == pytest.approx(0.5)


def test_deck_summary(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("T")
    c1 = handlers.add_card_to_deck(deck, "a", "α")
    c2 = handlers.add_card_to_deck(deck, "b", "β")
    handlers.add_card_to_deck(deck, "c", "γ")
    handlers.record_correct(c1)
    handlers.record_correct(c1)
    handlers.record_wrong(c2)
    s = handlers.deck_summary(deck)
    assert s.total_cards == 3
    assert s.reviewed_cards == 2
    assert s.total_correct == 2
    assert s.total_wrong == 1
    assert s.accuracy == pytest.approx(2 / 3)


# ----- search / duplicates --------------------------------------------------


def test_search_cards_in_deck_loads_and_matches(tmp_home: Path) -> None:
    deck, path = handlers.create_deck("T")
    handlers.add_card_to_deck(deck, "bonjour", "こんにちは")
    handlers.add_card_to_deck(deck, "merci", "ありがとう")
    handlers.save_deck(deck, path)
    result = handlers.search_cards_in_deck(path, "bon")
    assert [c.term for c in result] == ["bonjour"]


def test_search_cards_in_deck_respects_fields(tmp_home: Path) -> None:
    deck, path = handlers.create_deck("T")
    handlers.add_card_to_deck(deck, "apple", "りんご")
    handlers.add_card_to_deck(deck, "fruit", "apple pie")
    handlers.save_deck(deck, path)
    result = handlers.search_cards_in_deck(path, "apple", fields=["term"])
    assert [c.term for c in result] == ["apple"]


def test_search_cards_in_deck_case_sensitive(tmp_home: Path) -> None:
    deck, path = handlers.create_deck("T")
    handlers.add_card_to_deck(deck, "Apple", "りんご")
    handlers.save_deck(deck, path)
    assert handlers.search_cards_in_deck(path, "apple", case_sensitive=True) == []
    assert (
        len(handlers.search_cards_in_deck(path, "apple", case_sensitive=False)) == 1
    )


def test_find_duplicates_in_deck(tmp_home: Path) -> None:
    deck, path = handlers.create_deck("T")
    handlers.add_card_to_deck(deck, "apple", "りんご")
    handlers.add_card_to_deck(deck, "banana", "バナナ")
    handlers.add_card_to_deck(deck, "apple", "アップル")
    handlers.save_deck(deck, path)
    groups = handlers.find_duplicates_in_deck(path)
    assert len(groups) == 1
    assert [c.definition for c in groups[0]] == ["りんご", "アップル"]


def test_find_duplicates_in_deck_none(tmp_home: Path) -> None:
    deck, path = handlers.create_deck("T")
    handlers.add_card_to_deck(deck, "a", "α")
    handlers.add_card_to_deck(deck, "b", "β")
    handlers.save_deck(deck, path)
    assert handlers.find_duplicates_in_deck(path) == []


# ----- export_deck_to_path --------------------------------------------------


def test_export_keeps_stats_when_not_stripping(
    tmp_home: Path, tmp_path: Path
) -> None:
    deck, src = handlers.create_deck("T")
    card = handlers.add_card_to_deck(deck, "a", "α")
    handlers.record_correct(card)
    handlers.record_wrong(card)
    handlers.save_deck(deck, src)

    dest = tmp_path / "with_stats.json"
    handlers.export_deck_to_path(src, dest, strip_stats=False)

    loaded = handlers.load_deck(dest)
    assert len(loaded.cards) == 1
    assert loaded.cards[0].stats.correct == 1
    assert loaded.cards[0].stats.wrong == 1
    assert loaded.cards[0].stats.last_reviewed is not None


def test_export_strips_stats_when_requested(
    tmp_home: Path, tmp_path: Path
) -> None:
    deck, src = handlers.create_deck("T")
    card = handlers.add_card_to_deck(deck, "a", "α", notes="memo")
    handlers.record_correct(card)
    handlers.record_correct(card)
    handlers.record_wrong(card)
    handlers.save_deck(deck, src)

    dest = tmp_path / "clean.json"
    handlers.export_deck_to_path(src, dest, strip_stats=True)

    loaded = handlers.load_deck(dest)
    # Card content is preserved...
    assert loaded.cards[0].term == "a"
    assert loaded.cards[0].definition == "α"
    assert loaded.cards[0].notes == "memo"
    # ...but stats are reset to their initial state.
    assert loaded.cards[0].stats.correct == 0
    assert loaded.cards[0].stats.wrong == 0
    assert loaded.cards[0].stats.last_reviewed is None


def test_export_strip_does_not_mutate_source(
    tmp_home: Path, tmp_path: Path
) -> None:
    """Exporting with strip_stats must not touch the source file or the
    caller's in-memory deck."""
    deck, src = handlers.create_deck("T")
    card = handlers.add_card_to_deck(deck, "a", "α")
    handlers.record_correct(card)
    handlers.save_deck(deck, src)

    handlers.export_deck_to_path(src, tmp_path / "clean.json", strip_stats=True)

    # Source file untouched.
    assert handlers.load_deck(src).cards[0].stats.correct == 1
    # Caller's in-memory deck untouched.
    assert deck.cards[0].stats.correct == 1


def test_export_missing_source_propagates(tmp_path: Path) -> None:
    with pytest.raises(DeckNotFoundError):
        handlers.export_deck_to_path(
            tmp_path / "nope.json", tmp_path / "out.json"
        )


def test_export_to_directory_destination_raises_oserror(
    tmp_home: Path, tmp_path: Path
) -> None:
    """A destination that is an existing directory triggers an OSError.

    This is used in place of a chmod-based read-only directory: Windows
    does not reliably honor the write bit on directories, whereas
    replacing a directory with a file fails consistently everywhere.
    """
    deck, src = handlers.create_deck("T")
    handlers.add_card_to_deck(deck, "a", "α")
    handlers.save_deck(deck, src)
    dest_dir = tmp_path / "a_directory"
    dest_dir.mkdir()
    with pytest.raises(OSError):
        handlers.export_deck_to_path(src, dest_dir)


# ----- quiz modes / analytics handlers --------------------------------------


def test_set_quiz_mode_persists(tmp_home: Path) -> None:
    handlers.set_quiz_mode(QUIZ_MODE_WEAK)
    assert load_config().quiz_mode == QUIZ_MODE_WEAK


def test_pick_next_card_by_mode_random(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("T")
    card = handlers.add_card_to_deck(deck, "a", "α")
    picked = handlers.pick_next_card_by_mode(deck, QUIZ_MODE_RANDOM, AppConfig())
    assert picked is card


def test_pick_next_card_by_mode_weak(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("T")
    card = handlers.add_card_to_deck(deck, "a", "α")
    handlers.record_wrong(card)  # accuracy 0.0 → weak
    cfg = AppConfig(weak_threshold=0.7)
    picked = handlers.pick_next_card_by_mode(deck, QUIZ_MODE_WEAK, cfg)
    assert picked is card


def test_pick_next_card_by_mode_weak_none_raises(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("T")
    handlers.add_card_to_deck(deck, "a", "α")  # never attempted
    with pytest.raises(EmptyDeckError):
        handlers.pick_next_card_by_mode(deck, QUIZ_MODE_WEAK, AppConfig())


def test_pick_next_card_by_mode_unreviewed(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("T")
    card = handlers.add_card_to_deck(deck, "a", "α")  # never reviewed
    cfg = AppConfig(unreviewed_days=30)
    picked = handlers.pick_next_card_by_mode(deck, QUIZ_MODE_UNREVIEWED, cfg)
    assert picked is card


def test_count_freshness_in_deck(tmp_home: Path) -> None:
    deck, _ = handlers.create_deck("T")
    handlers.add_card_to_deck(deck, "a", "α")
    handlers.add_card_to_deck(deck, "b", "β")
    counts = handlers.count_freshness_in_deck(deck)
    assert counts[FRESHNESS_NEVER] == 2
    assert sum(counts.values()) == 2


def test_list_stale_cards_in_deck_includes_never_reviewed(
    tmp_home: Path,
) -> None:
    deck, _ = handlers.create_deck("T")
    card = handlers.add_card_to_deck(deck, "a", "α")  # never reviewed
    stale = handlers.list_stale_cards_in_deck(deck, 30)
    assert stale == [card]
