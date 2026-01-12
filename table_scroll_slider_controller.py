"""table_scroll_slider_controller.py

UI controller for a vocab table panel that includes:
  - a search bar
  - a vertical slider that mirrors the table's vertical scrollbar

This module is intentionally self-contained and must not import `category_manager`
(or any other UI-heavy modules) to avoid circular imports.

Contract (used by UI tests):
  - slider objectName: 'sliderTableScroll'
  - search objectName: 'editTableSearch'
  - table  objectName: 'tableVocab'

The tests import:
    from table_scroll_slider_controller import TableScrollSliderController

UI tests may also call:
    TableScrollSliderController.create_for_tests(...)

and expect the controller to be constructible and to expose the widgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pathlib import Path
from PySide6.QtCore import QFile, QIODevice
from PySide6.QtUiTools import QUiLoader

from PySide6.QtWidgets import QWidget


def _pyside6_or_skip():
    """Import PySide6 lazily so pure tests can import this module safely."""
    try:
        from PySide6.QtCore import Qt  # noqa: F401
        from PySide6.QtWidgets import (  # noqa: F401
            QWidget,
            QLineEdit,
            QSlider,
            QTableWidget,
            QTableView,
            QTableWidgetItem,
            QAbstractItemView,
            QVBoxLayout,
            QHBoxLayout,
            QSizePolicy,
        )
    except Exception as e:  # pragma: no cover
        raise ImportError("PySide6 is required for TableScrollSliderController") from e


def _load_vocab_table_scroll_panel_ui(parent: Optional["QWidget"] = None) -> Optional["QWidget"]:
    """Best-effort load of vocab_table_scroll_panel.ui.

    Returns the loaded QWidget, or None if not available.
    """
    try:
        # Local import to avoid hard dependency in pure contexts.
        from ui_paths import ui_path  # type: ignore
        ui_file = ui_path("vocab_table_scroll_panel.ui")
    except Exception:
        # Fallback: try relative to repo root / current working dir.
        ui_file = str(Path("ui") / "vocab_table_scroll_panel.ui")

    try:
        if not ui_file or not Path(ui_file).exists():
            return None
    except Exception:
        return None

    try:
        qf = QFile(ui_file)
        if not qf.open(QIODevice.OpenModeFlag.ReadOnly):
            return None
        try:
            loader = QUiLoader()
            w = loader.load(qf, parent)
            return w
        finally:
            try:
                qf.close()
            except Exception:
                pass
    except Exception:
        return None


@dataclass
class TableScrollWidgets:
    panel: "QWidget"
    table: object
    slider: object
    search: object


class TableScrollSliderController:
    """Controller that keeps a table, a vertical slider, and a search bar in sync."""

    def __init__(self, panel: "QWidget") -> None:
        _pyside6_or_skip()
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLineEdit, QSlider

        self._panel = panel

        self._table = panel.findChild(object, "tableVocab")
        self._slider = panel.findChild(QSlider, "sliderTableScroll")
        self._search = panel.findChild(QLineEdit, "editTableSearch")

        # Defensive: tests assert widgets exist; keep a clear error if not.
        if self._table is None:
            raise RuntimeError("tableVocab not found")
        if self._slider is None:
            raise RuntimeError("sliderTableScroll not found")
        if self._search is None:
            raise RuntimeError("editTableSearch not found")

        # Note: self._table may be a QTableView (not only QTableWidget).
        # The controller will still bind to verticalScrollBar() accordingly.

        # Slider configuration.
        try:
            self._slider.setOrientation(Qt.Orientation.Vertical)
        except Exception:
            # Some bindings accept int constants.
            self._slider.setOrientation(int(Qt.Orientation.Vertical))

        # Internal guard to prevent recursion.
        self._syncing = False

        # Wire up slider <-> table scrollbar.
        self._wire_scroll_sync()

        # Wire up search.
        try:
            self._search.textChanged.connect(self._on_search_text_changed)
        except Exception:
            pass

        # Ensure initial range is correct.
        self._refresh_slider_range_from_table()

    @property
    def panel(self) -> "QWidget":
        return self._panel

    @property
    def widget(self) -> "QWidget":
        """Back-compat alias for tests.

        UI integration tests expect the controller to expose `.widget`.
        Internally we treat the panel as the controller's root widget.
        """
        return self._panel

    @property
    def table(self):
        return self._table

    @property
    def slider(self):
        return self._slider

    @property
    def search(self):
        return self._search

    @classmethod
    def build_panel(cls, parent: Optional["QWidget"] = None, *, rows: int = 250) -> "QWidget":
        """Build a standalone panel that satisfies the test contract.

        The application may embed this panel inside a larger dialog, but the tests
        can also instantiate it standalone.
        """
        _pyside6_or_skip()
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QWidget,
            QLineEdit,
            QSlider,
            QTableWidget,
            QTableWidgetItem,
            QAbstractItemView,
            QVBoxLayout,
            QHBoxLayout,
            QSizePolicy,
        )

        panel_ui = _load_vocab_table_scroll_panel_ui(parent)
        if panel_ui is not None:
            # If the UI uses QTableView, tests still require it to have some scroll range.
            # We leave data/model setup to the controller/tests; here just ensure wiring.
            cls(panel_ui)
            return panel_ui

        panel = QWidget(parent)

        edit = QLineEdit(panel)
        edit.setObjectName("editTableSearch")
        try:
            edit.setPlaceholderText("Search…")
        except Exception:
            pass

        table = QTableWidget(panel)
        table.setObjectName("tableVocab")
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Jyutping", "Hanzi", "Meaning"])
        try:
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        except Exception:
            pass

        # Populate with deterministic dummy content so scroll exists.
        table.setRowCount(int(rows))
        r = 0
        while r < rows:
            jy = "jy{0}".format(r)
            hz = "字{0}".format(r)
            mn = "meaning {0}".format(r)
            table.setItem(r, 0, QTableWidgetItem(jy))
            table.setItem(r, 1, QTableWidgetItem(hz))
            table.setItem(r, 2, QTableWidgetItem(mn))
            r += 1

        slider = QSlider(panel)
        slider.setObjectName("sliderTableScroll")
        try:
            slider.setOrientation(Qt.Orientation.Vertical)
        except Exception:
            slider.setOrientation(int(Qt.Orientation.Vertical))
        slider.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        # Layout: search on top, then table + slider.
        root = QVBoxLayout(panel)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        root.addWidget(edit)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)
        body.addWidget(table)
        body.addWidget(slider)
        root.addLayout(body)

        # Construct controller to wire behaviour.
        cls(panel)
        return panel

    @classmethod
    def create_for_tests(
        cls,
        *,
        rows: int = 250,
        include_terms: bool = False,
        parent: Optional["QWidget"] = None,
    ) -> "TableScrollSliderController":
        """Factory used by UI integration tests.

        Tests expect:
          - TableScrollSliderController.create_for_tests(...)
          - returned object exposes .panel/.table/.slider/.search

        `include_terms=True` seeds deterministic rows containing common search terms.
        """
        _pyside6_or_skip()
        from PySide6.QtWidgets import QTableWidgetItem

        panel = cls.build_panel(parent, rows=rows)

        # NOTE: build_panel() already constructs a controller instance for wiring,
        # but it does not return it. Create and return our own controller instance.
        ctrl = cls(panel)

        try:
            table = ctrl.table
            if hasattr(table, "setRowCount") and hasattr(table, "setItem"):
                # QTableWidget path (already populated by build_panel fallback)
                pass
            else:
                from PySide6.QtGui import QStandardItem, QStandardItemModel
                model = QStandardItemModel(int(rows), 3)
                model.setHorizontalHeaderLabels(["Jyutping", "Hanzi", "Meaning"])
                rr = 0
                while rr < int(rows):
                    model.setItem(rr, 0, QStandardItem("jy{0}".format(rr)))
                    model.setItem(rr, 1, QStandardItem("字{0}".format(rr)))
                    model.setItem(rr, 2, QStandardItem("meaning {0}".format(rr)))
                    rr += 1
                try:
                    table.setModel(model)
                except Exception:
                    pass
        except Exception:
            pass

        if include_terms:
            try:
                table = ctrl.table
                # Seed a few rows with stable terms so tests can filter reliably.
                # Keep it simple: put terms in the Meaning column.
                if hasattr(table, "setItem"):
                    table.setItem(0, 2, QTableWidgetItem("alpha term"))
                    table.setItem(1, 2, QTableWidgetItem("beta term"))
                    table.setItem(2, 2, QTableWidgetItem("gamma term"))
                else:
                    model = None
                    try:
                        model = table.model()
                    except Exception:
                        model = None
                    if model is not None:
                        try:
                            from PySide6.QtCore import Qt
                            model.setData(model.index(0, 2), "alpha term", Qt.EditRole)
                            model.setData(model.index(1, 2), "beta term", Qt.EditRole)
                            model.setData(model.index(2, 2), "gamma term", Qt.EditRole)
                        except Exception:
                            pass
            except Exception:
                pass

        # Ensure the panel is realized so the table's scroll range is computed.
        # Without showing the widget, Qt often reports a zero scroll maximum.
        try:
            panel.resize(800, 500)
        except Exception:
            pass

        try:
            panel.show()
        except Exception:
            pass

        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        except Exception:
            pass

        # After show/processEvents, refresh the slider range from the table.
        try:
            ctrl._refresh_slider_range_from_table()
        except Exception:
            pass

        return ctrl

    def _wire_scroll_sync(self) -> None:
        """Connect table scrollbar <-> slider in both directions."""
        sb = self._get_table_vscrollbar()
        if sb is None:
            return

        try:
            sb.rangeChanged.connect(self._on_table_scroll_range_changed)
        except Exception:
            pass

        try:
            sb.valueChanged.connect(self._on_table_scroll_value_changed)
        except Exception:
            pass

        try:
            self._slider.valueChanged.connect(self._on_slider_value_changed)
        except Exception:
            pass

    def _get_table_vscrollbar(self):
        try:
            fn = getattr(self._table, "verticalScrollBar", None)
        except Exception:
            fn = None
        if callable(fn):
            try:
                return fn()
            except Exception:
                return None
        return None

    def _refresh_slider_range_from_table(self) -> None:
        sb = self._get_table_vscrollbar()
        if sb is None:
            return
        try:
            self._slider.setMinimum(int(sb.minimum()))
            self._slider.setMaximum(int(sb.maximum()))
            self._slider.setSingleStep(max(1, int(sb.singleStep())))
            self._slider.setPageStep(max(1, int(sb.pageStep())))
            self._slider.setValue(int(sb.value()))
        except Exception:
            # Best-effort: if any of these fail, do not crash UI.
            pass

    def _on_table_scroll_range_changed(self, _min: int, _max: int) -> None:
        if self._syncing:
            return
        self._refresh_slider_range_from_table()

    def _on_table_scroll_value_changed(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self._slider.setValue(int(value))
        finally:
            self._syncing = False

    def _on_slider_value_changed(self, value: int) -> None:
        if self._syncing:
            return
        sb = self._get_table_vscrollbar()
        if sb is None:
            return
        self._syncing = True
        try:
            sb.setValue(int(value))
        finally:
            self._syncing = False

    def _on_search_text_changed(self, text: str) -> None:
        """Filter rows (minimum contract) and reset scroll to top."""
        # We support both QTableWidget and QTableView-like APIs.
        needle = (text or "").strip().lower()

        # If table supports row hiding (QTableWidget/QTableView), we do that.
        row_count = 0
        try:
            row_count = int(self._table.rowCount())
        except Exception:
            row_count = 0

        if row_count > 0:
            r = 0
            while r < row_count:
                show = True
                if needle:
                    show = self._row_matches(r, needle)
                try:
                    self._table.setRowHidden(int(r), not bool(show))
                except Exception:
                    pass
                r += 1

        # Reset scroll to top and refresh slider.
        sb = self._get_table_vscrollbar()
        if sb is not None:
            self._syncing = True
            try:
                sb.setValue(int(sb.minimum()))
                self._slider.setValue(int(sb.minimum()))
            finally:
                self._syncing = False

        self._refresh_slider_range_from_table()

    def _row_matches(self, row: int, needle: str) -> bool:
        """Return True if any visible cell in the row contains needle."""
        # QTableWidget
        try:
            col_count = int(self._table.columnCount())
        except Exception:
            col_count = 0

        c = 0
        while c < col_count:
            try:
                it = self._table.item(int(row), int(c))
            except Exception:
                it = None
            try:
                s = "" if it is None else str(it.text() or "")
            except Exception:
                s = ""
            if needle in s.lower():
                return True
            c += 1
        return False