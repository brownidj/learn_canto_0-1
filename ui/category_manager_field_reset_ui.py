from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter


def _adapter(dialog_or_adapter) -> CategoryManagerDialogAdapter:
    if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
        return dialog_or_adapter
    return CategoryManagerDialogAdapter(dialog_or_adapter)


def refresh_save_gating(dialog_or_adapter) -> None:
    dlg = _adapter(dialog_or_adapter)
    try:
        fn_gate = dlg.get("_update_save_enabled")
        if callable(fn_gate):
            fn_gate()
    except (TypeError, AttributeError, RuntimeError):
        pass
