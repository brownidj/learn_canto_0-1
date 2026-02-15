import pytest

from ui.category_manager_vocab_search import CategoryManagerVocabSearch


class _StubTable:
    def __init__(self):
        self.text = None

    def set_search_filter(self, text):
        self.text = text


class _StubDialog:
    def __init__(self):
        self._vocab_table_ctrl = _StubTable()


@pytest.mark.pure
def test_vocab_search_applies_filter():
    dialog = _StubDialog()

    CategoryManagerVocabSearch.on_search_changed(dialog, "test")

    assert dialog._vocab_table_ctrl.text == "test"
