import pytest

import ui.category_manager_category_ops_ui_commit as commit_mod
from ui.category_manager_category_ops_ui_commit import CategoryOpsCommitEffects


class _StubDialog:
    pass


@pytest.mark.pure
def test_commit_effects_apply_and_gate(monkeypatch):
    calls = []

    monkeypatch.setattr(commit_mod, "CategoryOpsComboEffects", lambda *_: type("C", (), {
        "apply_commit_effects": lambda *args, **kwargs: calls.append("combo")
    })())

    effects = CategoryOpsCommitEffects(_StubDialog())
    monkeypatch.setattr(effects._dlg, "call", lambda *_args, **_kwargs: calls.append("gate"))

    effects.apply_commit_effects(cat="work", exists_now=True)
    effects.update_save_enabled()

    assert calls == ["combo", "gate"]
