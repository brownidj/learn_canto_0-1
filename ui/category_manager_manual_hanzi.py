"""
CategoryManager manual Hanzi mode extracted for maintainability.

Handles user's custom Hanzi entry mode.
"""

import logging
from typing import TYPE_CHECKING

from ui.widget_utils import WidgetAccessor

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerManualHanziController:
    """Manages manual Hanzi entry mode for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog

    def enter_manual_mode(self) -> None:
        """Enter manual Hanzi mode (user types their own Hanzi).

        Must not add UI elements; best-effort and never raise.
        """
        try:
            logger.debug("ManualHanzi: button clicked")
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Set mode flag
        try:
            self.dialog._manual_hanzi_mode = True
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Clear any existing auto-selected Hanzi
        try:
            self.dialog._mark_hanzi_committed(False)
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Update context
        try:
            ctx = getattr(self.dialog, "_add_edit_ctx", None)
        except (TypeError, AttributeError, RuntimeError):
            ctx = None

        if ctx is not None:
            try:
                ctx.manual_hanzi = True
            except (TypeError, AttributeError, RuntimeError):
                pass
            try:
                ctx.hanzi = ""
            except (TypeError, AttributeError, RuntimeError):
                pass
            try:
                ctx.hz_ok = False
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Make Hanzi field editable
        hz = getattr(self.dialog, "_add_hz", None)
        if hz is not None:
            try:
                hz.setReadOnly(False)
                hz.setPlaceholderText("Type Hanzi…")
            except (RuntimeError, AttributeError):
                pass
        WidgetAccessor.clear_text(hz)

        # Hide candidate combo
        combo = getattr(self.dialog, "_cand_combo", None)
        WidgetAccessor.set_visible(combo, False)
        WidgetAccessor.set_combo_index(combo, -1)

        # Focus Hanzi for typing
        try:
            self.dialog._focus_hanzi(select_all=True)
        except (TypeError, AttributeError, RuntimeError):
            try:
                if hz is not None and hasattr(hz, "setFocus"):
                    hz.setFocus()
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Refresh Save gating
        try:
            fn_gate = getattr(self.dialog, "_update_save_enabled", None)
        except (TypeError, AttributeError, RuntimeError):
            fn_gate = None

        if callable(fn_gate):
            try:
                fn_gate()
            except Exception:
                pass
