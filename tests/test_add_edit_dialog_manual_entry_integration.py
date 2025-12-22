import pytest

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QComboBox,
    QListView,
    QListWidget,
    QPushButton,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _load_add_dialog() -> QDialog:
    # Import lazily to avoid Qt side effects during collection
    import main

    dlg = main._load_add_item_ui(parent=None)
    assert isinstance(dlg, QDialog)
    return dlg


def _find_line_edit_by_name_or_hint(dlg: QDialog, *needles: str) -> QLineEdit | None:
    needles_l = [n.lower() for n in needles if n]
    for w in dlg.findChildren(QLineEdit):
        try:
            name = (w.objectName() or "").lower()
            ph = (w.placeholderText() or "").lower()
        except Exception:
            continue
        if any(n in name for n in needles_l) or any(n in ph for n in needles_l):
            return w
    return None


def _find_meanings_input(dlg: QDialog, *needles: str):
    """Find the meanings input widget.

    The UI may use QTextEdit or QPlainTextEdit. Fall back to QLineEdit if needed.
    """
    needles_l = [n.lower() for n in needles if n]

    def _match(w) -> bool:
        try:
            name = (w.objectName() or "").lower()
        except Exception:
            name = ""
        ph = ""
        try:
            if hasattr(w, "placeholderText") and callable(getattr(w, "placeholderText")):
                ph = str(w.placeholderText() or "").lower()
        except Exception:
            ph = ""
        return any(n in name for n in needles_l) or (ph and any(n in ph for n in needles_l))

    for w in dlg.findChildren(QTextEdit):
        if _match(w):
            return w

    for w in dlg.findChildren(QPlainTextEdit):
        if _match(w):
            return w

    for w in dlg.findChildren(QLineEdit):
        if _match(w):
            return w

    return None


def _find_category_control(dlg: QDialog):
    """Find the category selection control.

    Historically this has been a QComboBox, but some UI variants use a QListView/QListWidget.
    """
    # Prefer explicit objectName matches
    for w in dlg.findChildren(QComboBox):
        try:
            name = (w.objectName() or "").lower()
        except Exception:
            name = ""
        if "cat" in name or "category" in name:
            return w

    for w in dlg.findChildren(QListView):
        try:
            name = (w.objectName() or "").lower()
        except Exception:
            name = ""
        if "cat" in name or "category" in name:
            return w

    for w in dlg.findChildren(QListWidget):
        try:
            name = (w.objectName() or "").lower()
        except Exception:
            name = ""
        if "cat" in name or "category" in name:
            return w

    # Fallbacks: if there is exactly one plausible control, take it.
    cbs = dlg.findChildren(QComboBox)
    if len(cbs) == 1:
        return cbs[0]
    lws = dlg.findChildren(QListWidget)
    if len(lws) == 1:
        return lws[0]
    lvs = dlg.findChildren(QListView)
    if len(lvs) == 1:
        return lvs[0]

    return None


def _find_save_button(dlg: QDialog) -> QPushButton | None:
    # Prefer objectName match
    for b in dlg.findChildren(QPushButton):
        try:
            name = (b.objectName() or "").lower()
            text = (b.text() or "").lower()
        except Exception:
            continue
        if "save" in name or text in {"save", "add", "ok"} or "save" in text:
            return b
    return None


@pytest.mark.ui
def test_add_edit_manual_hanzi_entry_does_not_dead_end(qapp, monkeypatch):
    """Regression: if no candidates are found, user must still be able to enter Hanzi + meanings and save.

    This locks in the UI contract discovered during the reverse-index wrapper bug:
    - Candidate pipeline may return zero items.
    - Manual Hanzi entry must remain usable.
    - Save should become enabled once required fields are provided.
    """
    dlg = _load_add_dialog()

    # Best-effort: ensure candidate sources are empty so we exercise the manual path.
    try:
        if hasattr(dlg, "_reverse_jyut_map"):
            setattr(dlg, "_reverse_jyut_map", {})
        if hasattr(dlg, "_reverse_index"):
            setattr(dlg, "_reverse_index", {})
        if hasattr(dlg, "_char_map"):
            setattr(dlg, "_char_map", {})
    except Exception:
        pass

    # Patch the dialog's Tier-1/2 hooks if they exist.
    if hasattr(dlg, "_reverse_candidates_for_jy"):
        monkeypatch.setattr(dlg, "_reverse_candidates_for_jy", lambda *_a, **_k: [], raising=False)
    if hasattr(dlg, "compose_candidates_from_chars"):
        monkeypatch.setattr(dlg, "compose_candidates_from_chars", lambda *_a, **_k: [], raising=False)
    if hasattr(dlg, "_compose_candidates_from_chars"):
        monkeypatch.setattr(dlg, "_compose_candidates_from_chars", lambda *_a, **_k: [], raising=False)

    # Locate key widgets.
    jy = _find_line_edit_by_name_or_hint(dlg, "jyut", "jyutping")
    hz = _find_line_edit_by_name_or_hint(dlg, "hanzi", "hz")
    mn = _find_meanings_input(dlg, "meaning", "meanings", "gloss", "definition", "defs", "english")
    save_btn = _find_save_button(dlg)

    assert jy is not None, "Could not find Jyutping input in Add/Edit dialog"
    assert hz is not None, "Could not find Hanzi input in Add/Edit dialog"
    assert mn is not None, "Could not find Meanings input in Add/Edit dialog"
    assert save_btn is not None, "Could not find Save button in Add/Edit dialog"

    dlg.show()
    qapp.processEvents()
    # Locate category control after show (some UIs populate lazily).
    cat = _find_category_control(dlg)

    # Best effort: set a category so the save gate can become enabled.
    # Do not hard-fail if the control is not discoverable (some layouts embed it deeper
    # or store the selection purely in dialog state).
    if cat is not None:
        try:
            if isinstance(cat, QComboBox) and cat.count() > 0:
                cat.setCurrentIndex(0)
        except Exception:
            pass
        try:
            if isinstance(cat, QListWidget) and cat.count() > 0:
                cat.setCurrentRow(0)
        except Exception:
            pass
        try:
            if isinstance(cat, QListView) and cat.model() is not None and cat.model().rowCount() > 0:
                cat.setCurrentIndex(cat.model().index(0, 0))
        except Exception:
            pass
    else:
        # Fallback: some dialog implementations keep the selected category in an attribute.
        for attr in (
            "_active_cat",
            "_current_category",
            "_cat_key",
            "_category",
            "_selected_category",
            "_cat_name",
        ):
            try:
                if hasattr(dlg, attr):
                    setattr(dlg, attr, "colors")
            except Exception:
                pass

        # Or a method
        for meth in (
            "set_category",
            "setCategory",
            "_set_category",
            "_setCategory",
            "select_category",
            "_select_category",
        ):
            try:
                fn = getattr(dlg, meth, None)
                if callable(fn):
                    fn("colors")
                    break
            except Exception:
                pass

    qapp.processEvents()

    # Enter Jyutping that would normally produce candidates.
    jy.setText("ceng1")
    qapp.processEvents()

    # With no candidates, user must still be able to enter Hanzi manually.
    hz.setText("青")
    qapp.processEvents()

    # Provide meanings manually.
    if hasattr(mn, "setPlainText"):
        try:
            mn.setPlainText("blue/green")
        except Exception:
            pass
    if hasattr(mn, "setText"):
        try:
            mn.setText("blue/green")
        except Exception:
            pass
    qapp.processEvents()

    # Contract: Save becomes enabled once required fields are populated.
    assert save_btn.isEnabled(), (
        "Save should be enabled after manual Hanzi + meanings are provided. "
        "If this fails, the dialog may require an explicit category selection; "
        "ensure the test's category fallback matches the dialog's API/state."
    )

    dlg.close()