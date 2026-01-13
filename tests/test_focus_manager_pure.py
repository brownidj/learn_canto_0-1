"""Tests for FocusManager - pure logic, no Qt."""

import pytest
from ui.focus_manager import FocusManager, FocusState, FocusPolicy

pytestmark = pytest.mark.pure


class FocusTracker:
    """Tracks focus calls for testing."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def focus_jy(self):
        self.calls.append(("jy", {}))

    def focus_hz(self):
        self.calls.append(("hz", {}))

    def focus_mn(self):
        self.calls.append(("mn", {}))

    def focus_cat(self, show_popup: bool):
        self.calls.append(("cat", {"show_popup": show_popup}))

    def focus_cand(self):
        self.calls.append(("cand", {}))

    def last_call(self) -> tuple[str, dict] | None:
        return self.calls[-1] if self.calls else None

    def clear(self):
        self.calls.clear()


def test_focus_allows_user_action():
    """Should always allow focus on user action."""
    tracker = FocusTracker()
    manager = FocusManager(
        focus_jy=tracker.focus_jy,
        focus_hz=tracker.focus_hz,
        focus_mn=tracker.focus_mn,
        focus_cat=tracker.focus_cat,
        focus_cand=tracker.focus_cand,
    )

    state = FocusState(
        user_action=True,
        manual_mode=True,  # Would normally block
        hanzi_committed=True,  # Would normally block
    )

    result = manager.focus("mn", state=state)
    assert result is True
    assert tracker.last_call() == ("mn", {})


def test_focus_blocks_manual_mode():
    """Should block auto-focus in manual mode."""
    tracker = FocusTracker()
    manager = FocusManager(
        focus_jy=tracker.focus_jy,
        focus_hz=tracker.focus_hz,
        focus_mn=tracker.focus_mn,
        focus_cat=tracker.focus_cat,
        focus_cand=tracker.focus_cand,
    )

    state = FocusState(manual_mode=True)

    result = manager.focus("mn", state=state)
    assert result is False
    assert tracker.last_call() is None


def test_focus_blocks_committed_hanzi():
    """Should block re-focus after Hanzi committed."""
    tracker = FocusTracker()
    manager = FocusManager(
        focus_jy=tracker.focus_jy,
        focus_hz=tracker.focus_hz,
        focus_mn=tracker.focus_mn,
        focus_cat=tracker.focus_cat,
        focus_cand=tracker.focus_cand,
    )

    state = FocusState(hanzi_committed=True)

    result = manager.focus("hz", state=state)
    assert result is False
    assert tracker.last_call() is None


def test_focus_blocks_combo_focus():
    """Should block stealing focus from combo."""
    tracker = FocusTracker()
    manager = FocusManager(
        focus_jy=tracker.focus_jy,
        focus_hz=tracker.focus_hz,
        focus_mn=tracker.focus_mn,
        focus_cat=tracker.focus_cat,
        focus_cand=tracker.focus_cand,
    )

    state = FocusState(combo_has_focus=True)

    result = manager.focus("mn", state=state)
    assert result is False
    assert tracker.last_call() is None


def test_focus_blocks_view_focus():
    """Should block stealing focus from combo popup view."""
    tracker = FocusTracker()
    manager = FocusManager(
        focus_jy=tracker.focus_jy,
        focus_hz=tracker.focus_hz,
        focus_mn=tracker.focus_mn,
        focus_cat=tracker.focus_cat,
        focus_cand=tracker.focus_cand,
    )

    state = FocusState(view_has_focus=True)

    result = manager.focus("mn", state=state)
    assert result is False
    assert tracker.last_call() is None


def test_focus_policy_block():
    """Should respect BLOCK policy."""
    tracker = FocusTracker()
    manager = FocusManager(
        focus_jy=tracker.focus_jy,
        focus_hz=tracker.focus_hz,
        focus_mn=tracker.focus_mn,
        focus_cat=tracker.focus_cat,
        focus_cand=tracker.focus_cand,
    )

    result = manager.focus("mn", policy=FocusPolicy.BLOCK)
    assert result is False
    assert tracker.last_call() is None


def test_focus_policy_allow():
    """Should apply focus with ALLOW policy."""
    tracker = FocusTracker()
    manager = FocusManager(
        focus_jy=tracker.focus_jy,
        focus_hz=tracker.focus_hz,
        focus_mn=tracker.focus_mn,
        focus_cat=tracker.focus_cat,
        focus_cand=tracker.focus_cand,
    )

    result = manager.focus("mn", policy=FocusPolicy.ALLOW)
    assert result is True
    assert tracker.last_call() == ("mn", {})


def test_focus_defer():
    """Should defer focus with DEFER policy."""
    tracker = FocusTracker()
    deferred_calls: list[callable] = []

    def mock_defer(callback):
        deferred_calls.append(callback)

    manager = FocusManager(
        focus_jy=tracker.focus_jy,
        focus_hz=tracker.focus_hz,
        focus_mn=tracker.focus_mn,
        focus_cat=tracker.focus_cat,
        focus_cand=tracker.focus_cand,
        defer=mock_defer,
    )

    result = manager.focus("mn", policy=FocusPolicy.DEFER)
    assert result is True
    assert tracker.last_call() is None  # Not called yet
    assert len(deferred_calls) == 1

    # Execute deferred call
    deferred_calls[0]()
    assert tracker.last_call() == ("mn", {})


def test_focus_category_with_popup():
    """Should pass show_popup flag to category focus."""
    tracker = FocusTracker()
    manager = FocusManager(
        focus_jy=tracker.focus_jy,
        focus_hz=tracker.focus_hz,
        focus_mn=tracker.focus_mn,
        focus_cat=tracker.focus_cat,
        focus_cand=tracker.focus_cand,
    )

    manager.focus("cat", show_popup=True)
    assert tracker.last_call() == ("cat", {"show_popup": True})


def test_focus_all_targets():
    """Should focus all target types."""
    tracker = FocusTracker()
    manager = FocusManager(
        focus_jy=tracker.focus_jy,
        focus_hz=tracker.focus_hz,
        focus_mn=tracker.focus_mn,
        focus_cat=tracker.focus_cat,
        focus_cand=tracker.focus_cand,
    )

    manager.focus("jy")
    assert tracker.last_call() == ("jy", {})

    tracker.clear()
    manager.focus("hz")
    assert tracker.last_call() == ("hz", {})

    tracker.clear()
    manager.focus("mn")
    assert tracker.last_call() == ("mn", {})

    tracker.clear()
    manager.focus("cat")
    assert tracker.last_call() == ("cat", {"show_popup": False})

    tracker.clear()
    manager.focus("cand")
    assert tracker.last_call() == ("cand", {})


def test_focus_next_in_sequence():
    """Should move through Add/Edit sequence."""
    tracker = FocusTracker()
    manager = FocusManager(
        focus_jy=tracker.focus_jy,
        focus_hz=tracker.focus_hz,
        focus_mn=tracker.focus_mn,
        focus_cat=tracker.focus_cat,
        focus_cand=tracker.focus_cand,
    )

    # jy → cat
    result = manager.focus_next_in_sequence("jy")
    assert result is True
    assert tracker.calls[-1][0] == "cat"

    # cat → cand
    tracker.clear()
    result = manager.focus_next_in_sequence("cat")
    assert result is True
    assert tracker.calls[-1][0] == "cand"

    # cand → mn
    tracker.clear()
    result = manager.focus_next_in_sequence("cand")
    assert result is True
    assert tracker.calls[-1][0] == "mn"

    # hz → mn
    tracker.clear()
    result = manager.focus_next_in_sequence("hz")
    assert result is True
    assert tracker.calls[-1][0] == "mn"


def test_should_allow_focus_change_comprehensive():
    """Should apply all focus rules correctly."""
    tracker = FocusTracker()
    manager = FocusManager(
        focus_jy=tracker.focus_jy,
        focus_hz=tracker.focus_hz,
        focus_mn=tracker.focus_mn,
        focus_cat=tracker.focus_cat,
        focus_cand=tracker.focus_cand,
    )

    # Default state: allow
    state = FocusState()
    assert manager.should_allow_focus_change(state) is True

    # User action: allow (overrides all)
    state = FocusState(user_action=True, manual_mode=True, hanzi_committed=True)
    assert manager.should_allow_focus_change(state) is True

    # Manual mode: block
    state = FocusState(manual_mode=True)
    assert manager.should_allow_focus_change(state) is False

    # Hanzi committed: block
    state = FocusState(hanzi_committed=True)
    assert manager.should_allow_focus_change(state) is False

    # Combo focused: block
    state = FocusState(combo_has_focus=True)
    assert manager.should_allow_focus_change(state) is False

    # View focused: block
    state = FocusState(view_has_focus=True)
    assert manager.should_allow_focus_change(state) is False
