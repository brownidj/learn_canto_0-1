from utils import (
    is_category_placeholder,
    save_enabled_gate,
    should_show_custom_hanzi_button,
    prefer_meanings,
)


def test_regression_auto_none_of_these_not_shown_when_candidates_exist():
    assert should_show_custom_hanzi_button(["粉紅", "紅"]) is False


def test_regression_auto_none_of_these_shown_when_no_candidates():
    assert should_show_custom_hanzi_button([]) is True
    assert should_show_custom_hanzi_button(None) is True
    assert should_show_custom_hanzi_button(["", "   "]) is True


def test_regression_wrong_meanings_do_not_overwrite_primary():
    primary = ["now", "for now", "up to now"]
    fallback = ["(onom.) sound of singing, cheering etc", "(phonetic)", "(dialect) to chat"]
    assert prefer_meanings(primary, fallback) == primary


def test_regression_fallback_used_when_primary_empty():
    primary = ["", "  "]
    fallback = ["day"]
    assert prefer_meanings(primary, fallback) == fallback


def test_regression_category_placeholder_leakage_disables_save():
    placeholder = "— choose category —"
    assert is_category_placeholder(placeholder) is True
    assert save_enabled_gate("ng5", "五", ["five"], placeholder) is False

# ------------------------------
# Minimal UI smoke test
# ------------------------------

import os
import pytest


@pytest.mark.ui
def test_category_manager_dialog_smoke_ui():
    """Basic UI smoke test: dialog can be constructed, shown, and closed.

    Run with:
        .venv/bin/python3 -m pytest -q -m ui
    """

    # Skip in likely-headless environments (common on CI)
    if os.environ.get("CI") and not os.environ.get("DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
        pytest.skip("Headless CI environment without a Qt platform")

    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from category_manager import CategoryManagerDialog

    app = QApplication.instance() or QApplication([])

    vocab = {
        "白": [["White"], "baak6"],
    }
    cats = {
        "colors": ["白"],
        "unassigned": [],
    }

    dlg = CategoryManagerDialog(None, vocab_items=vocab, categories_map=cats)

    dlg.show()
    app.processEvents()

    # Key widgets should exist
    assert getattr(dlg, "_add_jy", None) is not None
    assert getattr(dlg, "_add_cat", None) is not None
    assert getattr(dlg, "_add_hz", None) is not None
    assert getattr(dlg, "_cand_combo", None) is not None
    assert getattr(dlg, "btn_save", None) is not None

    dlg.close()
    app.processEvents()