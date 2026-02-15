from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_field_reset_state import (
    reset_add_edit_state,
    reset_hanzi_committed,
    reset_state_machine,
)
from ui.category_manager_field_reset_ui import refresh_save_gating
from ui.category_manager_field_reset_widgets import (
    clear_text_fields,
    reset_candidates_ui,
    reset_category,
    reset_hanzi_editable,
    reset_manual_mode,
    reset_notes,
)


class FieldResetEffects:
    """UI effects for field reset plans."""

    def __init__(self, dialog_or_adapter):
        if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
            self._dlg = dialog_or_adapter
        else:
            self._dlg = CategoryManagerDialogAdapter(dialog_or_adapter)

    def apply(self, plan) -> None:
        clear_text_fields(self._dlg, plan)
        reset_notes(self._dlg, plan)
        reset_category(self._dlg, plan)
        reset_manual_mode(self._dlg, plan)
        reset_add_edit_state(self._dlg, plan)
        reset_hanzi_editable(self._dlg)
        reset_candidates_ui(self._dlg, plan)
        reset_hanzi_committed(self._dlg, plan)
        reset_state_machine(self._dlg, plan)
        refresh_save_gating(self._dlg)
