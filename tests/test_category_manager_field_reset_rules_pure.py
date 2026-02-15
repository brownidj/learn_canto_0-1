import pytest

from ui.category_manager_field_reset_rules import (
    plan_clear_add_entry_fields,
    plan_reset_add_panel_pre_validation,
    plan_reset_to_initial_state,
)


@pytest.mark.pure
def test_plan_clear_add_entry_fields_flags():
    plan = plan_clear_add_entry_fields()
    assert plan.clear_jy is True
    assert plan.clear_hz is True
    assert plan.clear_mn is True
    assert plan.clear_notes is True
    assert plan.reset_category is True
    assert plan.hide_candidates is False
    assert plan.reset_state is True
    assert plan.reset_manual_mode is True
    assert plan.reset_hanzi_committed is False
    assert plan.reset_state_machine is False


@pytest.mark.pure
def test_plan_reset_add_panel_pre_validation_flags():
    plan = plan_reset_add_panel_pre_validation()
    assert plan.clear_jy is False
    assert plan.clear_hz is True
    assert plan.clear_mn is True
    assert plan.hide_candidates is True
    assert plan.reset_state is True
    assert plan.reset_state_machine is False


@pytest.mark.pure
def test_plan_reset_to_initial_state_flags():
    plan = plan_reset_to_initial_state()
    assert plan.hide_candidates is True
    assert plan.reset_state_machine is True
