"""Category combo add-new coordinator (UI prompt + add callback)."""

from __future__ import annotations

from typing import Callable

from ui.category_combo import CategoryComboController


class CategoryComboAddController:
    """Orchestrates confirm + add for category combo."""

    def __init__(self, *, combo_ctrl: CategoryComboController, on_add_new: Callable[[str], bool] | None):
        self._combo_ctrl = combo_ctrl
        self._on_add_new = on_add_new

    def confirm_or_add_new_category(self, *, text: str | None = None) -> bool:
        cat = (text or self._combo_ctrl.current_text() or "").strip()
        if not cat:
            return False

        want_add = self._combo_ctrl.confirm_add_new_category(text=cat)
        if not want_add:
            return False

        fn = self._on_add_new
        if callable(fn):
            try:
                return bool(fn(cat))
            except (TypeError, AttributeError, RuntimeError, ValueError, OSError):
                return False
        return False
