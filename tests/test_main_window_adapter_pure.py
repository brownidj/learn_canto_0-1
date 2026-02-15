import pytest

from app.main_window_adapter import MainWindowAdapter


class _StubWindow:
    def __init__(self):
        self.calls = 0
        self.child = object()

    def findChild(self, cls, name):
        self.calls += 1
        return self.child

    def findChildren(self, cls):
        return []


@pytest.mark.pure
def test_main_window_adapter_widget_cache():
    win = _StubWindow()
    adapter = MainWindowAdapter(win)

    a = adapter.widget(object, "foo")
    b = adapter.widget(object, "foo")

    assert a is b
    assert win.calls == 1
