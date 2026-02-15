from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_widgets import resolve_category_manager_widgets
from ui.focus_policy import should_steal_focus
from ui.ui_services import focus, get_text, set_text, signals_blocked


class CategoryManagerFocusService:
    """Unified focus policy + effects for CategoryManager."""

    def __init__(self, dialog_or_adapter):
        if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
            self._dlg = dialog_or_adapter
        else:
            self._dlg = CategoryManagerDialogAdapter(dialog_or_adapter)
        self._widgets = None

    def _widget(self, key: str):
        if not isinstance(self._widgets, dict):
            self._widgets = resolve_category_manager_widgets(self._dlg)
        w = self._widgets.get(key) if isinstance(self._widgets, dict) else None
        if w is None:
            self._widgets = resolve_category_manager_widgets(self._dlg)
            w = self._widgets.get(key) if isinstance(self._widgets, dict) else None
        return w

    def focus_context(self) -> dict[str, bool]:
        combo = self._widget("cand_combo")
        try:
            _combo_hf = getattr(combo, "hasFocus", None)
            combo_has_focus = bool(combo is not None and callable(_combo_hf) and _combo_hf())
        except (TypeError, AttributeError, RuntimeError, ValueError):
            combo_has_focus = False

        try:
            view = combo.view() if combo is not None else None
        except (TypeError, AttributeError, RuntimeError, ValueError):
            view = None

        try:
            _view_hf = getattr(view, "hasFocus", None)
            view_has_focus = bool(view is not None and callable(_view_hf) and _view_hf())
        except (TypeError, AttributeError, RuntimeError, ValueError):
            view_has_focus = False

        manual_mode = bool(self._dlg.get("_manual_hanzi_mode", False))
        hanzi_committed = bool(self._dlg.get("_hanzi_committed", False))

        return {
            "combo_has_focus": combo_has_focus,
            "view_has_focus": view_has_focus,
            "manual_mode": manual_mode,
            "hanzi_committed": hanzi_committed,
        }

    def should_apply_focus(
        self,
        *,
        reason: str = "",
        user_action: bool = False,
        manual_mode: bool = False,
        hanzi_committed: bool = False,
        combo_has_focus: bool = False,
        view_has_focus: bool = False,
    ) -> bool:
        try:
            return bool(
                should_steal_focus(
                    reason=reason,
                    user_action=bool(user_action),
                    manual_mode=bool(manual_mode),
                    hanzi_committed=bool(hanzi_committed),
                    combo_has_focus=bool(combo_has_focus),
                    view_has_focus=bool(view_has_focus),
                )
            )
        except TypeError:
            try:
                return bool(
                    should_steal_focus(
                        bool(user_action),
                        bool(combo_has_focus),
                        bool(view_has_focus),
                        bool(manual_mode),
                        bool(hanzi_committed),
                    )
                )
            except (TypeError, AttributeError, RuntimeError, ValueError):
                return False
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return False

    def apply_focus_policy(
        self,
        *,
        target: str,
        reason: str = "",
        user_action: bool = False,
        show_popup: bool = False,
        select_all: bool = True,
    ) -> bool:
        ctx = self.focus_context()
        allowed = self.should_apply_focus(
            reason=reason,
            user_action=user_action,
            manual_mode=ctx["manual_mode"],
            hanzi_committed=ctx["hanzi_committed"],
            combo_has_focus=ctx["combo_has_focus"],
            view_has_focus=ctx["view_has_focus"],
        )
        if not allowed:
            return False

        if target == "jy":
            self.focus_jyutping(select_all=select_all)
            return True
        if target == "hz":
            self.focus_hanzi(select_all=select_all)
            return True
        if target == "mn":
            self.focus_meaning(select_all=select_all)
            return True
        if target == "cat":
            self.focus_category(select_all=select_all, show_popup=show_popup)
            return True
        return False

    def focus_jyutping(self, *, select_all: bool = True) -> None:
        focus(self._widget("add_jy"), select_all=bool(select_all))

    def focus_meaning(self, *, select_all: bool = True) -> None:
        focus(self._widget("add_mn"), select_all=bool(select_all))

    def focus_hanzi(self, *, select_all: bool = True) -> None:
        focus(self._widget("add_hz"), select_all=bool(select_all))

    def focus_category(self, *, select_all: bool = True, show_popup: bool = False) -> None:
        try:
            ctrl = self._dlg.get("_cat_combo_ctrl")
        except (TypeError, AttributeError, RuntimeError):
            ctrl = None
        if ctrl is not None and hasattr(ctrl, "focus"):
            try:
                ctrl.focus(select_all=select_all, show_popup=show_popup)
                return
            except (TypeError, AttributeError, RuntimeError):
                pass

        combo = self._widget("add_cat")
        focus(combo, select_all=bool(select_all))
        if show_popup and combo is not None:
            try:
                if hasattr(combo, "showPopup"):
                    combo.showPopup()
            except (TypeError, AttributeError, RuntimeError):
                pass

    def focus_candidates(self) -> bool:
        combo = self._widget("cand_combo")
        if combo is None:
            return False
        try:
            combo.setVisible(True)
        except (TypeError, AttributeError, RuntimeError):
            pass
        focus(combo, select_all=False)
        return True

    def enter_manual_mode_if_readonly(self) -> None:
        try:
            hz = self._widget("add_hz")
            hz_ro = bool(hz.isReadOnly()) if hz is not None else False
        except (TypeError, AttributeError, RuntimeError):
            hz_ro = False

        if not hz_ro:
            return

        try:
            self._dlg.call("_on_btn_custom_hz_clicked")
            return
        except (TypeError, AttributeError, RuntimeError):
            pass

        try:
            btn = self._widget("btn_custom_hz")
            if btn is not None and btn.isEnabled() and btn.isVisible():
                btn.click()
        except (TypeError, AttributeError, RuntimeError):
            pass

    def defer_focus(self, target: str, *, select_all: bool = True) -> None:
        try:
            from PySide6.QtCore import QTimer
        except (ImportError, TypeError):
            QTimer = None

        def _apply() -> None:
            if target == "cand":
                w_cat = self._widget("add_cat")
                vm = self._dlg.get("_add_edit_vm")
                current_cat = get_text(w_cat)
                ctx_cat = str(getattr(vm, "category", "") or "").strip() if vm is not None else ""
                last_cat = str(self._dlg.get("_last_committed_category", "") or "").strip()
                restore_cat = ctx_cat or last_cat
                if w_cat is not None and not current_cat and restore_cat:
                    with signals_blocked(w_cat):
                        try:
                            if hasattr(w_cat, "setCurrentText"):
                                w_cat.setCurrentText(restore_cat)
                            else:
                                set_text(w_cat, restore_cat)
                        except (TypeError, AttributeError, RuntimeError):
                            pass

            try:
                if target == "cand":
                    if self.focus_candidates():
                        return
                    target2 = "hz"
                else:
                    target2 = target

                if target2 == "hz":
                    self.focus_hanzi(select_all=bool(select_all))
                    self.enter_manual_mode_if_readonly()
                    self.focus_hanzi(select_all=bool(select_all))
                    return

                if target2 == "mn":
                    self.focus_meaning(select_all=True)
                    return
                if target2 == "jy":
                    self.focus_jyutping(select_all=True)
                    return
                if target2 == "cat":
                    self.focus_category(select_all=True, show_popup=True)
                    return

            except (TypeError, AttributeError, RuntimeError):
                pass

        if QTimer is not None and hasattr(QTimer, "singleShot"):
            try:
                QTimer.singleShot(0, _apply)
                return
            except (TypeError, AttributeError, RuntimeError):
                pass

        _apply()
