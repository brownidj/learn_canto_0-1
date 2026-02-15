from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_focus_service import CategoryManagerFocusService
from ui.category_manager_ui_services import CategoryManagerUIService


class CategoryOpsFocusEffects:
    """Focus and popup effects for category ops."""

    def __init__(self, dialog_or_adapter):
        if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
            self._dlg = dialog_or_adapter
        else:
            self._dlg = CategoryManagerDialogAdapter(dialog_or_adapter)
        self._ui = CategoryManagerUIService(self._dlg)
        self._focus = CategoryManagerFocusService(self._dlg)

    def defer_focus_hanzi(self) -> None:
        self.close_combo_popups()
        self._focus.defer_focus("hz", select_all=False)

    def close_combo_popups(self) -> None:
        try:
            combos = [self._ui.widget("cand_combo"), self._ui.widget("add_cat")]
        except (TypeError, AttributeError, RuntimeError):
            combos = [None, None]
        for combo in combos:
            if combo is None:
                continue
            try:
                if hasattr(combo, "hidePopup"):
                    combo.hidePopup()
            except (TypeError, AttributeError, RuntimeError):
                pass
            try:
                view = combo.view() if hasattr(combo, "view") else None
            except (TypeError, AttributeError, RuntimeError):
                view = None
            if view is not None:
                try:
                    view.clearFocus()
                except (TypeError, AttributeError, RuntimeError):
                    pass
            try:
                combo.clearFocus()
            except (TypeError, AttributeError, RuntimeError):
                pass

    def focus_category(self, *, select_all: bool = True, show_popup: bool = True) -> None:
        self._focus.focus_category(select_all=select_all, show_popup=show_popup)
