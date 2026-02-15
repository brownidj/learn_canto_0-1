"""
CategoryManager category ops UI helpers.

Widget access, UI side effects, and focus helpers for category commit flow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_ui_services import CategoryManagerUIService
from ui.category_manager_category_ops_ui_combo import CategoryOpsComboEffects
from ui.category_manager_category_ops_ui_focus import CategoryOpsFocusEffects
from ui.category_manager_category_ops_ui_commit import CategoryOpsCommitEffects

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog


class CategoryOpsUI:
    """UI helper for CategoryManager category operations."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        self._dlg = CategoryManagerDialogAdapter(dialog)
        self._ui = CategoryManagerUIService(self._dlg)
        self._combo = CategoryOpsComboEffects(self._dlg)
        self._focus = CategoryOpsFocusEffects(self._dlg)
        self._commit = CategoryOpsCommitEffects(self._dlg)

    def read_category_text(self):
        """Return (combo, cat_raw)."""
        try:
            w_cat = self._ui.widget("add_cat")
        except (TypeError, AttributeError, RuntimeError):
            w_cat = None

        cat_raw = self._ui.get_text_widget(w_cat) if w_cat is not None else ""
        if not cat_raw and w_cat is not None:
            try:
                le = w_cat.lineEdit() if hasattr(w_cat, "lineEdit") else None
            except (TypeError, AttributeError, RuntimeError):
                le = None
            if le is not None:
                cat_raw = self._ui.get_text_widget(le) if le is not None else ""

        return w_cat, str(cat_raw or "").strip()

    def read_jyutping(self) -> tuple[str, bool]:
        try:
            w_jy = self._ui.widget("add_jy")
        except (TypeError, AttributeError, RuntimeError):
            w_jy = None
        try:
            jy = self._ui.get_text_widget(w_jy) if w_jy is not None else ""
        except (TypeError, AttributeError, RuntimeError):
            jy = ""
        jy_s = str(jy or "").strip()
        return jy_s, bool(jy_s)

    def clear_and_refocus(self, *, preserve_text: str = "") -> None:
        self._commit.clear_and_refocus(preserve_text=preserve_text)

    def confirm_add_category(self, canon: str) -> bool:
        try:
            add_ctrl = self._dlg.get("_cat_combo_add_ctrl")
        except (TypeError, AttributeError, RuntimeError):
            add_ctrl = None
        if add_ctrl is not None and hasattr(add_ctrl, "confirm_or_add_new_category"):
            try:
                return bool(add_ctrl.confirm_or_add_new_category(text=canon))
            except (TypeError, AttributeError, RuntimeError, ValueError):
                return False
        try:
            ctrl = self._dlg.get("_cat_combo_ctrl")
        except (TypeError, AttributeError, RuntimeError):
            ctrl = None
        if ctrl is not None and hasattr(ctrl, "confirm_add_new_category"):
            try:
                return bool(ctrl.confirm_add_new_category(text=canon))
            except (TypeError, AttributeError, RuntimeError, ValueError):
                return False
        return False

    def apply_commit_effects(self, *, w_cat, cat: str, exists_now: bool) -> None:
        self._commit.apply_commit_effects(cat=cat, exists_now=exists_now)

    def fill_candidates_after_commit(self, *, cat: str, jy: str, should_fill: bool) -> None:
        self._commit.fill_candidates_after_commit(cat=cat, jy=jy, should_fill=should_fill)

    def defer_focus_hanzi(self) -> None:
        self._focus.defer_focus_hanzi()

    def focus_category(self, *, select_all: bool = True, show_popup: bool = True) -> None:
        self._focus.focus_category(select_all=select_all, show_popup=show_popup)

    def refresh_category_dropdown_from_cats(self, *, selected: str = "") -> None:
        self._combo.refresh_category_dropdown_from_cats(selected=selected)

    def update_save_enabled(self) -> None:
        self._commit.update_save_enabled()

    def get_flag(self, name: str) -> bool:
        try:
            return bool(self._dlg.get(name, False))
        except Exception:
            return False

    def set_flag(self, name: str, value: bool) -> None:
        try:
            self._dlg.set(name, bool(value))
        except Exception:
            pass
