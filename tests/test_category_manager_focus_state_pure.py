import pytest

from ui.category_manager_focus_state import (
    is_hanzi_committed,
    is_manual_hanzi_mode,
    set_hanzi_committed,
    set_manual_hanzi_mode,
)


class _StubDialog:
    def __init__(self):
        self._manual_hanzi_mode = False
        self._hanzi_committed = False


@pytest.mark.pure
def test_focus_state_roundtrip_flags():
    dialog = _StubDialog()

    assert is_manual_hanzi_mode(dialog) is False
    assert is_hanzi_committed(dialog) is False

    set_manual_hanzi_mode(dialog, True)
    set_hanzi_committed(dialog, True)

    assert is_manual_hanzi_mode(dialog) is True
    assert is_hanzi_committed(dialog) is True

    set_manual_hanzi_mode(dialog, False)
    set_hanzi_committed(dialog, False)

    assert is_manual_hanzi_mode(dialog) is False
    assert is_hanzi_committed(dialog) is False
