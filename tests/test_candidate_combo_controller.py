import os
import pytest


def _skip_if_headless_ci() -> None:
    """
    Mirror the project's existing UI-test posture:
    - If PySide6 isn't installed, tests are skipped.
    - If we're clearly in a headless environment without offscreen, skip.
    """
    pytest.importorskip("PySide6")

    # If running in CI/headless, require offscreen to avoid flaky focus/popup behavior.
    # This matches how you run UI tests with QT_QPA_PLATFORM=offscreen.
    if os.environ.get("CI"):
        if os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen":
            pytest.skip("UI test requires QT_QPA_PLATFORM=offscreen in CI/headless")


@pytest.mark.ui
def test_candidate_combo_populate_adds_items_and_sets_visible_true():
    _skip_if_headless_ci()

    from PySide6.QtWidgets import QApplication, QComboBox
    from ui.candidate_combo import CandidateComboController

    app = QApplication.instance() or QApplication([])

    combo = QComboBox()
    combo.setVisible(False)

    ctl = CandidateComboController(combo)

    n = ctl.populate(
        [
            ("風", "reverse_jyut", 1000),
            ("封", "reverse_jyut", 999),
        ]
    )

    assert n == 2
    assert combo.count() == 2
    assert ctl.has_candidates() is True
    assert combo.isVisible() is True


@pytest.mark.ui
def test_candidate_combo_populate_empty_hides_combo_and_returns_zero():
    _skip_if_headless_ci()

    from PySide6.QtWidgets import QApplication, QComboBox
    from ui.candidate_combo import CandidateComboController

    app = QApplication.instance() or QApplication([])

    combo = QComboBox()
    combo.setVisible(True)
    combo.addItem("dummy")

    ctl = CandidateComboController(combo)

    n = ctl.populate([])

    assert n == 0
    assert combo.count() == 0
    assert ctl.has_candidates() is False
    assert combo.isVisible() is False


@pytest.mark.ui
def test_candidate_combo_clear_clears_and_hides():
    _skip_if_headless_ci()

    from PySide6.QtWidgets import QApplication, QComboBox
    from ui.candidate_combo import CandidateComboController

    app = QApplication.instance() or QApplication([])

    combo = QComboBox()
    combo.addItem("風")
    combo.setVisible(True)

    ctl = CandidateComboController(combo)
    ctl.clear()

    assert combo.count() == 0
    assert combo.isVisible() is False
    assert ctl.has_candidates() is False


@pytest.mark.ui
def test_candidate_combo_show_and_focus_does_not_crash_offscreen():
    """
    We do not assert showPopup behavior (can be platform-dependent),
    only that it does not raise and results in focus being requested.
    """
    _skip_if_headless_ci()

    from PySide6.QtWidgets import QApplication, QComboBox
    from ui.candidate_combo import CandidateComboController

    app = QApplication.instance() or QApplication([])

    combo = QComboBox()
    ctl = CandidateComboController(combo)

    ctl.populate([("風", "reverse_jyut", 1000)])

    # Should be best-effort only: no exceptions.
    ctl.show_and_focus()

    # Process events so focus requests can land.
    try:
        app.processEvents()
    except Exception:
        pass

    # Offscreen focus can be quirky; assert only that the widget exists and remains visible.
    assert combo.isVisible() is True


@pytest.mark.ui
def test_candidate_combo_controller_handles_none_combo_safely():
    _skip_if_headless_ci()

    from ui.candidate_combo import CandidateComboController

    ctl = CandidateComboController(None)

    # All are no-ops; should not raise.
    assert ctl.populate([("風", "reverse_jyut", 1000)]) == 0
    assert ctl.has_candidates() is False
    ctl.show_and_focus()
    ctl.clear()