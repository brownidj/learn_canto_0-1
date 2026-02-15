"""Debug UI helpers for add_item dialog."""

from __future__ import annotations

import logging

from PySide6.QtCore import QFile, QIODevice, QTimer
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QGroupBox

from infra.paths import ui_path
from settings import bounds
from utils.debug_ui import dump_layout_tree, should_skip_debug_introspection

logger = logging.getLogger(__name__)


def load_add_item_ui(parent=None) -> QDialog | None:
    path = ui_path("add_item.ui")
    file = QFile(path)
    if not file.exists():
        logger.error("add_item.ui not found at %s", path)
        return None
    if not file.open(QIODevice.OpenModeFlag.ReadOnly):
        logger.error("Cannot open add_item.ui at %s", path)
        return None
    try:
        dlg = QUiLoader().load(file, parent)
        if not isinstance(dlg, QDialog):
            logger.error("add_item.ui root is not a QDialog; got %r", type(dlg))
            return None
        if dlg is None:
            logger.error("QUiLoader returned None for add_item.ui")
            return None

        portrait_w = None
        portrait_h = None
        try:
            b = bounds()
        except Exception:
            b = None

        try:
            if isinstance(b, dict):
                if "window" in b and isinstance(b.get("window"), (list, tuple)):
                    tup = b.get("window")
                    if len(tup) >= 2:
                        portrait_w = int(tup[0])
                        portrait_h = int(tup[1])
                if (portrait_w is None or portrait_h is None) and "screen" in b and isinstance(b.get("screen"),
                                                                                               (list, tuple)):
                    tup = b.get("screen")
                    if len(tup) >= 2:
                        portrait_w = int(tup[0])
                        portrait_h = int(tup[1])
        except Exception:
            portrait_w = None
            portrait_h = None

        if portrait_w is None or portrait_h is None:
            try:
                if parent is not None:
                    portrait_w = int(parent.width())
                    portrait_h = int(parent.height())
            except Exception:
                portrait_w = None
                portrait_h = None

        if portrait_w is None or portrait_h is None:
            try:
                sh = dlg.sizeHint()
                portrait_w = int(sh.width())
                portrait_h = int(sh.height())
            except Exception:
                portrait_w = 600
                portrait_h = 900

        try:
            land_w = 1280
            land_h = 720
        except Exception:
            land_w = 900
            land_h = 600

        def _apply_fixed_add_item_size():
            try:
                dlg.setFixedSize(land_w, land_h)
                dlg.setMinimumSize(land_w, land_h)
                dlg.setMaximumSize(land_w, land_h)
                dlg.resize(land_w, land_h)
                try:
                    dlg.updateGeometry()
                except Exception:
                    pass
                logger.debug(
                    "add_item dialog fixed size -> %dx%d (from portrait %dx%d)",
                    land_w,
                    land_h,
                    int(portrait_w),
                    int(portrait_h),
                )
            except Exception as _e:
                logger.debug("add_item dialog sizing failed: %r", _e)

        _apply_fixed_add_item_size()
        QTimer.singleShot(0, _apply_fixed_add_item_size)
        QTimer.singleShot(50, _apply_fixed_add_item_size)

        _orig_resize = dlg.resizeEvent

        def _dbg_resize(ev):
            logger.debug(
                "RESIZE: dlg %dx%d | entry=%s %dx%d | hanzi=%s %dx%d",
                dlg.width(), dlg.height(),
                getattr(dlg.findChild(QGroupBox, "groupEntry"), "objectName", lambda: "groupEntry")(),
                dlg.findChild(QGroupBox, "groupEntry").width() if dlg.findChild(QGroupBox, "groupEntry") else -1,
                dlg.findChild(QGroupBox, "groupEntry").height() if dlg.findChild(QGroupBox, "groupEntry") else -1,
                getattr(dlg.findChild(QGroupBox, "groupHanzi"), "objectName", lambda: "groupHanzi")(),
                dlg.findChild(QGroupBox, "groupHanzi").width() if dlg.findChild(QGroupBox, "groupHanzi") else -1,
                dlg.findChild(QGroupBox, "groupHanzi").height() if dlg.findChild(QGroupBox, "groupHanzi") else -1,
            )
            return _orig_resize(ev)

        dlg.resizeEvent = _dbg_resize

        def _after_show():
            if should_skip_debug_introspection():
                return

            try:
                import shiboken6  # type: ignore
            except Exception:
                shiboken6 = None

            try:
                if dlg is None:
                    return
                if shiboken6 is not None and hasattr(shiboken6, "isValid"):
                    try:
                        if not shiboken6.isValid(dlg):
                            return
                    except Exception:
                        pass
            except Exception:
                return

            try:
                if not dlg.isVisible():
                    return
            except RuntimeError:
                return
            except Exception:
                pass

            try:
                logger.debug("=== add_item.ui TREE DUMP (after show) ===")
                dump_layout_tree(dlg, 0)
                ge = dlg.geometry()
                logger.debug(
                    "DIALOG size: %dx%d minimum:%dx%d",
                    ge.width(),
                    ge.height(),
                    dlg.minimumWidth(),
                    dlg.minimumHeight(),
                )
            except RuntimeError:
                return

        if not should_skip_debug_introspection():
            QTimer.singleShot(50, _after_show)
        return dlg
    finally:
        file.close()


def debug_open_add_item_dialog(parent):
    dlg = load_add_item_ui(parent)
    if dlg is None:
        return
    dlg.show()
