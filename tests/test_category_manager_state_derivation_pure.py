import pytest

from ui.category_manager_state_derivation import AddEditStateDerivation


@pytest.mark.pure
def test_state_derivation_ready_when_all_fields_valid():
    derived = AddEditStateDerivation.derive(
        jy="nei5 hou2",
        hanzi="你好",
        meaning="hello",
        category="greetings",
        jy_ok=True,
        saving=False,
    )

    assert derived.jy_ok is True
    assert derived.hz_ok is True
    assert derived.mn_ok is True
    assert derived.cat_ok is True
    assert derived.ready_to_save is True


@pytest.mark.pure
def test_state_derivation_not_ready_when_saving_or_invalid():
    derived = AddEditStateDerivation.derive(
        jy="nei5 hou2",
        hanzi="你好",
        meaning="hello",
        category="greetings",
        jy_ok=True,
        saving=True,
    )
    assert derived.ready_to_save is False

    derived2 = AddEditStateDerivation.derive(
        jy="",
        hanzi="你好",
        meaning="hello",
        category="greetings",
        jy_ok=False,
        saving=False,
    )
    assert derived2.ready_to_save is False


@pytest.mark.pure
def test_state_derivation_blocks_unassigned_category():
    derived = AddEditStateDerivation.derive(
        jy="nei5 hou2",
        hanzi="你好",
        meaning="hello",
        category="unassigned",
        jy_ok=True,
        saving=False,
    )
    assert derived.cat_ok is False
    assert derived.ready_to_save is False
