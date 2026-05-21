"""tango-note CLI entry point.

Subcommands:

* ``init`` — create a new deck (auto-set as current)
* ``add`` — append a card to a deck
* ``list`` — show all cards in a deck
* ``list-decks`` — show all known decks
* ``use`` — switch the current deck
* ``quiz`` — interactive review session
* ``stats`` — print deck-level statistics
* ``export`` — copy a deck to an arbitrary destination
* ``import`` — copy a deck from elsewhere into the decks directory

All user-facing strings flow through :func:`tango_note.core.i18n.setup_i18n`.
Core exceptions are translated to friendly messages by the
``_handle_core_errors`` decorator and mapped to exit codes:

* 0 — success
* 1 — user / input error (missing deck, no current deck, file clash, …)
* 2 — data error (invalid deck schema, invalid config, …)
* 130 — interrupted by Ctrl-C during a quiz (stats are still saved)
"""

from __future__ import annotations

import functools
import enum
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import typer

# Force UTF-8 on stdout/stderr so non-ASCII output renders without
# UnicodeEncodeError on legacy Windows code pages (e.g. cp932).
# Best-effort: silently skipped if the stream does not support
# reconfigure (older Pythons, captured streams under pytest's capsys,
# custom IO wrappers, etc.).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError, ValueError):
        pass

from tango_note.core.analytics import (  # noqa: E402
    FRESHNESS_NEVER,
    FRESHNESS_STALE,
    FRESHNESS_WITHIN_MONTH,
    FRESHNESS_WITHIN_WEEK,
    count_by_review_freshness,
    list_stale_cards,
)
from tango_note.core.config import (  # noqa: E402  (imports after reconfigure)
    QUIZ_MODE_RANDOM,
    QUIZ_MODE_UNREVIEWED,
    QUIZ_MODE_WEAK,
    AppConfig,
    decks_dir,
    load_config,
    save_config,
)
from tango_note.core.exceptions import (  # noqa: E402
    CardNotFoundError,
    DeckNotFoundError,
    DuplicateCardError,
    EmptyDeckError,
    InvalidConfigError,
    InvalidDeckSchemaError,
)
from tango_note.core.i18n import setup_i18n  # noqa: E402
from tango_note.core.models import Card, Deck, DeckMeta  # noqa: E402
from tango_note.core.quiz import (  # noqa: E402
    pick_next,
    pick_next_unreviewed,
    pick_next_weak,
)
from tango_note.core.search import find_duplicates, search_cards  # noqa: E402
from tango_note.core.stats import (  # noqa: E402
    deck_summary,
    record_correct,
    record_wrong,
)
from tango_note.core.storage import (  # noqa: E402
    export_deck,
    load_deck,
    save_deck,
)


app = typer.Typer(
    name="tango-note",
    help="Local vocabulary deck app (CLI).",
    no_args_is_help=True,
    add_completion=False,
)


# ---- i18n plumbing ---------------------------------------------------------

# Translator function for the current process. Reset every invocation
# by the root callback so changes to ``TANGO_NOTE_HOME`` (and therefore
# to ``config.lang``) take effect for each ``CliRunner.invoke`` in tests.
_translator: Optional[Callable[[str], str]] = None


def _t(msg: str) -> str:
    """Translate ``msg`` using the active language, or pass it through."""
    if _translator is None:
        return msg
    return _translator(msg)


@app.callback()
def _root() -> None:
    """Initialize i18n for this invocation."""
    global _translator
    try:
        cfg = load_config()
        lang = cfg.lang
    except InvalidConfigError:
        lang = "ja"
    _translator = setup_i18n(lang)


# ---- helpers ---------------------------------------------------------------


def _resolve_deck_path(explicit: Optional[Path]) -> Path:
    """Decide which deck path to use for a command.

    Precedence: ``--deck`` option > ``config.current_deck`` > error.
    """
    if explicit is not None:
        return Path(explicit)
    cfg = load_config()
    if cfg.current_deck:
        return Path(cfg.current_deck)
    typer.echo(_t("No current deck set."), err=True)
    raise typer.Exit(code=1)


def _handle_core_errors(func: Callable) -> Callable:
    """Decorator: turn core exceptions into friendly CLI errors + exit codes."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DeckNotFoundError as e:
            typer.echo(
                _t("Deck not found: {path}").format(path=str(e)),
                err=True,
            )
            raise typer.Exit(code=1)
        except InvalidDeckSchemaError as e:
            typer.echo(
                _t("Invalid deck schema: {detail}").format(detail=str(e)),
                err=True,
            )
            raise typer.Exit(code=2)
        except EmptyDeckError:
            typer.echo(_t("Empty deck."), err=True)
            raise typer.Exit(code=1)
        except CardNotFoundError:
            typer.echo(_t("Card not found."), err=True)
            raise typer.Exit(code=1)
        except DuplicateCardError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=1)
        except InvalidConfigError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=2)

    return wrapper


def _print_quiz_summary(correct: int, wrong: int) -> None:
    total = correct + wrong
    typer.echo(_t("Reviewed: {n}").format(n=total))
    if total > 0:
        pct = correct / total * 100
        typer.echo(_t("Accuracy: {p}").format(p=f"{pct:.1f}%"))


def _format_notes_for_oneline(notes: str) -> str:
    """Collapse multi-line notes to a single-line preview.

    When ``notes`` contains a newline, only the first line is kept and
    `` ...`` is appended to signal that more text was elided. Single-line
    notes are returned unchanged. Shared by the ``list``, ``search``, and
    ``duplicates`` commands.
    """
    if "\n" not in notes:
        return notes
    return notes.split("\n", 1)[0] + " ..."


def _format_card_line(card: Card) -> str:
    """One-line representation of a card for list-style output."""
    line = f"{card.term}  ->  {card.definition}"
    if card.notes:
        line += f"  ({_format_notes_for_oneline(card.notes)})"
    return line


# ---- subcommands -----------------------------------------------------------


@app.command()
@_handle_core_errors
def init(
    name: str = typer.Argument(..., help="Deck name (any non-empty string)."),
    source_lang: str = typer.Option(
        "en",
        "--source-lang",
        "-s",
        help="ISO 639-1 code for the term language (default: en).",
    ),
    target_lang: str = typer.Option(
        "ja",
        "--target-lang",
        "-t",
        help="ISO 639-1 code for the definition language (default: ja).",
    ),
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        help="Destination file (default: <home>/decks/<uuid>.json).",
    ),
) -> None:
    """Create a new deck and mark it as the current deck."""
    deck_id = str(uuid.uuid4())
    target_path = Path(path) if path is not None else decks_dir() / f"{deck_id}.json"
    deck = Deck(
        meta=DeckMeta(
            id=deck_id,
            name=name,
            source_lang=source_lang,
            target_lang=target_lang,
            created_at=datetime.now(timezone.utc),
        )
    )
    save_deck(deck, target_path)
    cfg = load_config()
    cfg.current_deck = str(target_path)
    save_config(cfg)
    typer.echo(_t("Created deck: {name}").format(name=name))
    typer.echo(_t("Current deck: {path}").format(path=target_path))


@app.command()
@_handle_core_errors
def add(
    term: str = typer.Argument(..., help="The prompt side of the card."),
    definition: str = typer.Argument(..., help="The answer side of the card."),
    notes: str = typer.Option("", "--notes", "-n", help="Optional free-form notes."),
    notes_file: Optional[Path] = typer.Option(
        None,
        "--notes-file",
        help="Read notes from a UTF-8 text file (supports multi-line notes).",
    ),
    deck: Optional[Path] = typer.Option(
        None, "--deck", "-d", help="Deck file path (overrides current deck)."
    ),
) -> None:
    """Add a card to a deck.

    Notes may be given inline with ``--notes`` or loaded from a file
    with ``--notes-file``; the two options are mutually exclusive.
    """
    if notes and notes_file is not None:
        typer.echo(
            _t("Cannot specify both --notes and --notes-file."), err=True
        )
        raise typer.Exit(code=1)

    final_notes = notes
    if notes_file is not None:
        if not notes_file.exists():
            typer.echo(
                _t("Notes file not found: {path}").format(path=notes_file),
                err=True,
            )
            raise typer.Exit(code=1)
        # "utf-8-sig" transparently strips a leading BOM when present
        # (e.g. files written by PowerShell's `Out-File -Encoding utf8`)
        # and behaves like plain UTF-8 when there is no BOM.
        final_notes = notes_file.read_text(encoding="utf-8-sig")

    deck_path = _resolve_deck_path(deck)
    d = load_deck(deck_path)
    d.cards.append(
        Card(
            id=str(uuid.uuid4()),
            term=term,
            definition=definition,
            notes=final_notes,
        )
    )
    save_deck(d, deck_path)
    typer.echo(_t("Added card."))


@app.command(name="list")
@_handle_core_errors
def list_cmd(
    deck: Optional[Path] = typer.Option(
        None, "--deck", "-d", help="Deck file path (overrides current deck)."
    ),
) -> None:
    """List all cards in a deck."""
    deck_path = _resolve_deck_path(deck)
    d = load_deck(deck_path)
    if not d.cards:
        typer.echo(_t("Empty deck."))
        return
    for c in d.cards:
        typer.echo(_format_card_line(c))


@app.command()
@_handle_core_errors
def search(
    query: str = typer.Argument(..., help="Substring to search for."),
    field: Optional[list[str]] = typer.Option(
        None,
        "--field",
        help="Restrict search to a field (repeatable): term / definition / notes.",
    ),
    case_sensitive: bool = typer.Option(
        False, "--case-sensitive", "-c", help="Match case exactly."
    ),
    deck: Optional[Path] = typer.Option(
        None, "--deck", "-d", help="Deck file path (overrides current deck)."
    ),
) -> None:
    """Search cards by substring match across term / definition / notes."""
    deck_path = _resolve_deck_path(deck)
    d = load_deck(deck_path)
    # Typer yields None (or possibly an empty list) when --field is unused;
    # normalize either to None so search_cards targets all fields.
    fields = list(field) if field else None
    try:
        matches = search_cards(
            d, query, fields=fields, case_sensitive=case_sensitive
        )
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)
    if not matches:
        typer.echo(_t("No matches found."))
        return
    for c in matches:
        typer.echo(_format_card_line(c))


@app.command()
@_handle_core_errors
def duplicates(
    case_sensitive: bool = typer.Option(
        False, "--case-sensitive", "-c", help="Treat differing case as distinct."
    ),
    deck: Optional[Path] = typer.Option(
        None, "--deck", "-d", help="Deck file path (overrides current deck)."
    ),
) -> None:
    """Find cards that share the same term."""
    deck_path = _resolve_deck_path(deck)
    d = load_deck(deck_path)
    groups = find_duplicates(d, case_sensitive=case_sensitive)
    if not groups:
        typer.echo(_t("No duplicates found."))
        return
    for index, group in enumerate(groups, start=1):
        typer.echo(_t("Group {n}").format(n=index) + ":")
        for c in group:
            typer.echo(f"  {_format_card_line(c)}")


@app.command(name="list-decks")
@_handle_core_errors
def list_decks_cmd() -> None:
    """List known decks (those under <home>/decks/ plus the current deck)."""
    dd = decks_dir()
    found: list[Path] = []
    if dd.is_dir():
        found.extend(sorted(dd.glob("*.json")))
    cfg = load_config()
    current = Path(cfg.current_deck) if cfg.current_deck else None
    if current is not None and current not in found and current.exists():
        found.append(current)
    if not found:
        typer.echo(_t("No decks found."))
        return
    for p in found:
        marker = "* " if current is not None and p == current else "  "
        typer.echo(f"{marker}{p}")


@app.command()
@_handle_core_errors
def use(
    path: Path = typer.Argument(..., help="Deck file path to mark as current."),
) -> None:
    """Set the current deck."""
    if not path.exists():
        typer.echo(
            _t("Deck not found: {path}").format(path=path),
            err=True,
        )
        raise typer.Exit(code=1)
    # Validate schema before recording the path.
    load_deck(path)
    cfg = load_config()
    cfg.current_deck = str(path)
    save_config(cfg)
    typer.echo(_t("Current deck: {path}").format(path=path))


class _QuizModeChoice(str, enum.Enum):
    """``--mode`` choices for the quiz command (Typer validates these)."""

    random = QUIZ_MODE_RANDOM
    weak = QUIZ_MODE_WEAK
    unreviewed = QUIZ_MODE_UNREVIEWED


# Per-mode message shown when no card is eligible to quiz on.
_NO_CARDS_MSGID = {
    QUIZ_MODE_RANDOM: "Empty deck.",
    QUIZ_MODE_WEAK: "No weak cards found.",
    QUIZ_MODE_UNREVIEWED: "No long-unreviewed cards found.",
}


@app.command()
@_handle_core_errors
def quiz(
    mode: Optional[_QuizModeChoice] = typer.Option(
        None,
        "--mode",
        help="Card-selection mode for this session only; defaults to the "
        "configured quiz_mode. Does not change the saved setting.",
    ),
    deck: Optional[Path] = typer.Option(
        None, "--deck", "-d", help="Deck file path (overrides current deck)."
    ),
) -> None:
    """Run an interactive quiz session on a deck.

    Cards are selected per ``--mode`` (or the configured ``quiz_mode``):
    ``random``, ``weak`` (low accuracy), or ``unreviewed`` (not reviewed
    for a while). Each round: the term is printed, the user presses Enter
    to reveal the definition (or ``q`` to quit), then enters ``y``/``n``/
    ``q`` to grade. ``q`` or Ctrl-C ends the session; partial statistics
    are saved either way before exit.
    """
    cfg = load_config()
    effective_mode = mode.value if mode is not None else cfg.quiz_mode

    deck_path = _resolve_deck_path(deck)
    d = load_deck(deck_path)

    def _pick() -> Card:
        if effective_mode == QUIZ_MODE_WEAK:
            return pick_next_weak(d, threshold_accuracy=cfg.weak_threshold)
        if effective_mode == QUIZ_MODE_UNREVIEWED:
            return pick_next_unreviewed(d, days_threshold=cfg.unreviewed_days)
        return pick_next(d)

    # Up-front eligibility check so the empty case gets a clear,
    # mode-specific message and exit code 1.
    try:
        _pick()
    except EmptyDeckError:
        typer.echo(_t(_NO_CARDS_MSGID[effective_mode]), err=True)
        raise typer.Exit(code=1)

    correct_count = 0
    wrong_count = 0
    interrupted = False

    try:
        while True:
            try:
                card = _pick()
            except EmptyDeckError:
                # The eligible set was exhausted mid-session (e.g. a weak
                # card's accuracy rose above the threshold). End cleanly.
                break
            typer.echo("")
            typer.echo(card.term)
            try:
                reveal = input(_t("[Enter to reveal, q to quit] "))
            except EOFError:
                break
            if reveal.strip().lower() == "q":
                typer.echo(_t("Quit?"))
                break
            typer.echo(card.definition)
            if card.notes:
                typer.echo(f"  ({card.notes})")
            try:
                response = input(_t("Correct? [y/n/q]: "))
            except EOFError:
                break
            r = response.strip().lower()
            if r == "q":
                typer.echo(_t("Quit?"))
                break
            if r == "y":
                record_correct(card)
                correct_count += 1
                typer.echo(_t("Correct!"))
            elif r == "n":
                record_wrong(card)
                wrong_count += 1
                typer.echo(_t("Wrong."))
            # other inputs: ignore and re-prompt next round
    except KeyboardInterrupt:
        interrupted = True
        typer.echo("")
        typer.echo(_t("Quit?"))
    finally:
        # Always persist whatever stats accumulated so far, even on
        # Ctrl-C, then surface the summary.
        save_deck(d, deck_path)
        _print_quiz_summary(correct_count, wrong_count)

    if interrupted:
        raise typer.Exit(code=130)


@app.command()
@_handle_core_errors
def stats(
    stale: bool = typer.Option(
        False,
        "--stale",
        help="Also list cards not reviewed for a long time.",
    ),
    deck: Optional[Path] = typer.Option(
        None, "--deck", "-d", help="Deck file path (overrides current deck)."
    ),
) -> None:
    """Print summary statistics for a deck.

    Shows totals, overall accuracy, and a review-freshness breakdown.
    With ``--stale`` it also lists long-unreviewed cards (using the
    configured ``unreviewed_days`` threshold).
    """
    deck_path = _resolve_deck_path(deck)
    d = load_deck(deck_path)
    s = deck_summary(d)
    typer.echo(_t("Total cards: {n}").format(n=s.total_cards))
    typer.echo(_t("Reviewed: {n}").format(n=s.reviewed_cards))
    if s.accuracy is None:
        typer.echo(_t("Accuracy: {p}").format(p="-"))
    else:
        typer.echo(_t("Accuracy: {p}").format(p=f"{s.accuracy * 100:.1f}%"))

    # Review-freshness breakdown.
    counts = count_by_review_freshness(d)
    typer.echo("")
    typer.echo(_t("Review freshness") + ":")
    for label_msgid, key in (
        ("Never reviewed", FRESHNESS_NEVER),
        ("Within a week", FRESHNESS_WITHIN_WEEK),
        ("Within a month", FRESHNESS_WITHIN_MONTH),
        ("Older than a month", FRESHNESS_STALE),
    ):
        typer.echo(f"  {_t(label_msgid)}: {counts[key]}")

    if stale:
        cfg = load_config()
        cards = list_stale_cards(d, days_threshold=cfg.unreviewed_days)
        typer.echo("")
        typer.echo(_t("Long unreviewed cards") + ":")
        if not cards:
            typer.echo(f"  {_t('No long-unreviewed cards found.')}")
        else:
            for c in cards:
                last = c.stats.last_reviewed
                last_str = last.strftime("%Y-%m-%d") if last else "-"
                typer.echo(f"  {c.term}  ->  {c.definition}  ({last_str})")


@app.command(name="export")
@_handle_core_errors
def export_cmd(
    destination: Path = typer.Argument(..., help="Destination file path."),
    strip_stats: bool = typer.Option(
        False,
        "--strip-stats/--no-strip-stats",
        help="Reset every card's learning statistics in the exported copy.",
    ),
    deck: Optional[Path] = typer.Option(
        None, "--deck", "-d", help="Deck file path (overrides current deck)."
    ),
) -> None:
    """Export a deck to ``destination``.

    With ``--strip-stats`` the exported copy has every card's review
    statistics reset (suitable for sharing); the default keeps them.
    """
    deck_path = _resolve_deck_path(deck)
    export_deck(deck_path, destination, strip_stats=strip_stats)
    typer.echo(_t("Exported to: {path}").format(path=destination))


@app.command(name="import")
@_handle_core_errors
def import_cmd(
    source: Path = typer.Argument(..., help="Source file path."),
    force: bool = typer.Option(
        False, "--force", help="Overwrite if the destination already exists."
    ),
) -> None:
    """Import a deck from ``source`` into <home>/decks/<deck-id>.json."""
    d = load_deck(source)
    dest = decks_dir() / f"{d.meta.id}.json"
    if dest.exists() and not force:
        typer.echo(
            _t("File already exists. Use --force to overwrite."),
            err=True,
        )
        raise typer.Exit(code=1)
    save_deck(d, dest)
    typer.echo(_t("Imported from: {path}").format(path=source))


if __name__ == "__main__":
    app()
