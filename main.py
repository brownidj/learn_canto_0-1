"""Thin application entrypoint."""

from __future__ import annotations

from app.bootstrap import configure_logging, load_one
from app.debug_ui import load_add_item_ui as _load_add_item_ui_impl
from app.main_window import run
from app.test_helpers import load_add_dialog as _load_add_dialog_impl

__all__ = ["_load_add_dialog", "_load_add_item_ui", "load_one"]


def _load_add_dialog(parent=None):
    return _load_add_dialog_impl(parent)


def _load_add_item_ui(parent=None):
    return _load_add_item_ui_impl(parent)


if __name__ == "__main__":
    configure_logging()
    raise SystemExit(run())
