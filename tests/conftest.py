import os

import pytest


def _is_ui_run(config) -> bool:
    """Return True when pytest is explicitly running the UI-marked suite.

    This is intentionally conservative: it only returns True when the `ui`
    token is present in the mark expression, which matches `pytest -m ui`.
    """
    try:
        markexpr = getattr(getattr(config, "option", None), "markexpr", "") or ""
    except Exception:
        markexpr = ""

    tokens = {t.strip() for t in markexpr.replace("(", " ").replace(")", " ").split() if t.strip()}
    return "ui" in tokens


def pytest_configure(config):
    config.addinivalue_line("markers", "ui: tests that require a Qt GUI environment")
    config.addinivalue_line("markers", "pure: tests that are pure (no Qt / no external side effects)")

    # Deterministic headless configuration for explicit UI runs.
    # Never override a user/CI-provided QT_QPA_PLATFORM.
    if _is_ui_run(config):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, int(ms))
        except RuntimeError:
            break


@pytest.fixture(scope="session", autouse=True)
def _qt_session_app(request):
    """Create a QApplication only when running UI tests (or explicit headless UI runs).

    Key point: we do NOT call app.quit()/exit() in teardown because that has proven
    crash-prone under macOS + Qt headless platforms (offscreen/minimal).
    """
    config = getattr(request, "config", None)

    platform = os.environ.get("QT_QPA_PLATFORM")
    running_ui = _is_ui_run(config) if config is not None else False

    # If this is not a UI run and no headless platform is requested, do nothing.
    if (not running_ui) and (not platform):
        yield
        return

    try:
        from PySide6.QtWidgets import QApplication
    except (ImportError, ModuleNotFoundError):
        yield
        return

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    yield

    # Session teardown: close windows and drain events, but do not quit/exit.
    try:
        app.closeAllWindows()
    except RuntimeError:
        pass

    _drain_qt_events(app, rounds=30, ms=25)


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

    _drain_qt_events(app, rounds=15, ms=25)


def pytest_sessionfinish(session, exitstatus):
    """Work around macOS Qt-for-Python teardown segfaults in headless UI runs.

    Symptom: tests pass, then the interpreter segfaults while unloading Qt/Shiboken.
    Mitigation: once pytest has finished and printed results, terminate the process
    immediately, preserving the computed exit status.

    Scope: ONLY when running the UI-marked suite (pytest -m ui).
    """
    try:
        config = getattr(session, "config", None)
    except Exception:
        config = None

    if config is None:
        return

    if not _is_ui_run(config):
        return

    # Bypass fragile native teardown paths (Qt/Shiboken) while keeping accurate exit codes.
    # Note: os._exit avoids atexit handlers and interpreter finalization.
    os._exit(int(exitstatus))

import pytest
from pathlib import Path

@pytest.fixture(autouse=True)
def _isolate_categories_yaml(monkeypatch, tmp_path: Path):
    """
    Ensure tests never touch the real data/categories.yaml.
    """
    try:
        import categories_store
    except Exception:
        # If categories_store isn't importable in some test contexts, do nothing.
        return

    test_file = tmp_path / "categories.yaml"

    def _fake_categories_yaml_path(*, project_dir=None):
        return test_file

    # Patch the function *as used by categories_store*.
    monkeypatch.setattr(categories_store, "categories_yaml_path", _fake_categories_yaml_path, raising=True)