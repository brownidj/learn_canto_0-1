"""
CategoryManager Add/Edit flow orchestrator.

Workflow: Jyutping entry -> Category selection -> Candidate resolution -> Meaning confirmation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ui.category_manager_add_edit_input_handlers import (
    AddEditCategoryHandler,
    AddEditJyutpingHandler,
    AddEditMeaningHandler,
)
from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog



class CategoryManagerAddEditFlowController:
    """Manages Add/Edit entry workflow for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        self._dlg = CategoryManagerDialogAdapter(dialog)
        self._jy = AddEditJyutpingHandler(self._dlg)
        self._cat = AddEditCategoryHandler(self._dlg)
        self._mn = AddEditMeaningHandler(self._dlg)

    def on_jyut_enter(self) -> None:
        """Commit Jyutping entry into Add/Edit SM context and advance to Category."""
        self._jy.on_jyut_enter()

    def on_meaning_enter_committed(self) -> None:
        """Handle Enter/commit in Meaning field with confirmation dialog."""
        self._mn.on_meaning_enter_committed()

    def fill_hanzi_candidates(self, jy: str, category: str | None = None) -> None:
        """Fill Hanzi candidate combobox for given Jyutping."""
        self._cat.fill_hanzi_candidates(jy, category)

    def on_candidate_index_activated(self, *args) -> None:
        """Handle candidate selection from combobox."""
        self._cat.on_candidate_index_activated(*args)

    def on_candidate_text_changed(self, text: str) -> None:
        """Delegate to index-activated for consistent logic."""
        self._cat.on_candidate_text_changed(text)

    def _sync_add_edit_ctx(self) -> None:
        try:
            self._dlg.sync_add_edit_ctx()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass
