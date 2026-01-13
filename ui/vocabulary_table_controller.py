"""Vocabulary table controller - manages the vocab display table.

Extracts ~800 lines of table logic from category_manager.py.
"""

from __future__ import annotations
from typing import Any, Callable
from dataclasses import dataclass

from ui.widget_utils import WidgetAccessor


@dataclass(frozen=True)
class TableRow:
    """Single row in vocabulary table."""
    hanzi: str
    jyutping: str
    meanings: str
    categories: list[str]

    def to_list(self) -> list[str]:
        """Convert to list for table display."""
        return [
            self.hanzi,
            self.jyutping,
            self.meanings,
            ", ".join(self.categories) if self.categories else ""
        ]


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

    def build_rows(self) -> list[TableRow]:
        """Build all table rows from current vocab/categories.

        Returns:
            List of TableRow objects
        """
        rows = []

        # Build hanzi -> categories mapping
        hz_to_cats: dict[str, list[str]] = {}
        for cat, members in self._categories.items():
            for hz in members:
                if hz not in hz_to_cats:
                    hz_to_cats[hz] = []
                hz_to_cats[hz].append(cat)

        # Build rows
        for hanzi, data in self._vocab.items():
            if not isinstance(data, (list, tuple)) or len(data) < 2:
                continue

            meanings_raw, jyutping = data[0], data[1]

            # Flatten meanings
            meanings_list = []
            if isinstance(meanings_raw, (list, tuple)):
                for item in meanings_raw:
                    if isinstance(item, (list, tuple)):
                        meanings_list.extend(str(x) for x in item if x)
                    else:
                        meanings_list.append(str(item))
            else:
                meanings_list.append(str(meanings_raw))

            meanings = ", ".join(m.strip() for m in meanings_list if m.strip())
            categories = hz_to_cats.get(hanzi, [])

            rows.append(TableRow(
                hanzi=hanzi,
                jyutping=str(jyutping),
                meanings=meanings,
                categories=sorted(categories, key=lambda s: s.lower()),
            ))

        return rows

    def populate(self, *, sort: bool = True) -> None:
        """Populate table from current vocab/categories.

        Args:
            sort: Whether to sort rows (default True)
        """
        self._all_rows = self.build_rows()

        if sort:
            self._all_rows.sort(key=lambda r: (
                r.categories[0].lower() if r.categories else "~",
                r.meanings.lower(),
                r.hanzi,
            ))

        self._apply_filter()

    def _apply_filter(self) -> None:
        """Apply current search filter and update table display."""
        if not self._table:
            return

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
                            self._table.setItem(i, j, QTableWidgetItem(value))
                    except (RuntimeError, AttributeError, ImportError):
                        pass
        except (RuntimeError, AttributeError):
            pass

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
