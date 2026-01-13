"""
CategoryManager preview/confirmation extracted for maintainability.

Handles entry preview building and save confirmation dialogs.
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox
from ui.widget_utils import WidgetAccessor

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerPreviewConfirmController:
    """Manages preview and confirmation for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog

    def build_add_entry_preview(self) -> dict:
        """Build a stable preview payload for the pending add/edit entry (no mutation)."""
        try:
            from category_manager import AddEntryPreviewBuilder
            preview_obj = AddEntryPreviewBuilder.build(self.dialog)
            return preview_obj.to_payload()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return {}

    def confirm_add_entry(self, preview: dict) -> str:
        """Confirmation dialog for a pending add/edit entry.

        Returns: 'save' | 'edit' | 'cancel'
        """
        jy = str((preview.get("jyutping") or "")).strip()
        hz = str((preview.get("hanzi") or "")).strip()
        mn = str((preview.get("meaning") or "")).strip()
        cat = str((preview.get("category") or "")).strip()

        msg = QMessageBox(self.dialog)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("Confirm entry")
        msg.setText("Save this entry?")
        msg.setInformativeText(
            f"Jyutping: {jy}\nHanzi: {hz}\nMeaning: {mn}\nCategory: {cat}"
        )

        btn_save = msg.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        btn_edit = msg.addButton("Edit", QMessageBox.ButtonRole.ActionRole)

        try:
            msg.setDefaultButton(btn_save)
        except (TypeError, AttributeError, RuntimeError):
            pass

        try:
            msg.exec()
        except (TypeError, AttributeError, RuntimeError):
            return "edit"

        try:
            clicked = msg.clickedButton()
        except (TypeError, AttributeError, RuntimeError):
            clicked = None

        if clicked is btn_save:
            return "save"
        if clicked is btn_edit:
            return "edit"
        return "cancel"

    def set_save_button_visible(self, visible: bool) -> None:
        """Show/hide the legacy inline Save button.

        Rule:
          - Hidden by default
          - Shown only when the user chooses 'Edit' from the confirmation dialog
        """
        # Canonical: current implementation uses `self.btn_save`
        btn = getattr(self.dialog, "btn_save", None)

        # Qt-boundary fallback: objectName lookup
        if btn is None:
            try:
                from PySide6.QtWidgets import QPushButton
                btn = self.dialog.findChild(QPushButton, "btn_save")
            except (TypeError, AttributeError, RuntimeError):
                btn = None

        if btn is None:
            try:
                from PySide6.QtWidgets import QPushButton
                btn = self.dialog.findChild(QPushButton, "btnSave")
            except (TypeError, AttributeError, RuntimeError):
                btn = None

        WidgetAccessor.set_visible(btn, visible)
