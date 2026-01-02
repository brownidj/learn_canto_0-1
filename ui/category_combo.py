# ui/category_combo.py

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtWidgets import QComboBox, QLineEdit


class CategoryComboController:
    """Small UI-only controller for the Add-panel Category combobox.

    Responsibilities:
      - Normalised read/write of the category text.
      - Robust focus/select-all/popup behaviour.
      - A single "commit" entry point that can be triggered from:
          * Return/Enter on the editable line edit, or
          * Programmatic calls from tests/adapters.

    This module contains no domain logic.
    """

    def __init__(self, *, combo: QComboBox, on_commit: Callable[[], None] | None):
        self._combo = combo
        self._on_commit = on_commit

        le = self._line_edit()
        if le is not None:
            try:
                le.returnPressed.connect(self.commit)
            except Exception:
                pass

    # -------- public API --------

    def combo(self) -> QComboBox:
        return self._combo

    def line_edit(self) -> Optional[QLineEdit]:
        """Expose the underlying line edit if the combo is editable."""
        return self._line_edit()

    def current_text(self) -> str:
        """Return the current category text, stripped."""
        try:
            return (self._combo.currentText() or "").strip()
        except Exception:
            return ""

    def set_text(self, text: str) -> None:
        """Best-effort set of the combo text.

        Uses setCurrentText when available; falls back to setEditText for older builds.
        """
        t = (text or "").strip()
        try:
            self._combo.setCurrentText(t)
            return
        except Exception:
            pass
        try:
            self._combo.setEditText(t)
        except Exception:
            pass

    def focus(self, *, select_all: bool = True, show_popup: bool = False) -> None:
        """Focus the combo (or its line edit) and optionally select all / show popup."""
        try:
            self._combo.setFocus()
        except Exception:
            return

        le = self._line_edit()
        if le is not None:
            try:
                le.setFocus()
            except Exception:
                pass
            if select_all:
                try:
                    le.selectAll()
                except Exception:
                    pass

        if show_popup:
            try:
                self._combo.showPopup()
            except Exception:
                pass

    def has_focus(self) -> bool:
        """Return True if the combo, its view, or its line edit has focus."""
        try:
            if self._combo.hasFocus():
                return True
        except Exception:
            pass

        le = self._line_edit()
        if le is not None:
            try:
                if le.hasFocus():
                    return True
            except Exception:
                pass

        try:
            v = self._combo.view()
            if v is not None and v.hasFocus():
                return True
        except Exception:
            pass

        return False

    def commit(self) -> None:
        """Trigger the category-commit callback.

        This is safe to call from tests instead of reaching into combo.lineEdit().
        """
        if callable(self._on_commit):
            try:
                self._on_commit()
            except Exception:
                # UI must remain responsive
                pass

    # -------- internals --------

    def _line_edit(self) -> Optional[QLineEdit]:
        try:
            le = self._combo.lineEdit()
        except Exception:
            le = None
        return le