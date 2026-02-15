from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_focus_service import CategoryManagerFocusService
from ui.category_manager_ui_services import CategoryManagerUIService
from ui.category_manager_widgets import resolve_category_manager_widgets


def _adapter(dialog_or_adapter) -> CategoryManagerDialogAdapter:
    if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
        return dialog_or_adapter
    return CategoryManagerDialogAdapter(dialog_or_adapter)


def _widgets(dialog_or_adapter) -> dict[str, object | None]:
    return resolve_category_manager_widgets(dialog_or_adapter)


def _ui(dialog_or_adapter) -> CategoryManagerUIService:
    return CategoryManagerUIService(dialog_or_adapter)


def set_manual_mode_flags(dialog_or_adapter, enabled: bool) -> None:
    dlg = _adapter(dialog_or_adapter)
    try:
        dlg.set("_manual_hanzi_mode", bool(enabled))
    except (TypeError, AttributeError, RuntimeError):
        pass


def mark_hanzi_uncommitted(dialog_or_adapter) -> None:
    dlg = _adapter(dialog_or_adapter)
    try:
        ctrl = dlg.get("_focus_ctrl")
        if ctrl is not None:
            ctrl.mark_hanzi_committed(False)
    except (TypeError, AttributeError, RuntimeError):
        pass


def update_manual_state(dialog_or_adapter) -> None:
    dlg = _adapter(dialog_or_adapter)
    try:
        dlg.call("_update_add_edit_state", manual_hanzi=True, hanzi="", hz_ok=False)
    except (TypeError, AttributeError, RuntimeError, ValueError):
        pass


def ensure_hanzi_editable(dialog_or_adapter) -> None:
    ui = _ui(dialog_or_adapter)
    hz = ui.widget("add_hz")
    if hz is None:
        return
    try:
        if hasattr(hz, "objectName") and callable(hz.objectName):
            if not str(hz.objectName() or "").strip() and hasattr(hz, "setObjectName"):
                hz.setObjectName("editHanzi")
    except Exception:
        pass
    try:
        ui.set_hanzi_editable(readonly=False, enabled=True)
        if hasattr(hz, "setPlaceholderText"):
            hz.setPlaceholderText("Type Hanzi…")
    except (RuntimeError, AttributeError):
        pass
    ui.clear_text("add_hz")


def ensure_meaning_named(dialog_or_adapter) -> None:
    mn = _widgets(dialog_or_adapter).get("add_mn")
    if mn is None:
        return
    try:
        if hasattr(mn, "objectName") and callable(mn.objectName):
            if not str(mn.objectName() or "").strip() and hasattr(mn, "setObjectName"):
                mn.setObjectName("editMeaning")
    except Exception:
        pass


def hide_candidates(dialog_or_adapter) -> None:
    ui = _ui(dialog_or_adapter)
    ui.set_visible("cand_combo", False)
    ui.set_combo_index("cand_combo", -1)


def focus_hanzi(dialog_or_adapter) -> None:
    CategoryManagerFocusService(dialog_or_adapter).apply_focus_policy(
        target="hz",
        reason="manual_hanzi_mode",
        user_action=True,
        select_all=True,
    )


def refresh_save_gating(dialog_or_adapter) -> None:
    dlg = _adapter(dialog_or_adapter)
    fn_gate = dlg.get("_update_save_enabled")
    if callable(fn_gate):
        try:
            fn_gate()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass


def enter_manual_mode_if_readonly(dialog_or_adapter) -> None:
    CategoryManagerFocusService(dialog_or_adapter).enter_manual_mode_if_readonly()
