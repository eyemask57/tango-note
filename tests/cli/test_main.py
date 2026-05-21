"""CLI smoke and integration tests.

Each test redirects ``TANGO_NOTE_HOME`` to a fresh ``tmp_path`` so the
real user config at ``~/.tango-note/`` is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tango_note.cli.main import app

runner = CliRunner()


@pytest.fixture
def cli_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TANGO_NOTE_HOME", str(tmp_path))
    return tmp_path


def _read_config(home: Path) -> dict:
    return json.loads((home / "config.json").read_text(encoding="utf-8"))


def _read_deck(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ----- init -----------------------------------------------------------------


def test_init_creates_deck_in_home_decks_dir(cli_home: Path) -> None:
    result = runner.invoke(app, ["init", "French Basics"])
    assert result.exit_code == 0, result.output
    decks = list((cli_home / "decks").glob("*.json"))
    assert len(decks) == 1
    deck = _read_deck(decks[0])
    assert deck["deck"]["name"] == "French Basics"
    assert deck["deck"]["source_lang"] == "en"
    assert deck["deck"]["target_lang"] == "ja"
    assert deck["cards"] == []


def test_init_sets_current_deck_in_config(cli_home: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    cfg = _read_config(cli_home)
    decks = list((cli_home / "decks").glob("*.json"))
    assert cfg["current_deck"] == str(decks[0])


def test_init_respects_explicit_path(cli_home: Path, tmp_path: Path) -> None:
    explicit = tmp_path / "elsewhere" / "mydeck.json"
    result = runner.invoke(app, ["init", "Custom", "--path", str(explicit)])
    assert result.exit_code == 0, result.output
    assert explicit.exists()
    # No file landed in the default decks dir.
    assert not list((cli_home / "decks").glob("*.json"))
    # Config still points at the explicit path.
    cfg = _read_config(cli_home)
    assert cfg["current_deck"] == str(explicit)


def test_init_with_language_options(cli_home: Path) -> None:
    runner.invoke(
        app,
        ["init", "中国語", "--source-lang", "zh", "--target-lang", "ja"],
    )
    deck_path = Path(_read_config(cli_home)["current_deck"])
    deck = _read_deck(deck_path)
    assert deck["deck"]["source_lang"] == "zh"
    assert deck["deck"]["target_lang"] == "ja"
    assert deck["deck"]["name"] == "中国語"


# ----- add ------------------------------------------------------------------


def test_add_appends_card_to_current_deck(cli_home: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    result = runner.invoke(app, ["add", "bonjour", "こんにちは"])
    assert result.exit_code == 0, result.output
    deck_path = Path(_read_config(cli_home)["current_deck"])
    deck = _read_deck(deck_path)
    assert len(deck["cards"]) == 1
    assert deck["cards"][0]["term"] == "bonjour"
    assert deck["cards"][0]["definition"] == "こんにちは"
    assert deck["cards"][0]["notes"] == ""


def test_add_with_notes(cli_home: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "bonjour", "こんにちは", "--notes", "朝〜昼の挨拶"])
    deck_path = Path(_read_config(cli_home)["current_deck"])
    deck = _read_deck(deck_path)
    assert deck["cards"][0]["notes"] == "朝〜昼の挨拶"


def test_add_with_explicit_deck_option(cli_home: Path, tmp_path: Path) -> None:
    """--deck must override the current-deck setting."""
    runner.invoke(app, ["init", "Default"])
    other = tmp_path / "other.json"
    runner.invoke(app, ["init", "Other", "--path", str(other)])
    # Switch back to default
    runner.invoke(app, ["use", _read_config(cli_home)["current_deck"]])
    # Add via --deck to the *other* file, not the current one
    runner.invoke(app, ["add", "x", "y", "--deck", str(other)])
    other_deck = _read_deck(other)
    assert len(other_deck["cards"]) == 1


# ----- list -----------------------------------------------------------------


def test_list_shows_each_card(cli_home: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "bonjour", "こんにちは"])
    runner.invoke(app, ["add", "merci", "ありがとう"])
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0, result.output
    assert "bonjour" in result.output
    assert "merci" in result.output
    assert "こんにちは" in result.output
    assert "ありがとう" in result.output


def test_list_empty_deck_prints_message(cli_home: Path) -> None:
    runner.invoke(app, ["init", "Empty"])
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    # "Empty deck." translated to JA — accept either, just confirm non-empty output
    assert result.output.strip() != ""


# ----- list-decks -----------------------------------------------------------


def test_list_decks_shows_init_decks(cli_home: Path) -> None:
    runner.invoke(app, ["init", "A"])
    runner.invoke(app, ["init", "B"])
    result = runner.invoke(app, ["list-decks"])
    assert result.exit_code == 0
    # Two decks under <home>/decks/ → two lines containing .json.
    assert result.output.count(".json") >= 2


def test_list_decks_marks_current(cli_home: Path) -> None:
    runner.invoke(app, ["init", "A"])
    current = _read_config(cli_home)["current_deck"]
    result = runner.invoke(app, ["list-decks"])
    # The current line should contain a "*" marker
    for line in result.output.splitlines():
        if current in line:
            assert line.lstrip().startswith("*")
            break
    else:
        pytest.fail(f"current deck not in output:\n{result.output}")


def test_list_decks_when_none_present(cli_home: Path) -> None:
    result = runner.invoke(app, ["list-decks"])
    assert result.exit_code == 0
    assert result.output.strip() != ""


# ----- use ------------------------------------------------------------------


def test_use_switches_current_deck(cli_home: Path) -> None:
    runner.invoke(app, ["init", "A"])
    deck_a = _read_config(cli_home)["current_deck"]
    runner.invoke(app, ["init", "B"])
    deck_b = _read_config(cli_home)["current_deck"]
    assert deck_a != deck_b
    # Switch back
    result = runner.invoke(app, ["use", deck_a])
    assert result.exit_code == 0, result.output
    assert _read_config(cli_home)["current_deck"] == deck_a


def test_use_nonexistent_path_errors(cli_home: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["use", str(tmp_path / "missing.json")])
    assert result.exit_code == 1


def test_use_invalid_schema_errors(cli_home: Path, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"version": "99.0", "deck": {}}', encoding="utf-8")
    result = runner.invoke(app, ["use", str(bad)])
    assert result.exit_code == 2


# ----- error paths ----------------------------------------------------------


def test_add_without_current_deck_errors_with_exit_1(cli_home: Path) -> None:
    """No init, no --deck → friendly error, exit code 1."""
    result = runner.invoke(app, ["add", "x", "y"])
    assert result.exit_code == 1


def test_explicit_missing_deck_errors_with_exit_1(
    cli_home: Path, tmp_path: Path
) -> None:
    result = runner.invoke(
        app, ["add", "x", "y", "--deck", str(tmp_path / "no.json")]
    )
    assert result.exit_code == 1


def test_invalid_schema_errors_with_exit_2(
    cli_home: Path, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"version": "2.0", "deck": {"id": "x", "name": "y", '
        '"source_lang": "fr", "target_lang": "ja", '
        '"created_at": "2026-01-01T00:00:00Z"}, "cards": []}',
        encoding="utf-8",
    )
    result = runner.invoke(app, ["list", "--deck", str(bad)])
    assert result.exit_code == 2


# ----- quiz -----------------------------------------------------------------


def test_quiz_empty_deck_errors(cli_home: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    result = runner.invoke(app, ["quiz"])
    assert result.exit_code == 1


def test_quiz_grades_correct_and_wrong_then_quits(cli_home: Path) -> None:
    """With a single-card deck the pick is deterministic — exercise both grades."""
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "bonjour", "こんにちは"])
    # round 1: Enter, y → correct
    # round 2: Enter, n → wrong
    # round 3: q → quit
    result = runner.invoke(app, ["quiz"], input="\ny\n\nn\nq\n")
    assert result.exit_code == 0, result.output
    # Stats were saved
    deck_path = Path(_read_config(cli_home)["current_deck"])
    deck = _read_deck(deck_path)
    stats = deck["cards"][0]["stats"]
    assert stats["correct"] == 1
    assert stats["wrong"] == 1
    assert stats["last_reviewed"] is not None


def test_quiz_quits_immediately_with_q(cli_home: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "x", "y"])
    result = runner.invoke(app, ["quiz"], input="q\n")
    assert result.exit_code == 0
    # No stats recorded
    deck_path = Path(_read_config(cli_home)["current_deck"])
    deck = _read_deck(deck_path)
    stats = deck["cards"][0]["stats"]
    assert stats["correct"] == 0
    assert stats["wrong"] == 0


def test_quiz_keyboard_interrupt_saves_partial_stats(
    cli_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ctrl-C mid-quiz must still persist whatever was recorded."""
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "x", "y"])

    # input() sequence: Enter (reveal), 'y' (correct), then KeyboardInterrupt
    # on the next call (the second reveal prompt of round 2).
    responses = iter(["", "y"])

    def fake_input(prompt: str = "") -> str:
        try:
            return next(responses)
        except StopIteration:
            raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", fake_input)

    result = runner.invoke(app, ["quiz"])
    assert result.exit_code == 130, result.output

    deck_path = Path(_read_config(cli_home)["current_deck"])
    deck = _read_deck(deck_path)
    assert deck["cards"][0]["stats"]["correct"] == 1
    assert deck["cards"][0]["stats"]["wrong"] == 0


# ----- stats ----------------------------------------------------------------


def test_stats_unreviewed_deck(cli_home: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "x", "y"])
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0, result.output
    # Total cards is 1 — appears in output regardless of language.
    assert "1" in result.output
    # Accuracy is "-" for unreviewed decks.
    assert "-" in result.output


def test_stats_after_quiz(cli_home: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "x", "y"])
    runner.invoke(app, ["quiz"], input="\ny\nq\n")
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0, result.output
    assert "100" in result.output  # 100.0% accuracy


# ----- export / import ------------------------------------------------------


def test_export_writes_destination_file(cli_home: Path, tmp_path: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "x", "y"])
    dest = tmp_path / "exported.json"
    result = runner.invoke(app, ["export", str(dest)])
    assert result.exit_code == 0, result.output
    assert dest.exists()
    exported = _read_deck(dest)
    assert len(exported["cards"]) == 1


def test_import_succeeds_then_clashes_without_force(
    cli_home: Path, tmp_path: Path
) -> None:
    # Create a deck and export it.
    runner.invoke(app, ["init", "Source"])
    src = tmp_path / "exported.json"
    runner.invoke(app, ["export", str(src)])

    # Importing the same deck-id into the decks dir clashes (already
    # exists from the original init).
    result = runner.invoke(app, ["import", str(src)])
    assert result.exit_code == 1


def test_import_with_force_overwrites(cli_home: Path, tmp_path: Path) -> None:
    runner.invoke(app, ["init", "Source"])
    src = tmp_path / "exported.json"
    runner.invoke(app, ["export", str(src)])
    result = runner.invoke(app, ["import", str(src), "--force"])
    assert result.exit_code == 0, result.output


def test_import_invalid_schema_errors(cli_home: Path, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"version": "5.0", "deck": {}, "cards": []}', encoding="utf-8"
    )
    result = runner.invoke(app, ["import", str(bad)])
    assert result.exit_code == 2


# ----- help -----------------------------------------------------------------


def test_help_lists_all_subcommands(cli_home: Path) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for sub in (
        "init",
        "add",
        "list",
        "search",
        "duplicates",
        "list-decks",
        "use",
        "quiz",
        "stats",
        "export",
        "import",
    ):
        assert sub in result.output, f"{sub!r} missing from --help output"


# ----- search ---------------------------------------------------------------


def _seed_deck(cards: list[tuple[str, str]]) -> None:
    """init a deck then add the given (term, definition) pairs."""
    runner.invoke(app, ["init", "Test"])
    for term, definition in cards:
        runner.invoke(app, ["add", term, definition])


def test_search_finds_matching_card(cli_home: Path) -> None:
    _seed_deck([("bonjour", "こんにちは"), ("merci", "ありがとう")])
    result = runner.invoke(app, ["search", "bonjour"])
    assert result.exit_code == 0, result.output
    assert "bonjour" in result.output
    assert "merci" not in result.output


def test_search_no_match_prints_message(cli_home: Path) -> None:
    _seed_deck([("bonjour", "こんにちは")])
    result = runner.invoke(app, ["search", "zzzznomatch"])
    assert result.exit_code == 0
    assert result.output.strip() != ""
    assert "bonjour" not in result.output


def test_search_field_restricts_to_definition(cli_home: Path) -> None:
    _seed_deck([("apple", "りんご"), ("fruit", "apple pie")])
    # "apple" appears in term of card 1 and definition of card 2.
    result = runner.invoke(app, ["search", "apple", "--field", "definition"])
    assert result.exit_code == 0, result.output
    assert "fruit" in result.output
    assert "りんご" not in result.output


def test_search_case_sensitive(cli_home: Path) -> None:
    _seed_deck([("Apple", "りんご")])
    miss = runner.invoke(app, ["search", "apple", "--case-sensitive"])
    assert miss.exit_code == 0
    assert "Apple" not in miss.output
    hit = runner.invoke(app, ["search", "Apple", "-c"])
    assert "Apple" in hit.output


def test_search_invalid_field_errors(cli_home: Path) -> None:
    _seed_deck([("a", "b")])
    result = runner.invoke(app, ["search", "a", "--field", "bogus"])
    assert result.exit_code == 1


# ----- duplicates -----------------------------------------------------------


def test_duplicates_finds_groups(cli_home: Path) -> None:
    _seed_deck(
        [("apple", "りんご"), ("cat", "猫"), ("apple", "アップル")]
    )
    result = runner.invoke(app, ["duplicates"])
    assert result.exit_code == 0, result.output
    assert "りんご" in result.output
    assert "アップル" in result.output
    assert "猫" not in result.output


def test_duplicates_none_prints_message(cli_home: Path) -> None:
    _seed_deck([("apple", "りんご"), ("banana", "バナナ")])
    result = runner.invoke(app, ["duplicates"])
    assert result.exit_code == 0
    assert result.output.strip() != ""
    assert "りんご" not in result.output


# ----- add --notes-file -----------------------------------------------------


def test_add_with_notes_file_loads_multiline(
    cli_home: Path, tmp_path: Path
) -> None:
    notes_path = tmp_path / "notes.txt"
    notes_path.write_text("first line\nsecond line\nthird line", encoding="utf-8")
    runner.invoke(app, ["init", "Test"])
    result = runner.invoke(
        app, ["add", "test", "テスト", "--notes-file", str(notes_path)]
    )
    assert result.exit_code == 0, result.output
    deck_path = Path(_read_config(cli_home)["current_deck"])
    deck = _read_deck(deck_path)
    assert deck["cards"][0]["notes"] == "first line\nsecond line\nthird line"


def test_add_notes_and_notes_file_conflict_errors(
    cli_home: Path, tmp_path: Path
) -> None:
    notes_path = tmp_path / "notes.txt"
    notes_path.write_text("x", encoding="utf-8")
    runner.invoke(app, ["init", "Test"])
    result = runner.invoke(
        app,
        [
            "add",
            "test",
            "テスト",
            "--notes",
            "inline",
            "--notes-file",
            str(notes_path),
        ],
    )
    assert result.exit_code == 1


def test_add_notes_file_missing_errors(cli_home: Path, tmp_path: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    result = runner.invoke(
        app,
        ["add", "test", "テスト", "--notes-file", str(tmp_path / "nope.txt")],
    )
    assert result.exit_code == 1


# ----- multi-line notes display ---------------------------------------------


def test_list_collapses_multiline_notes(cli_home: Path, tmp_path: Path) -> None:
    """list output shows 'first line ...' for multi-line notes."""
    notes_path = tmp_path / "notes.txt"
    notes_path.write_text("first line\nsecond line", encoding="utf-8")
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "test", "テスト", "--notes-file", str(notes_path)])
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0, result.output
    assert "first line ..." in result.output
    assert "second line" not in result.output


def test_search_collapses_multiline_notes(cli_home: Path, tmp_path: Path) -> None:
    notes_path = tmp_path / "notes.txt"
    notes_path.write_text("alpha line\nbeta line", encoding="utf-8")
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "test", "テスト", "--notes-file", str(notes_path)])
    result = runner.invoke(app, ["search", "test"])
    assert result.exit_code == 0
    assert "alpha line ..." in result.output
    assert "beta line" not in result.output


# ----- --notes-file BOM handling --------------------------------------------


def test_add_notes_file_strips_utf8_bom(cli_home: Path, tmp_path: Path) -> None:
    """A UTF-8 BOM at the file start must not leak into the notes field."""
    notes_path = tmp_path / "notes_bom.txt"
    # b"\xef\xbb\xbf" is the UTF-8 BOM, as written by PowerShell's
    # `Out-File -Encoding utf8`.
    notes_path.write_bytes(
        b"\xef\xbb\xbf" + "BOM prefixed\nsecond line".encode("utf-8")
    )
    runner.invoke(app, ["init", "Test"])
    result = runner.invoke(
        app, ["add", "t", "テスト", "--notes-file", str(notes_path)]
    )
    assert result.exit_code == 0, result.output
    deck = _read_deck(Path(_read_config(cli_home)["current_deck"]))
    notes = deck["cards"][0]["notes"]
    assert "\ufeff" not in notes  # the BOM char must be gone
    assert notes == "BOM prefixed\nsecond line"


def test_add_notes_file_without_bom_unchanged(
    cli_home: Path, tmp_path: Path
) -> None:
    """A plain UTF-8 file (no BOM) still reads verbatim — regression guard."""
    notes_path = tmp_path / "notes_plain.txt"
    notes_path.write_bytes("プレーンな日本語\n二行目".encode("utf-8"))
    runner.invoke(app, ["init", "Test"])
    result = runner.invoke(
        app, ["add", "t", "テスト", "--notes-file", str(notes_path)]
    )
    assert result.exit_code == 0, result.output
    deck = _read_deck(Path(_read_config(cli_home)["current_deck"]))
    assert deck["cards"][0]["notes"] == "プレーンな日本語\n二行目"


# ----- export --strip-stats -------------------------------------------------


def test_export_keeps_stats_by_default(cli_home: Path, tmp_path: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "a", "α"])
    # One quiz round records a correct answer.
    runner.invoke(app, ["quiz"], input="\ny\nq\n")
    dest = tmp_path / "with_stats.json"
    result = runner.invoke(app, ["export", str(dest)])
    assert result.exit_code == 0, result.output
    exported = json.loads(dest.read_text(encoding="utf-8"))
    assert exported["cards"][0]["stats"]["correct"] == 1


def test_export_strip_stats_resets_stats(
    cli_home: Path, tmp_path: Path
) -> None:
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "a", "α"])
    runner.invoke(app, ["quiz"], input="\ny\nq\n")
    dest = tmp_path / "clean.json"
    result = runner.invoke(app, ["export", str(dest), "--strip-stats"])
    assert result.exit_code == 0, result.output
    exported = json.loads(dest.read_text(encoding="utf-8"))
    assert exported["cards"][0]["term"] == "a"  # content preserved
    assert exported["cards"][0]["stats"]["correct"] == 0
    assert exported["cards"][0]["stats"]["wrong"] == 0
    assert exported["cards"][0]["stats"]["last_reviewed"] is None


def test_export_strip_stats_leaves_source_deck_untouched(
    cli_home: Path, tmp_path: Path
) -> None:
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "a", "α"])
    runner.invoke(app, ["quiz"], input="\ny\nq\n")
    runner.invoke(
        app, ["export", str(tmp_path / "clean.json"), "--strip-stats"]
    )
    # The original deck on disk still has its stats.
    source = _read_deck(Path(_read_config(cli_home)["current_deck"]))
    assert source["cards"][0]["stats"]["correct"] == 1


# ----- quiz --mode ----------------------------------------------------------


def test_quiz_mode_weak_no_weak_cards_errors(cli_home: Path) -> None:
    """A deck of never-attempted cards has no weak card → exit 1."""
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "x", "y"])
    result = runner.invoke(app, ["quiz", "--mode", "weak"])
    assert result.exit_code == 1


def test_quiz_mode_weak_runs_with_a_weak_card(cli_home: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "x", "y"])
    # Answer once wrong → accuracy 0.0 → the card is now "weak".
    runner.invoke(app, ["quiz"], input="\nn\nq\n")
    result = runner.invoke(app, ["quiz", "--mode", "weak"], input="q\n")
    assert result.exit_code == 0, result.output


def test_quiz_mode_unreviewed_runs_with_fresh_card(cli_home: Path) -> None:
    """A never-reviewed card counts as long-unreviewed (include_never)."""
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "x", "y"])
    result = runner.invoke(
        app, ["quiz", "--mode", "unreviewed"], input="q\n"
    )
    assert result.exit_code == 0, result.output


def test_quiz_mode_unreviewed_all_recent_errors(cli_home: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "x", "y"])
    # Review the card now → last_reviewed is recent → not "unreviewed".
    runner.invoke(app, ["quiz"], input="\ny\nq\n")
    result = runner.invoke(app, ["quiz", "--mode", "unreviewed"])
    assert result.exit_code == 1


def test_quiz_invalid_mode_rejected(cli_home: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "x", "y"])
    result = runner.invoke(app, ["quiz", "--mode", "bogus"])
    assert result.exit_code != 0


# ----- stats: freshness + --stale -------------------------------------------


def test_stats_shows_review_freshness(cli_home: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "x", "y"])
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0, result.output
    assert "復習頻度" in result.output  # the "Review freshness" section


def test_stats_stale_lists_long_unreviewed(cli_home: Path) -> None:
    runner.invoke(app, ["init", "Test"])
    runner.invoke(app, ["add", "bonjour", "こんにちは"])
    result = runner.invoke(app, ["stats", "--stale"])
    assert result.exit_code == 0, result.output
    assert "長期未復習カード" in result.output
    # The never-reviewed card is listed as stale.
    assert "bonjour" in result.output
