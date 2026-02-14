"""
category_manager_signal_wiring.py

CategoryManager signal wiring extracted for maintainability.

Handles Qt signal/slot connections for Add/Edit panel.

PySide6 only. No UI creation here; only wiring.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ui.widget_utils import WidgetAccessor

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerSignalWiring:
    """Manages signal/slot wiring for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog

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
        if bool(getattr(self.dialog, "_add_edit_wired", False)):
            return

        try:
            # Hide legacy inline Save by default
            try:
                self.dialog._set_save_button_visible(False)
            except (TypeError, AttributeError, RuntimeError):
                pass

            fn_gate = getattr(self.dialog, "_update_save_enabled", None)

            # --- Jyutping wiring ---
            w_jy = getattr(self.dialog, "_add_jy", None)
            fn_jy_enter = getattr(self.dialog, "_on_jyut_enter", None)
            self._wire_line_edit_common(w_jy, on_enter=fn_jy_enter, on_change=fn_gate)

            # Reset dependent fields on user edits
            fn_reset = getattr(self.dialog, "_on_add_jy_user_edited", None)
            if w_jy is not None and callable(fn_reset):
                self._try_connect(getattr(w_jy, "textEdited", None), fn_reset)

            # On commit (editing finished), move focus to Category
            fn_jy_done = getattr(self.dialog, "_on_add_jy_editing_finished", None)
            if w_jy is not None and callable(fn_jy_done):
                self._try_connect(getattr(w_jy, "editingFinished", None), fn_jy_done)

            # --- Hanzi wiring ---
            w_hz = getattr(self.dialog, "_add_hz", None)
            if w_hz is not None:
                # Hanzi must be editable to allow Enter-driven flow.
                try:
                    w_hz.setReadOnly(False)
                except (TypeError, AttributeError, RuntimeError):
                    pass

                def _on_hanzi_enter() -> None:
                    """Enter in Hanzi field: resolve meanings and focus Meanings."""
                    try:
                        hz_text = ""
                        try:
                            hz_text = str(w_hz.text() or "").strip()
                        except Exception:
                            hz_text = ""
                        if not hz_text:
                            return

                        # Resolve meanings
                        meanings = []
                        try:
                            fn_resolve = getattr(self.dialog, "_resolve_meanings_for_candidate", None)
                        except (TypeError, AttributeError, RuntimeError):
                            fn_resolve = None
                        src = ""
                        try:
                            combo = getattr(self.dialog, "_cand_combo", None)
                        except (TypeError, AttributeError, RuntimeError):
                            combo = None
                        try:
                            idx = int(combo.currentIndex()) if combo is not None else -1
                            data = combo.itemData(idx) if idx >= 0 and combo is not None else None
                            if isinstance(data, dict):
                                src = str(data.get("src", "") or "").strip()
                            elif isinstance(data, (list, tuple)) and len(data) >= 2:
                                src = str(data[1] or "").strip()
                        except Exception:
                            src = ""
                        if callable(fn_resolve):
                            try:
                                meanings = fn_resolve(hz_text, src) or []
                            except TypeError:
                                meanings = fn_resolve(hz_text) or []
                            except Exception:
                                meanings = []

                        # Populate meaning field
                        w_mn_local = getattr(self.dialog, "_add_mn", None)
                        if w_mn_local is not None and meanings:
                            joined = ", ".join([str(x).strip() for x in meanings if str(x).strip()])
                            try:
                                if hasattr(w_mn_local, "setText"):
                                    w_mn_local.setText(joined)
                                elif hasattr(w_mn_local, "setPlainText"):
                                    w_mn_local.setPlainText(joined)
                            except Exception:
                                pass
                        if w_mn_local is not None and not (WidgetAccessor.get_text(w_mn_local) or "").strip():
                            try:
                                jy = WidgetAccessor.get_text(getattr(self.dialog, "_add_jy", None))
                            except Exception:
                                jy = ""
                            try:
                                self.dialog._fetch_canto_info_async(hanzi=hz_text, jyutping=jy)
                            except Exception:
                                pass

                        # Focus meaning field
                        try:
                            self.dialog._focus_meaning(select_all=True)
                        except Exception:
                            try:
                                if w_mn_local is not None and hasattr(w_mn_local, "setFocus"):
                                    w_mn_local.setFocus()
                            except Exception:
                                pass

                        # Update save gating
                        try:
                            if callable(fn_gate):
                                fn_gate()
                        except Exception:
                            pass

                    except Exception:
                        # Must never raise from wiring handlers
                        logger.debug("Hanzi enter handler failed", exc_info=True)

                self._try_connect(getattr(w_hz, "returnPressed", None), _on_hanzi_enter)

            # --- Meaning wiring ---
            w_mn = getattr(self.dialog, "_add_mn", None)
            fn_mn_enter = getattr(self.dialog, "_on_meaning_enter_committed", None)
            self._wire_line_edit_common(w_mn, on_enter=fn_mn_enter, on_change=fn_gate)

            # --- Category wiring ---
            w_cat = getattr(self.dialog, "_add_cat", None)
            if w_cat is not None and hasattr(w_cat, "setEditable"):
                try:
                    w_cat.setEditable(True)
                except (TypeError, AttributeError, RuntimeError):
                    pass

            # Save gating observes changes (must not commit or move focus)
            self._wire_combo_common(w_cat, on_change=fn_gate)

            # Commit only when user explicitly selects from popup (activated)
            fn_cat_commit = getattr(self.dialog, "_on_add_category_committed", None)
            if w_cat is not None and callable(fn_cat_commit):
                sig = getattr(w_cat, "activated", None)
                if sig is not None:
                    try:
                        sig_int = sig[int] if hasattr(sig, "__getitem__") else sig
                        self._try_connect(sig_int, fn_cat_commit)
                    except Exception:
                        self._try_connect(sig, fn_cat_commit)

            # --- Candidate combo wiring ---
            combo = getattr(self.dialog, "_cand_combo", None)

            if combo is not None:
                def _on_candidate_selected(index: int) -> None:
                    """Populate Hanzi + meanings from candidate selection and focus Hanzi."""
                    try:
                        try:
                            idx = int(index)
                        except Exception:
                            idx = -1
                        if idx < 0:
                            return

                        try:
                            hanzi_text = str(combo.itemText(idx) or "").strip()
                        except Exception:
                            hanzi_text = ""
                        if not hanzi_text:
                            return
                        if hanzi_text.startswith("—"):
                            return

                        # Set Hanzi field
                        hz_widget = getattr(self.dialog, "_add_hz", None)
                        if hz_widget is not None and hasattr(hz_widget, "setText"):
                            try:
                                hz_widget.setText(hanzi_text)
                            except Exception:
                                pass
                        # Resolve meanings
                        meanings = []
                        try:
                            fn_resolve = getattr(self.dialog, "_resolve_meanings_for_candidate", None)
                        except Exception:
                            fn_resolve = None
                        src = ""
                        try:
                            data = combo.itemData(idx) if combo is not None else None
                            if isinstance(data, dict):
                                src = str(data.get("src", "") or "").strip()
                            elif isinstance(data, (list, tuple)) and len(data) >= 2:
                                src = str(data[1] or "").strip()
                        except Exception:
                            src = ""
                        if callable(fn_resolve):
                            try:
                                meanings = fn_resolve(hanzi_text, src) or []
                            except TypeError:
                                meanings = fn_resolve(hanzi_text) or []
                            except Exception:
                                meanings = []
                        try:
                            logger.debug("MEANDBG: cand=%r src=%r meanings=%r", hanzi_text, src, meanings)
                        except Exception:
                            pass
                        if not meanings:
                            try:
                                fn_fallback = getattr(self.dialog, "_meanings_for_hanzi", None)
                            except Exception:
                                fn_fallback = None
                            if callable(fn_fallback):
                                try:
                                    meanings = fn_fallback(hanzi_text) or []
                                except Exception:
                                    meanings = []
                        try:
                            logger.debug("MEANDBG: cand=%r fallback_meanings=%r", hanzi_text, meanings)
                        except Exception:
                            pass

                        w_mn_local = getattr(self.dialog, "_add_mn", None)
                        if w_mn_local is not None:
                            joined = ", ".join([str(x).strip() for x in meanings if str(x).strip()])
                            try:
                                if hasattr(w_mn_local, "setText"):
                                    w_mn_local.setText(joined)
                                elif hasattr(w_mn_local, "setPlainText"):
                                    w_mn_local.setPlainText(joined)
                            except Exception:
                                pass
                        if not joined:
                            try:
                                jy = WidgetAccessor.get_text(getattr(self.dialog, "_add_jy", None))
                            except Exception:
                                jy = ""
                            try:
                                logger.debug("CANTO: request from candidate selection hanzi=%r", hanzi_text)
                            except Exception:
                                pass
                            try:
                                self.dialog._fetch_canto_info_async(hanzi=hanzi_text, jyutping=jy)
                            except Exception:
                                pass

                        # Focus Hanzi
                        try:
                            self.dialog._focus_hanzi(select_all=True)
                        except Exception:
                            try:
                                if hz_widget is not None and hasattr(hz_widget, "setFocus"):
                                    hz_widget.setFocus()
                            except Exception:
                                pass

                        # Update save gating
                        try:
                            if callable(fn_gate):
                                fn_gate()
                        except Exception:
                            pass

                    except Exception:
                        logger.debug("Candidate selection handler failed", exc_info=True)

                # Wire candidate selection events (outside the handler)
                sig_activated = getattr(combo, "activated", None)
                if sig_activated is not None:
                    try:
                        sig_int = sig_activated[int] if hasattr(sig_activated, "__getitem__") else sig_activated
                        self._try_connect(sig_int, _on_candidate_selected)
                    except Exception:
                        self._try_connect(sig_activated, _on_candidate_selected)

            # Final gating refresh
            if callable(fn_gate):
                try:
                    fn_gate()
                except Exception:
                    pass

        finally:
            try:
                self.dialog._add_edit_wired = True
            except Exception:
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
