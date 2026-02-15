from __future__ import annotations

from contextlib import contextmanager

from ui.widget_utils import SignalBlocker, WidgetAccessor


def get_text(widget) -> str:
    return WidgetAccessor.get_text(widget)


def set_text(widget, text: str) -> None:
    if widget is None:
        return
    try:
        if hasattr(widget, "setText"):
            widget.setText(str(text))
            return
        if hasattr(widget, "setPlainText"):
            widget.setPlainText(str(text))
            return
    except (TypeError, AttributeError, RuntimeError, ValueError):
        pass
    try:
        WidgetAccessor.set_text(widget, text)
    except Exception:
        pass


def clear_text(widget) -> None:
    if widget is None:
        return
    try:
        if hasattr(widget, "clear"):
            widget.clear()
            return
    except (TypeError, AttributeError, RuntimeError, ValueError):
        pass
    set_text(widget, "")


def set_visible(widget, visible: bool) -> None:
    if widget is None:
        return
    try:
        if hasattr(widget, "setVisible"):
            widget.setVisible(bool(visible))
            return
    except (TypeError, AttributeError, RuntimeError, ValueError):
        pass
    try:
        WidgetAccessor.set_visible(widget, bool(visible))
    except Exception:
        pass


def set_enabled(widget, enabled: bool) -> None:
    if widget is None:
        return
    try:
        if hasattr(widget, "setEnabled"):
            widget.setEnabled(bool(enabled))
    except (TypeError, AttributeError, RuntimeError, ValueError):
        pass


def set_readonly(widget, readonly: bool) -> None:
    if widget is None:
        return
    try:
        if hasattr(widget, "setReadOnly"):
            widget.setReadOnly(bool(readonly))
    except (TypeError, AttributeError, RuntimeError, ValueError):
        pass


def set_combo_index(widget, index: int) -> None:
    try:
        WidgetAccessor.set_combo_index(widget, int(index))
    except (TypeError, AttributeError, RuntimeError, ValueError):
        pass


def focus(widget, *, select_all: bool = True) -> None:
    try:
        WidgetAccessor.focus(widget, select_all=bool(select_all))
    except (TypeError, AttributeError, RuntimeError, ValueError):
        pass


@contextmanager
def signals_blocked(widget):
    if widget is None:
        yield
        return
    try:
        with SignalBlocker(widget):
            yield
    except (TypeError, AttributeError, RuntimeError, ValueError):
        yield
