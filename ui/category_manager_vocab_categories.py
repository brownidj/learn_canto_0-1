from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_combo_service import CategoryManagerComboService


class CategoryManagerVocabCategories:
    """Category dropdown refresh helpers for vocab display."""

    @staticmethod
    def refresh_category_dropdown_from_cats(dialog, *, selected: str = "") -> None:
        dlg = dialog if isinstance(dialog, CategoryManagerDialogAdapter) else CategoryManagerDialogAdapter(dialog)
        try:
            cats_map = dlg.get("_cats")
        except (TypeError, AttributeError, RuntimeError):
            cats_map = None

        CategoryManagerComboService(dlg).refresh_category_dropdown(cats_map, selected=selected)
