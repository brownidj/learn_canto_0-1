"""Application bootstrap helpers."""

from __future__ import annotations

import logging
import sys

from settings import load_all


def configure_logging() -> None:
    """Configure root logging for the app."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("docs/category_manager_debug.log", mode="w"),
        ],
    )
    logging.getLogger("ui.category_manager_signal_wiring").setLevel(logging.DEBUG)
    logging.getLogger("ui.category_manager_manual_hanzi").setLevel(logging.DEBUG)
    logging.getLogger("manual_hanzi_controller").setLevel(logging.DEBUG)


def load_one(key, default=None):
    """Load a single setting via load_all (best-effort)."""
    try:
        cfg = load_all()
        if isinstance(cfg, dict):
            return cfg.get(key, default)
    except Exception:
        pass
    return default


def ensure_qt_app():
    """Ensure a QApplication exists and return it."""
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return None
    try:
        app = QApplication.instance()
    except Exception:
        app = None
    if app is None:
        try:
            app = QApplication([])
        except Exception:
            return None
    return app
