"""
CategoryManager save/commit logic extracted for maintainability.

Handles save button clicks and commit operations.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

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
