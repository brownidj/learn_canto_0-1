"""Layout helpers for vocab table."""

from __future__ import annotations


def apply_column_widths(table) -> None:
    if not table:
        return
    try:
        from PySide6.QtWidgets import QHeaderView
        from PySide6.QtCore import QTimer
    except Exception:
        QHeaderView = None
        QTimer = None
    try:
        header = getattr(table, "horizontalHeader", None)
        header = header() if callable(header) else None
        if header is None:
            return
        if QHeaderView is not None and hasattr(header, "setSectionResizeMode"):
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(False)
        try:
            viewport = getattr(table, "viewport", None)
            viewport = viewport() if callable(viewport) else None
            width = int(viewport.width()) if viewport is not None else int(table.width())
        except Exception:
            width = int(table.width()) if hasattr(table, "width") else 0
        if width <= 0:
            if QTimer is not None:
                QTimer.singleShot(0, lambda: apply_column_widths(table))
            return
        w_hz = int(width * 0.20)
        w_jy = int(width * 0.15)
        w_mn = int(width * 0.40)
        w_cat = max(0, width - (w_hz + w_jy + w_mn))
        w_cat = w_cat + 80
        w_hz = max(w_hz, 120)
        w_jy = max(w_jy, 120)
        w_mn = max(w_mn, 240)
        w_cat = max(w_cat, 220)
        try:
            header.resizeSection(0, w_hz)
            header.resizeSection(1, w_jy)
            header.resizeSection(2, w_mn)
            header.resizeSection(3, w_cat)
        except Exception:
            pass
    except Exception:
        pass


__all__ = ["apply_column_widths"]
