import pytest

from ui.category_manager_vocab_categories import CategoryManagerVocabCategories


class _StubCombo:
    def __init__(self):
        self.items = []
        self.current = None

    def clear(self):
        self.items = []

    def addItems(self, items):
        self.items.extend(list(items))

    def setCurrentText(self, text):
        self.current = text


class _StubDialog:
    def __init__(self):
        self._cats = {"work": [], "unassigned": []}
        self._all_cats = []
        self._add_cat = _StubCombo()


@pytest.mark.pure
def test_vocab_categories_refresh_sets_combo_items_and_selection():
    dialog = _StubDialog()

    CategoryManagerVocabCategories.refresh_category_dropdown_from_cats(dialog, selected="work")

    assert "work" in dialog._add_cat.items
    assert dialog._add_cat.current == "work"
