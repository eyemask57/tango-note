"""Card-edit tab: search / list / add / delete / edit / export cards."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from tango_note.core.config import (
    EXPORT_DEFAULT_INCLUDE,
    EXPORT_DEFAULT_STRIP,
    load_config,
)
from tango_note.core.models import Card
from tango_note.core.search import find_duplicates, search_cards
from tango_note.gui import handlers
from tango_note.gui.utils import center_on_parent

# Characters that are illegal in Windows file names.
_ILLEGAL_FILENAME_CHARS = '<>:"/\\|?*'


def _resolve_strip_stats(
    export_default: str,
    ask_callback: Callable[[], Optional[bool]],
) -> Optional[bool]:
    """Decide whether to strip stats on export from the config setting.

    Args:
        export_default: The user's configured default — one of
            ``"strip"``, ``"include"``, or ``"ask"``.
        ask_callback: Called only in the ``"ask"`` path (or for any
            unrecognized value); returns ``True``/``False``/``None``.

    Returns:
        ``True`` to strip stats, ``False`` to include them, or ``None``
        when the user cancelled (only reachable via ``ask_callback``).

    Pure and Tk-free so it can be unit-tested without a display.
    """
    if export_default == EXPORT_DEFAULT_STRIP:
        return True
    if export_default == EXPORT_DEFAULT_INCLUDE:
        return False
    return ask_callback()


def _sanitize_filename(name: str) -> str:
    """Make ``name`` safe to use as a filename stem.

    Trims surrounding whitespace and replaces every character that is
    illegal in a Windows file name (``< > : " / \\ | ? *``) with an
    underscore. Falls back to ``"deck"`` if nothing usable remains, so
    the export dialog always has a non-empty default filename.
    """
    cleaned = name.strip()
    for ch in _ILLEGAL_FILENAME_CHARS:
        cleaned = cleaned.replace(ch, "_")
    cleaned = cleaned.strip()
    return cleaned or "deck"


def _format_notes_for_treeview(notes: str) -> str:
    """Collapse multi-line notes to ``first line ...`` for a Treeview cell.

    Kept deliberately separate from the CLI's one-line notes formatter:
    this one serves a fixed-width GUI table cell while the CLI's serves
    terminal output, so the two presentation concerns may diverge later
    without coupling.
    """
    if "\n" not in notes:
        return notes
    return notes.split("\n", 1)[0] + " ..."


class CardEditTab(ttk.Frame):
    """Treeview of all cards with a live search bar plus edit buttons.

    Behavior while a search query is active:

    * **Delete is disabled** — the selection is a subset of the deck, so
      deleting from a filtered view is error-prone.
    * **Add stays enabled** — blocking it would break the continuous-add
      workflow. A card added while a filter is active is inserted into
      the table directly (even if it does not match the filter) so it is
      never silently invisible; the add dialog also shows a note. Such a
      card will, however, be filtered out on the next ``refresh()``.
    * Editing an existing card (double-click) stays available since it
      does not change the card set.
    """

    def __init__(self, parent: tk.Widget, detail) -> None:
        super().__init__(parent)
        self.detail = detail
        self.t = detail.t
        self._search_query = ""
        self._build()
        self.refresh()
        # Keep the Save button in sync with the deck's dirty state.
        detail.add_dirty_listener(self._update_save_button_state)
        self._update_save_button_state(detail.dirty)

    def _build(self) -> None:
        # --- search bar ------------------------------------------------------
        search_bar = ttk.Frame(self)
        search_bar.pack(side="top", fill="x", padx=8, pady=(8, 0))
        ttk.Label(search_bar, text=self.t("Search:")).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_bar, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=4)
        self.search_entry.bind("<KeyRelease>", self._on_search_key)
        ttk.Button(
            search_bar, text=self.t("Duplicates"), command=self._on_duplicates
        ).pack(side="right")

        # --- body: treeview + buttons ---------------------------------------
        body = ttk.Frame(self)
        body.pack(side="top", fill="both", expand=True)

        # Fixed-width button column on the right, packed first so it keeps
        # its space; the tree area takes the rest and expands.
        btns = ttk.Frame(body)
        btns.pack(side="right", fill="y", padx=8, pady=8)
        self.add_btn = ttk.Button(
            btns, text=self.t("Add card"), command=self._on_add
        )
        self.add_btn.pack(fill="x", pady=4)
        self.delete_btn = ttk.Button(
            btns, text=self.t("Delete card"), command=self._on_delete
        )
        self.delete_btn.pack(fill="x", pady=4)

        # Highlight the Save button when the deck has unsaved changes.
        # Only the text *foreground* is restyled, never the background:
        # on the Windows "vista" ttk theme a Button's background is drawn
        # by the native renderer and ignores style.configure, whereas the
        # text foreground is honored on every theme. The button text also
        # gains a trailing " *", so the unsaved state stays clear even on
        # a theme that ignored the color too.
        ttk.Style().configure("Dirty.TButton", foreground="#cc3300")
        self.save_btn = ttk.Button(
            btns, text=self.t("Save"), command=self._on_save
        )
        self.save_btn.pack(fill="x", pady=(20, 4))
        ttk.Button(btns, text=self.t("Export"), command=self._on_export).pack(
            fill="x", pady=4
        )

        # Tree area: grid so the Treeview can carry both scrollbars and
        # still expand on resize.
        tree_frame = ttk.Frame(body)
        tree_frame.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        cols = ("term", "definition", "notes", "accuracy")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        self.tree.heading("term", text=self.t("Term"))
        self.tree.heading("definition", text=self.t("Definition"))
        self.tree.heading("notes", text=self.t("Notes"))
        self.tree.heading(
            "accuracy",
            text=self.t("Accuracy: {p}").format(p="").strip().rstrip(":"),
        )
        # minwidth + stretch lets columns grow/shrink with the window
        # instead of being pinned to a fixed pixel width.
        self.tree.column("term", minwidth=80, width=160, stretch=True)
        self.tree.column("definition", minwidth=100, width=200, stretch=True)
        self.tree.column("notes", minwidth=100, width=200, stretch=True)
        self.tree.column(
            "accuracy", minwidth=60, width=80, anchor="center", stretch=True
        )
        vbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hbar = ttk.Scrollbar(
            tree_frame, orient="horizontal", command=self.tree.xview
        )
        self.tree.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")

        self.tree.bind("<Double-Button-1>", self._on_edit)

    # ----- display ----------------------------------------------------------

    def _insert_card_row(self, card: Card) -> None:
        """Insert one card as a Treeview row (keyed by ``card.id``)."""
        acc = handlers.card_accuracy(card)
        acc_str = f"{acc * 100:.1f}%" if acc is not None else "-"
        self.tree.insert(
            "",
            "end",
            iid=card.id,
            values=(
                card.term,
                card.definition,
                _format_notes_for_treeview(card.notes),
                acc_str,
            ),
        )

    def refresh(self) -> None:
        """Repopulate the table, honoring the current search filter."""
        self.tree.delete(*self.tree.get_children())
        query = self._search_query.strip()
        if query:
            # Filter the in-memory deck (which may hold unsaved edits) —
            # not the on-disk copy.
            cards = search_cards(self.detail.deck, query)
        else:
            cards = self.detail.deck.cards
        for c in cards:
            self._insert_card_row(c)

    def _update_button_states(self) -> None:
        """Disable Delete while a search filter is active.

        Add stays enabled even while filtering so the continuous-add
        workflow is never blocked; Delete is disabled because deleting
        from a filtered (subset) view is error-prone.
        """
        filtering = bool(self._search_query.strip())
        self.delete_btn.configure(state="disabled" if filtering else "normal")

    def _update_save_button_state(self, dirty: bool) -> None:
        """Reflect the deck's dirty state on the Save button.

        Registered as a dirty-state listener on the ``DeckDetailScreen``,
        so it fires on every add / edit / delete / save. See ``_build``
        for why only the foreground color (plus a trailing " *") is used.
        """
        if dirty:
            self.save_btn.configure(
                style="Dirty.TButton", text=self.t("Save *")
            )
        else:
            self.save_btn.configure(style="TButton", text=self.t("Save"))

    # ----- search bar -------------------------------------------------------

    def _on_search_key(self, _event) -> None:
        self._search_query = self.search_var.get()
        self.refresh()
        self._update_button_states()

    def _on_duplicates(self) -> None:
        groups = find_duplicates(self.detail.deck)
        if not groups:
            messagebox.showinfo(
                self.t("Duplicates"), self.t("No duplicates found.")
            )
            return
        DuplicatesDialog(self, self.t, groups).show()

    def _on_export(self) -> None:
        """Export the whole deck to a user-chosen JSON file.

        Export always writes the *entire* deck as stored on disk, never
        the currently filtered/visible subset — an active search filter
        only affects what the table displays, not what is exported.

        Whether learning statistics are stripped depends on the user's
        ``export_default`` preference: ``"strip"`` / ``"include"`` apply
        silently, ``"ask"`` shows a Yes/No/Cancel dialog. The config is
        re-read on every export so a change made in the Preferences
        dialog takes effect immediately, without restarting the app.
        """
        default_name = _sanitize_filename(self.detail.deck.meta.name) + ".json"
        dest = filedialog.asksaveasfilename(
            title=self.t("Export deck"),
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            confirmoverwrite=True,
        )
        if not dest:  # user cancelled the file dialog
            return

        def _ask() -> Optional[bool]:
            return messagebox.askyesnocancel(
                self.t("Strip learning statistics?"),
                self.t(
                    "Choose 'Yes' to export without stats (suitable for "
                    "sharing), 'No' to include stats."
                ),
            )

        strip = _resolve_strip_stats(load_config().export_default, _ask)
        if strip is None:  # Cancel (only possible in the "ask" path)
            return

        try:
            handlers.export_deck_to_path(
                self.detail.deck_path, Path(dest), strip_stats=strip
            )
        except Exception as e:  # noqa: BLE001 (surface any failure to the user)
            messagebox.showerror(
                self.t("Export deck"),
                self.t("Export failed: {detail}").format(detail=str(e)),
            )
            return

        messagebox.showinfo(
            self.t("Export deck"),
            self.t("Export complete: {path}").format(path=dest),
        )

    # ----- button handlers --------------------------------------------------

    def _on_add(self) -> None:
        """Open the continuous-add dialog.

        The dialog stays open for repeated entry; each added card is
        reported via ``on_card_added``, which marks the deck dirty and
        inserts the row directly. The table is intentionally NOT
        refreshed after the dialog closes, so cards added while a search
        filter is active remain visible for the rest of the session.
        """

        def on_card_added(new_card: Card) -> None:
            self.detail.mark_dirty()
            self._insert_card_row(new_card)

        CardDialog(
            self,
            self.t,
            mode="add",
            deck=self.detail.deck,
            on_card_added=on_card_added,
            search_active=bool(self._search_query.strip()),
        ).show()

    def _on_delete(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        if not messagebox.askyesno(
            self.t("Are you sure?"),
            self.t("Delete card"),
        ):
            return
        for iid in sel:
            handlers.delete_card_from_deck(self.detail.deck, iid)
        self.detail.mark_dirty()
        self.refresh()

    def _on_edit(self, _event) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        card_id = sel[0]
        card = next((c for c in self.detail.deck.cards if c.id == card_id), None)
        if card is None:
            return
        result = CardDialog(
            self,
            self.t,
            mode="edit",
            existing_card=card,
        ).show()
        if result is None:
            return
        term, definition, notes = result
        handlers.update_card_in_deck(
            self.detail.deck, card_id, term, definition, notes
        )
        self.detail.mark_dirty()
        self.refresh()

    def _on_save(self) -> None:
        self.detail.save_now()


class DuplicatesDialog(tk.Toplevel):
    """Modal dialog showing duplicate-term groups as a tree."""

    def __init__(
        self,
        parent: tk.Widget,
        translator,
        groups: list[list[Card]],
    ) -> None:
        super().__init__(parent)
        self.t = translator
        self.title(self.t("Duplicate groups"))
        self._parent_window = parent.winfo_toplevel()
        self.transient(self._parent_window)
        self._groups = groups
        self._build()
        self.after(50, self._position_and_grab)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _position_and_grab(self) -> None:
        center_on_parent(self, self._parent_window)
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _build(self) -> None:
        # Button row first (fixed), then the expanding tree area.
        ttk.Button(self, text=self.t("Close"), command=self.destroy).pack(
            side="bottom", pady=8
        )

        tree_frame = ttk.Frame(self)
        tree_frame.pack(side="top", fill="both", expand=True, padx=8, pady=8)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        tree = ttk.Treeview(tree_frame, show="tree")
        vbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        hbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")

        for index, group in enumerate(self._groups, start=1):
            group_id = tree.insert(
                "", "end", text=self.t("Group {n}").format(n=index), open=True
            )
            for card in group:
                tree.insert(
                    group_id, "end", text=f"{card.term}  ->  {card.definition}"
                )

    def show(self) -> None:
        self.wait_window(self)


class CardDialog(tk.Toplevel):
    """Modal dialog for adding or editing one card.

    Two modes:

    * ``mode="edit"`` — opened by double-click on a row. Fill in, OK,
      dialog closes; ``show()`` returns the ``(term, definition, notes)``
      tuple (or ``None`` if cancelled). Unchanged legacy behavior.
    * ``mode="add"`` — opened by the "Add card" button. The dialog stays
      open for continuous entry: each "Add" appends a card, clears the
      fields, refocuses the term field, and bumps a counter shown in the
      title bar. Added cards are reported through the ``on_card_added``
      callback. Closed via the "Close" button.

    ``term`` and ``definition`` are single-line ``Entry`` widgets;
    ``notes`` is a multi-line ``Text`` widget so newlines are preserved.
    """

    def __init__(
        self,
        parent: tk.Widget,
        translator,
        *,
        mode: str = "edit",
        existing_card: Optional[Card] = None,
        deck=None,
        on_card_added: Optional[Callable[[Card], None]] = None,
        search_active: bool = False,
    ) -> None:
        super().__init__(parent)
        self.t = translator
        self.resizable(False, False)
        self._parent_window = parent.winfo_toplevel()
        self.transient(self._parent_window)

        self._mode = mode
        self._deck = deck
        self._on_card_added = on_card_added
        self._search_active = search_active
        self._added_count = 0
        # Edit mode reports its outcome through ``result``; add mode
        # reports each card through ``on_card_added`` and leaves this None.
        self.result: Optional[tuple[str, str, str]] = None
        if existing_card is not None:
            self._initial = (
                existing_card.term,
                existing_card.definition,
                existing_card.notes,
            )
        else:
            self._initial = ("", "", "")

        if self._mode == "add":
            self._update_title()
        else:
            self.title(self.t("Term"))  # pre-existing edit-mode title

        self._build()
        self._bind_keys()
        self.after(50, self._position_and_grab)
        self.protocol(
            "WM_DELETE_WINDOW",
            self._on_close if self._mode == "add" else self._on_cancel,
        )
        if self._mode == "add":
            self.term_entry.focus_set()

    def _update_title(self) -> None:
        """Refresh the add-mode title bar with the running added count."""
        self.title(
            self.t("Add card ({n} added)").format(n=self._added_count)
        )

    def _bind_keys(self) -> None:
        """Bind Ctrl+Enter (submit) and Escape (close) per mode.

        Plain Enter is intentionally left unbound so that pressing it in
        the term/definition fields never triggers a submit by accident.
        """
        if self._mode == "add":
            self.bind("<Control-Return>", lambda _e: self._on_add_clicked())
            self.bind("<Escape>", lambda _e: self._on_close())
        else:
            self.bind("<Control-Return>", lambda _e: self._on_ok())
            self.bind("<Escape>", lambda _e: self._on_cancel())

    def _position_and_grab(self) -> None:
        center_on_parent(self, self._parent_window)
        try:
            self.grab_set()
        except tk.TclError:
            pass

    @staticmethod
    def _focus_next(event: tk.Event) -> str:
        """Move focus to the next widget (used to override Text's Tab)."""
        event.widget.tk_focusNext().focus()
        return "break"  # suppress the literal tab character insertion

    @staticmethod
    def _focus_prev(event: tk.Event) -> str:
        """Move focus to the previous widget (Shift+Tab on the Text)."""
        event.widget.tk_focusPrev().focus()
        return "break"

    def _build(self) -> None:
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text=self.t("Term")).grid(row=0, column=0, sticky="w", pady=4)
        self.term_var = tk.StringVar(value=self._initial[0])
        self.term_entry = ttk.Entry(body, textvariable=self.term_var, width=36)
        self.term_entry.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(body, text=self.t("Definition")).grid(
            row=1, column=0, sticky="w", pady=4
        )
        self.def_var = tk.StringVar(value=self._initial[1])
        ttk.Entry(body, textvariable=self.def_var, width=36).grid(
            row=1, column=1, sticky="ew", pady=4
        )

        ttk.Label(body, text=self.t("Notes")).grid(
            row=2, column=0, sticky="nw", pady=4
        )
        notes_frame = ttk.Frame(body)
        notes_frame.grid(row=2, column=1, sticky="ew", pady=4)
        self.notes_text = tk.Text(notes_frame, width=36, height=4, wrap="word")
        notes_scroll = ttk.Scrollbar(
            notes_frame, orient="vertical", command=self.notes_text.yview
        )
        self.notes_text.configure(yscrollcommand=notes_scroll.set)
        self.notes_text.pack(side="left", fill="both", expand=True)
        notes_scroll.pack(side="right", fill="y")
        # A Text widget eats Tab as a literal character by default, which
        # traps keyboard focus. Rebind Tab / Shift+Tab to move focus so
        # the dialog stays keyboard-navigable (term -> definition ->
        # notes -> OK). A real tab character can still be inserted with
        # Ctrl+Tab, which is Tk's built-in behavior.
        self.notes_text.bind("<Tab>", self._focus_next)
        self.notes_text.bind("<Shift-Tab>", self._focus_prev)
        if self._initial[2]:
            self.notes_text.insert("1.0", self._initial[2])

        # Add mode: warn if a search filter is active in the list, since a
        # newly added card may not match it once the list is refreshed.
        if self._mode == "add" and self._search_active:
            ttk.Label(
                self,
                text=self.t(
                    "A search filter is active; new cards may be hidden "
                    "after the list refreshes."
                ),
                foreground="gray",
                wraplength=320,
                justify="left",
                padding=(12, 0),
            ).pack(fill="x")

        btns = ttk.Frame(self, padding=(12, 0, 12, 12))
        btns.pack(fill="x")
        if self._mode == "add":
            ttk.Button(
                btns, text=self.t("Add"), command=self._on_add_clicked
            ).pack(side="right")
            ttk.Button(
                btns, text=self.t("Close"), command=self._on_close
            ).pack(side="right", padx=6)
        else:
            ttk.Button(btns, text="OK", command=self._on_ok).pack(side="right")
            ttk.Button(
                btns, text=self.t("Cancel"), command=self._on_cancel
            ).pack(side="right", padx=6)

    def _read_notes(self) -> str:
        # Tk's Text widget always keeps a trailing newline that the user
        # never typed; "end-1c" means "end of text minus 1 char", which
        # drops exactly that auto-appended newline. Notes are otherwise
        # kept verbatim (no strip()) so intentional blank lines survive.
        return self.notes_text.get("1.0", "end-1c")

    def _clear_fields(self) -> None:
        self.term_var.set("")
        self.def_var.set("")
        self.notes_text.delete("1.0", "end")

    # ----- add mode ---------------------------------------------------------

    def _on_add_clicked(self) -> None:
        """Append one card and keep the dialog open for the next entry."""
        term = self.term_var.get().strip()
        if not term:
            messagebox.showwarning(
                self.t("Add card"), self.t("Term cannot be empty.")
            )
            self.term_entry.focus_set()
            return
        definition = self.def_var.get().strip()
        notes = self._read_notes()
        card = handlers.add_card_to_deck(self._deck, term, definition, notes)
        if self._on_card_added is not None:
            self._on_card_added(card)
        self._clear_fields()
        self.term_entry.focus_set()
        self._added_count += 1
        self._update_title()

    def _on_close(self) -> None:
        self.destroy()

    # ----- edit mode --------------------------------------------------------

    def _on_ok(self) -> None:
        term = self.term_var.get().strip()
        definition = self.def_var.get().strip()
        notes = self._read_notes()
        if not term or not definition:
            return
        self.result = (term, definition, notes)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def show(self) -> Optional[tuple[str, str, str]]:
        self.wait_window(self)
        return self.result
