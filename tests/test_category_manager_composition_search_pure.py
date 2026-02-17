from ui.category_manager_composition import CategoryManagerComposition


class _StubDialog:
    pass


def test_composition_sets_on_search_changed_handler(monkeypatch):
    dlg = _StubDialog()
    called = {"ok": False}

    def _fake_on_search_changed(_dlg, _text):
        called["ok"] = True

    monkeypatch.setattr("ui.category_manager_vocab_display.on_search_changed", _fake_on_search_changed)

    CategoryManagerComposition(dlg).build()
    assert callable(dlg._on_search_changed)

    dlg._on_search_changed("foo")
    assert called["ok"] is True
