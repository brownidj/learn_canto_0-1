from __future__ import annotations

from ui.category_manager_add_edit_meaning_apply import AddEditMeaningApplyService
from ui.category_manager_add_edit_state_service import AddEditStateService
from ui.category_manager_combo_service import CategoryManagerComboService
from ui.category_manager_ui_services import CategoryManagerUIService


class AddEditCandidateSelectionService:
    """Candidate selection + meaning application for Add/Edit."""

    def __init__(self, dialog_or_adapter):
        self._ui = CategoryManagerUIService(dialog_or_adapter)
        self._state = AddEditStateService(dialog_or_adapter)
        self._meaning = AddEditMeaningApplyService(dialog_or_adapter)
        self._combo = CategoryManagerComboService(dialog_or_adapter)

    def apply_selection(
        self,
        *,
        hanzi: str,
        src: str,
        jyutping: str = "",
        allow_canto: bool = False,
        focus_meaning: bool = True,
        update_save: bool = True,
    ) -> None:
        hz = str(hanzi or "").strip()
        if not hz:
            return
        self._ui.set_hanzi_text(hz)
        self._state.update_state(hanzi=hz, hz_ok=bool(hz))
        self._meaning.apply_meaning(
            hanzi=hz,
            src=str(src or "").strip(),
            jyutping=str(jyutping or "").strip(),
            allow_canto=bool(allow_canto),
        )
        if update_save:
            self._state.update_save_enabled()
        if focus_meaning:
            self._ui.focus_meaning(select_all=True)

    def apply_selection_from_combo_index(self, idx: int) -> None:
        hanzi = self._combo.candidate_text_for_index(idx)
        if not hanzi or hanzi.startswith("—"):
            return
        src = self._combo.candidate_src_for_index(idx)
        self.apply_selection(hanzi=hanzi, src=src, allow_canto=False, focus_meaning=True)

    def apply_hanzi_enter(self, *, hanzi: str, src: str, jyutping: str) -> None:
        self.apply_selection(
            hanzi=hanzi,
            src=src,
            jyutping=jyutping,
            allow_canto=True,
            focus_meaning=True,
            update_save=True,
        )
