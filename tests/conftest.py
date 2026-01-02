def pytest_configure(config):
    config.addinivalue_line("markers", "ui: tests that require a Qt GUI environment")
    config.addinivalue_line("markers", "pure: tests that are pure (no Qt / no external side effects)")


# Ensure Qt widgets are cleaned up after each UI test
import os
import pytest


def _drain_qt_events(app, *, rounds: int = 10, ms: int = 25) -> None:
    """Best-effort event drain to avoid UI-test hangs (bounded)."""
    try:
        from PySide6.QtCore import QEventLoop
    except (ImportError, ModuleNotFoundError):
        return

    if app is None:
        return

    for _ in range(max(1, int(rounds))):
        try:
            app.processEvents(QEventLoop.AllEvents, int(ms))
        except RuntimeError:
            break


@pytest.fixture(autouse=True)
def _qt_ui_cleanup(request):
    """Per-test cleanup for tests marked with @pytest.mark.ui."""
    if "ui" not in request.keywords:
        yield
        return

    try:
        from PySide6.QtWidgets import QApplication
    except (ImportError, ModuleNotFoundError):
        yield
        return

    app = QApplication.instance()
    if app is None:
        yield
        return

    # Run the test.
    yield

    # Close/hide/delete any surviving top-level widgets.
    try:
        widgets = list(QApplication.topLevelWidgets())
    except RuntimeError:
        widgets = []

    for w in widgets:
        if w is None:
            continue
        try:
            w.hide()
        except RuntimeError:
            continue
        try:
            w.close()
        except RuntimeError:
            pass
        try:
            w.deleteLater()
        except RuntimeError:
            pass

    _drain_qt_events(app, rounds=12, ms=25)

    # In offscreen runs, ask the app to quit so the Python process can terminate.
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        try:
            app.closeAllWindows()
        except RuntimeError:
            pass
        try:
            app.quit()
        except RuntimeError:
            pass
        try:
            app.exit(0)
        except RuntimeError:
            pass
        _drain_qt_events(app, rounds=12, ms=25)


@pytest.fixture(scope="session", autouse=True)
def _qt_session_teardown():
    """Final session teardown to ensure Qt does not keep pytest alive."""
    yield

    try:
        from PySide6.QtWidgets import QApplication
    except (ImportError, ModuleNotFoundError):
        return

    app = QApplication.instance()
    if app is None:
        return

    # Only force shutdown for explicit offscreen UI test runs.
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        return

    try:
        app.closeAllWindows()
    except RuntimeError:
        pass

    _drain_qt_events(app, rounds=20, ms=25)

    try:
        app.quit()
    except RuntimeError:
        pass

    try:
        app.exit(0)
    except RuntimeError:
        pass

    _drain_qt_events(app, rounds=20, ms=25)