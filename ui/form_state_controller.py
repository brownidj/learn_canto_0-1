"""Form state controller - manages Save button enable/disable logic.

Replaces scattered _update_save_enabled() calls with a clean, testable controller.
"""

from __future__ import annotations
from typing import Callable, Any
from dataclasses import dataclass

from domain.entry_validation import EntryValidator


@dataclass(frozen=True)
class FormState:
    """Immutable form state snapshot."""
    jyutping: str
    hanzi: str
    meanings: str
    category: str
    saving: bool = False
    manual_hanzi: bool = False

    def is_complete(self) -> bool:
        """Check if all required fields have values."""
        return all([
            self.jyutping.strip(),
            self.hanzi.strip(),
            self.meanings.strip(),
            self.category.strip(),
        ])


class FormStateController:
    """Controls form state and Save button enablement.

    Responsibilities:
    - Validates form fields
    - Decides when Save should be enabled
    - Triggers UI updates (via callbacks)

    Non-responsibilities:
    - Doesn't read widgets directly
    - Doesn't mutate state
    - Doesn't know about Qt
    """

    def __init__(
        self,
        validator: EntryValidator,
        *,
        on_state_changed: Callable[[bool], None] | None = None,
        reserved_categories: set[str] | None = None,
    ):
        """
        Args:
            validator: Entry validator for field validation
            on_state_changed: Called when valid state changes (bool: is_valid)
            reserved_categories: Categories that block save (e.g., 'unassigned', 'all')
        """
        self._validator = validator
        self._on_state_changed = on_state_changed
        self._reserved_categories = reserved_categories or {"unassigned", "all"}
        self._last_valid = None  # None = uninitialized, triggers first callback

    def is_category_valid(self, category: str) -> bool:
        """Check if category is valid for saving.

        Args:
            category: Category to check

        Returns:
            True if category allows saving
        """
        cat = (category or "").strip()
        if not cat:
            return False

        return cat.lower() not in self._reserved_categories

    def is_valid(self, state: FormState) -> bool:
        """Check if form is valid and ready to save.

        Args:
            state: Current form state

        Returns:
            True if Save should be enabled
        """
        # Can't save while saving
        if state.saving:
            return False

        # All fields must have values
        if not state.is_complete():
            return False

        # Category must not be reserved
        if not self.is_category_valid(state.category):
            return False

        # Validate Jyutping
        jy_result = self._validator.validate_jyutping(state.jyutping)
        if not jy_result.valid:
            return False

        # Validate Hanzi
        hz_result = self._validator.validate_hanzi(state.hanzi)
        if not hz_result.valid:
            return False

        # Validate meanings
        mn_result = self._validator.validate_meanings(state.meanings)
        if not mn_result.valid:
            return False

        return True

    def update(self, state: FormState) -> bool:
        """Update form state and trigger callbacks if changed.

        Args:
            state: New form state

        Returns:
            True if form is valid
        """
        valid = self.is_valid(state)

        # Call callback if state changed OR if this is first update (None)
        if valid != self._last_valid or self._last_valid is None:
            self._last_valid = valid
            if self._on_state_changed is not None:
                try:
                    self._on_state_changed(valid)
                except Exception:
                    # Callback errors should not break state logic
                    pass

        return valid

    def reset(self) -> None:
        """Reset controller state."""
        # Only call callback if we're not already False
        if self._last_valid is True or self._last_valid is None:
            self._last_valid = False
            if self._on_state_changed is not None:
                try:
                    self._on_state_changed(False)
                except Exception:
                    pass


__all__ = [
    "FormState",
    "FormStateController",
]
