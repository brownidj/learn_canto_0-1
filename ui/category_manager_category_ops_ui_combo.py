from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_combo_service import CategoryManagerComboService


class CategoryOpsComboEffects:
    """Combo refresh + selection effects for category ops."""

    def __init__(self, dialog_or_adapter):
        if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
            self._dlg = dialog_or_adapter
        else:
            self._dlg = CategoryManagerDialogAdapter(dialog_or_adapter)
        self._combo = CategoryManagerComboService(self._dlg)

    def apply_commit_effects(self, *, cat: str, exists_now: bool) -> None:
        self._combo.ensure_category_in_combo(cat)
        self._combo.set_category_selection(cat)
        try:
            if not exists_now:
                self.refresh_category_dropdown_from_cats(selected=cat)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

    def refresh_category_dropdown_from_cats(self, *, selected: str = "") -> None:
        try:
            cats_map = self._dlg.get("_cats")
        except (TypeError, AttributeError, RuntimeError):
            cats_map = None
        self._combo.refresh_category_dropdown(cats_map, selected=selected)
