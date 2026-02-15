"""Vocabulary display utilities for CategoryManagerDialog."""

from __future__ import annotations

from ui.category_manager_vocab_categories import CategoryManagerVocabCategories
from ui.category_manager_vocab_search import CategoryManagerVocabSearch
from ui.category_manager_vocab_table import CategoryManagerVocabTable


def flatten_vocab_meanings(raw_meanings) -> list[str]:
    """Flatten vocab meanings into a simple list of non-empty strings.

    The vocab store may contain meanings as a list of lists, or a flat list.
    This helper is intentionally conservative and never raises.
    """
    out: list[str] = []
    try:
        if isinstance(raw_meanings, (list, tuple)):
            for item in raw_meanings:
                if isinstance(item, (list, tuple)):
                    for sub in item:
                        try:
                            s = str(sub or "").strip()
                        except (TypeError, ValueError):
                            s = ""
                        if s:
                            out.append(s)
                else:
                    try:
                        s = str(item or "").strip()
                    except (TypeError, ValueError):
                        s = ""
                    if s:
                        out.append(s)
        else:
            try:
                s = str(raw_meanings or "").strip()
            except (TypeError, ValueError):
                s = ""
            if s:
                out.append(s)
    except (TypeError, ValueError):
        return out

    return out


def refresh_category_dropdown_from_cats(dialog, *, selected: str = "") -> None:
    """Refresh the Add/Edit category dropdown from the authoritative in-memory map."""
    CategoryManagerVocabCategories.refresh_category_dropdown_from_cats(dialog, selected=selected)


def refresh_table(dialog) -> None:
    """Refresh vocabulary table display."""
    CategoryManagerVocabTable.refresh_table(dialog)


def on_search_changed(dialog, text: str) -> None:
    """Handle search text change."""
    CategoryManagerVocabSearch.on_search_changed(dialog, text)
