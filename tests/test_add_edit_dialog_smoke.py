import pytest
from PySide6.QtWidgets import QApplication, QDialog, QGroupBox


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _load_add_dialog():
    import main
    dlg = main._load_add_item_ui(parent=None)
    assert isinstance(dlg, QDialog)
    return dlg


@pytest.mark.ui
def test_add_edit_dialog_smoke(qapp):
    dlg = _load_add_dialog()
    dlg.show()

    # These objectNames are relied on elsewhere in the app
    assert dlg.findChild(QGroupBox, "groupEntry") is not None
    assert dlg.findChild(QGroupBox, "groupHanzi") is not None

    dlg.close()