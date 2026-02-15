import pytest

from ui.category_manager_vocab_table import CategoryManagerVocabTable


class _StubDialog:
    def __init__(self):
        self.called = False

    def _rebuild_items_model(self):
        self.called = True


@pytest.mark.pure
def test_vocab_table_refresh_falls_back_to_rebuild():
    dialog = _StubDialog()

    CategoryManagerVocabTable.refresh_table(dialog)

    assert dialog.called is True
