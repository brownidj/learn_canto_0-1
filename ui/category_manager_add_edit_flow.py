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
        try:
            ctrl = getattr(self.dialog, "_cat_combo_ctrl", None)
            if ctrl is not None and hasattr(ctrl, "focus"):
                ctrl.focus()
        except (TypeError, AttributeError, RuntimeError):
            pass

        self._update_save_enabled()

    def on_meaning_enter_committed(self) -> None:
        """Handle Enter/commit in Meaning field with confirmation dialog."""
        try:
            preview = self.dialog._build_add_entry_preview()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            preview = {}

        jy_s, hz_s, mn_s, cat_s = self.dialog._read_add_fields()

        # Gather categories payload
        cats_out = []

        def _cat_ok(s) -> bool:
            try:
                t = str(s or "").strip()
                return bool(t) and t.lower() not in ("unassigned", "all")
            except Exception:
                return False

        def _first_valid(values):
            if values is None:
                return ""
            if isinstance(values, str):
                return str(values).strip() if _cat_ok(values) else ""
            if isinstance(values, (list, tuple, set)):
                for v in list(values):
                    if _cat_ok(v):
                        return str(v).strip()
            return ""

        # Source 1: read field
        if _cat_ok(cat_s):
            cats_out = [cat_s]

        # Source 2: widget
        if not cats_out:
            w_cat2 = getattr(self.dialog, "_add_cat", None)
            t2 = WidgetAccessor.get_text(w_cat2)
            if _cat_ok(t2):
                cats_out = [t2]

        # Source 3: preview
        if not cats_out and isinstance(preview, dict):
            for k in ("category", "cat", "categories", "cats"):
                c = _first_valid(preview.get(k))
                if c:
                    cats_out = [c]
                    break

        # Source 4: context
        if not cats_out:
            ctx3 = getattr(self.dialog, "_add_edit_ctx", None)
            if ctx3 is not None:
                c3 = getattr(ctx3, "category", "") or getattr(ctx3, "cat", "")
                if _cat_ok(c3):
                    cats_out = [str(c3).strip()]

        # User decision
        try:
            decision = self.dialog._confirm_add_entry(preview)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            decision = "edit"

        decision_s = str(decision or "").strip().lower()

        # Save: commit once
        if decision_s == "save":
            payload = dict(preview) if isinstance(preview, dict) else {}
            try:
                payload["jyutping"] = jy_s
                payload["hanzi"] = hz_s
                payload["meaning"] = mn_s
                payload["gloss"] = mn_s
                if cats_out:
                    payload["categories"] = list(cats_out)
                else:
                    existing = payload.get("categories")
                    if isinstance(existing, (list, tuple, set)) and list(existing):
                        payload["categories"] = [str(x).strip() for x in list(existing) if str(x).strip()]
                    else:
                        payload["categories"] = []
            except Exception:
                pass

            committed_once = False
            cb = getattr(self.dialog, "_commit_callback", None)
            if callable(cb):
                try:
                    cb(payload)
                    committed_once = True
                except (TypeError, AttributeError, RuntimeError):
                    committed_once = False

            if not committed_once:
                try:
                    self.dialog._on_save_clicked()
                except (TypeError, AttributeError, RuntimeError):
                    pass

            self.dialog._clear_add_entry_fields()
            self.dialog._set_save_button_visible(False)
            self.dialog._focus_jyutping(select_all=True)
            self._update_save_enabled()
            return

        # Edit: show Save button
        if decision_s == "edit":
            self.dialog._set_save_button_visible(True)
            self._update_save_enabled()
            return

        # Cancel: clear and refocus
        self.dialog._clear_add_entry_fields()
        self.dialog._set_save_button_visible(False)
        self.dialog._focus_jyutping(select_all=True)
        self._update_save_enabled()

    def fill_hanzi_candidates(self, jy: str, category: str | None = None) -> None:
        """Fill Hanzi candidate combobox for given Jyutping."""
        jy_s = str(jy or "").strip()
        if not jy_s:
            return

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
                f"The Jyutping "{jy}" already exists in your vocabulary.\n\nPlease edit the Jyutping and try again.",
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
