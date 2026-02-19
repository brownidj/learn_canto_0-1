from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_ui_services import CategoryManagerUIService


def _adapter(dialog_or_adapter) -> CategoryManagerDialogAdapter:
    if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
        return dialog_or_adapter
    return CategoryManagerDialogAdapter(dialog_or_adapter)


def _ui(dialog_or_adapter) -> CategoryManagerUIService:
    return CategoryManagerUIService(dialog_or_adapter)


def clear_text_fields(dialog_or_adapter, plan) -> None:
    ui = _ui(dialog_or_adapter)
    if plan.clear_jy:
        ui.clear_text("add_jy")
    if plan.clear_hz:
        ui.clear_text("add_hz")
    if plan.clear_mn:
        ui.clear_text("add_mn")


def reset_notes(dialog_or_adapter, plan) -> None:
    if not plan.clear_notes:
        return
    dlg = _adapter(dialog_or_adapter)
    try:
        dlg.call("_set_notes", "", source="auto-default")
    except (TypeError, AttributeError, RuntimeError):
        pass


def reset_category(dialog_or_adapter, plan) -> None:
    if not plan.reset_category:
        return
    dlg = _adapter(dialog_or_adapter)
    try:
        multi = bool(dlg.get("_cat_multi_select", False))
    except Exception:
        multi = False
    if multi:
        try:
            combo = _ui(dialog_or_adapter).widget("add_cat")
        except Exception:
            combo = None
        if combo is not None:
            try:
                from PySide6.QtCore import Qt
                model = combo.model() if hasattr(combo, "model") else None
                if model is not None and hasattr(model, "rowCount"):
                    for i in range(model.rowCount()):
                        item = model.item(i) if hasattr(model, "item") else None
                        if item is not None:
                            item.setData(Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
            except Exception:
                pass
        try:
            dlg.set("_selected_categories", [])
        except Exception:
            pass
        try:
            label = dlg.get("_cat_selected_label")
            if label is not None and hasattr(label, "setText"):
                label.setText("No categories selected")
        except Exception:
            pass
    else:
        _ui(dialog_or_adapter).set_combo_index("add_cat", -1)
    try:
        dlg.set("_last_committed_category", "")
    except (TypeError, AttributeError, RuntimeError):
        pass


def reset_manual_mode(dialog_or_adapter, plan) -> None:
    if not plan.reset_manual_mode:
        return
    dlg = _adapter(dialog_or_adapter)
    try:
        dlg.call("_mark_manual_hanzi_mode", False)
    except Exception:
        try:
            dlg.set("_manual_hanzi_mode", False)
        except Exception:
            pass


def reset_hanzi_editable(dialog_or_adapter) -> None:
    ui = _ui(dialog_or_adapter)
    hz = ui.widget("add_hz")
    if hz is not None:
        try:
            hz.setPlaceholderText("Auto, after reverse lookup")
        except Exception:
            pass
    ui.set_hanzi_editable(readonly=False, enabled=True)


def reset_candidates_ui(dialog_or_adapter, plan) -> None:
    if not plan.hide_candidates:
        return
    _ui(dialog_or_adapter).hide_candidates()
