"""Tests for widget utilities - uses mock Qt widgets."""

import pytest
from ui.widget_utils import WidgetAccessor, SignalBlocker

pytestmark = pytest.mark.pure


class MockWidget:
    """Mock Qt widget for testing."""

    def __init__(self):
        self.text_value = ""
        self.enabled = True
        self.visible = True
        self.focused = False
        self.selected = False
        self.signals_blocked = False
        self.current_index = -1
        self._deleted = False

    def text(self):
        if self._deleted:
            raise RuntimeError("Widget deleted")
        return self.text_value

    def setText(self, text):
        if self._deleted:
            raise RuntimeError("Widget deleted")
        self.text_value = str(text)

    def clear(self):
        if self._deleted:
            raise RuntimeError("Widget deleted")
        self.text_value = ""

    def setEnabled(self, enabled):
        if self._deleted:
            raise RuntimeError("Widget deleted")
        self.enabled = bool(enabled)

    def setVisible(self, visible):
        if self._deleted:
            raise RuntimeError("Widget deleted")
        self.visible = bool(visible)

    def setFocus(self):
        if self._deleted:
            raise RuntimeError("Widget deleted")
        self.focused = True

    def selectAll(self):
        if self._deleted:
            raise RuntimeError("Widget deleted")
        self.selected = True

    def blockSignals(self, block):
        if self._deleted:
            raise RuntimeError("Widget deleted")
        self.signals_blocked = bool(block)

    def signalsBlocked(self):
        if self._deleted:
            raise RuntimeError("Widget deleted")
        return self.signals_blocked

    def currentIndex(self):
        if self._deleted:
            raise RuntimeError("Widget deleted")
        return self.current_index

    def setCurrentIndex(self, index):
        if self._deleted:
            raise RuntimeError("Widget deleted")
        self.current_index = int(index)

    def currentText(self):
        if self._deleted:
            raise RuntimeError("Widget deleted")
        return self.text_value

    def setCurrentText(self, text):
        if self._deleted:
            raise RuntimeError("Widget deleted")
        self.text_value = str(text)


def test_get_text_from_widget():
    """Should get text from widget."""
    widget = MockWidget()
    widget.text_value = "  hello  "

    result = WidgetAccessor.get_text(widget)
    assert result == "hello"


def test_get_text_from_none():
    """Should return default for None widget."""
    result = WidgetAccessor.get_text(None)
    assert result == ""

    result = WidgetAccessor.get_text(None, default="fallback")
    assert result == "fallback"


def test_get_text_from_deleted_widget():
    """Should return default for deleted widget."""
    widget = MockWidget()
    widget._deleted = True

    result = WidgetAccessor.get_text(widget)
    assert result == ""


def test_set_text_on_widget():
    """Should set text on widget."""
    widget = MockWidget()

    result = WidgetAccessor.set_text(widget, "hello")
    assert result is True
    assert widget.text_value == "hello"


def test_set_text_on_none():
    """Should return False for None widget."""
    result = WidgetAccessor.set_text(None, "hello")
    assert result is False


def test_set_text_on_deleted_widget():
    """Should return False for deleted widget."""
    widget = MockWidget()
    widget._deleted = True

    result = WidgetAccessor.set_text(widget, "hello")
    assert result is False


def test_clear_text():
    """Should clear text from widget."""
    widget = MockWidget()
    widget.text_value = "hello"

    result = WidgetAccessor.clear_text(widget)
    assert result is True
    assert widget.text_value == ""


def test_set_enabled():
    """Should enable/disable widget."""
    widget = MockWidget()

    assert WidgetAccessor.set_enabled(widget, False) is True
    assert widget.enabled is False

    assert WidgetAccessor.set_enabled(widget, True) is True
    assert widget.enabled is True


def test_set_visible():
    """Should show/hide widget."""
    widget = MockWidget()

    assert WidgetAccessor.set_visible(widget, False) is True
    assert widget.visible is False

    assert WidgetAccessor.set_visible(widget, True) is True
    assert widget.visible is True


def test_focus_widget():
    """Should focus widget."""
    widget = MockWidget()

    result = WidgetAccessor.focus(widget)
    assert result is True
    assert widget.focused is True


def test_focus_with_select_all():
    """Should focus and select all text."""
    widget = MockWidget()

    result = WidgetAccessor.focus(widget, select_all=True)
    assert result is True
    assert widget.focused is True
    assert widget.selected is True


def test_get_combo_index():
    """Should get combo index."""
    widget = MockWidget()
    widget.current_index = 5

    result = WidgetAccessor.get_combo_index(widget)
    assert result == 5


def test_get_combo_index_default():
    """Should return default for None widget."""
    result = WidgetAccessor.get_combo_index(None)
    assert result == -1

    result = WidgetAccessor.get_combo_index(None, default=99)
    assert result == 99


def test_set_combo_index():
    """Should set combo index."""
    widget = MockWidget()

    result = WidgetAccessor.set_combo_index(widget, 3)
    assert result is True
    assert widget.current_index == 3


def test_block_signals():
    """Should block/unblock signals."""
    widget = MockWidget()

    assert WidgetAccessor.block_signals(widget, True) is True
    assert widget.signals_blocked is True

    assert WidgetAccessor.block_signals(widget, False) is True
    assert widget.signals_blocked is False


def test_signal_blocker_context():
    """Should block signals in context."""
    widget = MockWidget()
    assert widget.signals_blocked is False

    with SignalBlocker(widget):
        assert widget.signals_blocked is True

    assert widget.signals_blocked is False


def test_signal_blocker_multiple_widgets():
    """Should block multiple widgets."""
    w1 = MockWidget()
    w2 = MockWidget()

    with SignalBlocker(w1, w2):
        assert w1.signals_blocked is True
        assert w2.signals_blocked is True

    assert w1.signals_blocked is False
    assert w2.signals_blocked is False


def test_signal_blocker_with_none():
    """Should ignore None widgets."""
    widget = MockWidget()

    # Should not raise
    with SignalBlocker(widget, None):
        assert widget.signals_blocked is True


def test_signal_blocker_restores_original_state():
    """Should restore original signal state."""
    widget = MockWidget()
    widget.signals_blocked = True  # Start blocked

    with SignalBlocker(widget):
        pass  # Inner: forced to True

    # Should restore to True
    assert widget.signals_blocked is True
