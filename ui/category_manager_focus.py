"""
CategoryManager focus management extracted for maintainability.

Centralizes all focus movement logic, intent tracking, and policy decisions.
"""

import logging
from typing import TYPE_CHECKING

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_focus_service import CategoryManagerFocusService
from ui.category_manager_focus_state import (
    is_hanzi_committed,
    is_manual_hanzi_mode,
    set_hanzi_committed,
    set_manual_hanzi_mode,
)

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerFocusController:
    """Manages focus movement and intent tracking for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        self._dlg = CategoryManagerDialogAdapter(dialog)
        self._svc = CategoryManagerFocusService(self._dlg)

    # ---- Focus contract ----
    # - After category commit -> Hanzi (no select-all; user can open dropdown).
    # - After candidate selection -> Meaning (select-all).
    # - After Meaning save/commit -> Jyutping (select-all).
    # - After entering manual Hanzi mode -> Hanzi (select-all).

    # ---- Intent tracking ----

    def user_has_committed_hanzi(self) -> bool:
        """Check if user has committed Hanzi selection."""
        return is_hanzi_committed(self._dlg)

    def user_is_in_manual_hanzi_mode(self) -> bool:
        """Check if user is in manual Hanzi entry mode."""
        return is_manual_hanzi_mode(self._dlg)

    def mark_hanzi_committed(self, committed: bool = True) -> None:
        """Mark Hanzi as committed by user."""
        try:
            set_hanzi_committed(self._dlg, bool(committed))
        except (TypeError, AttributeError, RuntimeError):
            pass

    def mark_manual_hanzi_mode(self, enabled: bool = True) -> None:
        """Mark manual Hanzi mode enabled/disabled."""
        try:
            set_manual_hanzi_mode(self._dlg, bool(enabled))
        except (TypeError, AttributeError, RuntimeError):
            pass

    # ---- Basic focus helpers ----

    def focus_jyutping(self, *, select_all: bool = True) -> None:
        """Focus Jyutping field."""
        self._svc.focus_jyutping(select_all=select_all)

    def focus_meanings(self, *, select_all: bool = True) -> None:
        """Focus Meanings field."""
        self._svc.focus_meaning(select_all=select_all)

    def focus_hanzi(self, *, select_all: bool = True) -> None:
        """Focus Hanzi field."""
        self._svc.focus_hanzi(select_all=select_all)

    def focus_category(self, *, select_all: bool = True, show_popup: bool = False) -> None:
        """Focus category combobox."""
        self._svc.focus_category(select_all=select_all, show_popup=show_popup)

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
        self._svc.apply_focus_policy(
            target=target,
            reason=reason,
            user_action=user_action,
            show_popup=show_popup,
            select_all=select_all,
        )

    # ---- Deferred focus ----

    def defer_focus(self, target: str) -> None:
        """Defer focus movement to the next event-loop tick (best-effort).

        This prevents QComboBox signal churn from overriding our intended focus move.

        target: 'cand' | 'hz' | 'mn' | 'jy' | 'cat'
        """
        self._svc.defer_focus(target, select_all=True)
