# -----------------------------------------------------------------------------
# category_manager_vocab_display.py
#
# Vocabulary display and table refresh utilities for CategoryManagerDialog.
# Extracted to reduce main dialog file size and improve maintainability.
# -----------------------------------------------------------------------------

import logging
from ui.widget_utils import SignalBlocker

logger = logging.getLogger(__name__)


class CategoryManagerVocabDisplay:
    """Vocabulary display utilities for CategoryManagerDialog.

    Handles:
      - Vocabulary meaning flattening
      - Category dropdown refresh
      - Table refresh orchestration
      - Search filter handling
    """

    @staticmethod
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

    @staticmethod
    def refresh_category_dropdown_from_cats(dialog, *, selected: str = "") -> None:
        """Refresh the Add/Edit category dropdown from the authoritative in-memory map.

        Contract:
          - `_cats` is the single source of truth.
          - `_all_cats` is a sorted view derived from `_cats`.
          - The Add/Edit category combobox items must reflect `_all_cats`.

        Best-effort only: must never raise.
        """
        combo = None
        idx = -1
        try:
            cats_map = getattr(dialog, "_cats", None)
        except (TypeError, AttributeError, RuntimeError):
            cats_map = None

        if not isinstance(cats_map, dict):
            return

        # Rebuild derived list
        try:
            keys = [str(k).strip() for k in cats_map.keys() if str(k).strip()]
        except (TypeError, ValueError):
            keys = []

        try:
            keys = [k for k in keys if k.lower() != "all"]
        except (TypeError, ValueError):
            pass

        if not any((k.lower() == "unassigned") for k in keys):
            keys.append("unassigned")

        try:
            dialog._all_cats = sorted(set(keys), key=lambda s: str(s).lower())
        except (TypeError, ValueError):
            try:
                dialog._all_cats = list(dict.fromkeys(keys))
            except (TypeError, ValueError):
                return

        # Repopulate combobox items
        try:
            combo = getattr(dialog, "_add_cat", None)
        except (TypeError, AttributeError, RuntimeError):
            combo = None

        if combo is None or not hasattr(combo, "clear") or not hasattr(combo, "addItems"):
            return

        with SignalBlocker(combo):
            try:
                combo.clear()
            except (TypeError, AttributeError, RuntimeError):
                pass

            try:
                combo.addItems(dialog._all_cats)
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Preserve selection where possible
        sel = (selected or "").strip()
        if sel:
            try:
                if hasattr(combo, "findText") and int(combo.findText(sel)) < 0 and hasattr(combo, "addItem"):
                    combo.addItem(sel)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass
            try:
                combo.setCurrentText(sel)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                try:
                    idx = int(combo.findText(sel))
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    pass
        else:
            try:
                combo.setCurrentIndex(-1)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

        try:
            combo.blockSignals(False)
        except (TypeError, AttributeError, RuntimeError):
            pass

    @staticmethod
    def refresh_table(dialog) -> None:
        """Refresh vocabulary table display."""
        vocab_table_ctrl = getattr(dialog, "_vocab_table_ctrl", None)
        if vocab_table_ctrl is not None:
            try:
                vocab_table_ctrl.refresh_from_data()
            except (TypeError, AttributeError, RuntimeError):
                pass
        else:
            # Fallback: legacy rebuild if controller not available
            try:
                fn = getattr(dialog, "_rebuild_items_model", None)
                if callable(fn):
                    fn()
            except (TypeError, AttributeError, RuntimeError):
                pass

    @staticmethod
    def on_search_changed(dialog, text: str) -> None:
        """Handle search text change."""
        vocab_table_ctrl = getattr(dialog, "_vocab_table_ctrl", None)
        if vocab_table_ctrl is not None:
            try:
                vocab_table_ctrl.set_search_filter(text)
            except (TypeError, AttributeError, RuntimeError):
                pass
