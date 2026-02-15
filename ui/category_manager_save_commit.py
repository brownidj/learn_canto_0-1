"""
CategoryManager save/commit logic extracted for maintainability.

Handles save button clicks and commit operations.
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox
from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

from PySide6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)


class CategoryManagerSaveCommitController:
    """Manages save/commit operations for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        self._dlg = CategoryManagerDialogAdapter(dialog)

    def on_save_clicked(self) -> None:
        """Legacy inline Save button handler.

        This remains the manual-save pathway when the user chooses 'Edit'
        from the Meaning-Enter confirmation flow.

        Best-effort only: never raise from UI callbacks.
        """
        # Check for duplicate Jyutping before proceeding
        try:
            from ui.category_manager_helpers import CategoryManagerHelpers
            from domain.duplicate_detection import find_duplicate_jyutping
            jy, _hz, _mn, _cat = CategoryManagerHelpers.read_add_fields(self.dialog)()
            vocab = self._dlg.get("_vocab")
            is_duplicate, existing_hanzi = find_duplicate_jyutping(
                vocab if isinstance(vocab, dict) else {},
                jy,
            )

            if is_duplicate:
                QMessageBox.warning(
                    self._dlg.dialog,
                    "Duplicate Jyutping",
                    f"An entry with Jyutping '{jy}' already exists (Hanzi: {existing_hanzi}).\n\n"
                    f"Please use a different Jyutping or edit the existing entry."
                )
                return
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Prefer the historical handler name if present
        try:
            fn = self._dlg.get("_on_add_item_enter")
            if callable(fn):
                fn()
                return
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Fall back to other known save entry points
        try:
            fn = self._dlg.get("_save_add_item")
            if callable(fn):
                fn()
                return
        except (TypeError, AttributeError, RuntimeError):
            pass

        try:
            fn = self._dlg.get("_do_save")
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
            fn = self._dlg.get("_on_add_item_enter")
            if callable(fn):
                fn()
        except (TypeError, AttributeError, RuntimeError):
            pass
