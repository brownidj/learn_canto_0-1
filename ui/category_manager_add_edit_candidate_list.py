from __future__ import annotations

from ui.category_manager_add_edit_flow_services import (
    get_candidates,
    preferred_hanzi_for_category,
)
from ui.category_manager_add_edit_state_service import AddEditStateService
from ui.category_manager_add_edit_candidate_selection import AddEditCandidateSelectionService
from ui.category_manager_combo_service import CategoryManagerComboService
from ui.category_manager_ui_services import CategoryManagerUIService


class AddEditCandidateListService:
    """Candidate list population for Add/Edit."""

    def __init__(self, dialog_or_adapter):
        self._ui = CategoryManagerUIService(dialog_or_adapter)
        self._state = AddEditStateService(dialog_or_adapter)
        self._combo = CategoryManagerComboService(dialog_or_adapter)
        self._selection = AddEditCandidateSelectionService(dialog_or_adapter)
        self._dlg = self._state._dlg

    def _candidate_row(self, cands_list: list, idx: int):
        try:
            return cands_list[int(idx)] if int(idx) < len(cands_list) else None
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return None

    def _candidate_hanzi_src(self, combo, idx: int, cands_list: list):
        hz = ""
        src = ""
        row = self._candidate_row(cands_list, idx)
        if row is not None:
            hz = str((row[0] if isinstance(row, (list, tuple)) and len(row) >= 1 else row) or "").strip()
            if isinstance(row, (list, tuple)) and len(row) > 1:
                src = str(row[1] or "").strip()
        if not hz and combo is not None:
            try:
                hz = str(combo.currentText() or "").strip()
            except (TypeError, AttributeError, RuntimeError, ValueError):
                hz = ""
        return hz, src

    def fill_candidates(self, jy: str, category: str | None = None) -> None:
        jy_s = str(jy or "").strip()
        if not jy_s:
            return

        preserved_category = category or self._ui.get_category_text()
        if not preserved_category:
            try:
                vm = self._state.get_state()
                preserved_category = str(getattr(vm, "category", "") or "").strip() if vm is not None else ""
            except (TypeError, AttributeError, RuntimeError, ValueError):
                preserved_category = ""

        try:
            print(f"DBG[CAND] get_candidates jy='{jy_s}' category='{category or ''}' preserved='{preserved_category}'")
        except Exception:
            pass
        cands_list = get_candidates(self._dlg, jy_s)
        try:
            print(f"DBG[CAND] candidates count={len(cands_list) if cands_list is not None else 'None'}")
        except Exception:
            pass
        preferred_hz = preferred_hanzi_for_category(self._dlg, cands_list, category)

        combo = self._ui.widget("cand_combo")
        selected_hz = ""
        with self._ui.block_signals("cand_combo"):
            self._combo.populate_candidates(cands_list)

            if not cands_list:
                self._ui.hide_candidates()
                self._ui.clear_hanzi_and_meaning()
                self._state.update_state(
                    hanzi="",
                    hz_ok=False,
                    meaning="",
                    mn_ok=False,
                    candidates=(),
                )
                self._state.mark_hanzi_committed(False)
                return

            self._ui.show_candidates()

            sel_idx = 0
            if preferred_hz and combo is not None:
                try:
                    i = int(combo.findText(str(preferred_hz).strip()))
                    if i >= 0:
                        sel_idx = i
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    sel_idx = 0

            self._ui.set_candidate_index(sel_idx)

            selected_hz, selected_src = self._candidate_hanzi_src(combo, sel_idx, cands_list)
            if selected_hz:
                self._selection.apply_selection(
                    hanzi=selected_hz,
                    src=selected_src,
                    jyutping=jy_s,
                    allow_canto=True,
                    focus_meaning=False,
                    update_save=False,
                )
            else:
                self._ui.set_hanzi_text("")
                self._ui.set_meaning_text("")
                self._state.update_state(
                    hanzi="",
                    hz_ok=False,
                    meaning="",
                    mn_ok=False,
                    meaning_source="",
                )

        self._state.update_state(candidates=tuple(cands_list))

        self._state.mark_hanzi_committed(len(cands_list) == 1 and bool(selected_hz))
        self._state.update_save_enabled()

        if preserved_category and self._ui.get_category_text() == "":
            self._ui.set_category_text(preserved_category)

        self._ui.hide_candidate_popup()
        self._ui.focus_hanzi_later(select_all=False)
