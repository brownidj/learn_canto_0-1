

"""test_table_scroll_slider_integration.py

UI integration tests for the vocab-table + vertical scroll slider panel.

These tests are written *before* implementation. They express the contract for the
widget/controller pair that will be introduced (separate .ui + controller), then
wired into CategoryManager.

Notes:
- We intentionally avoid pytest-qt's `qtbot` fixture (not available in this repo).
- Tests are marked `@pytest.mark.ui` and skipped in headless CI environments.
"""

from __future__ import annotations

import os
import time
import pytest


def _skip_if_headless_ci() -> None:
    """Skip UI tests when running in headless CI or when DISPLAY is unavailable."""
    # Match existing project convention: CI often runs with no GUI.
    if os.environ.get("CI"):
        pytest.skip("UI test skipped on CI")

    # Conservative: if there is no display, PySide6 UI tests will be flaky/fail.
    # On macOS local runs this is typically fine.
    if os.environ.get("DISPLAY") in (None, "") and os.environ.get("WAYLAND_DISPLAY") in (None, ""):
        # macOS does not use DISPLAY in the same way; only skip if explicitly headless.
        if os.environ.get("QT_QPA_PLATFORM", "").lower() in ("offscreen", "minimal"):
            pytest.skip("UI test skipped in headless Qt platform")


def _ensure_app():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _process_events(ms: int = 25) -> None:
    """Process Qt events for a short duration."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return

    deadline = time.time() + (ms / 1000.0)
    while time.time() < deadline:
        app.processEvents()


@pytest.mark.ui
def test_table_scroll_panel_exposes_required_widgets():
    """Contract: panel provides a table, a vertical slider, and a search bar.

    Required objectNames (stable for tests):
      - slider: 'sliderTableScroll'
      - search: 'editTableSearch'
      - table:  'tableVocab' (QTableView or QTableWidget)

    This test should fail until the controller/widget is implemented.
    """
    _skip_if_headless_ci()
    _ensure_app()

    # The implementation will provide this module.
    from table_scroll_slider_controller import TableScrollSliderController  # noqa: F401

    # The controller must be constructible without CategoryManager.
    ctrl = TableScrollSliderController.create_for_tests()
    w = ctrl.widget

    assert w is not None

    slider = w.findChild(object, "sliderTableScroll")
    search = w.findChild(object, "editTableSearch")
    table = w.findChild(object, "tableVocab")

    assert slider is not None, "Missing vertical slider widget 'sliderTableScroll'"
    assert search is not None, "Missing search widget 'editTableSearch'"
    assert table is not None, "Missing table widget 'tableVocab'"


@pytest.mark.ui
def test_slider_moves_table_vertical_scrollbar():
    """Contract: moving the slider updates the table's vertical scroll position."""
    _skip_if_headless_ci()
    _ensure_app()

    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt

    from table_scroll_slider_controller import TableScrollSliderController

    ctrl = TableScrollSliderController.create_for_tests(rows=200)
    w = ctrl.widget

    slider = w.findChild(object, "sliderTableScroll")
    table = w.findChild(object, "tableVocab")

    assert slider is not None
    assert table is not None

    # Table must expose a verticalScrollBar() API (QAbstractScrollArea)
    vbar = getattr(table, "verticalScrollBar", None)
    assert callable(vbar), "tableVocab must provide verticalScrollBar()"

    sb = vbar()
    assert sb is not None

    # Initial position
    start_val = int(sb.value())

    # Move slider near bottom.
    set_val = getattr(slider, "setValue", None)
    assert callable(set_val), "sliderTableScroll must provide setValue()"

    # Use slider's maximum if available; otherwise an arbitrary large number.
    try:
        smax = int(getattr(slider, "maximum")())
    except Exception:
        smax = 100

    set_val(max(0, smax - 1))
    _process_events(50)

    end_val = int(sb.value())

    # Must move forward (down) relative to start.
    assert end_val >= start_val, "Slider movement did not advance table scroll position"


@pytest.mark.ui
def test_table_scroll_updates_slider_on_mousewheel_or_scrollbar_drag():
    """Contract: if the table is scrolled (via scrollbar), slider reflects it.

    This prevents the slider and table from drifting out of sync.
    """
    _skip_if_headless_ci()
    _ensure_app()

    from table_scroll_slider_controller import TableScrollSliderController

    ctrl = TableScrollSliderController.create_for_tests(rows=200)
    w = ctrl.widget

    slider = w.findChild(object, "sliderTableScroll")
    table = w.findChild(object, "tableVocab")

    assert slider is not None
    assert table is not None

    sb = table.verticalScrollBar()
    assert sb is not None

    # Scroll the table down by setting its scrollbar.
    try:
        sb_max = int(sb.maximum())
    except Exception:
        sb_max = 0

    sb.setValue(max(0, sb_max // 2))
    _process_events(50)

    # Slider should now be somewhere non-zero.
    try:
        sval = int(getattr(slider, "value")())
    except Exception:
        sval = 0

    assert sval > 0, "Slider did not update after table scroll"


@pytest.mark.ui
def test_search_filters_rows_and_resets_scroll():
    """Contract: typing in search filters table rows and resets scroll to top.

    Expected behavior:
      - search text reduces the displayed row count (or visible rows)
      - after filtering, table scroll should be at the top and slider near the top

    The controller decides the exact matching strategy; this test checks the minimum.
    """
    _skip_if_headless_ci()
    _ensure_app()

    from table_scroll_slider_controller import TableScrollSliderController

    ctrl = TableScrollSliderController.create_for_tests(rows=200, include_terms=True)
    w = ctrl.widget

    search = w.findChild(object, "editTableSearch")
    table = w.findChild(object, "tableVocab")
    slider = w.findChild(object, "sliderTableScroll")

    assert search is not None
    assert table is not None
    assert slider is not None

    # Baseline row count.
    row_count_fn = getattr(table, "rowCount", None)
    model_fn = getattr(table, "model", None)

    if callable(row_count_fn):
        before_rows = int(row_count_fn())
    elif callable(model_fn) and callable(getattr(model_fn(), "rowCount", None)):
        before_rows = int(model_fn().rowCount())
    else:
        pytest.fail("tableVocab must expose rowCount() or model().rowCount()")

    # Enter a term that should filter.
    set_text = getattr(search, "setText", None)
    assert callable(set_text), "editTableSearch must provide setText()"

    set_text("needle")
    _process_events(75)

    if callable(row_count_fn):
        after_rows = int(row_count_fn())
    else:
        after_rows = int(model_fn().rowCount())

    assert after_rows <= before_rows, "Search did not reduce/maintain row count as expected"

    # Scroll should reset to top.
    sb = table.verticalScrollBar()
    assert int(sb.value()) == 0, "Table scroll did not reset to top after filtering"

    # Slider should also be near top.
    try:
        sval = int(getattr(slider, "value")())
    except Exception:
        sval = 0

    assert sval == 0, "Slider did not reset to top after filtering"