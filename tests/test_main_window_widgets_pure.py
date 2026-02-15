import pytest

from app.main_window_adapter import MainWindowAdapter
from app.main_window_widgets import resolve_main_window_widgets, MainWindowWidgetNames


class _StubWindow:
    def __init__(self):
        self.calls = []

    def findChild(self, cls, name):
        self.calls.append((cls, name))
        return object()

    def findChildren(self, cls):
        return []


@pytest.mark.pure
def test_resolve_main_window_widgets_uses_names_and_caches():
    win = _StubWindow()
    adapter = MainWindowAdapter(win)
    names = MainWindowWidgetNames()
    class _Btn: ...
    class _Tool: ...
    class _Group: ...
    class _Combo: ...
    cls_map = {
        "QPushButton": _Btn,
        "QToolButton": _Tool,
        "QGroupBox": _Group,
        "QComboBox": _Combo,
    }

    widgets1 = resolve_main_window_widgets(adapter, names, cls_map=cls_map)
    calls_after_first = len(win.calls)
    widgets2 = resolve_main_window_widgets(adapter, names, cls_map=cls_map)

    assert widgets1["btn_add"] is widgets2["btn_add"]
    assert widgets1["combo_category"] is widgets2["combo_category"]
    assert calls_after_first == len(win.calls)
    assert (_Btn, names.btn_add) in win.calls
