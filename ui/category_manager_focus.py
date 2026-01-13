"""
CategoryManager focus management extracted for maintainability.

Centralizes all focus movement logic, intent tracking, and policy decisions.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerFocusController:
    """Manages focus movement and intent tracking for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog

    # ---- Intent tracking ----

    def user_has_committed_hanzi(self) -> bool:
        """Check if user has committed Hanzi selection."""
        return bool(getattr(self.dialog, "_hanzi_committed", False))

    def user_is_in_manual_hanzi_mode(self) -> bool:
        """Check if user is in manual Hanzi entry mode."""
        return bool(getattr(self.dialog, "_manual_hanzi_mode", False))

    def mark_hanzi_committed(self, committed: bool = True) -> None:
        """Mark Hanzi as committed by user."""
        try:
            self.dialog._hanzi_committed = bool(committed)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def mark_manual_hanzi_mode(self, enabled: bool = True) -> None:
        """Mark manual Hanzi mode enabled/disabled."""
        try:
            self.dialog._manual_hanzi_mode = bool(enabled)
        except (TypeError, AttributeError, RuntimeError):
            pass

    # ---- Basic focus helpers ----

    def focus_jyutping(self, *, select_all: bool = True) -> None:
        """Focus Jyutping field."""
        from ui.widget_utils import WidgetAccessor
        WidgetAccessor.focus(getattr(self.dialog, "_add_jy", None), select_all=select_all)

    def focus_meanings(self, *, select_all: bool = True) -> None:
        """Focus Meanings field."""
        from ui.widget_utils import WidgetAccessor
        WidgetAccessor.focus(getattr(self.dialog, "_add_mn", None), select_all=select_all)

    def focus_hanzi(self, *, select_all: bool = True) -> None:
        """Focus Hanzi field."""
        from ui.widget_utils import WidgetAccessor
        WidgetAccessor.focus(getattr(self.dialog, "_add_hz", None), select_all=select_all)

    def focus_category(self, *, select_all: bool = True, show_popup: bool = False) -> None:
        """Focus category combobox."""
        ctrl = getattr(self.dialog, "_cat_combo_ctrl", None)
        if ctrl is not None:
            try:
                ctrl.focus(select_all=select_all, show_popup=show_popup)
            except (TypeError, AttributeError, RuntimeError):
                pass

    # ---- Policy-based focus movement ----

    def apply_focus_policy(
        self,
        *,
        target: str,
        reason: str = "",
        user_action: bool = False,
        show_popup: bool = False,
        select_all: bool = True,
    ) -> None:
        """Apply a focus move if permitted by policy.

        target: 'jy' | 'hz' | 'mn' | 'cat'

        IMPORTANT: This method must never be recursed. It only dispatches to concrete helpers.
        """
        from ui.focus_policy import should_steal_focus

        combo = getattr(self.dialog, "_cand_combo", None)

        try:
            _combo_hf = getattr(combo, "hasFocus", None)
            combo_has_focus = bool(combo is not None and callable(_combo_hf) and _combo_hf())
        except (AttributeError, RuntimeError, TypeError):
            combo_has_focus = False

        try:
            view = combo.view() if combo is not None else None
        except (AttributeError, RuntimeError, TypeError):
            view = None

        try:
            _view_hf = getattr(view, "hasFocus", None)
            view_has_focus = bool(view is not None and callable(_view_hf) and _view_hf())
        except (AttributeError, RuntimeError, TypeError):
            view_has_focus = False

        manual_mode = self.user_is_in_manual_hanzi_mode()
        hanzi_committed = self.user_has_committed_hanzi()

        # Support both keyword-rich and minimal positional policy signatures
        try:
            allowed = bool(
                should_steal_focus(
                    reason=reason,
                    user_action=bool(user_action),
                    manual_mode=manual_mode,
                    hanzi_committed=hanzi_committed,
                    combo_has_focus=combo_has_focus,
                    view_has_focus=view_has_focus,
                )
            )
        except TypeError:
            # Positional fallback
            try:
                allowed = bool(
                    should_steal_focus(
                        bool(user_action),
                        bool(combo_has_focus),
                        bool(view_has_focus),
                        bool(manual_mode),
                        bool(hanzi_committed),
                    )
                )
            except (AttributeError, RuntimeError, TypeError, ValueError):
                allowed = False
        except (AttributeError, RuntimeError, TypeError, ValueError):
            allowed = False

        if not allowed:
            return

        if target == "jy":
            self.focus_jyutping(select_all=select_all)
            return
        if target == "hz":
            self.focus_hanzi(select_all=select_all)
            return
        if target == "mn":
            self.focus_meanings(select_all=select_all)
            return
        if target == "cat":
            self.focus_category(select_all=select_all, show_popup=show_popup)
            return

    # ---- Deferred focus ----

    def defer_focus(self, target: str) -> None:
        """Defer focus movement to the next event-loop tick (best-effort).

        This prevents QComboBox signal churn from overriding our intended focus move.

        target: 'cand' | 'hz' | 'mn' | 'jy' | 'cat'
        """
        try:
            from PySide6.QtCore import QTimer
        except (ImportError, TypeError):
            QTimer = None

        def _apply() -> None:
            # Debug logging
            try:
                from PySide6.QtWidgets import QApplication
                fw = QApplication.focusWidget()
                fw_name = ""
                try:
                    fw_name = str(fw.objectName() or "") if fw is not None else ""
                except (TypeError, AttributeError, RuntimeError):
                    fw_name = ""
                logger.debug(
                    "DEFER_FOCUS start: target=%r current_focus=%r name=%r",
                    target,
                    type(fw).__name__ if fw else None,
                    fw_name,
                )
            except (TypeError, AttributeError, RuntimeError):
                pass

            try:
                if target == "cand":
                    combo = getattr(self.dialog, "_cand_combo", None)
                    if combo is not None:
                        try:
                            combo.setVisible(True)
                            combo.setFocus()
                            return
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                    # Fallback to Hanzi
                    target2 = "hz"
                else:
                    target2 = target

                if target2 == "hz":
                    self.focus_hanzi(select_all=True)

                    # If Hanzi is read-only, enter manual mode
                    try:
                        hz = getattr(self.dialog, "_add_hz", None)
                        hz_ro = bool(hz.isReadOnly()) if hz is not None else False
                    except (TypeError, AttributeError, RuntimeError):
                        hz_ro = False

                    if hz_ro:
                        # Auto-enter manual Hanzi mode
                        try:
                            self.dialog._on_btn_custom_hz_clicked()
                        except (TypeError, AttributeError, RuntimeError):
                            # Fallback: click button
                            try:
                                btn = getattr(self.dialog, "_btn_custom_hz", None)
                                if btn is not None and btn.isEnabled() and btn.isVisible():
                                    btn.click()
                            except (TypeError, AttributeError, RuntimeError):
                                pass

                        # Try to focus Hanzi again after entering manual mode
                        try:
                            self.focus_hanzi(select_all=True)
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                    return

                if target2 == "mn":
                    self.focus_meanings(select_all=True)
                    return
                if target2 == "jy":
                    self.focus_jyutping(select_all=True)
                    return
                if target2 == "cat":
                    self.focus_category(select_all=True, show_popup=True)
                    return

            except (TypeError, AttributeError, RuntimeError):
                pass

            # Debug logging
            try:
                from PySide6.QtWidgets import QApplication
                fw2 = QApplication.focusWidget()
                fw2_name = ""
                try:
                    fw2_name = str(fw2.objectName() or "") if fw2 is not None else ""
                except (TypeError, AttributeError, RuntimeError):
                    fw2_name = ""
                logger.debug(
                    "DEFER_FOCUS end: target=%r final_focus=%r name=%r",
                    target,
                    type(fw2).__name__ if fw2 else None,
                    fw2_name,
                )
            except (TypeError, AttributeError, RuntimeError):
                pass

        if QTimer is not None and hasattr(QTimer, "singleShot"):
            try:
                QTimer.singleShot(0, _apply)
                return
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Fallback: apply immediately
        _apply()
