"""
CategoryManager category operations orchestrator.

Delegates service wiring to CategoryOpsServices and UI side effects to CategoryOpsUI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ui.category_manager_category_ops_logic import CategoryOpsCommitLogic
from ui.category_manager_category_ops_ui import CategoryOpsUI

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog


class CategoryManagerCategoryOpsController:
    """Manages category operations for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        self._logic = CategoryOpsCommitLogic(dialog)
        self._ui = CategoryOpsUI(dialog)

    def ensure_category_services(self):
        return self._logic.ensure_category_services()

    def add_new_category(self, cat: str) -> bool:
        return self._logic.add_new_category(cat)

    def on_add_category_committed(self, *args, user_action: bool = False, **kwargs) -> None:
        """Commit the Add/Edit category selection (best-effort, never raises)."""
        if self._ui.get_flag("_in_cat_commit"):
            return
        self._ui.set_flag("_in_cat_commit", True)

        try:
            w_cat, cat_raw = self._ui.read_category_text()
            if not cat_raw:
                self._ui.update_save_enabled()
                return

            jy, has_jy = self._ui.read_jyutping()

            decision = self._logic.decide_commit(
                cat_raw=cat_raw,
                has_jy=has_jy,
                confirm_add_fn=self._ui.confirm_add_category,
            )
            if decision is None:
                self._ui.update_save_enabled()
                return

            if not decision.ok or not decision.category:
                self._ui.clear_and_refocus(preserve_text=decision.canon or cat_raw)
                self._ui.update_save_enabled()
                return

            self._logic.apply_commit_state(
                cat=decision.category,
                exists_now=decision.exists_now,
                user_confirmed_add=decision.user_confirmed_add,
            )
            self._ui.apply_commit_effects(
                w_cat=w_cat,
                cat=decision.category,
                exists_now=decision.exists_now,
            )

            self._ui.fill_candidates_after_commit(
                cat=decision.category,
                jy=jy,
                should_fill=bool(decision.should_fill_candidates),
            )
            self._ui.update_save_enabled()
            self._ui.defer_focus_hanzi()
        finally:
            self._ui.set_flag("_in_cat_commit", False)

    def on_add_category_changed(self, *args, **kwargs) -> None:
        """Category text changed while typing (no-op)."""
        return
