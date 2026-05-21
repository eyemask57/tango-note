"""Quiz tab: present a card per the chosen mode, reveal, grade y/n.

The card-selection mode (random / weak-first / long-unreviewed) is
chosen with radio buttons at the top and persisted to the user config,
so it is restored on the next launch. Quiz grades auto-save after each
tap so the user never loses progress.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

from tango_note.core.config import (
    QUIZ_MODE_RANDOM,
    QUIZ_MODE_UNREVIEWED,
    QUIZ_MODE_WEAK,
    load_config,
)
from tango_note.core.exceptions import EmptyDeckError
from tango_note.core.models import Card
from tango_note.gui import handlers

# Message shown (in place of a term) when no card is eligible per mode.
_NO_CARDS_MSGID = {
    QUIZ_MODE_RANDOM: "Empty deck.",
    QUIZ_MODE_WEAK: "No weak cards found.",
    QUIZ_MODE_UNREVIEWED: "No long-unreviewed cards found.",
}


class QuizTab(ttk.Frame):
    """One-card-at-a-time review widget with a selectable quiz mode."""

    def __init__(self, parent: tk.Widget, detail) -> None:
        super().__init__(parent)
        self.detail = detail
        self.t = detail.t
        self._current_card: Optional[Card] = None
        self._revealed = False
        self._mode = load_config().quiz_mode
        self._build()
        self._next_card()

    def _build(self) -> None:
        self.term_var = tk.StringVar(value="")
        self.def_var = tk.StringVar(value="")
        self.notes_var = tk.StringVar(value="")

        # Mode selector, fixed at the top.
        mode_bar = ttk.Frame(self)
        mode_bar.pack(side="top", fill="x", padx=12, pady=(10, 0))
        ttk.Label(mode_bar, text=self.t("Quiz mode") + ":").pack(side="left")
        self.mode_var = tk.StringVar(value=self._mode)
        for value, label in (
            (QUIZ_MODE_RANDOM, "Random"),
            (QUIZ_MODE_WEAK, "Weak first"),
            (QUIZ_MODE_UNREVIEWED, "Long unreviewed"),
        ):
            ttk.Radiobutton(
                mode_bar,
                text=self.t(label),
                value=value,
                variable=self.mode_var,
                command=self._on_mode_change,
            ).pack(side="left", padx=6)

        # Two equal-weight spacer frames above and below the content keep
        # the quiz block vertically centered as the window grows.
        ttk.Frame(self).pack(side="top", fill="both", expand=True)

        self.term_label = ttk.Label(
            self,
            textvariable=self.term_var,
            anchor="center",
            font=("TkHeadingFont", 24),
            wraplength=600,
        )
        self.term_label.pack(side="top", fill="x", padx=16, pady=(0, 16))

        self.def_label = ttk.Label(
            self,
            textvariable=self.def_var,
            anchor="center",
            font=("TkTextFont", 18),
            wraplength=600,
        )
        self.def_label.pack(side="top", fill="x", padx=16, pady=8)

        self.notes_label = ttk.Label(
            self,
            textvariable=self.notes_var,
            anchor="center",
            font=("TkTextFont", 11),
            foreground="gray",
            wraplength=600,
        )
        self.notes_label.pack(side="top", fill="x", padx=16, pady=4)

        btns = ttk.Frame(self)
        btns.pack(side="top", pady=24)
        self.reveal_btn = ttk.Button(
            btns, text=self.t("Show answer"), command=self._on_reveal
        )
        self.reveal_btn.pack(side="left", padx=8)
        self.correct_btn = ttk.Button(
            btns, text=self.t("Correct"), command=self._on_correct, state="disabled"
        )
        self.correct_btn.pack(side="left", padx=8)
        self.wrong_btn = ttk.Button(
            btns, text=self.t("Wrong"), command=self._on_wrong, state="disabled"
        )
        self.wrong_btn.pack(side="left", padx=8)

        ttk.Frame(self).pack(side="top", fill="both", expand=True)

    # ----- public API used by DeckDetailScreen ------------------------------

    def refresh_if_needed(self) -> None:
        """Re-pick a card if the current one was deleted from the deck."""
        if self._current_card is None:
            self._next_card()
            return
        if self._current_card not in self.detail.deck.cards:
            self._next_card()

    # ----- mode selection ---------------------------------------------------

    def _on_mode_change(self) -> None:
        """Persist the chosen mode and immediately re-pick a card."""
        self._mode = self.mode_var.get()
        handlers.set_quiz_mode(self._mode)
        self._next_card()

    # ----- session logic ----------------------------------------------------

    def _next_card(self) -> None:
        # Reload config so weak / unreviewed thresholds changed in the
        # Preferences dialog take effect on the next card.
        cfg = load_config()
        try:
            self._current_card = handlers.pick_next_card_by_mode(
                self.detail.deck, self._mode, cfg
            )
        except EmptyDeckError:
            self._current_card = None
            self.term_var.set(self.t(_NO_CARDS_MSGID[self._mode]))
            self.def_var.set("")
            self.notes_var.set("")
            self.reveal_btn.configure(state="disabled")
            self.correct_btn.configure(state="disabled")
            self.wrong_btn.configure(state="disabled")
            return
        self._revealed = False
        self.term_var.set(self._current_card.term)
        self.def_var.set("")
        self.notes_var.set("")
        self.reveal_btn.configure(state="normal")
        self.correct_btn.configure(state="disabled")
        self.wrong_btn.configure(state="disabled")

    def _on_reveal(self) -> None:
        if self._current_card is None:
            return
        self.def_var.set(self._current_card.definition)
        self.notes_var.set(self._current_card.notes)
        self._revealed = True
        self.reveal_btn.configure(state="disabled")
        self.correct_btn.configure(state="normal")
        self.wrong_btn.configure(state="normal")

    def _on_correct(self) -> None:
        if self._current_card is None or not self._revealed:
            return
        handlers.record_correct(self._current_card)
        self.detail.mark_dirty()
        self.detail.save_now()
        self._next_card()

    def _on_wrong(self) -> None:
        if self._current_card is None or not self._revealed:
            return
        handlers.record_wrong(self._current_card)
        self.detail.mark_dirty()
        self.detail.save_now()
        self._next_card()
