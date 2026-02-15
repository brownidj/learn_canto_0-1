from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_add_edit_candidate_selection import AddEditCandidateSelectionService
from ui.category_manager_ui_services import CategoryManagerUIService
from ui.category_manager_combo_service import CategoryManagerComboService


class AddEditCoordinator:
    """Single coordination point for Add/Edit signal handlers."""

    def __init__(self, dialog_or_adapter):
        if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
            self._dlg = dialog_or_adapter
        else:
            self._dlg = CategoryManagerDialogAdapter(dialog_or_adapter)
        self._ui = CategoryManagerUIService(self._dlg)
        self._cand = AddEditCandidateSelectionService(self._dlg)
        self._combo = CategoryManagerComboService(self._dlg)

    def _flow(self):
        try:
            return self._dlg.get("_add_edit_flow")
        except (TypeError, AttributeError, RuntimeError):
            return None

    def on_jyut_enter(self) -> None:
        flow = self._flow()
        if flow is not None and hasattr(flow, "on_jyut_enter"):
            try:
                flow.on_jyut_enter()
            except (TypeError, AttributeError, RuntimeError):
                pass

    def on_meaning_enter(self) -> None:
        flow = self._flow()
        if flow is not None and hasattr(flow, "on_meaning_enter_committed"):
            try:
                flow.on_meaning_enter_committed()
            except (TypeError, AttributeError, RuntimeError):
                pass

    def on_hanzi_enter(self, hz_text: str) -> None:
        hz = str(hz_text or "").strip()
        if not hz:
            return
        idx = self._combo.current_candidate_index()
        src = self._combo.candidate_src_for_index(idx) if idx >= 0 else ""
        jy = self._ui.get_text("add_jy")

        self._cand.apply_hanzi_enter(hanzi=hz, src=src, jyutping=jy)

    def on_candidate_selected(self, idx: int) -> None:
        self._cand.apply_selection_from_combo_index(idx)

    def on_candidate_text_changed(self) -> None:
        idx = self._combo.current_candidate_index()
        if idx < 0:
            return
        self.on_candidate_selected(idx)
