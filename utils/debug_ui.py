"""
Debug utilities for UI layout introspection.

This module contains tools for debugging Qt widget layouts, size policies,
and geometry. These are only used during development/debugging and should
not affect production runtime.
"""
import logging
import os

from PySide6.QtWidgets import QWidget, QLayout
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)


def dump_layout_tree(widget: QWidget, indent: int = 0):
    """Print the widget/layout hierarchy with size policies and geometries.

    This is a diagnostic tool for understanding Qt layout behavior.

    Args:
        widget: Root widget to inspect
        indent: Current indentation level (for recursive calls)
    """
    sp = widget.sizePolicy()
    try:
        geo = widget.geometry()
        geo_str = f"{geo.width()}x{geo.height()}@{geo.x()},{geo.y()}"
    except Exception:
        geo_str = "n/a"

    logger.debug(
        "%s[%s] name=%r policy=%s/%s min=%sx%s max=%sx%s geo=%s",
        "  " * indent,
        widget.metaObject().className(),
        widget.objectName(),
        sp.horizontalPolicy(),
        sp.verticalPolicy(),
        widget.minimumWidth(),
        widget.minimumHeight(),
        widget.maximumWidth(),
        widget.maximumHeight(),
        geo_str,
    )

    lay = widget.layout()
    if isinstance(lay, QLayout):
        logger.debug(
            "%s  <layout %s name=%r margin=%s spacing=%s>",
            "  " * indent,
            type(lay).__name__,
            getattr(lay, "objectName", lambda: "")(),
            lay.contentsMargins(),
            lay.spacing(),
        )
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item is None:
                continue
            if item.widget():
                dump_layout_tree(item.widget(), indent + 2)
            elif item.layout():
                logger.debug("%s  <sublayout %s>", "  " * (indent + 1), type(item.layout()).__name__)
                sub = item.layout()
                for j in range(sub.count()):
                    subitem = sub.itemAt(j)
                    if subitem and subitem.widget():
                        dump_layout_tree(subitem.widget(), indent + 3)
    else:
        # Find child widgets
        _opts = None
        try:
            from PySide6.QtCore import Qt as _Qt
            _opt = getattr(_Qt, "FindChildOption", None)
            if _opt is not None:
                _opts = getattr(_opt, "FindDirectChildrenOnly", None)
                if _opts is None:
                    _opts = getattr(_opt, "FindChildrenRecursively", None)
        except Exception:
            _opts = None

        if _opts is None:
            for ch in widget.findChildren(QWidget):
                dump_layout_tree(ch, indent + 1)
        else:
            for ch in widget.findChildren(QWidget, options=_opts):
                dump_layout_tree(ch, indent + 1)


def should_skip_debug_introspection() -> bool:
    """Check if we should skip heavy debug introspection.

    Returns True if:
    - Running in offscreen mode
    - Running in pytest
    - CI environment

    Returns:
        True if debug introspection should be skipped
    """
    try:
        if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
            return True
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return True
        if os.environ.get("CI"):
            return True
    except Exception:
        pass
    return False
