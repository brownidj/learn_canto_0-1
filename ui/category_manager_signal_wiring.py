"""
CategoryManager signal wiring extracted for maintainability.

Handles Qt signal/slot connections for Add/Edit panel.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerSignalWiring:
    """Manages signal/slot wiring for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog

    def wire_add_edit_signals(self) -> None:
        """Wire Add or Edit widgets for Enter/validation.

        Rules:
          - Meaning Enter triggers Save/Edit/Cancel confirmation flow
          - Legacy inline Save button hidden by default, shown only on 'Edit'
          - Use UniqueConnection where available
          - Wiring is idempotent via _add_edit_wired guard
        """
        if bool(getattr(self.dialog, "_add_edit_wired", False)):
            return

        try:
            # Hide legacy inline Save by default
            try:
                self.dialog._set_save_button_visible(False)
            except (TypeError, AttributeError, RuntimeError):
                pass

            fn_gate = getattr(self.dialog, "_update_save_enabled", None)

            # Jyutping wiring
            w_jy = getattr(self.dialog, "_add_jy", None)
            fn_jy_enter = getattr(self.dialog, "_on_jyut_enter", None)
            try:
                self._wire_line_edit_common(
                    w_jy,
                    on_enter=fn_jy_enter,
                    on_change=fn_gate,
                )
            except (TypeError, AttributeError, RuntimeError):
                pass

            # Reset dependent fields on user edits
            try:
                fn_reset = getattr(self.dialog, "_on_add_jy_user_edited", None)
                if w_jy is not None and callable(fn_reset):
                    self._try_connect(getattr(w_jy, "textEdited", None), fn_reset)
            except (TypeError, AttributeError, RuntimeError):
                pass

            # Meaning wiring
            w_mn = getattr(self.dialog, "_add_mn", None)
            fn_mn_enter = getattr(self.dialog, "_on_meaning_enter_committed", None)
            try:
                self._wire_line_edit_common(
                    w_mn,
                    on_enter=fn_mn_enter,
                    on_change=fn_gate,
                )
            except (TypeError, AttributeError, RuntimeError):
                pass

            # Category wiring
            w_cat = getattr(self.dialog, "_add_cat", None)

            # Ensure editable
            try:
                if w_cat is not None and hasattr(w_cat, "setEditable"):
                    w_cat.setEditable(True)
            except (TypeError, AttributeError, RuntimeError):
                pass

            # Save gating observes changes (must not commit or move focus)
            try:
                self._wire_combo_common(w_cat, on_change=fn_gate)
            except (TypeError, AttributeError, RuntimeError):
                pass

            # Debug: log when category text changes to track unwanted clears
            if w_cat is not None:
                def _debug_cat_change(text):
                    logger.debug("CATDBG: currentTextChanged to %r", text)
                try:
                    self._try_connect(getattr(w_cat, "currentTextChanged", None), _debug_cat_change)
                except (TypeError, AttributeError, RuntimeError):
                    pass

            # Commit only when user explicitly selects from popup (activated)
            fn_cat_commit = getattr(self.dialog, "_on_add_category_committed", None)
            if w_cat is not None and callable(fn_cat_commit):
                try:
                    sig = getattr(w_cat, "activated", None)
                    if sig is not None:
                        try:
                            sig_int = sig[int] if hasattr(sig, "__getitem__") else sig
                            self._try_connect(sig_int, fn_cat_commit)
                        except (TypeError, AttributeError, RuntimeError):
                            self._try_connect(sig, fn_cat_commit)
                except (TypeError, AttributeError, RuntimeError):
                    pass

            # Hanzi candidate combobox wiring
            try:
                combo = getattr(self.dialog, "_cand_combo", None)
            except (TypeError, AttributeError, RuntimeError):
                combo = None

            try:
                if combo is not None:
                    from ui.candidate_combo import CandidateComboController
                    self.dialog._cand_combo_ctrl = CandidateComboController(combo)
                else:
                    self.dialog._cand_combo_ctrl = None
            except (TypeError, AttributeError, RuntimeError, ImportError):
                self.dialog._cand_combo_ctrl = None

            if combo is not None:
                try:
                    fn_pick = getattr(self.dialog, "_on_candidate_index_activated", None)
                    if callable(fn_pick):
                        sig = getattr(combo, "currentIndexChanged", None)
                        if sig is not None:
                            try:
                                sig_int = sig[int] if hasattr(sig, "__getitem__") else sig
                                self._try_connect(sig_int, fn_pick)
                            except (TypeError, AttributeError, RuntimeError):
                                self._try_connect(sig, fn_pick)

                        sig2 = getattr(combo, "activated", None)
                        if sig2 is not None:
                            try:
                                sig2_int = sig2[int] if hasattr(sig2, "__getitem__") else sig2
                                self._try_connect(sig2_int, fn_pick)
                            except (TypeError, AttributeError, RuntimeError):
                                self._try_connect(sig2, fn_pick)
                except (TypeError, AttributeError, RuntimeError):
                    pass

            if callable(fn_gate):
                try:
                    fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass

        finally:
            self.dialog._add_edit_wired = True

    def _connect_unique(self, signal, slot) -> None:
        """Best-effort signal connect without duplicate wiring."""
        if signal is None or not callable(slot):
            return

        try:
            from PySide6.QtCore import Qt
            signal.connect(slot, Qt.ConnectionType.UniqueConnection)
            return
        except (ImportError, TypeError, AttributeError, RuntimeError):
            pass

        try:
            signal.connect(slot)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _try_connect(self, signal, slot) -> None:
        """Connect a signal to a callable slot (best-effort, no duplicates)."""
        if signal is None or slot is None or not callable(slot):
            return
        try:
            self._connect_unique(signal, slot)
        except (TypeError, AttributeError, RuntimeError):
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
