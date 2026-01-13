"""Tests for VocabularyTableController - uses mock table."""

import pytest
from ui.vocabulary_table_controller import VocabularyTableController, TableRow

pytestmark = pytest.mark.pure


class MockTableItem:
    """Mock QTableWidgetItem."""
    def __init__(self, text=""):
        self.text_value = str(text)

    def text(self):
        return self.text_value


class MockTable:
    """Mock QTableWidget."""
    def __init__(self):
        self.rows = []
        self.current_row = -1

    def setRowCount(self, count):
        self.rows = [None] * count

    def rowCount(self):
        return len(self.rows)

    def setItem(self, row, col, item):
        if row >= len(self.rows):
            self.rows.extend([None] * (row - len(self.rows) + 1))
        if self.rows[row] is None:
            self.rows[row] = []
        while len(self.rows[row]) <= col:
            self.rows[row].append(None)
        self.rows[row][col] = item

    def item(self, row, col):
        if row < 0 or row >= len(self.rows):
            return None
        if self.rows[row] is None or col >= len(self.rows[row]):
            return None
        return self.rows[row][col]

    def currentRow(self):
        return self.current_row


def test_table_row_to_list():
    """Should convert row to list."""
    row = TableRow(
        hanzi="你好",
        jyutping="nei5 hou2",
        meanings="hello",
        categories=["greetings"]
    )

    result = row.to_list()
    assert result == ["你好", "nei5 hou2", "hello", "greetings"]


def test_table_row_multiple_categories():
    """Should join multiple categories."""
    row = TableRow(
        hanzi="好",
        jyutping="hou2",
        meanings="good",
        categories=["adjectives", "common"]
    )

    result = row.to_list()
    assert result[3] == "adjectives, common"


def test_build_rows():
    """Should build rows from vocab and categories."""
    vocab = {
        "你好": (["hello"], "nei5 hou2"),
        "好": (["good"], "hou2"),
    }
    cats = {
        "greetings": ["你好"],
        "adjectives": ["好"],
    }

    table = MockTable()
    controller = VocabularyTableController(table, vocab, cats)
    rows = controller.build_rows()

    assert len(rows) == 2
    assert any(r.hanzi == "你好" and "greetings" in r.categories for r in rows)
    assert any(r.hanzi == "好" and "adjectives" in r.categories for r in rows)


def test_populate():
    """Should populate table from vocab."""
    vocab = {
        "你好": (["hello"], "nei5 hou2"),
        "好": (["good"], "hou2"),
    }
    cats = {
        "greetings": ["你好"],
        "adjectives": ["好"],
    }

    table = MockTable()
    controller = VocabularyTableController(table, vocab, cats)
    controller.populate()

    assert table.rowCount() == 2


def test_search_filter():
    """Should filter rows by search text."""
    vocab = {
        "你好": (["hello"], "nei5 hou2"),
        "好": (["good"], "hou2"),
        "再見": (["goodbye"], "zoi3 gin3"),
    }
    cats = {"greetings": ["你好", "再見"], "adjectives": ["好"]}

    table = MockTable()
    controller = VocabularyTableController(table, vocab, cats)
    controller.populate()

    # All rows initially
    assert table.rowCount() == 3

    # Filter by Hanzi
    controller.set_search_filter("好")
    assert table.rowCount() == 2  # 你好 and 好

    # Filter by meaning
    controller.set_search_filter("goodbye")
    assert table.rowCount() == 1

    # Filter by Jyutping
    controller.set_search_filter("hou2")
    assert table.rowCount() == 2  # nei5 hou2 and hou2

    # Clear filter
    controller.set_search_filter("")
    assert table.rowCount() == 3


def test_get_selected_hanzi():
    """Should get Hanzi from selected row."""
    vocab = {"你好": (["hello"], "nei5 hou2")}
    cats = {"greetings": ["你好"]}

    table = MockTable()
    controller = VocabularyTableController(table, vocab, cats)
    controller.populate()

    # No selection
    assert controller.get_selected_hanzi() is None

    # Select row
    table.current_row = 0
    hanzi = controller.get_selected_hanzi()
    assert hanzi == "你好"


def test_refresh_from_data():
    """Should refresh table after external data changes."""
    vocab = {"你好": (["hello"], "nei5 hou2")}
    cats = {"greetings": ["你好"]}

    table = MockTable()
    controller = VocabularyTableController(table, vocab, cats)
    controller.populate()

    assert table.rowCount() == 1

    # Add new entry externally
    vocab["好"] = (["good"], "hou2")
    cats["adjectives"] = ["好"]

    # Refresh
    controller.refresh_from_data()
    assert table.rowCount() == 2


def test_clear():
    """Should clear all rows."""
    vocab = {"你好": (["hello"], "nei5 hou2")}
    cats = {"greetings": ["你好"]}

    table = MockTable()
    controller = VocabularyTableController(table, vocab, cats)
    controller.populate()

    assert table.rowCount() == 1

    controller.clear()
    assert table.rowCount() == 0


def test_sort_by_category_and_meaning():
    """Should sort rows by category then meaning."""
    vocab = {
        "好": (["good"], "hou2"),
        "你好": (["hello"], "nei5 hou2"),
        "再見": (["goodbye"], "zoi3 gin3"),
    }
    cats = {
        "greetings": ["你好", "再見"],
        "adjectives": ["好"],
    }

    table = MockTable()
    controller = VocabularyTableController(table, vocab, cats)
    controller.populate(sort=True)

    # Should be sorted by category (adjectives < greetings)
    # then by meaning
    assert table.rowCount() == 3

    # Get first row hanzi
    first_item = table.item(0, 0)
    assert first_item is not None
    # Should be "好" (adjectives comes first)
    assert first_item.text() == "好"
