from __future__ import annotations

from contextlib import contextmanager

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_focus_service import CategoryManagerFocusService
from ui.category_manager_widgets import resolve_category_manager_widgets
from ui.ui_services import (
    clear_text,
    focus,
    get_text,
    set_combo_index,
    set_enabled,
    set_readonly,
    set_text,
    set_visible,
    signals_blocked,
)


def _adapter(dialog_or_adapter) -> CategoryManagerDialogAdapter:
    if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
        return dialog_or_adapter
    return CategoryManagerDialogAdapter(dialog_or_adapter)


class CategoryManagerUIService:
    """Shared UI side effects for CategoryManager."""

    def __init__(self, dialog_or_adapter):
        self._dlg = _adapter(dialog_or_adapter)
        self._widgets = None

    def widget(self, key: str):
        if not isinstance(self._widgets, dict):
            self._widgets = resolve_category_manager_widgets(self._dlg)
        w = self._widgets.get(key) if isinstance(self._widgets, dict) else None
        if w is None:
            self._widgets = resolve_category_manager_widgets(self._dlg)
            w = self._widgets.get(key) if isinstance(self._widgets, dict) else None
        return w

    def get_text(self, key: str) -> str:
        return get_text(self.widget(key))

    def set_text(self, key: str, text: str) -> None:
        set_text(self.widget(key), text)

    def get_text_widget(self, widget) -> str:
        return get_text(widget)

    def set_text_widget(self, widget, text: str) -> None:
        set_text(widget, text)

    def clear_text(self, key: str) -> None:
        clear_text(self.widget(key))

    def set_visible(self, key: str, visible: bool) -> None:
        set_visible(self.widget(key), visible)

    def set_combo_index(self, key: str, index: int) -> None:
        set_combo_index(self.widget(key), index)

    def set_category_text(self, text: str) -> None:
        w_cat = self.widget("add_cat")
        if w_cat is None:
            return
        try:
            with signals_blocked(w_cat):
                w_cat.setCurrentText(str(text))
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

    def get_category_text(self) -> str:
        w_cat = self.widget("add_cat")
        try:
            return str(w_cat.currentText() if w_cat is not None else "").strip()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return ""

    def set_hanzi_text(self, text: str) -> None:
        self.set_text("add_hz", text)

    def get_hanzi_text(self) -> str:
        return self.get_text("add_hz")

    def set_meaning_text(self, text: str) -> None:
        self.set_text("add_mn", text)

    def get_meaning_text(self) -> str:
        return self.get_text("add_mn")

    def join_meanings(self, meanings: list[str]) -> str:
        return ", ".join([str(x).strip() for x in meanings if str(x).strip()])

    def set_notes(self, text: str, *, source: str = "") -> None:
        try:
            self._dlg.call("_set_notes", text, source=source)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def clear_hanzi_and_meaning(self) -> None:
        self.clear_text("add_hz")
        self.clear_text("add_mn")

    def show_candidates(self) -> None:
        self.set_visible("cand_combo", True)

    def hide_candidates(self) -> None:
        combo = self.widget("cand_combo")
        if combo is None:
            return
        try:
            with signals_blocked(combo):
                set_visible(combo, False)
                combo.clear()
        except (TypeError, AttributeError, RuntimeError):
            pass

    def set_candidate_index(self, idx: int) -> None:
        self.set_combo_index("cand_combo", idx)

    def hide_candidate_popup(self) -> None:
        combo = self.widget("cand_combo")
        if combo is None:
            return
        try:
            if hasattr(combo, "hidePopup"):
                combo.hidePopup()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass
        try:
            view = combo.view() if hasattr(combo, "view") else None
        except (TypeError, AttributeError, RuntimeError, ValueError):
            view = None
        if view is not None:
            try:
                view.clearFocus()
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass
        try:
            combo.clearFocus()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

    def focus_category(self, *, show_popup: bool = True, select_all: bool = True) -> None:
        CategoryManagerFocusService(self._dlg).focus_category(
            select_all=bool(select_all), show_popup=bool(show_popup)
        )

    def focus_hanzi(self, *, select_all: bool = False) -> None:
        CategoryManagerFocusService(self._dlg).focus_hanzi(select_all=bool(select_all))

    def focus_meaning(self, *, select_all: bool = True) -> None:
        CategoryManagerFocusService(self._dlg).focus_meaning(select_all=bool(select_all))

    def focus_jyutping(self, *, select_all: bool = True) -> None:
        CategoryManagerFocusService(self._dlg).focus_jyutping(select_all=bool(select_all))

    def focus_hanzi_later(self, *, select_all: bool = False) -> None:
        CategoryManagerFocusService(self._dlg).defer_focus("hz", select_all=bool(select_all))

    def set_hanzi_editable(self, *, readonly: bool, enabled: bool) -> None:
        hz = self.widget("add_hz")
        set_readonly(hz, bool(readonly))
        set_enabled(hz, bool(enabled))

    def focus_widget(self, key: str, *, select_all: bool = True) -> None:
        focus(self.widget(key), select_all=bool(select_all))

    @contextmanager
    def block_signals(self, key: str):
        with signals_blocked(self.widget(key)):
            yield
