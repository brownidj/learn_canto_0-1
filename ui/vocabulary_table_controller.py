"""Vocabulary table controller - manages the vocab display table."""

from __future__ import annotations
from typing import Any, Callable

from ui.vocab_table_category_editor import make_category_combo_delegate
from ui.vocab_table_layout import apply_column_widths
from ui.vocab_table_rows import TableRow, build_rows_from_vocab
from ui.vocab_table_sorting import sync_header_arrows_from_native


class VocabularyTableController:
    """Controls the vocabulary display table.

    Responsibilities:
    - Populate table from vocab data
    - Handle search/filter
    - Handle sorting
    - Handle row selection
    - Handle category edits

    Does NOT:
    - Mutate vocab/categories directly
    - Handle save/delete operations
    - Know about Add/Edit panel
    """

    def __init__(
        self,
        table: Any,
        vocab: dict[str, Any],
        categories: dict[str, list[str]],
        *,
        on_row_selected: Callable[[str], None] | None = None,
        on_category_changed: Callable[[str, list[str]], None] | None = None,
    ):
        """
        Args:
            table: QTableWidget
            vocab: Vocabulary data (hanzi -> [meanings, jyutping])
            categories: Category memberships (category -> [hanzi...])
            on_row_selected: Called when row selected (with hanzi)
            on_category_changed: Called when category changed (hanzi, new_categories)
        """
        self._table = table
        self._vocab = vocab
        self._categories = categories
        self._on_row_selected = on_row_selected
        self._on_category_changed = on_category_changed

        self._search_filter = ""
        self._all_rows: list[TableRow] = []
        self._sort_enabled = False
        self._sort_column = 0
        self._sort_order = 0
        self._use_native_sort_indicator = False
        self._updating_table = False

        self._wire_sorting()
        self._wire_category_editing()

    def _wire_sorting(self) -> None:
        if not self._table:
            return
        try:
            if hasattr(self._table, "setSortingEnabled"):
                self._table.setSortingEnabled(True)
            header = getattr(self._table, "horizontalHeader", None)
            header = header() if callable(header) else None
            if header is not None and hasattr(header, "sectionClicked"):
                try:
                    header.setSectionsClickable(True)
                    header.setSortIndicatorShown(False)
                except Exception:
                    pass
                header.sectionClicked.connect(self._on_header_clicked)
                self._sort_enabled = True
        except Exception:
            self._sort_enabled = False

    def _on_header_clicked(self, col: int) -> None:
        if not self._table:
            return
        try:
            col_i = int(col)
        except Exception:
            return

        if col_i == 2:
            # Meanings column is not sortable.
            try:
                from PySide6.QtCore import Qt
                order = Qt.SortOrder.AscendingOrder if self._sort_order == 0 else Qt.SortOrder.DescendingOrder
                if hasattr(self._table, "sortItems"):
                    self._table.sortItems(self._sort_column, order)
            except Exception:
                pass
            self._sync_header_arrows_from_native(force_col=self._sort_column, force_order=self._sort_order)
            return

        try:
            header = getattr(self._table, "horizontalHeader", None)
            header = header() if callable(header) else None
            if header is not None:
                self._sort_column = int(header.sortIndicatorSection())
                order = int(header.sortIndicatorOrder())
                self._sort_order = 0 if order == 0 else 1
        except Exception:
            pass

        self._sync_header_arrows_from_native()

    def build_rows(self) -> list[TableRow]:
        """Build all table rows from current vocab/categories."""
        return build_rows_from_vocab(self._vocab, self._categories)

    def populate(self, *, sort: bool = True) -> None:
        """Populate table from current vocab/categories.

        Args:
            sort: Whether to sort rows (default True)
        """
        self._all_rows = self.build_rows()

        if sort:
            self._all_rows.sort(key=lambda r: (
                r.categories[0].lower() if r.categories else "~",
                r.jyutping.lower(),
                r.hanzi,
                r.meanings.lower(),
            ))

        try:
            if hasattr(self._table, "setSortingEnabled"):
                self._table.setSortingEnabled(True)
        except Exception:
            pass

        self._apply_filter()
        self._sync_header_arrows_from_native()
        apply_column_widths(self._table)

    def _sync_header_arrows_from_native(self, *, force_col: int | None = None, force_order: int | None = None) -> None:
        if not self._table:
            return
        self._sort_column, self._sort_order = sync_header_arrows_from_native(
            self._table,
            sort_column=self._sort_column,
            sort_order=self._sort_order,
            force_col=force_col,
            force_order=force_order,
        )

    def ensure_sort_indicator(self) -> None:
        """Public hook for UI builders to re-assert sort indicator after show."""
        self._sync_header_arrows_from_native()

    def _apply_filter(self) -> None:
        """Apply current search filter and update table display."""
        if not self._table:
            return

        try:
            if hasattr(self._table, "setSortingEnabled"):
                self._table.setSortingEnabled(False)
        except Exception:
            pass
        self._updating_table = True

        # Filter rows
        if self._search_filter:
            filter_lower = self._search_filter.lower()
            filtered = [
                r for r in self._all_rows
                if filter_lower in r.hanzi.lower()
                or filter_lower in r.jyutping.lower()
                or filter_lower in r.meanings.lower()
                or any(filter_lower in c.lower() for c in r.categories)
            ]
        else:
            filtered = self._all_rows

        # Update table
        try:
            if hasattr(self._table, "setRowCount"):
                self._table.setRowCount(len(filtered))

            for i, row in enumerate(filtered):
                for j, value in enumerate(row.to_list()):
                    try:
                        if hasattr(self._table, "setItem"):
                            # QTableWidget
                            from PySide6.QtWidgets import QTableWidgetItem
                            item = QTableWidgetItem(value)
                            try:
                                from PySide6.QtCore import Qt
                                if j != 3:
                                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                                else:
                                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                            except Exception:
                                pass
                            self._table.setItem(i, j, item)
                    except (RuntimeError, AttributeError, ImportError):
                        pass
        except (RuntimeError, AttributeError):
            pass
        finally:
            try:
                if hasattr(self._table, "setSortingEnabled"):
                    self._table.setSortingEnabled(True)
            except Exception:
                pass
            self._updating_table = False
        apply_column_widths(self._table)


    def _wire_category_editing(self) -> None:
        if not self._table:
            return
        try:
            delegate = make_category_combo_delegate(self._category_names)
            if delegate is not None:
                self._table.setItemDelegateForColumn(3, delegate)
        except Exception:
            pass
        try:
            from PySide6.QtWidgets import QAbstractItemView
        except Exception:
            QAbstractItemView = None
        if QAbstractItemView is not None:
            try:
                self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
                self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            except Exception:
                pass
            try:
                self._table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
            except Exception:
                try:
                    self._table.setEditTriggers(
                        QAbstractItemView.EditTrigger.EditKeyPressed
                        | QAbstractItemView.EditTrigger.DoubleClicked
                        | QAbstractItemView.EditTrigger.SelectedClicked
                    )
                except Exception:
                    pass
        try:
            sig = getattr(self._table, "itemChanged", None)
            if callable(sig):
                sig.connect(self._on_item_changed)
        except Exception:
            pass
        try:
            sig = getattr(self._table, "cellClicked", None)
            if callable(sig):
                sig.connect(self._on_cell_clicked)
        except Exception:
            pass

    def _on_cell_clicked(self, row: int, col: int) -> None:
        try:
            if int(col) != 3:
                return
        except Exception:
            return
        try:
            item = self._table.item(int(row), 3)
        except Exception:
            item = None
        if item is None:
            return
        try:
            self._table.setCurrentCell(int(row), 3)
        except Exception:
            pass
        try:
            self._table.setFocus()
        except Exception:
            pass
        try:
            self._table.editItem(item)
        except Exception:
            pass

    def _on_item_changed(self, item) -> None:
        if self._updating_table:
            return
        try:
            col = int(item.column())
        except Exception:
            return
        if col != 3:
            return
        try:
            row = int(item.row())
        except Exception:
            return
        try:
            hz_item = self._table.item(row, 0)
            hanzi = hz_item.text() if hz_item is not None else ""
        except Exception:
            hanzi = ""
        if not str(hanzi or "").strip():
            return
        cats = self._parse_categories(item.text())
        if callable(self._on_category_changed):
            try:
                self._on_category_changed(hanzi, cats)
            except Exception:
                pass

    def _parse_categories(self, text: str) -> list[str]:
        raw = str(text or "")
        parts = [p.strip() for p in raw.replace(";", ",").split(",")]
        out = [p for p in parts if p]
        return out

    def _category_names(self) -> list[str]:
        try:
            names = [str(k) for k in self._categories.keys()]
        except Exception:
            names = []
        names = [n for n in names if n.strip()]
        return sorted(names, key=lambda s: s.lower())

    def set_search_filter(self, text: str) -> None:
        """Set search filter text and refresh display.

        Args:
            text: Search text (searches hanzi, jyutping, meanings, categories)
        """
        self._search_filter = (text or "").strip()
        self._apply_filter()

    def get_selected_hanzi(self) -> str | None:
        """Get Hanzi from currently selected row.

        Returns:
            Hanzi string or None if no selection
        """
        if not self._table:
            return None

        try:
            if hasattr(self._table, "currentRow"):
                row = self._table.currentRow()
                if row >= 0 and hasattr(self._table, "item"):
                    item = self._table.item(row, 0)  # Hanzi column
                    if item:
                        return item.text()
        except (RuntimeError, AttributeError):
            pass

        return None

    def refresh_from_data(self) -> None:
        """Refresh table from current vocab/categories data.

        Call this after vocab/categories have been modified externally.
        """
        self.populate(sort=True)

    def clear(self) -> None:
        """Clear all rows from table."""
        if self._table and hasattr(self._table, "setRowCount"):
            try:
                self._table.setRowCount(0)
            except RuntimeError:
                pass


__all__ = [
    "VocabularyTableController",
    "TableRow",
]
