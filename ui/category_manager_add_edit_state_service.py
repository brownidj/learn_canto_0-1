from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter


class AddEditStateService:
    """Shared Add/Edit state updates for CategoryManager."""

    def __init__(self, dialog_or_adapter):
        if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
            self._dlg = dialog_or_adapter
        else:
            self._dlg = CategoryManagerDialogAdapter(dialog_or_adapter)

    def get_vm(self):
        return self._dlg.get("_add_edit_vm")

    def update_vm(self, **kwargs) -> None:
        vm = self.get_vm()
        if vm is None:
            return
        for key, value in kwargs.items():
            try:
                setattr(vm, key, value)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

    def update_state(self, **kwargs) -> None:
        try:
            self._dlg.call("_update_add_edit_state", **kwargs)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

    def get_state(self):
        try:
            vm = self._dlg.get("_add_edit_vm")
        except (TypeError, AttributeError, RuntimeError):
            vm = None
        if vm is None:
            try:
                from ui.add_edit_view_model import AddEditViewModel
                ctx = self._dlg.get("_add_edit_ctx")
                vm = AddEditViewModel.from_context(ctx)
                self._dlg.set("_add_edit_vm", vm)
            except Exception:
                return None
        return vm

    def sync_ctx(self) -> None:
        try:
            self._dlg.sync_add_edit_ctx()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

    def update_save_enabled(self) -> None:
        try:
            fn_gate = self._dlg.get("_update_save_enabled")
            if callable(fn_gate):
                fn_gate()
        except (TypeError, AttributeError, RuntimeError):
            pass

    def mark_hanzi_committed(self, committed: bool) -> None:
        try:
            ctrl = self._dlg.get("_focus_ctrl")
            if ctrl is not None:
                ctrl.mark_hanzi_committed(bool(committed))
                return
        except (TypeError, AttributeError, RuntimeError):
            pass
        try:
            self._dlg.set("_hanzi_committed", bool(committed))
        except (TypeError, AttributeError, RuntimeError):
            pass
