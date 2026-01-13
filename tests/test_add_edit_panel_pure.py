"""Tests for AddEditPanel - uses mock widgets."""

import pytest
from ui.add_edit_panel import AddEditPanel, AddEditResult
from ui.widget_utils import WidgetAccessor
from domain.vocabulary_service import VocabularyService
from domain.entry_validation import EntryValidator

pytestmark = pytest.mark.pure


class MockWidget:
    """Mock Qt widget."""
    def __init__(self):
        self.text_value = ""
        self.enabled = True
        self.readonly = False
        self.focused = False

    def text(self):
        return self.text_value

    def setText(self, text):
        self.text_value = str(text)

    def clear(self):
        self.text_value = ""

    def setEnabled(self, enabled):
        self.enabled = bool(enabled)

    def setReadOnly(self, readonly):
        self.readonly = bool(readonly)

    def setFocus(self):
        self.focused = True

    def selectAll(self):
        pass

    def blockSignals(self, block):
        pass

    def currentText(self):
        return self.text_value

    def setCurrentText(self, text):
        self.text_value = str(text)


def create_panel():
    """Create panel with mock widgets and services."""
    jy = MockWidget()
    hz = MockWidget()
    mn = MockWidget()
    cat = MockWidget()
    btn = MockWidget()

    vocab = {}
    cats = {}
    service = VocabularyService(vocab, cats)
    validator = EntryValidator()

    panel = AddEditPanel(
        jyutping_widget=jy,
        hanzi_widget=hz,
        meanings_widget=mn,
        category_widget=cat,
        save_button=btn,
        vocabulary_service=service,
        validator=validator,
    )

    return panel, jy, hz, mn, cat, btn, vocab, cats


def test_get_values():
    """Should get current form values."""
    panel, jy, hz, mn, cat, btn, _, _ = create_panel()

    jy.text_value = "nei5 hou2"
    hz.text_value = "你好"
    mn.text_value = "hello"
    cat.text_value = "greetings"

    state = panel.get_values()
    assert state.jyutping == "nei5 hou2"
    assert state.hanzi == "你好"
    assert state.meanings == "hello"
    assert state.category == "greetings"


def test_set_values():
    """Should set form values."""
    panel, jy, hz, mn, cat, btn, _, _ = create_panel()

    panel.set_values(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )

    assert jy.text_value == "nei5 hou2"
    assert hz.text_value == "你好"
    assert mn.text_value == "hello"
    assert cat.text_value == "greetings"


def test_clear():
    """Should clear all fields."""
    panel, jy, hz, mn, cat, btn, _, _ = create_panel()

    panel.set_values(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )

    panel.clear()

    assert jy.text_value == ""
    assert hz.text_value == ""
    assert mn.text_value == ""
    assert cat.text_value == ""


def test_is_valid_complete_form():
    """Should validate complete form."""
    panel, jy, hz, mn, cat, btn, _, _ = create_panel()

    panel.set_values(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )

    assert panel.is_valid() is True


def test_is_valid_incomplete_form():
    """Should reject incomplete form."""
    panel, jy, hz, mn, cat, btn, _, _ = create_panel()

    panel.set_values(
        jyutping="",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )

    assert panel.is_valid() is False


def test_validate_returns_errors():
    """Should return validation errors."""
    panel, jy, hz, mn, cat, btn, _, _ = create_panel()

    panel.set_values(
        jyutping="invalid",
        hanzi="",
        meanings="",
        category="unassigned"
    )

    errors = panel.validate()
    assert "jyutping" in errors
    assert "hanzi" in errors
    assert "meanings" in errors
    assert "category" in errors


def test_save_valid_entry():
    """Should save valid entry."""
    panel, jy, hz, mn, cat, btn, vocab, cats = create_panel()

    panel.set_values(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )

    result = panel.save()

    assert result.success is True
    assert result.entry is not None
    assert result.entry.hanzi == "你好"
    assert result.error is None

    # Check vocab updated
    assert "你好" in vocab
    assert "greetings" in cats


def test_save_invalid_entry():
    """Should reject invalid entry."""
    panel, jy, hz, mn, cat, btn, vocab, cats = create_panel()

    panel.set_values(
        jyutping="invalid",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )

    result = panel.save()

    assert result.success is False
    assert result.entry is None
    assert result.error is not None
    assert "jyutping" in result.error.lower()


def test_save_duplicate_entry():
    """Should reject duplicate entry."""
    panel, jy, hz, mn, cat, btn, vocab, cats = create_panel()

    # Add first entry
    panel.set_values(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )
    panel.save()

    # Try duplicate
    result = panel.save()

    assert result.success is False
    assert result.error is not None
    assert "duplicate" in result.error.lower() or "exists" in result.error.lower()


def test_save_callbacks():
    """Should call callbacks on save."""
    panel, jy, hz, mn, cat, btn, vocab, cats = create_panel()

    saved_entries = []
    errors = []

    def on_save(entry):
        saved_entries.append(entry)

    def on_error(error):
        errors.append(error)

    panel._on_save = on_save
    panel._on_error = on_error

    # Valid save
    panel.set_values(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )
    panel.save()

    assert len(saved_entries) == 1
    assert len(errors) == 0

    # Invalid save
    panel.set_values(jyutping="invalid", hanzi="X", meanings="x", category="c")
    panel.save()

    assert len(saved_entries) == 1  # Still 1
    assert len(errors) == 1


def test_focus_field():
    """Should focus specific fields."""
    panel, jy, hz, mn, cat, btn, _, _ = create_panel()

    assert panel.focus_field("jyutping") is True
    assert jy.focused is True

    hz.focused = False
    assert panel.focus_field("hanzi") is True
    assert hz.focused is True

    mn.focused = False
    assert panel.focus_field("meanings") is True
    assert mn.focused is True

    cat.focused = False
    assert panel.focus_field("category") is True
    assert cat.focused is True


def test_focus_invalid_field():
    """Should return False for invalid field."""
    panel, jy, hz, mn, cat, btn, _, _ = create_panel()

    result = panel.focus_field("invalid")
    assert result is False


def test_manual_hanzi_mode():
    """Should enter/exit manual Hanzi mode."""
    panel, jy, hz, mn, cat, btn, _, _ = create_panel()

    # Initially not in manual mode
    state = panel.get_values()
    assert state.manual_hanzi is False

    # Enter manual mode
    panel.enter_manual_hanzi_mode()
    assert hz.readonly is False
    assert hz.focused is True

    state = panel.get_values()
    assert state.manual_hanzi is True

    # Exit manual mode
    panel.exit_manual_hanzi_mode()
    assert hz.readonly is True

    state = panel.get_values()
    assert state.manual_hanzi is False


def test_save_button_enabled_on_valid():
    """Should enable Save button when form is valid."""
    panel, jy, hz, mn, cat, btn, _, _ = create_panel()

    # Start invalid - button should be disabled
    print(f"Initial button state: {btn.enabled}")
    panel.set_values(jyutping="", hanzi="", meanings="", category="")
    print(f"After empty set_values, button: {btn.enabled}")
    print(f"Form is_valid: {panel.is_valid()}")

    state = panel.get_values()
    print(f"State: jy={state.jyutping!r}, hz={state.hanzi!r}, mn={state.meanings!r}, cat={state.category!r}")

    assert btn.enabled is False, f"Expected button disabled, but enabled={btn.enabled}"

    # Make valid - button should be enabled
    panel.set_values(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )
    print(f"After valid set_values, button: {btn.enabled}")
    print(f"Form is_valid: {panel.is_valid()}")

    assert btn.enabled is True, f"Expected button enabled, but enabled={btn.enabled}"


def test_save_button_disabled_while_saving():
    """Should disable Save button while saving."""
    panel, jy, hz, mn, cat, btn, _, _ = create_panel()

    panel.set_values(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )
    assert btn.enabled is True

    # Mock saving state
    panel._saving = True
    panel._update_form_state()
    assert btn.enabled is False


def test_set_hanzi_readonly():
    """Should set Hanzi readonly state."""
    panel, jy, hz, mn, cat, btn, _, _ = create_panel()

    panel.set_hanzi_readonly(True)
    assert hz.readonly is True

    panel.set_hanzi_readonly(False)
    assert hz.readonly is False
