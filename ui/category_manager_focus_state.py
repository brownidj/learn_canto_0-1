from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter


def _adapter(dialog_or_adapter) -> CategoryManagerDialogAdapter:
    if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
        return dialog_or_adapter
    return CategoryManagerDialogAdapter(dialog_or_adapter)


def is_manual_hanzi_mode(dialog_or_adapter) -> bool:
    dlg = _adapter(dialog_or_adapter)
    try:
        return bool(dlg.get("_manual_hanzi_mode", False))
    except (TypeError, AttributeError, RuntimeError):
        return False


def is_hanzi_committed(dialog_or_adapter) -> bool:
    dlg = _adapter(dialog_or_adapter)
    try:
        return bool(dlg.get("_hanzi_committed", False))
    except (TypeError, AttributeError, RuntimeError):
        return False


def set_manual_hanzi_mode(dialog_or_adapter, enabled: bool) -> None:
    dlg = _adapter(dialog_or_adapter)
    try:
        dlg.set("_manual_hanzi_mode", bool(enabled))
    except (TypeError, AttributeError, RuntimeError):
        pass


def set_hanzi_committed(dialog_or_adapter, committed: bool) -> None:
    dlg = _adapter(dialog_or_adapter)
    try:
        dlg.set("_hanzi_committed", bool(committed))
    except (TypeError, AttributeError, RuntimeError):
        pass
