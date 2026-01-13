import os

import pytest
from PySide6.QtWidgets import QApplication


def _skip_if_headless_ci() -> None:
    """Skip UI tests in truly headless CI environments.

    This project sometimes runs UI tests offscreen locally; we only skip when CI
    is set and there's no reasonable Qt platform configured.
    """
    ci = str(os.environ.get("CI", "")).strip().lower()
    if ci not in ("1", "true", "yes"):
        return

    # If the user has configured an offscreen/minimal platform, allow the test.
    qpa = str(os.environ.get("QT_QPA_PLATFORM", "")).strip().lower()
    if qpa in ("offscreen", "minimal"):
        return

    pytest.skip("Headless CI without QT_QPA_PLATFORM=offscreen/minimal")


@pytest.mark.ui
@pytest.mark.skip(reason="Refactoring: _on_jyut_enter removed, needs update for AddEditPanel")
def test_add_new_category_yes_adds_and_selects(monkeypatch):
    """Regression: entering a brand-new category and confirming 'Yes' adds it.

    Contract:
      - The new category must be added to the authoritative in-memory map `dlg._cats`.
      - The combobox should leave the new category selected.
    """

    _skip_if_headless_ci()

    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from category_manager import CategoryManagerDialog

    app = QApplication.instance() or QApplication([])

    # Force the add-category confirmation to Yes.
    def _fake_question(*args, **kwargs):
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", _fake_question)

    vocab = {"前": [["front"], "cin4"]}
    cats = {"direction": [], "unassigned": []}

    dlg = CategoryManagerDialog(None, vocab_items=vocab, categories_map=cats)
    dlg.show()
    app.processEvents()

    # Jyutping validated
    dlg._add_jy.setText("cin4")
    dlg._on_jyut_enter()
    app.processEvents()

    # New category entry + commit
    new_cat = "verbs_actions"
    dlg._add_cat.setEditable(True)
    dlg._add_cat.setCurrentText(new_cat)
    dlg._on_add_category_committed(user_action=True)
    app.processEvents()

    # Must exist in the authoritative in-memory map
    assert isinstance(getattr(dlg, "_cats", None), dict)
    assert new_cat in dlg._cats

    # And remain selected in the combobox
    assert (dlg._add_cat.currentText() or "").strip() == new_cat


@pytest.mark.ui
@pytest.mark.skip(reason="Refactoring: _on_jyut_enter removed, needs update for AddEditPanel")
def test_add_new_category_no_clears_and_refocuses(monkeypatch):
    """Regression: confirming 'No' should not add the category and should clear."""

    _skip_if_headless_ci()

    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from category_manager import CategoryManagerDialog

    app = QApplication.instance() or QApplication([])

    # Force the add-category confirmation to No.
    def _fake_question(*args, **kwargs):
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", _fake_question)

    vocab = {"前": [["front"], "cin4"]}
    cats = {"direction": [], "unassigned": []}

    dlg = CategoryManagerDialog(None, vocab_items=vocab, categories_map=cats)
    dlg.show()
    app.processEvents()

    dlg._add_jy.setText("cin4")
    dlg._on_jyut_enter()
    app.processEvents()

    new_cat = "verbs_actions"
    dlg._add_cat.setEditable(True)
    dlg._add_cat.setCurrentText(new_cat)
    dlg._on_add_category_committed(user_action=True)
    app.processEvents()

    assert isinstance(getattr(dlg, "_cats", None), dict)
    assert new_cat not in dlg._cats

    # Category entry should be cleared for reselection.
    assert (dlg._add_cat.currentText() or "").strip() in ("", "direction", "unassigned")