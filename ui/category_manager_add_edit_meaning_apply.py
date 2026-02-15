from __future__ import annotations

from ui.category_manager_add_edit_meaning import resolve_meaning_for_add_edit
from ui.category_manager_add_edit_state_service import AddEditStateService
from ui.category_manager_ui_services import CategoryManagerUIService


class AddEditMeaningApplyService:
    """Resolve meaning + apply to UI/state for Add/Edit."""

    def __init__(self, dialog_or_adapter):
        self._ui = CategoryManagerUIService(dialog_or_adapter)
        self._state = AddEditStateService(dialog_or_adapter)
        self._dlg = self._state._dlg

    def apply_meaning(
        self,
        *,
        hanzi: str,
        src: str,
        jyutping: str,
        allow_canto: bool,
    ) -> tuple[str, str]:
        joined, src_tag = resolve_meaning_for_add_edit(
            self._dlg,
            hanzi=hanzi,
            src=src,
            jyutping=jyutping,
            allow_canto=allow_canto,
        )
        if str(joined or "").strip():
            self._ui.set_meaning_text(joined)
        else:
            self._ui.set_meaning_text("")
        self._state.update_state(
            meaning=joined,
            mn_ok=bool(str(joined or "").strip()),
            meaning_source=src_tag,
        )
        return joined, src_tag
