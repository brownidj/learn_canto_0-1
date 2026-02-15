import pytest

from ui.category_manager_add_edit_state_coordinator import AddEditStateCoordinator


class _StubDialog:
    def __init__(self):
        self._add_edit_vm = _StubVM()
        self._add_edit_ctx = None
        self._add_edit_state = None
        self._saving_now = False


class _StubVM:
    def __init__(self):
        self.jy = ""
        self.jy_ok = False
        self.hanzi = ""
        self.hz_ok = False
        self.meaning = ""
        self.mn_ok = False
        self.category = ""
        self.cat_ok = False
        self.saving = False

    def to_context(self):  # minimal stub
        return self


@pytest.mark.pure
def test_state_coordinator_updates_vm_and_sets_ready():
    dialog = _StubDialog()
    coord = AddEditStateCoordinator(dialog)

    coord.update_from_fields(
        jy="nei5 hou2",
        hanzi="你好",
        meaning="hello",
        category="greetings",
        jy_ok=True,
        saving=False,
    )

    vm = dialog._add_edit_vm
    assert vm.jy == "nei5 hou2"
    assert vm.hanzi == "你好"
    assert vm.meaning == "hello"
    assert vm.category == "greetings"
    assert vm.jy_ok is True
    assert vm.hz_ok is True
    assert vm.mn_ok is True
    assert vm.cat_ok is True
