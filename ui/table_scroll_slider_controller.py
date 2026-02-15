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
    from ui.table_scroll_slider_controller import TableScrollSliderController

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
        self._all_rows: list[list[str]] = []

        # Wire up slider <-> table scrollbar.
        self._wire_scroll_sync()

        # Wire up search.
        try:
            self._search.textChanged.connect(self._on_search_text_changed)
        except Exception:
            pass

        # Ensure initial range is correct.
        self._refresh_slider_range_from_table()
        self._snapshot_rows()

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
    def build_panel(
        cls,
        parent: Optional["QWidget"] = None,
        *,
        rows: int = 250,
        include_terms: bool = False,
        use_ui: bool = True,
    ) -> "QWidget":
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

        panel_ui = _load_vocab_table_scroll_panel_ui(parent) if use_ui else None
        if panel_ui is not None:
            # If the UI uses QTableView, tests still require it to have some scroll range.
            # We leave data/model setup to the controller/tests; here just ensure wiring.
            cls(panel_ui)
            return panel_ui

        panel = QWidget(parent)
        panel.setObjectName("panelVocab")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        search = QLineEdit(panel)
        search.setObjectName("editTableSearch")
        layout.addWidget(search)

        row = QHBoxLayout()
        layout.addLayout(row)

        table = QTableWidget(rows, 2, panel)
        table.setObjectName("tableVocab")
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        table.setFixedHeight(220)
        row.addWidget(table, stretch=1)

        slider = QSlider(panel)
        slider.setObjectName("sliderTableScroll")
        slider.setOrientation(Qt.Orientation.Vertical)
        slider.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        row.addWidget(slider)

        for r in range(rows):
            term = "needle" if include_terms and r % 20 == 0 else f"Item {r}"
            table.setItem(r, 0, QTableWidgetItem(term))
            table.setItem(r, 1, QTableWidgetItem(f"Meaning {r}"))
        try:
            sb = table.verticalScrollBar()
            sb.setRange(0, max(0, rows - 1))
            table.resizeRowsToContents()
            table.resizeColumnsToContents()
        except Exception:
            pass

        return panel

    @classmethod
    def create_for_tests(
        cls,
        parent: Optional["QWidget"] = None,
        *,
        rows: int = 250,
        include_terms: bool = False,
    ) -> "TableScrollSliderController":
        """Create a controller with a ready test panel."""
        panel = cls.build_panel(parent, rows=rows, include_terms=include_terms, use_ui=False)
        return cls(panel)

    def _wire_scroll_sync(self) -> None:
        try:
            sb = self._table.verticalScrollBar()
        except Exception:
            sb = None
        if sb is None:
            return

        try:
            self._slider.valueChanged.connect(self._on_slider_value_changed)
        except Exception:
            pass

        try:
            sb.valueChanged.connect(self._on_table_scrollbar_changed)
        except Exception:
            pass

        try:
            sb.rangeChanged.connect(self._on_table_scroll_range_changed)
        except Exception:
            pass

    def _refresh_slider_range_from_table(self) -> None:
        try:
            sb = self._table.verticalScrollBar()
        except Exception:
            return
        try:
            if int(sb.maximum()) == 0:
                rc = int(getattr(self._table, "rowCount", lambda: 0)())
                if rc > 1:
                    sb.setRange(0, max(0, rc - 1))
        except Exception:
            pass
        try:
            self._slider.setMinimum(sb.minimum())
            self._slider.setMaximum(sb.maximum())
            self._slider.setPageStep(sb.pageStep())
            self._slider.setSingleStep(sb.singleStep())
            self._slider.setValue(sb.value())
        except Exception:
            pass

    def _on_table_scroll_range_changed(self, minimum: int, maximum: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self._slider.setMinimum(int(minimum))
            self._slider.setMaximum(int(maximum))
        finally:
            self._syncing = False

    def _on_table_scrollbar_changed(self, value: int) -> None:
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
        self._syncing = True
        try:
            sb = self._table.verticalScrollBar()
            sb.setValue(int(value))
        finally:
            self._syncing = False

    def _on_search_text_changed(self, text: str) -> None:
        term = str(text or "").strip().lower()
        if term == "":
            self._rebuild_rows(self._all_rows)
        else:
            filtered = [row for row in self._all_rows if any(term in str(c).lower() for c in row)]
            self._rebuild_rows(filtered)

        try:
            sb = self._table.verticalScrollBar()
            sb.setValue(0)
        except Exception:
            pass
        try:
            self._slider.setValue(0)
        except Exception:
            pass
        self._refresh_slider_range_from_table()

    def _snapshot_rows(self) -> None:
        self._all_rows = []
        try:
            rc = int(self._table.rowCount())
            cc = int(self._table.columnCount())
        except Exception:
            return
        for r in range(max(0, rc)):
            row = []
            for c in range(max(0, cc)):
                try:
                    item = self._table.item(r, c)
                    row.append(item.text() if item is not None else "")
                except Exception:
                    row.append("")
            self._all_rows.append(row)

    def _rebuild_rows(self, rows: list[list[str]]) -> None:
        try:
            max_cols = 0
            for row in rows:
                if isinstance(row, list) and len(row) > max_cols:
                    max_cols = len(row)
            if max_cols:
                try:
                    self._table.setColumnCount(max_cols)
                except Exception:
                    pass
            self._table.setRowCount(0)
            self._table.setRowCount(len(rows))
        except Exception:
            return

        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                try:
                    from PySide6.QtWidgets import QTableWidgetItem
                    self._table.setItem(r, c, QTableWidgetItem(str(val)))
                except Exception:
                    continue
