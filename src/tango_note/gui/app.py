"""Main window and deck-detail orchestrator for the tango-note GUI.

The window-management policy is intentionally simple: at any time
exactly one *screen* widget is packed into the root window. Navigation
between screens (e.g., deck list -> deck detail) destroys the previous
screen and packs the new one. The currently displayed screen may
register itself as the "close handler" by exposing a
``request_close()`` method that returns ``False`` to abort the close.
"""

from __future__ import annotations

import platform
import sys
import tkinter as tk
from importlib.resources import files as _resource_files
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import Callable, Optional

from tango_note.gui import handlers


def _locate_icon() -> Path | None:
    """Return the path to the application-icon PNG, or ``None``.

    Resolution order, matching the three ways the app gets run:

    1. PyInstaller bundle — ``sys._MEIPASS/assets/tango-note_source.png``
       (``tango-note.spec`` copies the PNG into ``assets/``).
    2. wheel install — ``<pkg>/assets/icon.png`` (placed there by the
       ``force-include`` entry in ``pyproject.toml``).
    3. editable / source checkout — ``<repo>/installer/tango-note_source.png``.

    Returns ``None`` when no candidate exists, so the caller can fall
    back to Tk's default icon without crashing.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "assets" / "tango-note_source.png"
        if bundled.is_file():
            return bundled

    try:
        pkg_asset = _resource_files("tango_note") / "assets" / "icon.png"
        if pkg_asset.is_file():
            return Path(str(pkg_asset))
    except (ModuleNotFoundError, FileNotFoundError):
        pass

    repo_asset = (
        Path(__file__).resolve().parents[3]
        / "installer"
        / "tango-note_source.png"
    )
    if repo_asset.is_file():
        return repo_asset

    return None


class MainWindow:
    """Top-level application window."""

    def __init__(self, translator: Callable[[str], str]) -> None:
        self.t = translator
        self.root = tk.Tk()
        self.root.title("tango-note")
        self.root.geometry("900x650")
        self.root.minsize(600, 400)
        self.root.resizable(True, True)
        # Replace Tk's default feather icon with the tango-note logo.
        self._app_icon: Optional[tk.PhotoImage] = None
        self._apply_app_icon()
        self._setup_fonts()
        self._build_menu()
        self._current_screen: Optional[tk.Widget] = None
        # Name of the deck currently open, or None on the deck-list
        # screen; drives the window title (see _update_window_title).
        self._current_deck_name: Optional[str] = None
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show_deck_list()

    # ----- application icon -------------------------------------------------

    def _apply_app_icon(self) -> None:
        """Set the window icon to the tango-note logo.

        ``iconphoto(True, ...)`` applies the image to this window *and*
        every Toplevel opened afterwards (SettingsDialog, CardDialog, …),
        so they all inherit the logo automatically.

        The ``PhotoImage`` is stored on ``self`` deliberately: Tkinter
        keeps no reference of its own, so a local variable would be
        garbage-collected and the icon would silently revert. A corrupt
        or unsupported PNG raises ``TclError``; that is swallowed so a
        bad asset can never take down the whole app.
        """
        icon_path = _locate_icon()
        if icon_path is None:
            return
        try:
            self._app_icon = tk.PhotoImage(file=str(icon_path))
            self.root.iconphoto(True, self._app_icon)
        except tk.TclError:
            pass

    # ----- menu bar ---------------------------------------------------------

    def _build_menu(self) -> None:
        """Build the application menu bar.

        The menu and its keyboard accelerators live on ``self.root``, so
        they persist across every screen swap (``_set_screen`` only ever
        destroys/packs child frames, never the root).
        """
        menubar = tk.Menu(self.root, tearoff=False)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(
            label=self.t("Quit"), command=self._on_close, accelerator="Ctrl+Q"
        )
        menubar.add_cascade(label=self.t("File"), menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=False)
        tools_menu.add_command(
            label=self.t("Preferences..."),
            command=self._open_settings,
            accelerator="Ctrl+,",
        )
        menubar.add_cascade(label=self.t("Tools"), menu=tools_menu)

        self.root.config(menu=menubar)

        # ``accelerator=`` only draws the hint text; the real key handlers
        # must be bound separately. ``bind_all`` so the shortcut fires
        # regardless of which widget inside the current screen has focus.
        self.root.bind_all("<Control-q>", lambda _e: self._on_close())
        self.root.bind_all("<Control-comma>", lambda _e: self._open_settings())

    def _open_settings(self) -> None:
        # Late import keeps the dependency tree linear (matches the
        # show_deck_list / show_deck_detail pattern).
        from tango_note.core.config import load_config
        from tango_note.gui.screens.settings import SettingsDialog

        # Re-read fresh: the config may have changed on disk (e.g. via the
        # CLI) since the window opened.
        SettingsDialog(self.root, self.t, load_config()).show()

    # ----- platform-specific font selection ---------------------------------

    def _setup_fonts(self) -> None:
        """Apply a platform-appropriate default font for Japanese text.

        Tk's default font on macOS does not always have CJK glyphs;
        on Windows the default is OK in recent builds but Yu Gothic UI
        renders kanji more cleanly. Linux: leave the Tk default alone
        (distros vary widely).
        """
        system = platform.system()
        if system == "Darwin":
            family, size = "Hiragino Sans", 12
        elif system == "Windows":
            family, size = "Yu Gothic UI", 10
        else:
            family, size = "", 10  # use Tk default family

        for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont"):
            f = tkfont.nametofont(name)
            if family:
                f.configure(family=family)
            f.configure(size=size)

    # ----- screen navigation ------------------------------------------------

    def show_deck_list(self) -> None:
        # Late import to avoid a circular import at module load time.
        from tango_note.gui.screens.deck_list import DeckListScreen

        self._set_screen(DeckListScreen(self.root, self))
        self._current_deck_name = None
        self._update_window_title()

    def show_deck_detail(self, deck_path: Path) -> None:
        try:
            deck = handlers.load_deck(deck_path)
        except Exception as e:  # noqa: BLE001 (surface anything to the user)
            messagebox.showerror(
                self.t("Are you sure?"),
                self.t("Failed to load deck: {detail}").format(detail=str(e)),
            )
            return
        self._set_screen(DeckDetailScreen(self.root, self, deck_path, deck))
        # A freshly loaded deck is clean — no asterisk yet.
        self._current_deck_name = deck.meta.name
        self._update_window_title(dirty=False)

    def _update_window_title(self, dirty: bool = False) -> None:
        """Set the window title, with a trailing ``*`` for unsaved changes.

        Shows just ``tango-note`` on the deck-list screen (no deck open);
        ``tango-note - <deck>`` inside a deck, plus `` *`` while there are
        unsaved changes. Registered as a dirty-state listener by each
        ``DeckDetailScreen`` so it tracks add / edit / delete / save.
        """
        if self._current_deck_name is None:
            self.root.title("tango-note")
        else:
            suffix = " *" if dirty else ""
            self.root.title(f"tango-note - {self._current_deck_name}{suffix}")

    def _set_screen(self, screen: tk.Widget) -> None:
        if self._current_screen is not None:
            self._current_screen.destroy()
        self._current_screen = screen
        screen.pack(fill="both", expand=True)

    # ----- close handling ---------------------------------------------------

    def _on_close(self) -> None:
        screen = self._current_screen
        if screen is not None and hasattr(screen, "request_close"):
            if not screen.request_close():
                return
        self.root.destroy()

    # ----- mainloop ---------------------------------------------------------

    def run(self) -> None:  # pragma: no cover (loop)
        self.root.mainloop()


class DeckDetailScreen(ttk.Frame):
    """Tabbed view of a single deck: cards / quiz / stats.

    The deck is loaded once on entry and held in memory; the three
    tabs all read/write this shared object. Card edits set ``self.dirty``
    and require an explicit Save; quiz grades auto-save (and clear
    ``dirty`` as a side-effect). On Back / window close, if ``dirty``
    is set, the user is prompted to save / discard / cancel.
    """

    def __init__(
        self,
        parent: tk.Widget,
        app: MainWindow,
        deck_path: Path,
        deck,
    ) -> None:
        super().__init__(parent)
        self.app = app
        self.t = app.t
        self.deck_path = deck_path
        self.deck = deck
        self.dirty = False
        # Callbacks invoked (with the new bool) whenever ``dirty`` flips.
        # Set up before _build() so child tabs can register during build.
        self._dirty_listeners: list[Callable[[bool], None]] = []
        self._build()
        # Mirror the dirty state into the window title bar.
        self.add_dirty_listener(lambda d: self.app._update_window_title(d))

    # ----- public API used by tabs ------------------------------------------

    def add_dirty_listener(self, listener: Callable[[bool], None]) -> None:
        """Register a callback invoked whenever the dirty flag changes.

        Kept deliberately minimal — a plain callback list, no unregister.
        Listeners live and die with this screen, so nothing leaks when
        the screen is destroyed on navigation.
        """
        self._dirty_listeners.append(listener)

    def _set_dirty(self, value: bool) -> None:
        """Update the dirty flag and notify every registered listener."""
        self.dirty = value
        for listener in self._dirty_listeners:
            listener(value)

    def mark_dirty(self) -> None:
        """Called by a tab when the deck has been mutated in memory."""
        self._set_dirty(True)

    def save_now(self) -> None:
        """Persist the deck to disk and clear the dirty flag."""
        handlers.save_deck(self.deck, self.deck_path)
        self._set_dirty(False)
        # Let the card-edit tab re-render its row accuracies, etc.
        if hasattr(self, "card_tab") and self.card_tab is not None:
            self.card_tab.refresh()
        if hasattr(self, "stats_tab") and self.stats_tab is not None:
            self.stats_tab.refresh()

    # ----- close hooks ------------------------------------------------------

    def request_close(self) -> bool:
        """Called by MainWindow before the window is destroyed."""
        return self._confirm_discard_or_save()

    def _confirm_discard_or_save(self) -> bool:
        """Returns True if it is OK to proceed; False to abort navigation."""
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            self.t("Are you sure?"),
            self.t("You have unsaved changes. Save before continuing?"),
        )
        if answer is None:  # Cancel
            return False
        if answer:  # Yes -> save
            self.save_now()
        return True

    # ----- UI ---------------------------------------------------------------

    @staticmethod
    def _style_notebook_tabs() -> None:
        """Make the deck-detail tabs larger and easier to read (v1.1.1).

        The tabs get wider padding (a bigger click target), a bold 11pt
        font, and a distinct selected-vs-unselected color. The font
        family is taken from ``TkDefaultFont`` so it stays correct on
        every platform (it resolves to Yu Gothic UI on Windows).

        Only the *foreground* color is relied on for the selected-state
        cue: on the Windows "vista" ttk theme a tab's background is drawn
        by the native renderer and ignores ``style.map`` — the same
        constraint ``Primary.TButton`` works around. A background map is
        set as well (harmless, and honored on themes that support it),
        but the foreground contrast is what guarantees the selected tab
        is always identifiable.
        """
        style = ttk.Style()
        base = tkfont.nametofont("TkDefaultFont")
        style.configure(
            "TNotebook.Tab",
            padding=[20, 10],
            font=(base.cget("family"), 11, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[
                ("selected", "#e8eef5"),
                ("!selected", "#f5f5f5"),
            ],
            foreground=[
                ("selected", "#1e3a5f"),
                ("!selected", "#888888"),
            ],
        )

    def _build(self) -> None:
        # Top bar: back button + deck name
        top = ttk.Frame(self)
        top.pack(side="top", fill="x", padx=8, pady=6)
        ttk.Button(top, text=self.t("Back"), command=self._on_back).pack(side="left")
        ttk.Label(
            top,
            text=self.deck.meta.name,
            font=("TkHeadingFont", 14, "bold"),
        ).pack(side="left", padx=12)

        # Tabbed body
        self._style_notebook_tabs()
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=6)

        # Late imports to keep the dependency tree linear.
        from tango_note.gui.screens.card_edit import CardEditTab
        from tango_note.gui.screens.quiz import QuizTab
        from tango_note.gui.screens.stats import StatsTab

        self.card_tab = CardEditTab(notebook, self)
        self.quiz_tab = QuizTab(notebook, self)
        self.stats_tab = StatsTab(notebook, self)

        notebook.add(self.card_tab, text=self.t("Cards"))
        notebook.add(self.quiz_tab, text=self.t("Quiz"))
        notebook.add(self.stats_tab, text=self.t("Stats"))

        # Refresh stats and the quiz card whenever the user switches into them.
        def _on_tab_changed(event: tk.Event) -> None:
            current = event.widget.nametowidget(event.widget.select())
            if current is self.stats_tab:
                self.stats_tab.refresh()
            elif current is self.quiz_tab:
                self.quiz_tab.refresh_if_needed()

        notebook.bind("<<NotebookTabChanged>>", _on_tab_changed)

    def _on_back(self) -> None:
        if self._confirm_discard_or_save():
            self.app.show_deck_list()
