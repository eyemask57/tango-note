"""GUI smoke test.

Constructs the main window, walks through every screen by directly
invoking the navigation methods, then tears it down. The aim is only
to catch import errors and widget-tree assembly failures — interactive
behavior is verified manually.

Skipped automatically when:

* ``SKIP_GUI_TESTS=1`` is set (CI / explicit opt-out), or
* On Linux without a ``DISPLAY`` (headless).

Note: this is intentionally a single test rather than several. Python's
embedded Tcl can fail to re-initialize after a ``Tk()`` instance is
destroyed within the same process (``Can't find a usable init.tcl``),
so we keep to one ``Tk()`` per pytest invocation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_GUI_TESTS") == "1"
    or (sys.platform.startswith("linux") and not os.environ.get("DISPLAY")),
    reason="GUI smoke test requires a display environment",
)


def test_mainwindow_walks_all_screens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Build the window, navigate every screen, then destroy."""
    monkeypatch.setenv("TANGO_NOTE_HOME", str(tmp_path))

    # Pre-seed a deck so the deck-list isn't empty and detail navigation
    # has a real path to load.
    from tango_note.gui import handlers

    _, deck_path = handlers.create_deck("SmokeDeck")
    deck = handlers.load_deck(deck_path)
    handlers.add_card_to_deck(deck, "bonjour", "こんにちは", notes="朝の挨拶")
    handlers.save_deck(deck, deck_path)

    from tango_note.core.i18n import setup_i18n
    from tango_note.gui.app import MainWindow

    translator = setup_i18n("ja")
    window = MainWindow(translator=translator)
    try:
        # Realize the deck-list screen.
        window.root.update_idletasks()

        # The window icon was swapped from Tk's default feather to the
        # tango-note logo. The PhotoImage must be retained on the instance
        # so it is not garbage-collected (which would revert the icon).
        import tkinter as tk

        assert window._app_icon is not None
        assert isinstance(window._app_icon, tk.PhotoImage)

        # Navigate into the deck-detail tabbed view (cards / quiz / stats).
        window.show_deck_detail(deck_path)
        window.root.update_idletasks()

        # CardDialog must keep keyboard focus navigable: the notes Text
        # widget rebinds Tab / Shift-Tab to move focus rather than insert
        # a tab character. Assert those bindings exist (actual focus
        # traversal is verified manually). One Tk() per process, so this
        # piggybacks on the smoke test rather than being its own test.
        from tango_note.core.models import Card
        from tango_note.gui.screens import card_edit
        from tango_note.gui.screens.card_edit import CardDialog

        detail = window._current_screen

        # --- edit-mode CardDialog: tab bindings + result/return -------------
        existing = detail.deck.cards[0]
        dialog = CardDialog(
            detail.card_tab, translator, mode="edit", existing_card=existing
        )
        window.root.update_idletasks()
        assert dialog.notes_text.bind("<Tab>") != ""
        assert dialog.notes_text.bind("<Shift-Tab>") != ""
        # Edit OK returns the (term, definition, notes) tuple.
        dialog.term_var.set("EDITED")
        dialog._on_ok()
        assert dialog.result == ("EDITED", existing.definition, existing.notes)

        # Edit OK with an empty term must be rejected (result stays None).
        dialog2 = CardDialog(
            detail.card_tab, translator, mode="edit", existing_card=existing
        )
        window.root.update_idletasks()
        dialog2.term_var.set("   ")
        dialog2._on_ok()
        assert dialog2.result is None
        dialog2.destroy()

        # --- add-mode CardDialog: continuous entry -------------------------
        added: list[Card] = []
        add_dialog = CardDialog(
            detail.card_tab,
            translator,
            mode="add",
            deck=detail.deck,
            on_card_added=added.append,
        )
        window.root.update_idletasks()
        deck_size_before = len(detail.deck.cards)

        add_dialog.term_var.set("hola")
        add_dialog.def_var.set("こんにちは")
        add_dialog.notes_text.insert("1.0", "greeting")
        add_dialog._on_add_clicked()
        # The card was created and reported; the deck grew by one.
        assert len(added) == 1
        assert isinstance(added[0], Card)
        assert added[0].term == "hola"
        assert len(detail.deck.cards) == deck_size_before + 1
        # Fields cleared and the counter advanced.
        assert add_dialog.term_var.get() == ""
        assert add_dialog.def_var.get() == ""
        assert add_dialog.notes_text.get("1.0", "end-1c") == ""
        assert add_dialog._added_count == 1
        assert "1" in add_dialog.title()

        # An empty term must be rejected without creating a card.
        monkeypatch.setattr(card_edit.messagebox, "showwarning", lambda *a, **k: None)
        add_dialog.term_var.set("   ")
        add_dialog._on_add_clicked()
        assert len(added) == 1  # unchanged
        assert add_dialog._added_count == 1
        add_dialog.destroy()

        # --- CardEditTab._insert_card_row adds one Treeview row ------------
        rows_before = len(detail.card_tab.tree.get_children())
        detail.card_tab._insert_card_row(added[0])
        assert len(detail.card_tab.tree.get_children()) == rows_before + 1

        # The menu bar and its accelerators live on the root window and
        # must persist across screen swaps.
        assert window.root.cget("menu") != ""
        assert window.root.bind_all("<Control-q>") != ""
        assert window.root.bind_all("<Control-comma>") != ""

        # SettingsDialog: built directly (not via _open_settings, which
        # blocks on wait_window). Verify it reflects config and persists.
        from tango_note.core.config import AppConfig, load_config
        from tango_note.gui.screens.settings import SettingsDialog

        settings = SettingsDialog(
            window.root,
            translator,
            AppConfig(
                export_default="ask", weak_threshold=0.7, unreviewed_days=30
            ),
        )
        window.root.update_idletasks()
        assert settings.export_var.get() == "ask"
        # Quiz tuning fields reflect the config (0.7 -> "70", 30 -> "30").
        assert settings.weak_var.get() == "70"
        assert settings.days_var.get() == "30"
        settings.export_var.set("strip")
        settings.weak_var.set("55")
        settings.days_var.set("14")
        assert settings._persist() is True
        reloaded = load_config()
        assert reloaded.export_default == "strip"
        assert reloaded.weak_threshold == 0.55
        assert reloaded.unreviewed_days == 14
        settings.destroy()

        # --- QuizTab: mode radios persist to config ------------------------
        from tango_note.core.config import QUIZ_MODE_WEAK
        from tango_note.gui.screens import quiz as quiz_mod  # noqa: F401

        quiz_tab = detail.quiz_tab
        assert quiz_tab.mode_var.get() in (
            "random",
            "weak",
            "unreviewed",
        )
        quiz_tab.mode_var.set(QUIZ_MODE_WEAK)
        quiz_tab._on_mode_change()
        assert quiz_tab._mode == QUIZ_MODE_WEAK
        assert load_config().quiz_mode == QUIZ_MODE_WEAK

        # --- StatsTab: freshness summary + stale table ---------------------
        stats_tab = detail.stats_tab
        stats_tab.refresh()
        assert "復習頻度" in stats_tab.summary_var.get()
        # The deck's pre-seeded never-reviewed card shows up as stale.
        assert len(stats_tab.stale_tree.get_children()) >= 1

        # --- unsaved-changes indicators (Save button + window title) -------
        card_tab = detail.card_tab
        # Direct method behavior.
        card_tab._update_save_button_state(True)
        assert card_tab.save_btn.cget("style") == "Dirty.TButton"
        assert card_tab.save_btn.cget("text").endswith("*")
        card_tab._update_save_button_state(False)
        assert card_tab.save_btn.cget("style") == "TButton"
        assert not card_tab.save_btn.cget("text").endswith("*")

        window._update_window_title(dirty=True)
        assert window.root.title().endswith(" *")
        window._update_window_title(dirty=False)
        assert not window.root.title().endswith(" *")

        # End-to-end: marking the deck dirty must light up both indicators,
        # and saving must clear them again.
        detail.mark_dirty()
        assert detail.dirty is True
        assert card_tab.save_btn.cget("style") == "Dirty.TButton"
        assert window.root.title().endswith(" *")
        detail.save_now()
        assert detail.dirty is False
        assert card_tab.save_btn.cget("style") == "TButton"
        assert not window.root.title().endswith(" *")

        # Back out to the deck list.
        window.show_deck_list()
        window.root.update_idletasks()
        # The deck-list screen carries no deck name and no asterisk.
        assert window.root.title() == "tango-note"
    finally:
        window.root.destroy()


def test_locate_icon_resolves_to_an_existing_file() -> None:
    """``_locate_icon`` finds the app-icon PNG in this source checkout.

    Run from the repo (editable layout), the editable-layout branch must
    resolve ``installer/tango-note_source.png``. The function is Tk-free,
    so it needs no display — it lives here next to the GUI smoke test
    only because it exercises ``tango_note.gui.app``.
    """
    from tango_note.gui.app import _locate_icon

    path = _locate_icon()
    assert path is not None
    assert path.is_file()
