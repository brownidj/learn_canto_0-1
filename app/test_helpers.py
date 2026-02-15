"""Test helpers for main application."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget

from app.bootstrap import ensure_qt_app
from persistence.categories_store import load_categories as _load_categories
from services.vocab_loader import load_vocab_from_unified_yaml as _load_vocab_from_unified_yaml
from category_manager import CategoryManagerDialog


def load_add_dialog(parent: Optional[QWidget] = None) -> CategoryManagerDialog:
    """Create and return the Add/Edit dialog (CategoryManagerDialog) for tests."""
    ensure_qt_app()

    try:
        vocab_dict, vocab_categories_map = _load_vocab_from_unified_yaml()
    except Exception:
        vocab_dict, vocab_categories_map = {}, {}

    cats_map = None
    try:
        cats_map = _load_categories()
    except Exception:
        cats_map = None

    if not isinstance(cats_map, dict) or not cats_map:
        cats_map = vocab_categories_map if isinstance(vocab_categories_map, dict) else {}

    return CategoryManagerDialog(parent, vocab_dict if isinstance(vocab_dict, dict) else {}, cats_map)
