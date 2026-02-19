"""
CategoryManager preview/confirmation extracted for maintainability.

Handles entry preview building and save confirmation dialogs.
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox
from ui.ui_services import set_visible
from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerPreviewConfirmController:
    """Manages preview and confirmation for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        self._dlg = CategoryManagerDialogAdapter(dialog)

    def build_add_entry_preview(self) -> dict:
        """Build a stable preview payload for the pending add/edit entry (no mutation)."""
        try:
            from ui.category_manager_preview_builder import AddEntryPreviewBuilder
            preview_obj = AddEntryPreviewBuilder.build(self._dlg.dialog)
            return preview_obj.to_payload()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return {}

    def confirm_add_entry(self, preview: dict) -> str:
        """Confirmation dialog for a pending add/edit entry.

        Returns: 'save' | 'edit' | 'cancel'

        Behavior:
          - Save: Commits the entry and clears the form
          - Edit: Returns focus to the form without clearing
          - Cancel: Clears the form and returns focus
        """
        jy = str((preview.get("jyutping") or "")).strip()
        hz = str((preview.get("hanzi") or "")).strip()
        mn = str((preview.get("meaning") or "")).strip()
        cats = preview.get("categories")
        if isinstance(cats, (list, tuple)) and cats:
            cat = ", ".join([str(c).strip() for c in cats if str(c).strip()])
        else:
            cat = str((preview.get("category") or "")).strip()

        msg = QMessageBox(self._dlg.dialog)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("Confirm Entry")
        msg.setText("Review and confirm this entry:")
        msg.setInformativeText(
            f"Jyutping:  {jy}\nHanzi:     {hz}\nMeaning:   {mn}\nCategory:  {cat}"
        )

        btn_save = msg.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        btn_edit = msg.addButton("Edit", QMessageBox.ButtonRole.ActionRole)
        btn_cancel = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

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
        if clicked is btn_cancel:
            return "cancel"
        return "cancel"

    def set_save_button_visible(self, visible: bool) -> None:
        """Show/hide the legacy inline Save button.

        Rule:
          - Hidden by default
          - Shown only when the user chooses 'Edit' from the confirmation dialog
        """
        # Canonical: current implementation uses `self.btn_save`
        btn = self._dlg.get("btn_save")

        # Qt-boundary fallback: objectName lookup
        if btn is None:
            try:
                from PySide6.QtWidgets import QPushButton
                btn = self._dlg.dialog.findChild(QPushButton, "btn_save")
            except (TypeError, AttributeError, RuntimeError):
                btn = None

        if btn is None:
            try:
                from PySide6.QtWidgets import QPushButton
                btn = self._dlg.dialog.findChild(QPushButton, "btnSave")
            except (TypeError, AttributeError, RuntimeError):
                btn = None

        set_visible(btn, visible)
