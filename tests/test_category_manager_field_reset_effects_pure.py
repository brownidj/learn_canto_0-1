import pytest

import ui.category_manager_field_reset_effects as effects
from ui.category_manager_field_reset_rules import plan_clear_add_entry_fields


class _StubDialog:
    pass


@pytest.mark.pure
def test_field_reset_effects_apply_calls_widgets_and_state(monkeypatch):
    calls = []

    def _mark(name):
        def _fn(*_args, **_kwargs):
            calls.append(name)
        return _fn

    monkeypatch.setattr(effects, "clear_text_fields", _mark("clear_text_fields"))
    monkeypatch.setattr(effects, "reset_notes", _mark("reset_notes"))
    monkeypatch.setattr(effects, "reset_category", _mark("reset_category"))
    monkeypatch.setattr(effects, "reset_manual_mode", _mark("reset_manual_mode"))
    monkeypatch.setattr(effects, "reset_add_edit_state", _mark("reset_add_edit_state"))
    monkeypatch.setattr(effects, "reset_hanzi_editable", _mark("reset_hanzi_editable"))
    monkeypatch.setattr(effects, "reset_candidates_ui", _mark("reset_candidates_ui"))
    monkeypatch.setattr(effects, "reset_hanzi_committed", _mark("reset_hanzi_committed"))
    monkeypatch.setattr(effects, "reset_state_machine", _mark("reset_state_machine"))
    monkeypatch.setattr(effects, "refresh_save_gating", _mark("refresh_save_gating"))

    plan = plan_clear_add_entry_fields()
    effects.FieldResetEffects(_StubDialog()).apply(plan)

    assert calls == [
        "clear_text_fields",
        "reset_notes",
        "reset_category",
        "reset_manual_mode",
        "reset_add_edit_state",
        "reset_hanzi_editable",
        "reset_candidates_ui",
        "reset_hanzi_committed",
        "reset_state_machine",
        "refresh_save_gating",
    ]
