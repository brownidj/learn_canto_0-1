from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_focus_service import CategoryManagerFocusService
from ui.category_manager_ui_services import CategoryManagerUIService


class AddEditUIActions:
    """UI actions for Add/Edit handlers (preview, focus, reset, commit)."""

    def __init__(self, dialog_or_adapter):
        if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
            self._dlg = dialog_or_adapter
        else:
            self._dlg = CategoryManagerDialogAdapter(dialog_or_adapter)
        self._ui = CategoryManagerUIService(self._dlg)
        self._focus = CategoryManagerFocusService(self._dlg)

    def get_jyutping_text(self) -> str:
        return self._ui.get_text("add_jy")

    def set_jyutping_text(self, text: str) -> None:
        self._ui.set_text("add_jy", text)

    def focus_category(self, *, show_popup: bool = True, select_all: bool = True) -> None:
        self._focus.apply_focus_policy(
            target="cat",
            reason="jyut_committed",
            user_action=True,
            show_popup=bool(show_popup),
            select_all=bool(select_all),
        )

    def focus_meaning(self, *, select_all: bool = True) -> None:
        self._ui.focus_meaning(select_all=select_all)

    def focus_jyutping(self, *, select_all: bool = True) -> None:
        self._ui.focus_jyutping(select_all=select_all)

    def warn_duplicate_jyutping(self, jy: str) -> None:
        try:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self._dlg.dialog,
                "Duplicate Jyutping",
                f'The Jyutping "{jy}" already exists in your vocabulary.\n\nPlease edit the Jyutping and try again.',
            )
        except (TypeError, AttributeError, RuntimeError, ValueError, ImportError):
            pass
        self.focus_jyutping(select_all=True)

    def update_save_enabled(self) -> None:
        self._dlg.update_save_enabled()

    def clear_add_entry_fields(self) -> None:
        try:
            self._dlg.get("_field_reset").clear_add_entry_fields()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

    def reset_to_initial_state(self) -> None:
        try:
            self._dlg.get("_field_reset").reset_to_initial_state()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            self.clear_add_entry_fields()

    def build_preview(self) -> dict:
        try:
            preview_ctrl = self._dlg.get("_preview_confirm")
            return preview_ctrl.build_add_entry_preview() if preview_ctrl is not None else {}
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return {}

    def confirm_preview(self, preview: dict) -> str:
        try:
            preview_ctrl = self._dlg.get("_preview_confirm")
            return preview_ctrl.confirm_add_entry(preview) if preview_ctrl is not None else "cancel"
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return "cancel"

    def commit_payload(self, payload: dict) -> bool:
        committed = False
        cb = self._dlg.get("_commit_callback")
        if callable(cb):
            try:
                cb(payload)
                committed = True
            except (TypeError, AttributeError, RuntimeError, ValueError):
                committed = False
        if not committed:
            try:
                save_ctrl = self._dlg.get("_save_commit")
                if save_ctrl is not None:
                    save_ctrl.on_save_clicked()
                    committed = True
            except (TypeError, AttributeError, RuntimeError, ValueError):
                committed = False
        return committed
