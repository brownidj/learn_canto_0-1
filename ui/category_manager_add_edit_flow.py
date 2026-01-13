"""
CategoryManager Add/Edit flow extracted for maintainability.

Handles the core workflow: Jyutping entry → Category selection → Candidate resolution → Meaning confirmation.
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from ui.widget_utils import WidgetAccessor, SignalBlocker

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerAddEditFlowController:
    """Manages Add/Edit entry workflow for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog

    def on_jyut_enter(self) -> None:
        """Commit Jyutping entry into Add/Edit SM context and advance to Category."""
        jy = WidgetAccessor.get_text(getattr(self.dialog, "_add_jy", None))
        jy_s = self.dialog._normalize_jy(jy)

        # Ensure context exists
        ctx = getattr(self.dialog, "_add_edit_ctx", None)
        if ctx is None:
            try:
                from domain.add_edit_sm import AddEditContext
                ctx = AddEditContext()
                self.dialog._add_edit_ctx = ctx
            except (TypeError, AttributeError, RuntimeError, ImportError):
                ctx = None

        def _ctx_replace(**kwargs) -> None:
            nonlocal ctx
            if ctx is None:
                return
            try:
                import dataclasses
                ctx = dataclasses.replace(ctx, **kwargs)
                self.dialog._add_edit_ctx = ctx
            except (TypeError, AttributeError, RuntimeError, ValueError):
                return

        # Write normalized back to widget
        WidgetAccessor.set_text(getattr(self.dialog, "_add_jy", None), jy_s)

        # Update context
        if ctx is not None:
            try:
                ctx.jy = jy_s
            except (TypeError, AttributeError, RuntimeError):
                _ctx_replace(jy=jy_s)

        if not jy_s:
            if ctx is not None:
                try:
                    ctx.jy_ok = False
                except (TypeError, AttributeError, RuntimeError):
                    _ctx_replace(jy_ok=False)
            self._update_save_enabled()
            return

        # Validate
        jy_ok = True
        try:
            vocab_svc = getattr(self.dialog, "_vocab_service", None)
            if vocab_svc is not None and hasattr(vocab_svc, "validate_jyutping"):
                try:
                    vocab_svc.validate_jyutping(jy_s)
                    jy_ok = True
                except Exception:
                    jy_ok = False
            else:
                from domain.jyutping_validation import validate_jyut_syllables
                jy_ok, _ = validate_jyut_syllables(jy_s)
        except Exception:
            jy_ok = True

        if ctx is not None:
            try:
                ctx.jy_ok = bool(jy_ok)
            except (TypeError, AttributeError, RuntimeError):
                _ctx_replace(jy_ok=bool(jy_ok))

        if not jy_ok:
            self._update_save_enabled()
            return

        # Duplicate detection
        dup = False
        try:
            vocab_svc = getattr(self.dialog, "_vocab_service", None)
            if vocab_svc is not None and hasattr(vocab_svc, "check_duplicate_jyutping"):
                dup = vocab_svc.check_duplicate_jyutping(jy_s)
            else:
                from domain.duplicate_rules import is_duplicate_jy
                dup = is_duplicate_jy(jy_s, vocab=self.dialog._vocab, normalize=self.dialog._normalize_jy)
        except Exception:
            dup = False

        if ctx is not None:
            try:
                ctx.duplicate = jy_s if dup else None
            except (TypeError, AttributeError, RuntimeError):
                _ctx_replace(duplicate=jy_s if dup else None)

        if dup:
            self._warn_duplicate_jy_and_reset(jy_s)
            self._update_save_enabled()
            return

        # Advance to category
        focused = False
        try:
            ctrl = getattr(self.dialog, "_cat_combo_ctrl", None)
            if ctrl is not None and hasattr(ctrl, "focus"):
                ctrl.focus()
                focused = True
        except (TypeError, AttributeError, RuntimeError):
            focused = False

        # Direct fallback: focus the Category widget itself
        if not focused:
            try:
                cat_widget = getattr(self.dialog, "_add_cat", None)
                if cat_widget is not None and hasattr(cat_widget, "setFocus"):
                    cat_widget.setFocus()
                    # Select all text in the line edit for easy typing
                    if hasattr(cat_widget, "lineEdit"):
                        le = cat_widget.lineEdit()
                        if le is not None and hasattr(le, "selectAll"):
                            QTimer.singleShot(0, le.selectAll)
            except (TypeError, AttributeError, RuntimeError):
                pass

        self._update_save_enabled()

    def on_meaning_enter_committed(self) -> None:
        """Handle Enter/commit in Meaning field with confirmation dialog.

        Workflow:
          1. Build preview with current field values (including any user edits to Meaning)
          2. Show confirmation dialog with Save/Edit/Cancel
          3. Handle user choice:
             - Save: Commit the entry, clear form, focus Jyutping
             - Edit: Return to form without clearing, focus Meaning for editing
             - Cancel: Clear form, focus Jyutping
        """
        # Build preview from current UI state
        # The builder reads directly from widgets, capturing any user edits
        try:
            preview = self.dialog._build_add_entry_preview()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            preview = {}

        # Extract values from preview for use in payload
        jy_s = str(preview.get("jyutping", "") or "").strip() if isinstance(preview, dict) else ""
        hz_s = str(preview.get("hanzi", "") or "").strip() if isinstance(preview, dict) else ""
        mn_s = str(preview.get("meaning", "") or "").strip() if isinstance(preview, dict) else ""
        cat_s = str(preview.get("category", "") or "").strip() if isinstance(preview, dict) else ""

        # Show confirmation dialog
        try:
            decision = self.dialog._confirm_add_entry(preview)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            decision = "cancel"

        decision_s = str(decision or "").strip().lower()

        # Handle Save: commit the entry using preview values
        if decision_s == "save":
            # Build payload from preview (which was shown to user and includes their edits)
            payload = dict(preview) if isinstance(preview, dict) else {}

            # Extract values from preview
            payload_jy = str(payload.get("jyutping", "") or "").strip()
            payload_hz = str(payload.get("hanzi", "") or "").strip()
            payload_mn = str(payload.get("meaning", "") or "").strip()
            payload_cat = str(payload.get("category", "") or "").strip()

            # Build category list
            cat_list = []
            if payload_cat and str(payload_cat).lower() not in ("unassigned", "all"):
                cat_list = [payload_cat]

            # Ensure payload has all required fields with correct values
            try:
                payload["jyutping"] = payload_jy
                payload["hanzi"] = payload_hz
                payload["meaning"] = payload_mn
                payload["gloss"] = payload_mn  # Legacy alias
                payload["category"] = payload_cat
                payload["categories"] = cat_list  # Legacy alias
            except (TypeError, AttributeError, RuntimeError):
                pass

            # Log for debugging
            try:
                logger.debug(
                    "Save: committing payload jy=%r hz=%r mn=%r cat=%r",
                    payload_jy, payload_hz, payload_mn, payload_cat
                )
            except (TypeError, AttributeError, RuntimeError):
                pass

            # Commit via callback or save handler
            committed = False
            cb = getattr(self.dialog, "_commit_callback", None)
            if callable(cb):
                try:
                    cb(payload)
                    committed = True
                except (TypeError, AttributeError, RuntimeError) as e:
                    try:
                        logger.debug("Commit callback failed: %s", e)
                    except (TypeError, AttributeError, RuntimeError):
                        pass

            if not committed:
                try:
                    self.dialog._on_save_clicked()
                except (TypeError, AttributeError, RuntimeError):
                    pass

            # Clear form and return to Jyutping
            self.dialog._clear_add_entry_fields()
            self.dialog._focus_jyutping(select_all=True)
            self._update_save_enabled()
            return

        # Handle Edit: return focus to Meaning field for editing
        if decision_s == "edit":
            # Focus the Meaning field so user can continue editing
            try:
                mn_widget = getattr(self.dialog, "_add_mn", None)
                if mn_widget is not None:
                    WidgetAccessor.focus(mn_widget, select_all=True)
            except (TypeError, AttributeError, RuntimeError):
                pass
            self._update_save_enabled()
            return

        # Handle Cancel: reset both Entry and Hanzi panels to initial state
        try:
            self.dialog._reset_to_initial_state()
        except (TypeError, AttributeError, RuntimeError):
            # Fallback: just clear fields
            self.dialog._clear_add_entry_fields()

        self.dialog._focus_jyutping(select_all=True)
        self._update_save_enabled()

    def _handle_save_decision(self, preview: dict) -> None:
        """Handle Save decision from confirmation dialog."""
        try:
            # Delegate to save/commit controller
            save_ctrl = getattr(self._dialog, "_save_commit", None)
            if save_ctrl is not None:
                # Commit the entry
                self._commit_entry(preview)
                # Clear form
                self._reset_form()
                # Return focus to jyutping for next entry
                self._focus_jyutping()
        except (TypeError, AttributeError, RuntimeError) as e:
            logger.debug(f"Save decision handling failed: {e}")

    def _handle_edit_decision(self) -> None:
        """Handle Edit decision from confirmation dialog."""
        try:
            # Show save button for manual confirmation
            preview_ctrl = getattr(self._dialog, "_preview_confirm", None)
            if preview_ctrl is not None:
                preview_ctrl.set_save_button_visible(True)
            # Keep focus on meaning field
            # (user is already there)
        except (TypeError, AttributeError, RuntimeError) as e:
            logger.debug(f"Edit decision handling failed: {e}")

    def _handle_cancel_decision(self) -> None:
        """Handle Cancel decision from confirmation dialog."""
        try:
            # Clear form
            self._reset_form()
            # Return focus to jyutping
            self._focus_jyutping()
        except (TypeError, AttributeError, RuntimeError) as e:
            logger.debug(f"Cancel decision handling failed: {e}")

    def _commit_entry(self, preview: dict) -> None:
        """Commit entry to storage."""
        try:
            # Call the dialog's historical commit entry point
            fn = getattr(self._dialog, "_on_add_item_enter", None)
            if callable(fn):
                fn()
        except (TypeError, AttributeError, RuntimeError) as e:
            logger.debug(f"Entry commit failed: {e}")

    def _reset_form(self) -> None:
        """Reset all entry form fields."""
        try:
            reset_ctrl = getattr(self._dialog, "_field_reset", None)
            if reset_ctrl is not None and hasattr(reset_ctrl, "clear_add_entry_fields"):
                reset_ctrl.clear_add_entry_fields()
        except (TypeError, AttributeError, RuntimeError) as e:
            logger.debug(f"Form reset failed: {e}")

    def _focus_jyutping(self) -> None:
        """Set focus to jyutping field."""
        try:
            fn = getattr(self._dialog, "_focus_jyutping", None)
            if callable(fn):
                fn()
        except (TypeError, AttributeError, RuntimeError) as e:
            logger.debug(f"Focus jyutping failed: {e}")

    def fill_hanzi_candidates(self, jy: str, category: str | None = None) -> None:
        """Fill Hanzi candidate combobox for given Jyutping."""
        jy_s = str(jy or "").strip()
        if not jy_s:
            return

        # Preserve the category selection throughout the flow
        cat_widget = getattr(self.dialog, "_add_cat", None)
        preserved_category = category or (cat_widget.currentText() if cat_widget else None)

        logger.debug("_fill_hanzi_candidates: start jy=%r category=%r", jy_s, category or "")

        # Gather candidates
        try:
            cands = self.dialog._reverse_candidates_for_jy(jy_s)
        except (TypeError, AttributeError, RuntimeError):
            cands = []

        cands_list = list(cands or [])
        logger.debug("_fill_hanzi_candidates: raw candidates n=%d", len(cands_list))

        # Find preferred within category
        preferred_hz = ""
        cat_s = str(category or "").strip()
        if cat_s:
            members = None
            try:
                cats_map = getattr(self.dialog, "_cats", None)
                members = cats_map.get(cat_s) if isinstance(cats_map, dict) else None
            except (TypeError, AttributeError, RuntimeError):
                members = None

            if isinstance(members, (list, tuple, set)) and cands_list:
                member_set = set([str(x).strip() for x in list(members) if str(x).strip()])
                if member_set:
                    for row in cands_list:
                        hz0 = str((row[0] if isinstance(row, (list, tuple)) and len(row) >= 1 else row) or "").strip()
                        if hz0 and hz0 in member_set:
                            preferred_hz = hz0
                            break

        combo = getattr(self.dialog, "_cand_combo", None)

        # Ensure controller exists
        try:
            if combo is not None:
                from ui.candidate_combo import CandidateComboController
                self.dialog._cand_combo_ctrl = CandidateComboController(combo)
            else:
                self.dialog._cand_combo_ctrl = None
        except (TypeError, AttributeError, RuntimeError, ImportError):
            self.dialog._cand_combo_ctrl = None

        ctx = getattr(self.dialog, "_add_edit_ctx", None)

        def _ctx_set(name: str, value) -> None:
            if ctx is None:
                return
            try:
                setattr(ctx, name, value)
            except (TypeError, AttributeError, RuntimeError):
                pass

        with SignalBlocker(combo):
            # Populate
            ctrl = getattr(self.dialog, "_cand_combo_ctrl", None)
            if ctrl is not None:
                try:
                    ctrl.clear()
                    ctrl.populate(cands_list)
                except (TypeError, AttributeError, RuntimeError):
                    pass

            # Empty: hide and clear
            if not cands_list:
                logger.debug("_fill_hanzi_candidates: no candidates -> hiding combo")
                WidgetAccessor.set_visible(combo, False)
                WidgetAccessor.clear_text(getattr(self.dialog, "_add_hz", None))
                WidgetAccessor.clear_text(getattr(self.dialog, "_add_mn", None))
                _ctx_set("hanzi", "")
                _ctx_set("hz_ok", False)
                _ctx_set("meaning", "")
                _ctx_set("mn_ok", False)
                self.dialog._mark_hanzi_committed(False)
                return

            # Show combo
            WidgetAccessor.set_visible(combo, True)

            # Select preferred or first
            sel_idx = 0
            if preferred_hz and combo is not None:
                try:
                    i = int(combo.findText(str(preferred_hz).strip()))
                    if i >= 0:
                        sel_idx = i
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    sel_idx = 0

            WidgetAccessor.set_combo_index(combo, sel_idx)

            # Resolve selected
            selected_hz = ""
            selected_src = ""
            try:
                row = cands_list[int(sel_idx)] if int(sel_idx) < len(cands_list) else None
            except (TypeError, AttributeError, RuntimeError, ValueError, IndexError):
                row = None

            if row is not None:
                selected_hz = str((row[0] if isinstance(row, (list, tuple)) and len(row) >= 1 else row) or "").strip()
                if isinstance(row, (list, tuple)) and len(row) > 1:
                    selected_src = str(row[1] or "").strip()

            if not selected_hz and combo is not None:
                selected_hz = str(combo.currentText() or "").strip()

            # Set Hanzi field
            w_hz2 = getattr(self.dialog, "_add_hz", None)
            if selected_hz:
                WidgetAccessor.set_text(w_hz2, selected_hz)
            else:
                WidgetAccessor.clear_text(w_hz2)

            _ctx_set("hanzi", selected_hz)
            _ctx_set("hz_ok", bool(selected_hz))

            # Meaning autofill
            joined = ""
            if selected_hz:
                try:
                    ms = self.dialog._resolve_meanings_for_candidate(selected_hz, selected_src)
                    joined = ", ".join([str(x).strip() for x in (ms or []) if str(x).strip()])
                except (TypeError, AttributeError, RuntimeError):
                    joined = ""

            if (not str(joined or "").strip()) and (len(cands_list) == 1) and selected_hz:
                try:
                    ms2 = self.dialog._meanings_for_hanzi(selected_hz)
                    joined = ", ".join([str(x).strip() for x in (ms2 or []) if str(x).strip()])
                except (TypeError, AttributeError, RuntimeError):
                    joined = ""

            w_mn2 = getattr(self.dialog, "_add_mn", None)
            if str(joined or "").strip():
                WidgetAccessor.set_text(w_mn2, joined)
            else:
                WidgetAccessor.clear_text(w_mn2)

            _ctx_set("meaning", joined)
            _ctx_set("mn_ok", bool(str(joined or "").strip()))

            # Mark committed if single candidate
            if len(cands_list) == 1 and bool(selected_hz):
                self.dialog._mark_hanzi_committed(True)
            else:
                self.dialog._mark_hanzi_committed(False)

        # Refresh Save gating
        self._update_save_enabled()

        # Restore category if it was inadvertently cleared
        if preserved_category and cat_widget:
            current_text = cat_widget.currentText()
            if not current_text or current_text.strip() == "":
                try:
                    # Restore the category text without triggering signals
                    with SignalBlocker(cat_widget):
                        cat_widget.setCurrentText(str(preserved_category))
                    logger.debug("_fill_hanzi_candidates: restored category to %r", preserved_category)
                except (TypeError, AttributeError, RuntimeError):
                    pass

        # Focus behaviour
        if len(cands_list) == 1:
            WidgetAccessor.focus(getattr(self.dialog, "_add_mn", None))
        else:
            WidgetAccessor.focus(combo)

    def on_candidate_index_activated(self, *args) -> None:
        """Handle candidate selection from combobox."""
        combo = getattr(self.dialog, "_cand_combo", None)
        if combo is None:
            return

        idx = None
        if args:
            a0 = args[0]
            if isinstance(a0, int):
                idx = a0
            elif isinstance(a0, str):
                try:
                    idx = int(combo.findText(a0))
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    idx = None

        if idx is None:
            try:
                idx = int(combo.currentIndex())
            except (TypeError, AttributeError, RuntimeError, ValueError):
                idx = -1

        if idx < 0:
            return

        # Get selected Hanzi
        selected_hz = ""
        try:
            if hasattr(combo, "itemText"):
                selected_hz = str(combo.itemText(idx) or "").strip()
        except (TypeError, AttributeError, RuntimeError):
            selected_hz = ""

        if not selected_hz:
            try:
                selected_hz = str(combo.currentText() or "").strip()
            except (TypeError, AttributeError, RuntimeError):
                selected_hz = ""

        if not selected_hz:
            return

        # Get src from itemData
        src = ""
        try:
            from PySide6.QtCore import Qt as _Qt
            data = None
            try:
                data = combo.itemData(idx)
            except (TypeError, AttributeError, RuntimeError):
                data = None

            if (data is None) and (_Qt is not None):
                try:
                    data = combo.itemData(idx, _Qt.ItemDataRole.UserRole)
                except (TypeError, AttributeError, RuntimeError):
                    data = None

            if isinstance(data, dict):
                src = str(data.get("src", "") or "").strip()
            elif isinstance(data, (list, tuple)) and len(data) >= 2:
                src = str(data[1] or "").strip()
        except (TypeError, AttributeError, RuntimeError):
            src = ""

        # Apply selection
        WidgetAccessor.set_text(getattr(self.dialog, "_add_hz", None), selected_hz)

        try:
            ms = self.dialog._resolve_meanings_for_candidate(selected_hz, src)
            joined = ", ".join([str(x).strip() for x in (ms or []) if str(x).strip()])
            WidgetAccessor.set_text(getattr(self.dialog, "_add_mn", None), joined)
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Update context
        ctx = getattr(self.dialog, "_add_edit_ctx", None)
        if ctx is not None:
            try:
                ctx.hanzi = selected_hz
            except (TypeError, AttributeError, RuntimeError):
                pass

        self._update_save_enabled()

        # Focus meanings
        w_mn = getattr(self.dialog, "_add_mn", None)
        if w_mn is not None and hasattr(w_mn, "setFocus"):
            try:
                QTimer.singleShot(0, w_mn.setFocus)
            except (TypeError, AttributeError, RuntimeError):
                try:
                    w_mn.setFocus()
                except (TypeError, AttributeError, RuntimeError):
                    pass

    def on_candidate_text_changed(self, text: str) -> None:
        """Delegate to index-activated for consistent logic."""
        try:
            combo = getattr(self.dialog, "_cand_combo", None)
            if combo is None:
                return
            idx = int(combo.currentIndex())
            if idx < 0:
                return
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return

        try:
            self.on_candidate_index_activated(idx)
        except (TypeError, AttributeError, RuntimeError):
            return

    def _warn_duplicate_jy_and_reset(self, jy: str) -> None:
        """Warn about duplicate Jyutping and refocus."""
        try:
            QMessageBox.warning(
                self.dialog,
                "Duplicate Jyutping",
                f'The Jyutping "{jy}" already exists in your vocabulary.\n\nPlease edit the Jyutping and try again.',
            )
        except (TypeError, AttributeError, RuntimeError):
            pass

        self.dialog._focus_jyutping(select_all=True)

    def _update_save_enabled(self) -> None:
        """Delegate to dialog's save gating logic."""
        try:
            fn = getattr(self.dialog, "_update_save_enabled", None)
            if callable(fn):
                fn()
        except (TypeError, AttributeError, RuntimeError):
            pass
