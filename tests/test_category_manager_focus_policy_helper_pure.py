import pytest

from ui.category_manager_focus_service import CategoryManagerFocusService


class _StubDialog:
    pass


@pytest.mark.pure
def test_should_apply_focus_allows_user_action_even_when_guarded():
    allowed = CategoryManagerFocusService(_StubDialog()).should_apply_focus(
        reason="test",
        user_action=True,
        manual_mode=True,
        hanzi_committed=True,
        combo_has_focus=True,
        view_has_focus=True,
    )
    assert allowed is True


@pytest.mark.pure
def test_should_apply_focus_blocks_manual_mode_without_user_action():
    allowed = CategoryManagerFocusService(_StubDialog()).should_apply_focus(
        reason="test",
        user_action=False,
        manual_mode=True,
        hanzi_committed=False,
        combo_has_focus=False,
        view_has_focus=False,
    )
    assert allowed is False


@pytest.mark.pure
def test_should_apply_focus_blocks_committed_without_user_action():
    allowed = CategoryManagerFocusService(_StubDialog()).should_apply_focus(
        reason="test",
        user_action=False,
        manual_mode=False,
        hanzi_committed=True,
        combo_has_focus=False,
        view_has_focus=False,
    )
    assert allowed is False


@pytest.mark.pure
def test_should_apply_focus_blocks_when_combo_has_focus():
    allowed = CategoryManagerFocusService(_StubDialog()).should_apply_focus(
        reason="test",
        user_action=False,
        manual_mode=False,
        hanzi_committed=False,
        combo_has_focus=True,
        view_has_focus=False,
    )
    assert allowed is False
