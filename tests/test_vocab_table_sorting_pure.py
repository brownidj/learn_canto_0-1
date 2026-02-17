from ui.vocab_table_sorting import sync_header_arrows_from_native


class _HeaderItem:
    def __init__(self, text):
        self.text = text

    def setText(self, text):
        self.text = text


class _Header:
    def __init__(self):
        self._section = 1
        self._order = 0
        self.clickable = False
        self.shown = True

    def setSectionsClickable(self, value):
        self.clickable = value

    def setSortIndicatorShown(self, value):
        self.shown = value

    def sortIndicatorSection(self):
        return self._section

    def sortIndicatorOrder(self):
        return self._order


class _Table:
    def __init__(self):
        self._header = _Header()
        self._items = [_HeaderItem("Hanzi"), _HeaderItem("Jyutping"), _HeaderItem("Meanings"), _HeaderItem("Categories")]

    def horizontalHeader(self):
        return self._header

    def horizontalHeaderItem(self, i):
        return self._items[i]


def test_sync_header_arrows_uses_native_state():
    table = _Table()
    col, order = sync_header_arrows_from_native(table, sort_column=0, sort_order=0)
    assert (col, order) == (1, 0)
    assert "\u25B2" in table._items[1].text  # active ascending arrow
    assert "\u25BD" in table._items[0].text  # inactive arrows on others
