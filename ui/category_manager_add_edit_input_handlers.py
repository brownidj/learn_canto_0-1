from __future__ import annotations

from ui.category_manager_add_edit_state_service import AddEditStateService
from ui.category_manager_add_edit_flow_rules import normalize_preview_payload
from ui.category_manager_add_edit_flow_services import (
    check_duplicate_jyutping,
    normalize_jyutping_text,
    validate_jyutping,
)
from ui.category_manager_add_edit_ui_actions import AddEditUIActions
from ui.category_manager_add_edit_candidate_list import AddEditCandidateListService
from ui.category_manager_add_edit_candidate_selection import AddEditCandidateSelectionService
from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter


class AddEditJyutpingHandler:
    """Handles Jyutping entry flow."""

    def __init__(self, dialog_or_adapter):
        if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
            self._dlg = dialog_or_adapter
        else:
            self._dlg = CategoryManagerDialogAdapter(dialog_or_adapter)
        self._state = AddEditStateService(self._dlg)
        self._ui = AddEditUIActions(self._dlg)

    def on_jyut_enter(self) -> None:
        jy = self._ui.get_jyutping_text()
        jy_s = normalize_jyutping_text(jy)
        self._ui.set_jyutping_text(jy_s)

        self._state.update_vm(jy=jy_s)

        if not jy_s:
            self._state.update_vm(jy_ok=False)
            self._state.sync_ctx()
            self._state.update_save_enabled()
            return

        jy_ok = validate_jyutping(self._dlg, jy_s)
        self._state.update_vm(jy_ok=bool(jy_ok))

        if not jy_ok:
            self._state.sync_ctx()
            self._state.update_save_enabled()
            return

        dup = check_duplicate_jyutping(self._dlg, jy_s)
        self._state.update_vm(duplicate=jy_s if dup else None)

        if dup:
            self._state.sync_ctx()
            self._ui.warn_duplicate_jyutping(jy_s)
            self._state.update_save_enabled()
            return

        self._state.sync_ctx()
        self._ui.focus_category(show_popup=True, select_all=True)
        self._state.update_save_enabled()


class AddEditMeaningHandler:
    """Handles Meaning entry commit flow."""

    def __init__(self, dialog_or_adapter):
        if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
            self._dlg = dialog_or_adapter
        else:
            self._dlg = CategoryManagerDialogAdapter(dialog_or_adapter)
        self._ui = AddEditUIActions(self._dlg)

    def on_meaning_enter_committed(self) -> None:
        preview = self._ui.build_preview()
        decision = self._ui.confirm_preview(preview)
        decision_s = str(decision or "").strip().lower()

        if decision_s == "save":
            payload = normalize_preview_payload(preview)
            self._ui.commit_payload(payload)
            self._ui.clear_add_entry_fields()
            self._ui.focus_jyutping(select_all=True)
            self._ui.update_save_enabled()
            return

        if decision_s == "edit":
            self._ui.focus_meaning(select_all=True)
            self._ui.update_save_enabled()
            return

        self._ui.reset_to_initial_state()
        self._ui.focus_jyutping(select_all=True)
        self._ui.update_save_enabled()


class AddEditCategoryHandler:
    """Handles category/candidate stage for Add/Edit."""

    def __init__(self, dialog_or_adapter):
        if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
            self._dlg = dialog_or_adapter
        else:
            self._dlg = CategoryManagerDialogAdapter(dialog_or_adapter)
        self._list = AddEditCandidateListService(self._dlg)
        self._selection = AddEditCandidateSelectionService(self._dlg)
        from ui.category_manager_combo_service import CategoryManagerComboService
        self._combo = CategoryManagerComboService(self._dlg)

    def fill_hanzi_candidates(self, jy: str, category: str | None = None) -> None:
        self._list.fill_candidates(jy, category)

    def on_candidate_index_activated(self, *args) -> None:
        idx = self._combo.candidate_index_from_args(args)
        if idx < 0:
            return

        self._selection.apply_selection_from_combo_index(idx)

    def on_candidate_text_changed(self, text: str) -> None:
        idx = self._combo.current_candidate_index()
        if idx < 0:
            return
        self._selection.apply_selection_from_combo_index(idx)
