import pytest

import ui.category_manager_category_ops_ui_combo as combo_mod
import ui.category_manager_category_ops_ui_focus as focus_mod
from ui.category_manager_category_ops_ui_combo import CategoryOpsComboEffects
from ui.category_manager_category_ops_ui_focus import CategoryOpsFocusEffects


class _StubDialog:
    pass


@pytest.mark.pure
def test_combo_effects_apply_commit_calls_combo(monkeypatch):
    calls = []

    class _Combo:
        def ensure_category_in_combo(self, *_):
            calls.append("ensure")

        def set_category_selection(self, *_):
            calls.append("select")

        def refresh_category_dropdown(self, *_args, **_kwargs):
            calls.append("refresh")

    monkeypatch.setattr(combo_mod, "CategoryManagerComboService", lambda *_: _Combo())
    effects = CategoryOpsComboEffects(_StubDialog())

    effects.apply_commit_effects(cat="work", exists_now=False)

    assert calls == ["ensure", "select", "refresh"]


@pytest.mark.pure
def test_focus_effects_defer_calls_focus_service(monkeypatch):
    calls = []

    class _Focus:
        def defer_focus(self, *_args, **_kwargs):
            calls.append("defer")

    monkeypatch.setattr(focus_mod, "CategoryManagerFocusService", lambda *_: _Focus())
    effects = CategoryOpsFocusEffects(_StubDialog())
    monkeypatch.setattr(effects, "close_combo_popups", lambda *_: calls.append("close"))

    effects.defer_focus_hanzi()

    assert calls == ["close", "defer"]
