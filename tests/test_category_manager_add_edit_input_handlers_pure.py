import pytest

import ui.category_manager_add_edit_input_handlers as handlers
from ui.category_manager_add_edit_input_handlers import (
    AddEditJyutpingHandler,
    AddEditMeaningHandler,
)


class _StubState:
    def __init__(self):
        self.updated = []
        self.synced = False
        self.gated = False

    def update_vm(self, **kwargs):
        self.updated.append(kwargs)

    def sync_ctx(self):
        self.synced = True

    def update_save_enabled(self):
        self.gated = True


class _StubDialog:
    def __init__(self):
        self._add_jy = None
        self.focused = []

class _StubActions:
    def __init__(self):
        self.focused = []
        self.calls = []
        self._jy = "bad"

    def get_jyutping_text(self):
        return self._jy

    def set_jyutping_text(self, *_args, **_kwargs):
        return None

    def warn_duplicate_jyutping(self, *_args, **_kwargs):
        self.calls.append("warn_dup")

    def focus_category(self, *_args, **_kwargs):
        self.focused.append("cat")

    def build_preview(self):
        return {"ok": True}

    def confirm_preview(self, _preview):
        return "save"

    def commit_payload(self, *_args, **_kwargs):
        self.calls.append("commit")
        return True

    def clear_add_entry_fields(self):
        self.calls.append("clear")

    def focus_jyutping(self, *_args, **_kwargs):
        self.calls.append("focus_jy")

    def focus_meaning(self, *_args, **_kwargs):
        self.calls.append("focus_mn")

    def update_save_enabled(self):
        self.calls.append("gate")

    def reset_to_initial_state(self):
        self.calls.append("reset")


@pytest.mark.pure
def test_jyutping_handler_invalid_does_not_focus_category(monkeypatch):
    state = _StubState()
    actions = _StubActions()
    monkeypatch.setattr(handlers, "AddEditStateService", lambda *_: state)
    monkeypatch.setattr(handlers, "normalize_jyutping_text", lambda *_: "bad")
    monkeypatch.setattr(handlers, "validate_jyutping", lambda *_: False)
    monkeypatch.setattr(handlers, "AddEditUIActions", lambda *_: actions)

    handler = AddEditJyutpingHandler(_StubDialog())
    handler.on_jyut_enter()

    assert actions.focused == []
    assert state.gated is True


@pytest.mark.pure
def test_meaning_handler_save_clears_and_focuses(monkeypatch):
    monkeypatch.setattr(handlers, "normalize_preview_payload", lambda *_: {"ok": True})
    actions = _StubActions()
    monkeypatch.setattr(handlers, "AddEditUIActions", lambda *_: actions)

    handler = AddEditMeaningHandler(_StubDialog())
    handler.on_meaning_enter_committed()

    assert actions.calls == ["commit", "clear", "focus_jy", "gate"]
