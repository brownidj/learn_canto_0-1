from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_ui_services import CategoryManagerUIService
from ui.category_manager_category_ops_ui_combo import CategoryOpsComboEffects
from ui.category_manager_category_ops_ui_focus import CategoryOpsFocusEffects


class CategoryOpsCommitEffects:
    """Commit-side UI effects for category ops."""

    def __init__(self, dialog_or_adapter):
        if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
            self._dlg = dialog_or_adapter
        else:
            self._dlg = CategoryManagerDialogAdapter(dialog_or_adapter)
        self._ui = CategoryManagerUIService(self._dlg)
        self._combo = CategoryOpsComboEffects(self._dlg)
        self._focus = CategoryOpsFocusEffects(self._dlg)

    def clear_and_refocus(self, *, preserve_text: str = "") -> None:
        preserve = str(preserve_text or "").strip()

        if preserve:
            try:
                w = self._ui.widget("add_cat")
            except (TypeError, AttributeError, RuntimeError):
                w = None

            if w is not None:
                with self._ui.block_signals("add_cat"):
                    try:
                        if hasattr(w, "setCurrentText"):
                            w.setCurrentText(preserve)
                        else:
                            self._ui.set_text_widget(w, preserve)
                    except (TypeError, AttributeError, RuntimeError):
                        pass
            self._focus.focus_category(select_all=True, show_popup=True)
            return

        try:
            ctrl2 = self._dlg.get("_cat_combo_ctrl")
        except (TypeError, AttributeError, RuntimeError):
            ctrl2 = None

        if ctrl2 is not None and hasattr(ctrl2, "clear_and_refocus"):
            try:
                ctrl2.clear_and_refocus()
                return
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

        try:
            w = self._ui.widget("add_cat")
        except (TypeError, AttributeError, RuntimeError):
            w = None

        if w is not None:
            with self._ui.block_signals("add_cat"):
                try:
                    le2 = w.lineEdit() if hasattr(w, "lineEdit") else None
                except (TypeError, AttributeError, RuntimeError):
                    le2 = None

                if le2 is not None:
                    try:
                        le2.clear()
                    except (TypeError, AttributeError, RuntimeError):
                        pass

                try:
                    w.setCurrentIndex(-1)
                except (TypeError, AttributeError, RuntimeError):
                    try:
                        w.setCurrentText("")
                    except (TypeError, AttributeError, RuntimeError):
                        pass

        self._focus.focus_category(select_all=True, show_popup=True)

    def apply_commit_effects(self, *, cat: str, exists_now: bool) -> None:
        self._combo.apply_commit_effects(cat=cat, exists_now=exists_now)

    def fill_candidates_after_commit(self, *, cat: str, jy: str, should_fill: bool) -> None:
        if not bool(should_fill):
            return

        try:
            flow = self._dlg.get("_add_edit_flow")
        except (TypeError, AttributeError, RuntimeError):
            flow = None

        if flow is not None and hasattr(flow, "fill_hanzi_candidates"):
            try:
                flow.fill_hanzi_candidates(jy, category=cat)
            except TypeError:
                try:
                    flow.fill_hanzi_candidates(jy)
                except (TypeError, AttributeError, RuntimeError):
                    pass
            except (TypeError, AttributeError, RuntimeError):
                pass

    def update_save_enabled(self) -> None:
        self._dlg.call("_update_save_enabled")
