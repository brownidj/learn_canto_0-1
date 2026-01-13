"""Tests for FormStateController - pure logic, no Qt."""

import pytest
from ui.form_state_controller import FormState, FormStateController
from domain.entry_validation import EntryValidator

pytestmark = pytest.mark.pure


def test_form_state_is_complete():
    """Should check if form has all required fields."""
    state = FormState(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )
    assert state.is_complete() is True

    # Missing jyutping
    state = FormState(jyutping="", hanzi="你好", meanings="hello", category="greetings")
    assert state.is_complete() is False

    # Missing hanzi
    state = FormState(jyutping="nei5 hou2", hanzi="", meanings="hello", category="greetings")
    assert state.is_complete() is False

    # Missing meanings
    state = FormState(jyutping="nei5 hou2", hanzi="你好", meanings="", category="greetings")
    assert state.is_complete() is False

    # Missing category
    state = FormState(jyutping="nei5 hou2", hanzi="你好", meanings="hello", category="")
    assert state.is_complete() is False


def test_is_category_valid():
    """Should validate categories for saving."""
    validator = EntryValidator()
    controller = FormStateController(validator)

    assert controller.is_category_valid("greetings") is True
    assert controller.is_category_valid("unassigned") is False
    assert controller.is_category_valid("all") is False
    assert controller.is_category_valid("") is False


def test_is_valid_complete_form():
    """Should validate complete valid form."""
    validator = EntryValidator()
    controller = FormStateController(validator)

    state = FormState(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )

    assert controller.is_valid(state) is True


def test_is_valid_blocks_saving():
    """Should block validation while saving."""
    validator = EntryValidator()
    controller = FormStateController(validator)

    state = FormState(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings",
        saving=True
    )

    assert controller.is_valid(state) is False


def test_is_valid_incomplete_form():
    """Should reject incomplete form."""
    validator = EntryValidator()
    controller = FormStateController(validator)

    state = FormState(jyutping="", hanzi="你好", meanings="hello", category="greetings")
    assert controller.is_valid(state) is False


def test_is_valid_reserved_category():
    """Should reject reserved categories."""
    validator = EntryValidator()
    controller = FormStateController(validator)

    state = FormState(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="unassigned"
    )
    assert controller.is_valid(state) is False


def test_is_valid_invalid_jyutping():
    """Should reject invalid Jyutping."""
    validator = EntryValidator()
    controller = FormStateController(validator)

    state = FormState(
        jyutping="invalid",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )
    assert controller.is_valid(state) is False


def test_is_valid_empty_hanzi():
    """Should reject empty Hanzi."""
    validator = EntryValidator()
    controller = FormStateController(validator)

    state = FormState(
        jyutping="nei5 hou2",
        hanzi="",
        meanings="hello",
        category="greetings"
    )
    assert controller.is_valid(state) is False


def test_is_valid_empty_meanings():
    """Should reject empty meanings."""
    validator = EntryValidator()
    controller = FormStateController(validator)

    state = FormState(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="",
        category="greetings"
    )
    assert controller.is_valid(state) is False


def test_update_triggers_callback_on_change():
    """Should call callback when validity changes."""
    validator = EntryValidator()
    calls = []

    def callback(valid: bool):
        calls.append(valid)

    controller = FormStateController(validator, on_state_changed=callback)

    # Start invalid
    state = FormState(jyutping="", hanzi="", meanings="", category="")
    controller.update(state)
    assert calls == [False]

    # Still invalid - no callback
    calls.clear()
    state = FormState(jyutping="nei5", hanzi="", meanings="", category="")
    controller.update(state)
    assert calls == []

    # Now valid - callback
    state = FormState(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )
    controller.update(state)
    assert calls == [True]

    # Still valid - no callback
    calls.clear()
    state = FormState(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello, hi",
        category="greetings"
    )
    controller.update(state)
    assert calls == []


def test_update_returns_validity():
    """Should return current validity."""
    validator = EntryValidator()
    controller = FormStateController(validator)

    state = FormState(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )
    assert controller.update(state) is True

    state = FormState(jyutping="", hanzi="", meanings="", category="")
    assert controller.update(state) is False


def test_reset_triggers_callback():
    """Should reset state and trigger callback if needed."""
    validator = EntryValidator()
    calls = []

    def callback(valid: bool):
        calls.append(valid)

    controller = FormStateController(validator, on_state_changed=callback)

    # Start valid
    state = FormState(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )
    controller.update(state)
    assert calls == [True]

    # Reset
    calls.clear()
    controller.reset()
    assert calls == [False]

    # Reset again - no callback (already invalid)
    calls.clear()
    controller.reset()
    assert calls == []


def test_callback_exception_does_not_break():
    """Should handle callback exceptions gracefully."""
    validator = EntryValidator()

    def bad_callback(valid: bool):
        raise RuntimeError("Callback error")

    controller = FormStateController(validator, on_state_changed=bad_callback)

    # Should not raise
    state = FormState(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )
    result = controller.update(state)
    assert result is True


def test_custom_reserved_categories():
    """Should respect custom reserved categories."""
    validator = EntryValidator()
    controller = FormStateController(
        validator,
        reserved_categories={"forbidden", "blocked"}
    )

    # Default reserved categories should now be allowed
    assert controller.is_category_valid("unassigned") is True
    assert controller.is_category_valid("all") is True

    # Custom reserved categories should be blocked
    assert controller.is_category_valid("forbidden") is False
    assert controller.is_category_valid("blocked") is False
