"""Category editor delegate for vocab table."""

from __future__ import annotations

from typing import Callable, Iterable

try:
    from PySide6.QtWidgets import QStyledItemDelegate, QComboBox
except Exception:  # pragma: no cover - PySide6 optional for pure tests
    QStyledItemDelegate = None
    QComboBox = None


class CategoryComboDelegate(QStyledItemDelegate):
    def __init__(self, get_names: Callable[[], Iterable[str]]):
        super().__init__()
        self._get_names = get_names

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        try:
            editor.setEditable(False)
        except Exception:
            pass
        try:
            names = list(self._get_names())
        except Exception:
            names = []
        editor.addItems(names)
        try:
            editor.currentTextChanged.connect(lambda _=None: self._commit(editor))
        except Exception:
            pass
        return editor

    def setEditorData(self, editor, index):
        try:
            text = str(index.data() or "")
        except Exception:
            text = ""
        try:
            i = editor.findText(text)
            if i >= 0:
                editor.setCurrentIndex(i)
        except Exception:
            pass

    def setModelData(self, editor, model, index):
        try:
            model.setData(index, editor.currentText())
        except Exception:
            pass

    def _commit(self, editor):
        try:
            self.commitData.emit(editor)
            self.closeEditor.emit(editor)
        except Exception:
            pass


def make_category_combo_delegate(get_names: Callable[[], Iterable[str]]):
    if QStyledItemDelegate is None or QComboBox is None:
        return None
    return CategoryComboDelegate(get_names)


__all__ = ["CategoryComboDelegate", "make_category_combo_delegate"]
