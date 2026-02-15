import pytest

from ui.category_manager_add_edit_coordinator import AddEditCoordinator


class _StubFlow:
    def __init__(self):
        self.jy_called = False
        self.mn_called = False

    def on_jyut_enter(self):
        self.jy_called = True

    def on_meaning_enter_committed(self):
        self.mn_called = True


class _StubDialog:
    def __init__(self):
        self._add_edit_flow = _StubFlow()


@pytest.mark.pure
def test_add_edit_coordinator_delegates_to_flow():
    dialog = _StubDialog()
    coord = AddEditCoordinator(dialog)

    coord.on_jyut_enter()
    coord.on_meaning_enter()

    flow = dialog._add_edit_flow
    assert flow.jy_called is True
    assert flow.mn_called is True
