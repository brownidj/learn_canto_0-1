"""Safe widget access utilities - no more scattered try/except blocks.

This module provides defensive accessors for Qt widgets that handle all the
edge cases (deleted widgets, None values, type errors) in one place.
"""

from __future__ import annotations
from typing import Any, TypeVar, cast

# Type variable for generic returns
T = TypeVar('T')


class WidgetAccessor:
    """Safe accessors for Qt widget properties.

    All methods are defensive - they never raise, always return sensible defaults.
    """

    @staticmethod
    def get_text(widget: Any, default: str = "") -> str:
        """Get text from QLineEdit, QTextEdit, or QComboBox.

        Args:
            widget: Widget to read from (can be None)
            default: Default value if read fails

        Returns:
            Stripped text or default
        """
        if widget is None:
            return default

        # QLineEdit, QLabel
        try:
            if hasattr(widget, 'text') and callable(widget.text):
                result = widget.text()
                if result is not None:
                    return str(result).strip()
        except RuntimeError:
            # Widget deleted - common in tests
            return default
        except (TypeError, AttributeError):
            pass

        # QTextEdit, QPlainTextEdit
        try:
            if hasattr(widget, 'toPlainText') and callable(widget.toPlainText):
                result = widget.toPlainText()
                if result is not None:
                    return str(result).strip()
        except RuntimeError:
            return default
        except (TypeError, AttributeError):
            pass

        # QComboBox
        try:
            if hasattr(widget, 'currentText') and callable(widget.currentText):
                result = widget.currentText()
                if result is not None:
                    return str(result).strip()
        except RuntimeError:
            return default
        except (TypeError, AttributeError):
            pass

        return default

    @staticmethod
    def set_text(widget: Any, text: str) -> bool:
        """Set text on QLineEdit, QTextEdit, or QComboBox.

        Args:
            widget: Widget to update (can be None)
            text: Text to set

        Returns:
            True if successful
        """
        if widget is None:
            return False

        text_str = str(text) if text is not None else ""

        # QLineEdit, QLabel
        try:
            if hasattr(widget, 'setText') and callable(widget.setText):
                widget.setText(text_str)
                return True
        except RuntimeError:
            return False
        except (TypeError, AttributeError):
            pass

        # QTextEdit, QPlainTextEdit
        try:
            if hasattr(widget, 'setPlainText') and callable(widget.setPlainText):
                widget.setPlainText(text_str)
                return True
        except RuntimeError:
            return False
        except (TypeError, AttributeError):
            pass

        # QComboBox (editable)
        try:
            if hasattr(widget, 'setCurrentText') and callable(widget.setCurrentText):
                widget.setCurrentText(text_str)
                return True
        except RuntimeError:
            return False
        except (TypeError, AttributeError):
            pass

        return False

    @staticmethod
    def clear_text(widget: Any) -> bool:
        """Clear text from widget.

        Args:
            widget: Widget to clear (can be None)

        Returns:
            True if successful
        """
        if widget is None:
            return False

        # Try clear() first (most widgets)
        try:
            if hasattr(widget, 'clear') and callable(widget.clear):
                widget.clear()
                return True
        except RuntimeError:
            return False
        except (TypeError, AttributeError):
            pass

        # Fallback: setText("")
        return WidgetAccessor.set_text(widget, "")

    @staticmethod
    def set_enabled(widget: Any, enabled: bool) -> bool:
        """Enable or disable widget.

        Args:
            widget: Widget to update (can be None)
            enabled: True to enable, False to disable

        Returns:
            True if successful
        """
        if widget is None:
            return False

        try:
            if hasattr(widget, 'setEnabled') and callable(widget.setEnabled):
                widget.setEnabled(bool(enabled))
                return True
        except RuntimeError:
            return False
        except (TypeError, AttributeError):
            pass

        return False

    @staticmethod
    def set_visible(widget: Any, visible: bool) -> bool:
        """Show or hide widget.

        Args:
            widget: Widget to update (can be None)
            visible: True to show, False to hide

        Returns:
            True if successful
        """
        if widget is None:
            return False

        try:
            if hasattr(widget, 'setVisible') and callable(widget.setVisible):
                widget.setVisible(bool(visible))
                return True
        except RuntimeError:
            return False
        except (TypeError, AttributeError):
            pass

        return False

    @staticmethod
    def focus(widget: Any, select_all: bool = False) -> bool:
        """Set focus to widget.

        Args:
            widget: Widget to focus (can be None)
            select_all: If True, select all text (for text widgets)

        Returns:
            True if successful
        """
        if widget is None:
            return False

        try:
            if hasattr(widget, 'setFocus') and callable(widget.setFocus):
                widget.setFocus()

                if select_all:
                    try:
                        if hasattr(widget, 'selectAll') and callable(widget.selectAll):
                            widget.selectAll()
                    except RuntimeError:
                        pass

                return True
        except RuntimeError:
            return False
        except (TypeError, AttributeError):
            pass

        return False

    @staticmethod
    def get_combo_index(widget: Any, default: int = -1) -> int:
        """Get current index from QComboBox.

        Args:
            widget: Combobox widget (can be None)
            default: Default value if read fails

        Returns:
            Current index or default
        """
        if widget is None:
            return default

        try:
            if hasattr(widget, 'currentIndex') and callable(widget.currentIndex):
                result = widget.currentIndex()
                if result is not None:
                    return int(result)
        except RuntimeError:
            return default
        except (TypeError, AttributeError, ValueError):
            pass

        return default

    @staticmethod
    def set_combo_index(widget: Any, index: int) -> bool:
        """Set current index on QComboBox.

        Args:
            widget: Combobox widget (can be None)
            index: Index to set

        Returns:
            True if successful
        """
        if widget is None:
            return False

        try:
            if hasattr(widget, 'setCurrentIndex') and callable(widget.setCurrentIndex):
                widget.setCurrentIndex(int(index))
                return True
        except RuntimeError:
            return False
        except (TypeError, AttributeError, ValueError):
            pass

        return False

    @staticmethod
    def block_signals(widget: Any, block: bool) -> bool:
        """Block or unblock widget signals.

        Args:
            widget: Widget to update (can be None)
            block: True to block, False to unblock

        Returns:
            True if successful
        """
        if widget is None:
            return False

        try:
            if hasattr(widget, 'blockSignals') and callable(widget.blockSignals):
                widget.blockSignals(bool(block))
                return True
        except RuntimeError:
            return False
        except (TypeError, AttributeError):
            pass

        return False


class SignalBlocker:
    """Context manager to temporarily block widget signals.

    Example:
        with SignalBlocker(my_widget):
            my_widget.setText("...")  # No signals emitted
    """

    def __init__(self, *widgets: Any):
        """
        Args:
            *widgets: Widgets to block (can include None)
        """
        self.widgets = [w for w in widgets if w is not None]
        self.original_states: dict[Any, bool] = {}

    def __enter__(self):
        for widget in self.widgets:
            try:
                if hasattr(widget, 'signalsBlocked') and hasattr(widget, 'blockSignals'):
                    self.original_states[widget] = widget.signalsBlocked()
                    widget.blockSignals(True)
            except RuntimeError:
                pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for widget, original_state in self.original_states.items():
            try:
                widget.blockSignals(original_state)
            except RuntimeError:
                pass
        return False


__all__ = [
    "WidgetAccessor",
    "SignalBlocker",
]
