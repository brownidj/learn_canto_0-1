import pytest
from PySide6.QtWidgets import QApplication, QDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _load_add_dialog():
    # Import lazily to avoid Qt side effects during collection
    import main
    dlg = main._load_add_item_ui(parent=None)
    assert isinstance(dlg, QDialog)
    return dlg


def test_add_edit_dialog_is_landscape(qapp):
    dlg = _load_add_dialog()
    dlg.show()

    # Allow any QTimer-based sizing logic to run (main.py uses QTimer.singleShot)
    from PySide6.QtTest import QTest

    QTest.qWait(150)
    qapp.processEvents()

    w = int(dlg.width())
    h = int(dlg.height())

    # Expected size: portrait baseline from settings.bounds(), swapped into landscape.
    exp_portrait_w = 720
    exp_portrait_h = 1280
    try:
        from settings import bounds

        b = bounds()
        if isinstance(b, dict):
            tup = None
            if isinstance(b.get("window"), (list, tuple)) and len(b.get("window")) >= 2:
                tup = b.get("window")
            elif isinstance(b.get("screen"), (list, tuple)) and len(b.get("screen")) >= 2:
                tup = b.get("screen")
            if tup is not None:
                exp_portrait_w = int(tup[0])
                exp_portrait_h = int(tup[1])
    except Exception:
        pass

    exp_w = max(exp_portrait_w, exp_portrait_h)
    exp_h = min(exp_portrait_w, exp_portrait_h)

    # Geometry contract: dialog must match the portrait baseline swapped into landscape.
    assert (w, h) == (exp_w, exp_h), f"Expected {exp_w}x{exp_h} dialog, got {w}x{h}"

    # Tighten: minimum size should not allow smaller than the target.
    assert int(dlg.minimumWidth()) >= exp_w
    assert int(dlg.minimumHeight()) >= exp_h

    dlg.close()