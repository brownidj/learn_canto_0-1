"""Layout helpers for vocab table."""

from __future__ import annotations

from typing import Optional


def install_column_width_resizer(table) -> None:
    if not table:
        return
    try:
        from PySide6.QtCore import QObject, QEvent, QTimer
    except Exception:
        return

    # Avoid multiple installs.
    if getattr(table, "_column_width_resizer", None) is not None:
        return

    class _TableResizeFilter(QObject):
        def eventFilter(self, obj, event) -> bool:
            try:
                if event.type() == QEvent.Type.Resize:
                    apply_column_widths(table, _defer=False)
            except Exception:
                pass
            return False

    try:
        viewport = table.viewport() if hasattr(table, "viewport") else None
    except Exception:
        viewport = None
    target = viewport if viewport is not None else table
    try:
        filt = _TableResizeFilter(target)
        target.installEventFilter(filt)
        setattr(table, "_column_width_resizer", filt)
    except Exception:
        pass

    # Rebalance after manual header drags.
    try:
        header = getattr(table, "horizontalHeader", None)
        header = header() if callable(header) else None
        if header is None:
            return
        if getattr(table, "_column_width_header_hook", False):
            return

        def _on_section_resized(*_args):
            if getattr(table, "_column_width_rebalance", False):
                return
            setattr(table, "_column_width_rebalance", True)

            def _rebalance() -> None:
                try:
                    apply_column_widths(table, _defer=False)
                finally:
                    try:
                        setattr(table, "_column_width_rebalance", False)
                    except Exception:
                        pass

            QTimer.singleShot(120, _rebalance)

        try:
            header.sectionResized.connect(_on_section_resized)
            setattr(table, "_column_width_header_hook", True)
        except Exception:
            pass
    except Exception:
        pass


def apply_column_widths(table, *, _defer: bool = True) -> None:
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
                QTimer.singleShot(0, lambda: apply_column_widths(table, _defer=False))
            return
        w_hz = int(width * 0.10)
        w_jy = int(width * 0.15)
        w_mn = int(width * 0.45)
        w_cat = max(0, width - (w_hz + w_jy + w_mn))
        try:
            header.resizeSection(0, w_hz)
            header.resizeSection(1, w_jy)
            header.resizeSection(2, w_mn)
            header.resizeSection(3, w_cat)
        except Exception:
            pass
        if _defer and QTimer is not None:
            try:
                if not getattr(table, "_defer_column_widths", False):
                    setattr(table, "_defer_column_widths", True)
                    def _later() -> None:
                        try:
                            setattr(table, "_defer_column_widths", False)
                        except Exception:
                            pass
                        apply_column_widths(table, _defer=False)
                    QTimer.singleShot(0, _later)
                    QTimer.singleShot(60, _later)
            except Exception:
                pass
    except Exception:
        pass


__all__ = ["apply_column_widths", "install_column_width_resizer"]
