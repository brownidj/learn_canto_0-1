import pytest

from ui.category_manager_add_edit_meaning_apply import AddEditMeaningApplyService


class _StubDialog:
    pass


@pytest.mark.pure
def test_add_edit_meaning_apply_sets_meaning_and_source(monkeypatch):
    svc = AddEditMeaningApplyService(_StubDialog())

    monkeypatch.setattr(svc._ui, "set_meaning_text", lambda *_: None)
    captured = {}
    monkeypatch.setattr(svc._state, "update_state", lambda **kwargs: captured.update(kwargs))

    monkeypatch.setattr(
        "ui.category_manager_add_edit_meaning_apply.resolve_meaning_for_add_edit",
        lambda *_args, **_kwargs: ("to meet", "resolver"),
    )

    meaning, source = svc.apply_meaning(hanzi="開會", src="tier2", jyutping="hoi1 wui6", allow_canto=True)

    assert meaning == "to meet"
    assert source == "resolver"
    assert captured["meaning"] == "to meet"
    assert captured["meaning_source"] == "resolver"
