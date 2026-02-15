import pytest

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_field_reset_rules import plan_clear_add_entry_fields
from ui.category_manager_field_reset_widgets import (
    clear_text_fields,
    reset_category,
    reset_manual_mode,
)


class _StubLineEdit:
    def __init__(self, text=""):
        self._text = text

    def clear(self):
        self._text = ""

    def text(self):
        return self._text


class _StubCombo:
    def __init__(self):
        self.index = 5

    def setCurrentIndex(self, idx):
        self.index = int(idx)


class _StubDialog:
    def __init__(self):
        self._add_jy = _StubLineEdit("jy")
        self._add_hz = _StubLineEdit("hz")
        self._add_mn = _StubLineEdit("mn")
        self._add_cat = _StubCombo()
        self._last_committed_category = "work"
        self._manual_hanzi_mode = True

    def _mark_manual_hanzi_mode(self, enabled):
        self._manual_hanzi_mode = bool(enabled)


@pytest.mark.pure
def test_field_reset_ui_clears_and_resets():
    dialog = _StubDialog()
    dlg = CategoryManagerDialogAdapter(dialog)
    plan = plan_clear_add_entry_fields()

    clear_text_fields(dlg, plan)
    reset_category(dlg, plan)
    reset_manual_mode(dlg, plan)

    assert dialog._add_jy.text() == ""
    assert dialog._add_hz.text() == ""
    assert dialog._add_mn.text() == ""
    assert dialog._add_cat.index == -1
    assert dialog._last_committed_category == ""
    assert dialog._manual_hanzi_mode is False
