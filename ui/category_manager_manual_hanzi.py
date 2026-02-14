"""
CategoryManager manual Hanzi mode extracted for maintainability.

Handles user's custom Hanzi entry mode.
"""

import logging
import traceback
from typing import TYPE_CHECKING

from ui.widget_utils import WidgetAccessor

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerManualHanziController:
    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        logger.debug(f"CategoryManagerManualHanziController initialized: {type(dialog)}")

    def enter_manual_mode(self) -> None:
        """Enter manual Hanzi mode (user types their own Hanzi).

        Must not add UI elements; best-effort and never raise.
        """
        try:
            logger.debug("ManualHanzi: button clicked")
            logger.debug(f"Button exists: {hasattr(self.dialog, '_btn_custom_hz')}")
            btn = getattr(self.dialog, '_btn_custom_hz', None)
            logger.debug(f"Button details: {btn}, text={btn.text() if btn else 'N/A'}")

            logger.debug(f"Hanzi input exists: {hasattr(self.dialog, '_add_hz')}")
            hz = getattr(self.dialog, '_add_hz', None)
            logger.debug(f"Hanzi input details: {hz}, readonly={hz.isReadOnly() if hz else 'N/A'}")
        except Exception as e:
            logger.error(f"Error checking dialog attributes: {e}")
            import traceback
            logger.error(traceback.format_exc())

        # Existing method remains the same
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
                # Ensure stable objectName for tests/debugging (CategoryManager may construct widgets without names)
                try:
                    if hasattr(hz, "objectName") and callable(hz.objectName):
                        if not str(hz.objectName() or "").strip() and hasattr(hz, "setObjectName"):
                            hz.setObjectName("editHanzi")
                except Exception:
                    pass

                logger.debug(
                    "ManualHanzi: before editable hz=%r objectName=%r readonly=%s",
                    type(hz),
                    (hz.objectName() if hasattr(hz, "objectName") else ""),
                    (hz.isReadOnly() if hasattr(hz, "isReadOnly") else "?"),
                )

                if hasattr(hz, "setReadOnly"):
                    hz.setReadOnly(False)
                if hasattr(hz, "setEnabled"):
                    hz.setEnabled(True)
                if hasattr(hz, "setPlaceholderText"):
                    hz.setPlaceholderText("Type Hanzi…")

                logger.debug(
                    "ManualHanzi: after editable hz=%r objectName=%r readonly=%s",
                    type(hz),
                    (hz.objectName() if hasattr(hz, "objectName") else ""),
                    (hz.isReadOnly() if hasattr(hz, "isReadOnly") else "?"),
                )
            except (RuntimeError, AttributeError) as e:
                logger.error("Error setting Hanzi editable: %s", e)

        WidgetAccessor.clear_text(hz)

        # Also name Meaning field if it exists (helps downstream focus/lookup)
        try:
            mn = getattr(self.dialog, "_add_mn", None)
        except Exception:
            mn = None
        if mn is not None:
            try:
                if hasattr(mn, "objectName") and callable(mn.objectName):
                    if not str(mn.objectName() or "").strip() and hasattr(mn, "setObjectName"):
                        mn.setObjectName("editMeaning")
            except Exception:
                pass

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
            except Exception as e:
                logger.error(f"Error in save gating: {e}")
