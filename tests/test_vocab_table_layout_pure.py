from ui.vocab_table_layout import apply_column_widths


class _Header:
    def __init__(self):
        self.sections = {}
        self.mode = None
        self.stretch = None

    def setSectionResizeMode(self, mode):
        self.mode = mode

    def setStretchLastSection(self, value):
        self.stretch = value

    def resizeSection(self, idx, width):
        self.sections[idx] = width


class _Viewport:
    def __init__(self, width):
        self._width = width

    def width(self):
        return self._width


class _Table:
    def __init__(self, width):
        self._width = width
        self._header = _Header()
        self._viewport = _Viewport(width)

    def horizontalHeader(self):
        return self._header

    def width(self):
        return self._width

    def viewport(self):
        return self._viewport


def test_apply_column_widths_sets_proportions():
    table = _Table(1000)
    apply_column_widths(table)
    w_hz = table._header.sections.get(0)
    w_jy = table._header.sections.get(1)
    w_mn = table._header.sections.get(2)
    w_cat = table._header.sections.get(3)
    assert w_hz is not None and w_jy is not None and w_mn is not None and w_cat is not None
    assert w_mn > w_jy
    assert w_cat > w_jy
