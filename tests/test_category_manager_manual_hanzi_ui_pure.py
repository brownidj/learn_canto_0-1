import pytest

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_manual_hanzi_ui import (
    hide_candidates,
    set_manual_mode_flags,
    update_manual_state,
)


class _StubCombo:
    def __init__(self):
        self.visible = True
        self.index = 0

    def setVisible(self, v):
        self.visible = bool(v)

    def setCurrentIndex(self, idx):
        self.index = int(idx)


class _StubDialog:
    def __init__(self):
        self._manual_hanzi_mode = False
        self._cand_combo = _StubCombo()
        self._updated = {}

    def _update_add_edit_state(self, **kwargs):
        self._updated.update(kwargs)


@pytest.mark.pure
def test_manual_hanzi_ui_helpers_update_state_and_hide_candidates():
    dialog = _StubDialog()
    dlg = CategoryManagerDialogAdapter(dialog)

    set_manual_mode_flags(dlg, True)
    update_manual_state(dlg)
    hide_candidates(dlg)

    assert dialog._manual_hanzi_mode is True
    assert dialog._updated.get("manual_hanzi") is True
    assert dialog._updated.get("hanzi") == ""
    assert dialog._updated.get("hz_ok") is False
    assert dialog._cand_combo.visible is False
    assert dialog._cand_combo.index == -1
