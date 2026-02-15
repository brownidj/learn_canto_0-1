"""
category_manager_signal_wiring.py

CategoryManager signal wiring extracted for maintainability.

Handles Qt signal/slot connections for Add/Edit panel.

PySide6 only. No UI creation here; only wiring.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_signal_wiring_basic import wire_add_edit
from ui.category_manager_add_edit_coordinator import AddEditCoordinator
from ui.category_manager_widgets import resolve_category_manager_widgets

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerSignalWiring:
    """Manages signal/slot wiring for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        self._dlg = CategoryManagerDialogAdapter(dialog)
        self._widgets = resolve_category_manager_widgets(dialog)
        self._coord = AddEditCoordinator(self._dlg)

    def wire_add_edit_signals(self) -> None:
        """Wire Add/Edit widgets for Enter/validation.

        Rules:
          - Jyutping Enter triggers Save/Edit/Cancel confirmation flow
          - Meaning Enter triggers Save/Edit/Cancel confirmation flow
          - Hanzi Enter triggers meaning lookup and focus to Meaning
          - Candidate selection triggers Hanzi population, meaning lookup, and focus to Meaning
          - Legacy inline Save button hidden by default, shown only on 'Edit'
          - Wiring is idempotent via _add_edit_wired guard
        """
        if bool(self._dlg.get("_add_edit_wired", False)):
            return

        try:
            self._hide_inline_save_button()
            fn_gate = self._dlg.get("_update_save_enabled")

            wire_add_edit(self, fn_gate)

            if callable(fn_gate):
                try:
                    fn_gate()
                except Exception:
                    pass

        finally:
            try:
                self._dlg.set("_add_edit_wired", True)
            except Exception:
                pass

    def _hide_inline_save_button(self) -> None:
        try:
            preview_ctrl = self._dlg.get("_preview_confirm")
            if preview_ctrl is not None:
                preview_ctrl.set_save_button_visible(False)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _connect_unique(self, signal, slot) -> None:
        """Connect a signal to a slot (avoid UniqueConnection warnings)."""
        if signal is None or not callable(slot):
            return

        try:
            signal.connect(slot)
        except Exception:
            pass

    def _try_connect(self, signal, slot) -> None:
        """Connect a signal to a callable slot (best-effort, no duplicates)."""
        if signal is None or slot is None or not callable(slot):
            return
        try:
            self._connect_unique(signal, slot)
        except Exception:
            pass

    def _wire_line_edit_common(self, w, *, on_enter=None, on_change=None) -> None:
        """Common wiring for QLineEdit-like widgets.

        - on_enter: connected to returnPressed
        - on_change: connected to editingFinished and textChanged
        """
        if w is None:
            return

        if on_enter is not None and callable(on_enter):
            self._try_connect(getattr(w, "returnPressed", None), on_enter)

        if on_change is not None and callable(on_change):
            self._try_connect(getattr(w, "editingFinished", None), on_change)
            self._try_connect(getattr(w, "textChanged", None), on_change)

    def _wire_combo_common(self, w, *, on_change=None, on_activate=None) -> None:
        """Common wiring for QComboBox-like widgets (best-effort).

        - on_change: connected to currentTextChanged
        - on_activate: connected to activated
        """
        if w is None:
            return

        if on_change is not None and callable(on_change):
            self._try_connect(getattr(w, "currentTextChanged", None), on_change)

        if on_activate is not None and callable(on_activate):
            self._try_connect(getattr(w, "activated", None), on_activate)
