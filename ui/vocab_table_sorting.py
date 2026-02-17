"""Header arrow rendering + sort indicator helpers for vocab table."""

from __future__ import annotations

from typing import Iterable


def sync_header_arrows_from_native(
    table,
    *,
    sort_column: int,
    sort_order: int,
    force_col: int | None = None,
    force_order: int | None = None,
    labels: Iterable[str] = ("Hanzi", "Jyutping", "Meanings", "Categories"),
) -> tuple[int, int]:
    """Sync arrow labels from the table's native sort state.

    Returns updated (sort_column, sort_order).
    """
    if table is None:
        return sort_column, sort_order

    try:
        from PySide6.QtCore import QTimer
    except Exception:
        QTimer = None

    try:
        header = getattr(table, "horizontalHeader", None)
        header = header() if callable(header) else None
        if header is not None:
            try:
                header.setSectionsClickable(True)
                header.setSortIndicatorShown(False)
            except Exception:
                pass
            if force_col is not None and force_order is not None:
                sort_column = int(force_col)
                sort_order = int(force_order)
            else:
                try:
                    sort_column = int(header.sortIndicatorSection())
                    order = int(header.sortIndicatorOrder())
                    sort_order = 0 if order == 0 else 1
                except Exception:
                    pass
        if QTimer is not None and header is not None:
            def _kick():
                try:
                    header.setSortIndicatorShown(False)
                except Exception:
                    pass
            QTimer.singleShot(0, _kick)
            QTimer.singleShot(50, _kick)
            QTimer.singleShot(150, _kick)
    except Exception:
        pass

    apply_header_label_arrows(table, sort_column, sort_order, labels=labels)
    return sort_column, sort_order


def apply_header_label_arrows(
    table,
    sort_column: int,
    sort_order: int,
    *,
    labels: Iterable[str] = ("Hanzi", "Jyutping", "Meanings", "Categories"),
) -> None:
    """Apply ▲/▼ and △/▽ labels to headers."""
    if table is None or not hasattr(table, "horizontalHeaderItem"):
        return
    try:
        asc_active = " \u25B2"
        desc_active = " \u25BC"
        asc_inactive = " \u25B3"
        desc_inactive = " \u25BD"
        try:
            from PySide6.QtWidgets import QTableWidgetItem
        except Exception:
            QTableWidgetItem = None
        for i, label in enumerate(labels):
            item = table.horizontalHeaderItem(i)
            if item is None and QTableWidgetItem is not None:
                try:
                    item = QTableWidgetItem(str(label))
                    table.setHorizontalHeaderItem(i, item)
                except Exception:
                    item = None
            if item is None:
                continue
            suffix = asc_inactive + desc_inactive
            if i == sort_column:
                if sort_order == 0:
                    suffix = asc_active + " " + desc_inactive
                else:
                    suffix = desc_active + " " + asc_inactive
            item.setText(str(label) + suffix)
    except Exception:
        pass


__all__ = ["sync_header_arrows_from_native", "apply_header_label_arrows"]
