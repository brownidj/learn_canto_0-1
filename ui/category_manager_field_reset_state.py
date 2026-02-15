from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter


def _adapter(dialog_or_adapter) -> CategoryManagerDialogAdapter:
    if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
        return dialog_or_adapter
    return CategoryManagerDialogAdapter(dialog_or_adapter)


def reset_add_edit_state(dialog_or_adapter, plan) -> None:
    if not plan.reset_state:
        return
    dlg = _adapter(dialog_or_adapter)
    try:
        dlg.call(
            "_update_add_edit_state",
            jy="",
            jy_ok=False,
            duplicate=None,
            category="",
            cat_ok=False,
            candidates=(),
            hanzi="",
            hz_ok=False,
            manual_hanzi=False,
            meaning="",
            mn_ok=False,
        )
    except Exception:
        pass


def reset_hanzi_committed(dialog_or_adapter, plan) -> None:
    if not plan.reset_hanzi_committed:
        return
    dlg = _adapter(dialog_or_adapter)
    try:
        ctrl = dlg.get("_focus_ctrl")
        if ctrl is not None:
            ctrl.mark_hanzi_committed(False)
            return
    except (TypeError, AttributeError, RuntimeError):
        pass
    try:
        dlg.set("_hanzi_committed", False)
    except (TypeError, AttributeError, RuntimeError):
        pass


def reset_state_machine(dialog_or_adapter, plan) -> None:
    if not plan.reset_state_machine:
        return
    dlg = _adapter(dialog_or_adapter)
    try:
        from domain.add_edit_sm import AddEditState, AddEditContext
        from ui.add_edit_view_model import AddEditViewModel
        dlg.set("_add_edit_state", AddEditState.EMPTY)
        ctx = AddEditContext(
            jy="",
            jy_ok=False,
            duplicate=None,
            hanzi="",
            hz_ok=False,
            manual_hanzi=False,
            meaning="",
            mn_ok=False,
            category="",
            cat_ok=False,
            saving=False,
        )
        dlg.set("_add_edit_ctx", ctx)
        dlg.set("_add_edit_vm", AddEditViewModel.from_context(ctx))
    except (TypeError, AttributeError, RuntimeError, ImportError):
        pass
