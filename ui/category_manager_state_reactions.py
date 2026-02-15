from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from domain.add_edit_sm import AddEditState


class AddEditStateReactions:
    """Apply UI/state reactions based on derived Add/Edit state."""

    def __init__(self, dialog_or_adapter):
        if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
            self._dlg = dialog_or_adapter
        else:
            self._dlg = CategoryManagerDialogAdapter(dialog_or_adapter)

    def apply_ready_state(self, *, ready: bool, hz_ok: bool) -> None:
        try:
            if ready:
                self._dlg.set("_add_edit_state", AddEditState.READY_TO_SAVE)
                if hz_ok:
                    try:
                        self._dlg.set("_hanzi_committed", True)
                    except (TypeError, AttributeError, RuntimeError):
                        pass
                    try:
                        ctrl = self._dlg.get("_focus_ctrl")
                        if ctrl is not None:
                            ctrl.mark_hanzi_committed(True)
                    except (TypeError, AttributeError, RuntimeError):
                        pass
            else:
                if self._dlg.get("_add_edit_state") == AddEditState.READY_TO_SAVE:
                    self._dlg.set("_add_edit_state", AddEditState.CATEGORY_COMMITTED)
        except (TypeError, AttributeError, RuntimeError):
            pass
