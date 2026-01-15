"""
CategoryManager signal wiring extracted for maintainability.

Handles Qt signal/slot connections for Add/Edit panel.
"""

import logging
import traceback
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerSignalWiring:
    """Manages signal/slot wiring for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        # Debug: Test all logging levels
        print(f"Logger name: {logger.name}")
        print(f"Logger level: {logger.level}")
        print(f"Effective level: {logger.getEffectiveLevel()}")

        logger.error("TEST ERROR: This should always appear")
        logger.warning("TEST WARNING: This should appear")
        logger.info("TEST INFO: This should appear")
        logger.debug("TEST DEBUG: This should appear if DEBUG is enabled")
        logger.debug(f"CategoryManagerManualHanziController initialized: {type(dialog)}")
        # Add extra diagnostic logging
        try:
            logger.debug(f"Dialog attributes: {[attr for attr in dir(dialog) if attr.startswith('_') and not attr.startswith('__')]}")
            logger.debug(f"Dialog type: {type(dialog)}")
        except Exception as e:
            logger.error(f"Error logging dialog details: {e}")

    def wire_add_edit_signals(self) -> None:
        """Wire Add or Edit widgets for Enter/validation.

        Rules:
          - Jyutping Enter triggers Save/Edit/Cancel confirmation flow
          - Meaning Enter triggers Save/Edit/Cancel confirmation flow
          - Hanzi Enter triggers meaning lookup and focus to Meaning
          - Candidate selection triggers Hanzi population, meaning lookup, and focus to Meaning
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

            # Hanzi wiring - ALWAYS EDITABLE with Enter handler
            w_hz = getattr(self.dialog, "_add_hz", None)
            if w_hz is not None:
                # Make Hanzi field always editable
                try:
                    w_hz.setReadOnly(False)
                    w_hz.setPlaceholderText("Auto-filled from candidates or type your own...")
                except (TypeError, AttributeError, RuntimeError):
                    pass

                # Wire Enter key to trigger meaning lookup and focus transfer
                def _on_hanzi_enter():
                    """Handle Enter key in Hanzi field - lookup meanings and focus to Meaning field."""
                    logger.debug("Hanzi Enter pressed - resolving meanings and focusing Meaning field")
                    try:
                        # Get current Hanzi text
                        hz_text = w_hz.text().strip() if w_hz else ""
                        if not hz_text:
                            return

                        # Resolve meanings for the Hanzi
                        meanings = self.dialog._resolve_meanings_for_candidate(hz_text) or []

                        # Populate meaning field if we found meanings
                        mn_widget = getattr(self.dialog, "_add_mn", None)
                        if mn_widget is not None and meanings:
                            meaning_text = ", ".join(meanings[:3])  # Limit to first 3 meanings

                            # Set meaning text based on widget type
                            if hasattr(mn_widget, 'setPlainText'):
                                mn_widget.setPlainText(meaning_text)
                            elif hasattr(mn_widget, 'setText'):
                                mn_widget.setText(meaning_text)

                            logger.debug(f"Set meanings: {meaning_text}")

                        # Focus the meaning field
                        if mn_widget is not None:
                            try:
                                from ui.widget_utils import WidgetAccessor
                                WidgetAccessor.focus(mn_widget, select_all=True)
                                logger.debug("Focused meaning field")
                            except (TypeError, AttributeError, RuntimeError):
                                # Fallback focus method
                                if hasattr(mn_widget, 'setFocus'):
                                    mn_widget.setFocus()
                                    if hasattr(mn_widget, 'selectAll'):
                                        mn_widget.selectAll()

                        # Update save state
                        if callable(fn_gate):
                            fn_gate()

                    except Exception as e:
                        logger.error(f"Error in Hanzi Enter handler: {e}")
                        import traceback
                        logger.debug(traceback.format_exc())

                # Wire the Enter key
                try:
                    self._try_connect(getattr(w_hz, "returnPressed", None), _on_hanzi_enter)
                    logger.debug("Hanzi Enter key handler connected")
                except (TypeError, AttributeError, RuntimeError):
                    pass

                # Wire text changes to update save state
                try:
                    self._try_connect(getattr(w_hz, "textChanged", None), fn_gate)
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

            # Hanzi candidate combobox wiring - ENHANCED
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
                # Enhanced candidate selection handler
                def _on_candidate_selected(index):
                    """Handle candidate selection from combo - populate Hanzi, resolve meanings, focus Meaning."""
                    logger.debug(f"Candidate selected at index: {index}")
                    try:
                        if index < 0 or index >= combo.count():
                            return

                        # Get selected Hanzi text
                        hanzi_text = combo.itemText(index).strip()
                        if not hanzi_text or hanzi_text.startswith("—"):  # Skip placeholder items
                            return

                        # Set Hanzi field
                        hz_widget = getattr(self.dialog, "_add_hz", None)
                        if hz_widget is not None:
                            hz_widget.setText(hanzi_text)
                            logger.debug(f"Set Hanzi field to: {hanzi_text}")

                        # Resolve meanings for the selected Hanzi
                        meanings = self.dialog._resolve_meanings_for_candidate(hanzi_text) or []

                        # Populate meaning field
                        mn_widget = getattr(self.dialog, "_add_mn", None)
                        if mn_widget is not None and meanings:
                            meaning_text = ", ".join(meanings[:3])  # Limit to first 3 meanings

                            # Set meaning text based on widget type
                            if hasattr(mn_widget, 'setPlainText'):
                                mn_widget.setPlainText(meaning_text)
                            elif hasattr(mn_widget, 'setText'):
                                mn_widget.setText(meaning_text)

                            logger.debug(f"Set meanings from candidate: {meaning_text}")

                        # Focus the meaning field
                        if mn_widget is not None:
                            try:
                                from ui.widget_utils import WidgetAccessor
                                WidgetAccessor.focus(mn_widget, select_all=True)
                                logger.debug("Focused meaning field from candidate selection")
                            except (TypeError, AttributeError, RuntimeError):
                                # Fallback focus method
                                if hasattr(mn_widget, 'setFocus'):
                                    mn_widget.setFocus()
                                    if hasattr(mn_widget, 'selectAll'):
                                        mn_widget.selectAll()

                        # Update save state
                        if callable(fn_gate):
                            fn_gate()

                    except Exception as e:
                        logger.error(f"Error in candidate selection handler: {e}")
                        import traceback
                        logger.debug(traceback.format_exc())

                    # Wire candidate selection events
                    try:
                        # activated signal - when user selects from dropdown
                        sig_activated = getattr(combo, "activated", None)
                        if sig_activated is not None:
                            try:
                                sig_int = sig_activated[int] if hasattr(sig_activated, "__getitem__") else sig_activated
                                self._try_connect(sig_int, _on_candidate_selected)
                                logger.debug("Candidate combo activated signal connected")
                            except (TypeError, AttributeError, RuntimeError):
                                self._try_connect(sig_activated, _on_candidate_selected)

                        # currentIndexChanged signal - when selection changes
                        sig_changed = getattr(combo, "currentIndexChanged", None)
                        if sig_changed is not None:
                            try:
                                sig_int = sig_changed[int] if hasattr(sig_changed, "__getitem__") else sig_changed
                                self._try_connect(sig_int, _on_candidate_selected)
                                logger.debug("Candidate combo currentIndexChanged signal connected")
                            except (TypeError, AttributeError, RuntimeError):
                                self._try_connect(sig_changed, _on_candidate_selected)

                    except (TypeError, AttributeError, RuntimeError) as e:
                        logger.error(f"Error wiring candidate combo signals: {e}")

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
