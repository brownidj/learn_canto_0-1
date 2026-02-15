"""Dialog helpers for main window."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QComboBox

from category_manager import CategoryManagerDialog
from main_helpers import perf_start as _perf_start, perf_end as _perf_end
from services.vocab_loader import load_categories_map as _load_categories_map, commit_vocab_entry


def open_category_manager(
    *,
    window,
    vocab: dict,
    categories_map: dict,
    controller,
    focus_add: bool = False,
) -> dict:
    """Open the Add & Edit dialog and return updated categories_map."""
    vocab_dict = vocab if isinstance(vocab, dict) else {}

    try:
        cats = _load_categories_map()
    except Exception:
        cats = {}

    if isinstance(cats, dict) and cats:
        try:
            setattr(window, "_categories_map", cats)
        except Exception:
            pass
        categories_map = cats
    else:
        try:
            cats = getattr(window, "_categories_map", None)
        except Exception:
            cats = None
        if not isinstance(cats, dict):
            cats = {}

    dlg = CategoryManagerDialog(window, vocab_dict, cats)

    try:
        def _commit_with_dialog(entry: dict):
            return commit_vocab_entry(entry, vocab, categories_map, window, dlg)

        dlg._commit_callback = _commit_with_dialog
    except Exception:
        pass

    try:
        if isinstance(getattr(window, "_char_map", None), dict):
            dlg._char_map = window._char_map
    except Exception:
        pass

    if focus_add:
        try:
            if hasattr(dlg, "_add_jy") and dlg._add_jy is not None:
                dlg._add_jy.setFocus()
        except Exception:
            pass

    _t_exec = _perf_start("CategoryManagerDialog.exec")
    dlg.exec()
    _perf_end("CategoryManagerDialog.exec", _t_exec)

    try:
        cats_after = _load_categories_map()
    except Exception:
        cats_after = {}

    if isinstance(cats_after, dict) and cats_after:
        try:
            setattr(window, "_categories_map", cats_after)
        except Exception:
            pass
        categories_map = cats_after

        try:
            combo_main = window.findChild(QComboBox, "comboCategory")
        except Exception:
            combo_main = None

        if combo_main is not None:
            try:
                sel = combo_main.currentText() or "All"
            except Exception:
                sel = "All"

            try:
                combo_main.blockSignals(True)
                combo_main.clear()
                combo_main.addItem("All")
                for k in sorted((categories_map or {}).keys()):
                    combo_main.addItem(k)
                idx = combo_main.findText(sel)
                if idx >= 0:
                    combo_main.setCurrentIndex(idx)
                else:
                    idx_all = combo_main.findText("All")
                    if idx_all >= 0:
                        combo_main.setCurrentIndex(idx_all)
            except Exception:
                pass
            finally:
                try:
                    combo_main.blockSignals(False)
                except Exception:
                    pass

    try:
        combo = window.findChild(QComboBox, "comboCategory")
        current_cat = combo.currentText() if combo is not None else "All"
    except Exception:
        current_cat = "All"
    controller.apply_category_filter(current_cat)

    return categories_map
