from __future__ import annotations


class MainWindowAdapter:
    """Stable access surface for main window internals."""

    def __init__(self, window):
        self._window = window
        self._widget_cache: dict[tuple[type, str], object | None] = {}

    @property
    def window(self):
        return self._window

    def get(self, name: str, default=None):
        try:
            return getattr(self._window, name, default)
        except (TypeError, AttributeError, RuntimeError):
            return default

    def set(self, name: str, value) -> None:
        try:
            setattr(self._window, name, value)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def find_child(self, cls, name: str):
        try:
            return self._window.findChild(cls, name)
        except (TypeError, AttributeError, RuntimeError):
            return None

    def find_children(self, cls):
        try:
            return list(self._window.findChildren(cls))
        except (TypeError, AttributeError, RuntimeError):
            return []

    def widget(self, cls, name: str):
        key = (cls, name)
        if key in self._widget_cache:
            return self._widget_cache[key]
        w = self.find_child(cls, name)
        self._widget_cache[key] = w
        return w
