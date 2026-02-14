"""
CategoryManager field reset extracted for maintainability.

Handles clearing and resetting Add/Edit panel fields.
"""

import logging
from typing import TYPE_CHECKING

from ui.widget_utils import WidgetAccessor, SignalBlocker

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerFieldResetController:
    """Manages field clearing and reset for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog

    def clear_add_entry_fields(self) -> None:
        """Clear Add/Edit fields best-effort."""
        WidgetAccessor.clear_text(getattr(self.dialog, "_add_jy", None))
        WidgetAccessor.clear_text(getattr(self.dialog, "_add_hz", None))
        WidgetAccessor.clear_text(getattr(self.dialog, "_add_mn", None))

        try:
            self.dialog._set_notes("", source="auto-default")
        except (TypeError, AttributeError, RuntimeError):
            pass

        WidgetAccessor.set_combo_index(getattr(self.dialog, "_add_cat", None), -1)
        try:
            self.dialog._last_committed_category = ""
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Reset manual-Hanzi state
        try:
            self.dialog._mark_manual_hanzi_mode(False)
        except Exception:
            try:
                self.dialog._manual_hanzi_mode = False
            except Exception:
                pass

        try:
            ctx = getattr(self.dialog, "_add_edit_ctx", None)
        except (TypeError, AttributeError, RuntimeError):
            ctx = None

        if ctx is not None:
            try:
                ctx.manual_hanzi = False
            except Exception:
                pass
            try:
                ctx.hanzi = ""
            except Exception:
                pass
            try:
                ctx.hz_ok = False
            except Exception:
                pass

        # Keep Hanzi field editable
        try:
            hz = getattr(self.dialog, "_add_hz", None)
        except (TypeError, AttributeError, RuntimeError):
            hz = None

        if hz is not None:
            try:
                hz.setPlaceholderText("Auto, after reverse lookup")
            except Exception:
                pass

        # Reset candidate combo
        try:
            combo = getattr(self.dialog, "_cand_combo", None)
        except (TypeError, AttributeError, RuntimeError):
            combo = None

        if combo is not None:
            try:
                combo.setCurrentIndex(-1)
            except Exception:
                pass

        try:
            if callable(getattr(self.dialog, "_update_save_enabled", None)):
                try:
                    fn_gate = getattr(self.dialog, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
        except (TypeError, AttributeError, RuntimeError):
            pass

    def reset_add_panel_pre_validation(self) -> None:
        """Return Add/Edit panel to pre-validation state (placeholders only)."""
        # Clear dependent fields
        try:
            if getattr(self.dialog, "_add_mn", None) is not None:
                self.dialog._add_mn.clear()
        except (TypeError, AttributeError, RuntimeError):
            pass

        try:
            if getattr(self.dialog, "_add_hz", None) is not None:
                self.dialog._add_hz.clear()
                # ALWAYS keep Hanzi field editable
                self.dialog._add_hz.setReadOnly(False)
                self.dialog._add_hz.setPlaceholderText("Auto-filled from candidates or type your own...")
        except (TypeError, AttributeError, RuntimeError):
            pass

        try:
            self.dialog._set_notes("", source="auto-default")
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Reset category selection to placeholder
        try:
            if getattr(self.dialog, "_add_cat", None) is not None:
                try:
                    self.dialog._add_cat.setCurrentIndex(-1)
                except (TypeError, AttributeError, RuntimeError):
                    pass
        except (TypeError, AttributeError, RuntimeError):
            pass
        try:
            self.dialog._last_committed_category = ""
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Hide and clear candidate combobox
        try:
            combo = getattr(self.dialog, "_cand_combo", None)
            if combo is not None:
                with SignalBlocker(combo):
                    try:
                        combo.clear()
                    except (TypeError, AttributeError, RuntimeError):
                        pass
                    try:
                        combo.setVisible(False)
                    except (TypeError, AttributeError, RuntimeError):
                        pass
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Reset intent flags
        try:
            self.dialog._mark_hanzi_committed(False)
        except (TypeError, AttributeError, RuntimeError):
            try:
                self.dialog._hanzi_committed = False
            except (TypeError, AttributeError, RuntimeError):
                pass

        try:
            self.dialog._mark_manual_hanzi_mode(False)
        except (TypeError, AttributeError, RuntimeError):
            try:
                self.dialog._manual_hanzi_mode = False
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Reset SM context best-effort
        ctx = None
        try:
            ctx = getattr(self.dialog, "_add_edit_ctx", None)
        except (TypeError, AttributeError, RuntimeError):
            ctx = None

        if ctx is not None:
            for _k, _v in (
                ("jy_ok", False),
                ("duplicate", None),
                ("hanzi", ""),
                ("hz_ok", False),
                ("manual_hanzi", False),
                ("meaning", ""),
                ("mn_ok", False),
                ("category", ""),
                ("cat_ok", False),
            ):
                try:
                    setattr(ctx, _k, _v)
                except (TypeError, AttributeError, RuntimeError):
                    pass

        try:
            if callable(getattr(self.dialog, "_update_save_enabled", None)):
                try:
                    fn_gate = getattr(self.dialog, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
        except (TypeError, AttributeError, RuntimeError):
            pass
