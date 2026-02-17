from ui.vocab_table_searching import wire_search_field


class _Signal:
    def __init__(self):
        self._cb = None

    def connect(self, cb):
        self._cb = cb


class _Search:
    def __init__(self):
        self.textChanged = _Signal()
        self.returnPressed = _Signal()
        self.clear_enabled = False

    def setClearButtonEnabled(self, value):
        self.clear_enabled = bool(value)

    def text(self):
        return "foo"


def test_wire_search_field_sets_clear_and_connects():
    search = _Search()
    called = {"ok": False}

    def _cb(_text):
        called["ok"] = True

    wire_search_field(search, _cb)
    assert search.clear_enabled is True
    assert search.textChanged._cb is _cb
    assert search.returnPressed._cb is not None
