"""
CategoryManager field reset extracted for maintainability.

Handles clearing and resetting Add/Edit panel fields.
"""

import logging
from typing import TYPE_CHECKING

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_field_reset_rules import (
    plan_clear_add_entry_fields,
    plan_reset_add_panel_pre_validation,
    plan_reset_to_initial_state,
)
from ui.category_manager_field_reset_effects import FieldResetEffects

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerFieldResetController:
    """Manages field clearing and reset for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        self._dlg = CategoryManagerDialogAdapter(dialog)
        self._effects = FieldResetEffects(self._dlg)

    def clear_add_entry_fields(self) -> None:
        """Clear Add/Edit fields best-effort."""
        self._apply_reset(plan_clear_add_entry_fields())

    def reset_add_panel_pre_validation(self) -> None:
        """Return Add/Edit panel to pre-validation state (placeholders only)."""
        self._apply_reset(plan_reset_add_panel_pre_validation())

    def reset_to_initial_state(self) -> None:
        """Reset Entry + Hanzi panels to the initial dialog state."""
        self._apply_reset(plan_reset_to_initial_state())

    def _apply_reset(self, plan) -> None:
        self._effects.apply(plan)
