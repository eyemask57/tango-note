"""Preferences dialog.

Exposes the deck-export default plus the quiz tuning thresholds (weak
accuracy cutoff, long-unreviewed day count). Future settings (language,
deck-storage location, fonts, ...) will be added as further groups here.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from tango_note.core.config import (
    EXPORT_DEFAULT_ASK,
    EXPORT_DEFAULT_INCLUDE,
    EXPORT_DEFAULT_STRIP,
    AppConfig,
    save_config,
)
from tango_note.gui.utils import center_on_parent


class SettingsDialog(tk.Toplevel):
    """Modal preferences dialog.

    Follows the same modal pattern as ``NewDeckDialog``: ``transient`` +
    deferred ``center_on_parent`` / ``grab_set``, ``show()`` blocks on
    ``wait_window``.

    Args:
        parent: The widget the dialog is modal to.
        translator: The ``_`` translator function.
        config: The current ``AppConfig``. The dialog mutates this
            object in place and persists it via ``save_config`` on
            OK / Apply.
    """

    def __init__(
        self,
        parent: tk.Widget,
        translator,
        config: AppConfig,
    ) -> None:
        super().__init__(parent)
        self.t = translator
        self._config = config
        self.title(self.t("Preferences"))
        self.resizable(False, False)
        self._parent_window = parent.winfo_toplevel()
        self.transient(self._parent_window)
        self._build()
        # Defer centering + grab until the dialog is viewable.
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

        export_group = ttk.LabelFrame(body, text=self.t("Export"))
        export_group.pack(fill="x")

        ttk.Label(export_group, text=self.t("Default action")).pack(
            anchor="w", padx=8, pady=(8, 4)
        )
        self.export_var = tk.StringVar(value=self._config.export_default)
        for value, label in (
            (EXPORT_DEFAULT_ASK, "Ask each time (recommended)"),
            (EXPORT_DEFAULT_STRIP, "Always strip stats (suitable for sharing)"),
            (EXPORT_DEFAULT_INCLUDE, "Always include stats (suitable for backup)"),
        ):
            ttk.Radiobutton(
                export_group,
                text=self.t(label),
                value=value,
                variable=self.export_var,
            ).pack(anchor="w", padx=16, pady=2)
        # bottom padding inside the group
        ttk.Frame(export_group, height=8).pack()

        quiz_group = ttk.LabelFrame(body, text=self.t("Quiz"))
        quiz_group.pack(fill="x", pady=(10, 0))

        weak_row = ttk.Frame(quiz_group)
        weak_row.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(
            weak_row, text=self.t("Weak threshold (accuracy %)")
        ).pack(side="left")
        # Config stores weak_threshold as a 0.0-1.0 float; the UI edits
        # it as a 0-100 integer percentage.
        self.weak_var = tk.StringVar(
            value=str(round(self._config.weak_threshold * 100))
        )
        ttk.Spinbox(
            weak_row, from_=0, to=100, textvariable=self.weak_var, width=6
        ).pack(side="right")

        days_row = ttk.Frame(quiz_group)
        days_row.pack(fill="x", padx=8, pady=(2, 8))
        ttk.Label(
            days_row, text=self.t("Unreviewed days threshold")
        ).pack(side="left")
        self.days_var = tk.StringVar(value=str(self._config.unreviewed_days))
        ttk.Spinbox(
            days_row, from_=1, to=365, textvariable=self.days_var, width=6
        ).pack(side="right")

        btns = ttk.Frame(self, padding=(12, 0, 12, 12))
        btns.pack(fill="x")
        ttk.Button(btns, text=self.t("OK"), command=self._on_ok).pack(side="right")
        ttk.Button(btns, text=self.t("Cancel"), command=self._on_cancel).pack(
            side="right", padx=6
        )
        ttk.Button(btns, text=self.t("Apply"), command=self._on_apply).pack(
            side="right"
        )

    # ----- persistence ------------------------------------------------------

    @staticmethod
    def _parse_int(text: str, low: int, high: int) -> int | None:
        """Parse ``text`` as an integer in [low, high], else return None."""
        try:
            value = int(text)
        except (ValueError, TypeError):
            return None
        return value if low <= value <= high else None

    def _persist(self) -> bool:
        """Validate the inputs and, if all valid, save the config.

        Returns:
            ``True`` if everything was valid and saved; ``False`` (after
            a warning dialog) if an out-of-range value was rejected.
        """
        weak_pct = self._parse_int(self.weak_var.get(), 0, 100)
        if weak_pct is None:
            messagebox.showwarning(
                self.t("Preferences"),
                self.t(
                    "Weak threshold must be an integer between 0 and 100."
                ),
            )
            return False
        days = self._parse_int(self.days_var.get(), 1, 365)
        if days is None:
            messagebox.showwarning(
                self.t("Preferences"),
                self.t(
                    "Unreviewed days must be an integer between 1 and 365."
                ),
            )
            return False

        self._config.export_default = self.export_var.get()
        self._config.weak_threshold = weak_pct / 100.0
        self._config.unreviewed_days = days
        save_config(self._config)
        return True

    # ----- button handlers --------------------------------------------------

    def _on_ok(self) -> None:
        if self._persist():
            self.destroy()

    def _on_apply(self) -> None:
        # Save but keep the dialog open (no-op on invalid input).
        self._persist()

    def _on_cancel(self) -> None:
        # Discard any radio change made since the last save / Apply.
        self.destroy()

    def show(self) -> None:
        """Block until the dialog is closed."""
        self.wait_window(self)
