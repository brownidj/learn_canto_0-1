"""
CategoryManager manual Hanzi mode extracted for maintainability.

Handles user's custom Hanzi entry mode.
"""

from typing import TYPE_CHECKING

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_manual_hanzi_ui import (
    ensure_hanzi_editable,
    ensure_meaning_named,
    focus_hanzi,
    hide_candidates,
    mark_hanzi_uncommitted,
    refresh_save_gating,
    set_manual_mode_flags,
    update_manual_state,
)

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

class CategoryManagerManualHanziController:
    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        self._dlg = CategoryManagerDialogAdapter(dialog)

    def enter_manual_mode(self) -> None:
        """Enter manual Hanzi mode (user types their own Hanzi).

        Must not add UI elements; best-effort and never raise.
        """
        set_manual_mode_flags(self._dlg, True)
        mark_hanzi_uncommitted(self._dlg)
        update_manual_state(self._dlg)
        ensure_hanzi_editable(self._dlg)
        ensure_meaning_named(self._dlg)
        hide_candidates(self._dlg)
        focus_hanzi(self._dlg)
        refresh_save_gating(self._dlg)
