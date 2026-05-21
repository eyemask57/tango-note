"""Deck-list screen: pick / create / import a deck."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from tango_note.gui import handlers
from tango_note.gui.utils import center_on_parent


class DeckListScreen(ttk.Frame):
    """First screen: lists known decks; provides new / import / select."""

    def __init__(self, parent: tk.Widget, app) -> None:
        super().__init__(parent)
        self.app = app
        self.t = app.t
        self._entries: list[handlers.DeckEntry] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        # Pack fixed-height regions (header, button row) before the
        # expanding list so they always keep their space when the window
        # is resized down to the minimum.
        header = ttk.Label(
            self,
            text=self.t("Deck list"),
            font=("TkHeadingFont", 14, "bold"),
        )
        header.pack(side="top", anchor="w", padx=12, pady=(12, 4))

        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", padx=12, pady=8)
        ttk.Button(bottom, text=self.t("New deck"), command=self._on_new).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(bottom, text=self.t("Import"), command=self._on_import).pack(
            side="left", padx=6
        )
        # Destructive — starts disabled, enabled only while a deck is
        # selected (see _on_listbox_select).
        self.delete_btn = ttk.Button(
            bottom,
            text=self.t("Delete"),
            command=self._on_delete,
            state="disabled",
        )
        self.delete_btn.pack(side="left", padx=6)
        ttk.Button(bottom, text=self.t("Select"), command=self._on_select).pack(
            side="right"
        )

        body = ttk.Frame(self)
        body.pack(side="top", fill="both", expand=True, padx=12, pady=4)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self.listbox = tk.Listbox(body, activestyle="dotbox")
        vbar = ttk.Scrollbar(body, orient="vertical", command=self.listbox.yview)
        hbar = ttk.Scrollbar(body, orient="horizontal", command=self.listbox.xview)
        self.listbox.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        self.listbox.bind("<Double-Button-1>", lambda e: self._on_select())
        self.listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

    def refresh(self) -> None:
        self._entries = handlers.list_known_decks()
        self.listbox.delete(0, tk.END)
        for e in self._entries:
            marker = "* " if e.is_current else "  "
            self.listbox.insert(tk.END, f"{marker}{e.name}    ({e.path})")
        # The list was rebuilt — nothing is selected, so keep Delete off.
        self._on_listbox_select()

    # ----- actions ----------------------------------------------------------

    def _on_new(self) -> None:
        result = NewDeckDialog(self, self.t).show()
        if result is None:
            return
        name, source_lang, target_lang = result
        try:
            _, path = handlers.create_deck(name, source_lang, target_lang)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(
                self.t("Are you sure?"),
                self.t("Failed to load deck: {detail}").format(detail=str(e)),
            )
            return
        self.refresh()
        # Auto-select the new deck on the next user click.
        self._select_path(path)

    def _on_import(self) -> None:
        source = filedialog.askopenfilename(
            title=self.t("Import"),
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not source:
            return
        try:
            handlers.import_deck(Path(source))
        except FileExistsError:
            # Try again with force after confirmation
            if messagebox.askyesno(
                self.t("Are you sure?"),
                self.t("File already exists. Use --force to overwrite."),
            ):
                try:
                    handlers.import_deck(Path(source), force=True)
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror(
                        self.t("Are you sure?"),
                        self.t("Failed to load deck: {detail}").format(detail=str(e)),
                    )
                    return
            else:
                return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(
                self.t("Are you sure?"),
                self.t("Failed to load deck: {detail}").format(detail=str(e)),
            )
            return
        self.refresh()

    def _on_select(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo(
                self.t("Are you sure?"),
                self.t("No deck selected."),
            )
            return
        entry = self._entries[idx]
        self.app.show_deck_detail(entry.path)

    def _on_delete(self) -> None:
        """Permanently delete the selected deck after confirmation.

        The confirmation defaults to "No" to guard against a misclick.
        After deletion the list is rebuilt; if the deleted deck was the
        configured current deck, ``current_deck`` is left pointing at
        the now-missing file — ``list_known_decks`` already tolerates a
        missing current deck, and the next ``use`` / open surfaces it.
        """
        idx = self._selected_index()
        if idx is None:
            return
        entry = self._entries[idx]
        confirmed = messagebox.askyesno(
            self.t("Delete deck"),
            self.t(
                "Delete the deck '{name}' ({n} cards). "
                "This action cannot be undone. Continue?"
            ).format(name=entry.name, n=entry.card_count),
            default=messagebox.NO,
        )
        if not confirmed:
            return
        try:
            handlers.delete_deck(entry.path)
        except Exception as e:  # noqa: BLE001 (surface any failure)
            messagebox.showerror(self.t("Delete deck"), str(e))
            return
        self.refresh()

    # ----- helpers ----------------------------------------------------------

    def _on_listbox_select(self, _event=None) -> None:
        """Enable the Delete button only while a deck is selected."""
        state = "normal" if self._selected_index() is not None else "disabled"
        self.delete_btn.configure(state=state)

    def _selected_index(self) -> Optional[int]:
        sel = self.listbox.curselection()
        if not sel:
            return None
        return int(sel[0])

    def _select_path(self, path: Path) -> None:
        for i, e in enumerate(self._entries):
            if e.path == path:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                self.listbox.activate(i)
                self.listbox.see(i)
                # A programmatic selection_set does not fire
                # <<ListboxSelect>>, so sync the Delete button by hand.
                self._on_listbox_select()
                return


class NewDeckDialog(tk.Toplevel):
    """Modal dialog asking for new deck's name and language codes."""

    def __init__(self, parent: tk.Widget, translator) -> None:
        super().__init__(parent)
        self.t = translator
        self.title(self.t("New deck"))
        self.resizable(False, False)
        self._parent_window = parent.winfo_toplevel()
        self.transient(self._parent_window)
        self.result: Optional[tuple[str, str, str]] = None
        self._build()
        # Defer centering + grab until the dialog is viewable. Doing it in
        # an after() callback lets update_idletasks() report real sizes
        # and avoids "grab failed: window not viewable".
        self.after(50, self._position_and_grab)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _position_and_grab(self) -> None:
        center_on_parent(self, self._parent_window)
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _build(self) -> None:
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text=self.t("Name")).grid(row=0, column=0, sticky="w", pady=4)
        self.name_var = tk.StringVar()
        ttk.Entry(body, textvariable=self.name_var, width=30).grid(
            row=0, column=1, sticky="ew", pady=4
        )

        ttk.Label(body, text=self.t("Source language")).grid(
            row=1, column=0, sticky="w", pady=4
        )
        self.source_var = tk.StringVar(value="en")
        ttk.Entry(body, textvariable=self.source_var, width=10).grid(
            row=1, column=1, sticky="w", pady=4
        )

        ttk.Label(body, text=self.t("Target language")).grid(
            row=2, column=0, sticky="w", pady=4
        )
        self.target_var = tk.StringVar(value="ja")
        ttk.Entry(body, textvariable=self.target_var, width=10).grid(
            row=2, column=1, sticky="w", pady=4
        )

        btns = ttk.Frame(self, padding=(12, 0, 12, 12))
        btns.pack(fill="x")
        ttk.Button(btns, text="OK", command=self._on_ok).pack(side="right")
        ttk.Button(btns, text=self.t("Cancel"), command=self._on_cancel).pack(
            side="right", padx=6
        )

    def _on_ok(self) -> None:
        name = self.name_var.get().strip()
        source = self.source_var.get().strip() or "en"
        target = self.target_var.get().strip() or "ja"
        if not name:
            return
        self.result = (name, source, target)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def show(self) -> Optional[tuple[str, str, str]]:
        """Block until the dialog is closed and return the result."""
        self.wait_window(self)
        return self.result
