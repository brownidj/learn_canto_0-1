import os
import pytest


def _skip_if_headless_ci() -> None:
    if os.environ.get("CI") and not os.environ.get("DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
        pytest.skip("Headless CI environment without a Qt platform")


@pytest.mark.ui
def test_category_manager_dialog_smoke_ui():
    """Basic UI smoke test: dialog can be constructed, shown, and closed.

    Run with:
        .venv/bin/python3 -m pytest -q -m ui
    """
    _skip_if_headless_ci()

    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from category_manager import CategoryManagerDialog

    app = QApplication.instance() or QApplication([])

    vocab = {"白": [["White"], "baak6"]}
    cats = {"colors": ["白"], "unassigned": []}

    dlg = CategoryManagerDialog(None, vocab_items=vocab, categories_map=cats)
    dlg.show()
    app.processEvents()
    dlg.close()
    app.processEvents()


@pytest.mark.ui
def test_category_manager_dialog_uses_domain_validate_jyut_syllables(monkeypatch):
    """Regression: CategoryManagerDialog must delegate detailed Jyutping validation to domain.jyutping_validation."""
    _skip_if_headless_ci()

    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    import category_manager as cm
    from category_manager import CategoryManagerDialog

    app = QApplication.instance() or QApplication([])

    vocab = {"白": [["White"], "baak6"]}
    cats = {"colors": ["白"], "unassigned": []}

    dlg = CategoryManagerDialog(None, vocab_items=vocab, categories_map=cats)

    called = {"n": 0}

    def fake_validate(jy: str):
        called["n"] += 1
        return True, None

    monkeypatch.setattr(cm, "validate_jyut_syllables", fake_validate)

    ok, reason = dlg._validate_jyut_syllables("nei5 hou2")
    assert ok is True
    assert reason is None
    assert called["n"] == 1

    dlg.close()
    app.processEvents()