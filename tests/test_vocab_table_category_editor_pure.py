import ui.vocab_table_category_editor as _mod


def test_make_delegate_returns_none_without_qt(monkeypatch):
    monkeypatch.setattr(_mod, "QStyledItemDelegate", None)
    monkeypatch.setattr(_mod, "QComboBox", None)
    assert _mod.make_category_combo_delegate(lambda: []) is None
