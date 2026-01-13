"""
CategoryManager save/commit logic extracted for maintainability.

Handles save button clicks and commit operations.
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

from PySide6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)


class CategoryManagerSaveCommitController:
    """Manages save/commit operations for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog

    def on_save_clicked(self) -> None:
        """Legacy inline Save button handler.

        This remains the manual-save pathway when the user chooses 'Edit'
        from the Meaning-Enter confirmation flow.

        Best-effort only: never raise from UI callbacks.
        """
        # Check for duplicate Jyutping before proceeding
        try:
            jy, hz, mn, cat = self.dialog._read_add_fields()
            is_duplicate, existing_hanzi = self.dialog._check_duplicate_jyutping(jy)

            if is_duplicate:
                QMessageBox.warning(
                    self.dialog,
                    "Duplicate Jyutping",
                    f"An entry with Jyutping '{jy}' already exists (Hanzi: {existing_hanzi}).\n\n"
                    f"Please use a different Jyutping or edit the existing entry."
                )
                return
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Prefer the historical handler name if present
        try:
            fn = getattr(self.dialog, "_on_add_item_enter", None)
            if callable(fn):
                fn()
                return
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Fall back to other known save entry points
        try:
            fn = getattr(self.dialog, "_save_add_item", None)
            if callable(fn):
                fn()
                return
        except (TypeError, AttributeError, RuntimeError):
            pass

        try:
            fn = getattr(self.dialog, "_do_save", None)
            if callable(fn):
                fn()
                return
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Absolute last resort: do nothing
        return

    def save_add_item(self) -> None:
        """Legacy save entry point shim."""
        try:
            fn = getattr(self.dialog, "_on_add_item_enter", None)
            if callable(fn):
                fn()
        except (TypeError, AttributeError, RuntimeError):
            pass
