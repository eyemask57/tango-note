"""Stats tab: deck summary, review-freshness breakdown, per-card table,
and a long-unreviewed-cards table."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from tango_note.core.analytics import (
    FRESHNESS_NEVER,
    FRESHNESS_STALE,
    FRESHNESS_WITHIN_MONTH,
    FRESHNESS_WITHIN_WEEK,
)
from tango_note.core.config import load_config
from tango_note.gui import handlers


class StatsTab(ttk.Frame):
    """Deck summary + freshness breakdown + per-card and stale tables."""

    def __init__(self, parent: tk.Widget, detail) -> None:
        super().__init__(parent)
        self.detail = detail
        self.t = detail.t
        self._build()
        self.refresh()

    def _build(self) -> None:
        # Fixed text block: summary + review-freshness breakdown.
        self.summary_var = tk.StringVar(value="")
        ttk.Label(
            self,
            textvariable=self.summary_var,
            font=("TkTextFont", 12),
            justify="left",
        ).pack(side="top", anchor="w", padx=12, pady=(12, 4))

        ttk.Button(self, text=self.t("Refresh"), command=self.refresh).pack(
            side="top", anchor="w", padx=12, pady=(0, 8)
        )

        # Two stacked, labelled tables share the remaining space.
        body = ttk.Frame(self)
        body.pack(side="top", fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        per_card = ttk.Frame(body)
        per_card.grid(row=0, column=0, sticky="nsew", padx=8, pady=(0, 4))
        ttk.Label(per_card, text=self.t("Cards")).pack(side="top", anchor="w")
        self.tree = self._make_tree(
            per_card,
            (
                ("term", self.t("Term"), 160, "w"),
                ("definition", self.t("Definition"), 200, "w"),
                ("correct", self.t("Correct"), 80, "center"),
                ("wrong", self.t("Wrong"), 80, "center"),
                (
                    "accuracy",
                    self.t("Accuracy: {p}").format(p="").strip().rstrip(":"),
                    80,
                    "center",
                ),
            ),
        )

        stale = ttk.Frame(body)
        stale.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))
        ttk.Label(stale, text=self.t("Long unreviewed cards")).pack(
            side="top", anchor="w"
        )
        self.stale_tree = self._make_tree(
            stale,
            (
                ("term", self.t("Term"), 160, "w"),
                ("definition", self.t("Definition"), 220, "w"),
                ("last", self.t("Last reviewed"), 120, "center"),
            ),
        )
        self.stale_tree.bind("<Double-Button-1>", self._on_stale_edit)

    def _make_tree(self, parent: tk.Widget, columns) -> ttk.Treeview:
        """Build a Treeview with v/h scrollbars; return the Treeview.

        ``columns`` is a sequence of ``(col_id, heading, width, anchor)``.
        """
        frame = ttk.Frame(parent)
        frame.pack(side="top", fill="both", expand=True)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        col_ids = [c[0] for c in columns]
        tree = ttk.Treeview(frame, columns=col_ids, show="headings")
        for col_id, heading, width, anchor in columns:
            tree.heading(col_id, text=heading)
            tree.column(
                col_id, minwidth=60, width=width, anchor=anchor, stretch=True
            )
        vbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        return tree

    # ----- display ----------------------------------------------------------

    def refresh(self) -> None:
        deck = self.detail.deck
        s = handlers.deck_summary(deck)
        acc_str = "-" if s.accuracy is None else f"{s.accuracy * 100:.1f}%"
        counts = handlers.count_freshness_in_deck(deck)
        self.summary_var.set(
            "\n".join(
                [
                    self.t("Total cards: {n}").format(n=s.total_cards),
                    self.t("Reviewed: {n}").format(n=s.reviewed_cards),
                    self.t("Accuracy: {p}").format(p=acc_str),
                    "",
                    self.t("Review freshness") + ":",
                    f"  {self.t('Never reviewed')}: {counts[FRESHNESS_NEVER]}",
                    f"  {self.t('Within a week')}: {counts[FRESHNESS_WITHIN_WEEK]}",
                    f"  {self.t('Within a month')}: {counts[FRESHNESS_WITHIN_MONTH]}",
                    f"  {self.t('Older than a month')}: {counts[FRESHNESS_STALE]}",
                ]
            )
        )

        self.tree.delete(*self.tree.get_children())
        for c in deck.cards:
            acc = handlers.card_accuracy(c)
            row_acc = "-" if acc is None else f"{acc * 100:.1f}%"
            self.tree.insert(
                "",
                "end",
                values=(
                    c.term,
                    c.definition,
                    c.stats.correct,
                    c.stats.wrong,
                    row_acc,
                ),
            )

        self.stale_tree.delete(*self.stale_tree.get_children())
        days = load_config().unreviewed_days
        for c in handlers.list_stale_cards_in_deck(deck, days):
            last = c.stats.last_reviewed
            last_str = last.strftime("%Y-%m-%d") if last is not None else "-"
            self.stale_tree.insert(
                "", "end", iid=c.id, values=(c.term, c.definition, last_str)
            )

    # ----- editing from the stale table -------------------------------------

    def _on_stale_edit(self, _event) -> None:
        """Double-click a stale row to edit that card, then re-render."""
        sel = self.stale_tree.selection()
        if not sel:
            return
        card_id = sel[0]
        card = next(
            (c for c in self.detail.deck.cards if c.id == card_id), None
        )
        if card is None:
            return
        # Late import to avoid a circular import at module load.
        from tango_note.gui.screens.card_edit import CardDialog

        result = CardDialog(
            self, self.t, mode="edit", existing_card=card
        ).show()
        if result is None:
            return
        term, definition, notes = result
        handlers.update_card_in_deck(
            self.detail.deck, card_id, term, definition, notes
        )
        self.detail.mark_dirty()
        self.refresh()
