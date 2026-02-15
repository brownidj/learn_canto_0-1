from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter

if TYPE_CHECKING:
    from PySide6.QtWidgets import QLineEdit, QComboBox, QPushButton


@dataclass(frozen=True)
class CategoryManagerWidgetNames:
    add_jy: str = "_add_jy"
    add_hz: str = "_add_hz"
    add_mn: str = "_add_mn"
    add_notes: str = "_add_notes"
    add_cat: str = "_add_cat"
    cand_combo: str = "_cand_combo"
    btn_custom_hz: str = "_btn_custom_hz"
    search: str = "_search"
    table: str = "_table"
    btn_save: str = "btn_save"


def resolve_category_manager_widgets(
    dialog_or_adapter,
    names: CategoryManagerWidgetNames | None = None,
) -> dict[str, object | None]:
    dlg = dialog_or_adapter
    if not isinstance(dlg, CategoryManagerDialogAdapter):
        dlg = CategoryManagerDialogAdapter(dialog_or_adapter)
    names = names or CategoryManagerWidgetNames()
    return {
        "add_jy": dlg.get(names.add_jy),
        "add_hz": dlg.get(names.add_hz),
        "add_mn": dlg.get(names.add_mn),
        "add_notes": dlg.get(names.add_notes),
        "add_cat": dlg.get(names.add_cat),
        "cand_combo": dlg.get(names.cand_combo),
        "btn_custom_hz": dlg.get(names.btn_custom_hz),
        "search": dlg.get(names.search),
        "table": dlg.get(names.table),
        "btn_save": dlg.get(names.btn_save),
    }
