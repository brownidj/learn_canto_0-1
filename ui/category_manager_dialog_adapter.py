from __future__ import annotations


class CategoryManagerDialogAdapter:
    """Stable access surface for CategoryManagerDialog internals."""

    def __init__(self, dialog):
        self._dialog = dialog

    @property
    def dialog(self):
        return self._dialog

    def get(self, name: str, default=None):
        try:
            return getattr(self._dialog, name, default)
        except (TypeError, AttributeError, RuntimeError):
            return default

    def set(self, name: str, value) -> None:
        try:
            setattr(self._dialog, name, value)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def call(self, name: str, *args, **kwargs):
        try:
            fn = getattr(self._dialog, name, None)
        except (TypeError, AttributeError, RuntimeError):
            return None
        if callable(fn):
            try:
                return fn(*args, **kwargs)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                return None
        return None

    def update_add_edit_state(self, **kwargs) -> None:
        self.call("_update_add_edit_state", **kwargs)

    def sync_add_edit_ctx(self) -> None:
        self.call("_sync_add_edit_ctx")

    def update_save_enabled(self) -> None:
        self.call("_update_save_enabled")
