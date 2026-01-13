"""Add/Edit panel controller - owns the form and orchestrates the workflow.

This extracts 1000+ lines of widget management from category_manager.py into
a clean, testable controller.
"""

from __future__ import annotations
from typing import Any, Callable
from dataclasses import dataclass

from ui.widget_utils import WidgetAccessor, SignalBlocker
from ui.form_state_controller import FormState, FormStateController
from ui.focus_manager import FocusManager, FocusState
from domain.vocabulary_service import VocabularyService, VocabEntry
from domain.entry_validation import EntryValidator
from domain.exceptions import (
    DuplicateEntryError,
    JyutpingValidationError,
    ValidationError,
)


@dataclass(frozen=True)
class AddEditResult:
    """Result of an add/edit operation."""
    success: bool
    entry: VocabEntry | None = None
    error: str | None = None


class AddEditPanel:
    """Controller for Add/Edit form panel.

    Owns:
    - All form widgets (jyutping, hanzi, meanings, category)
    - Form validation state
    - Save button state
    - Focus management

    Delegates to:
    - VocabularyService (domain logic)
    - EntryValidator (validation)
    - FormStateController (save button)
    - FocusManager (focus flow)
    """

    def __init__(
        self,
        *,
        # Widgets
        jyutping_widget: Any,
        hanzi_widget: Any,
        meanings_widget: Any,
        category_widget: Any,
        save_button: Any | None = None,
        # Services
        vocabulary_service: VocabularyService,
        validator: EntryValidator,
        # Optional controllers
        form_state_controller: FormStateController | None = None,
        focus_manager: FocusManager | None = None,
        # Callbacks
        on_save: Callable[[VocabEntry], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ):
        """
        Args:
            jyutping_widget: QLineEdit for Jyutping
            hanzi_widget: QLineEdit for Hanzi
            meanings_widget: QLineEdit for meanings
            category_widget: QComboBox for category
            save_button: Optional QPushButton for save
            vocabulary_service: Domain service for vocab operations
            validator: Entry validator
            form_state_controller: Optional form state controller
            focus_manager: Optional focus manager
            on_save: Callback when entry saved successfully
            on_error: Callback for errors
        """
        self._jy_widget = jyutping_widget
        self._hz_widget = hanzi_widget
        self._mn_widget = meanings_widget
        self._cat_widget = category_widget
        self._save_button = save_button

        self._vocab_service = vocabulary_service
        self._validator = validator

        # Controllers
        self._form_controller = form_state_controller or FormStateController(
            validator,
            on_state_changed=self._on_form_state_changed,
        )
        self._focus_manager = focus_manager

        # Callbacks
        self._on_save = on_save
        self._on_error = on_error

        # State
        self._saving = False
        self._manual_hanzi_mode = False

        # Initialize form state
        self._update_form_state()

    def _on_form_state_changed(self, valid: bool) -> None:
        """Called when form validity changes."""
        if self._save_button is not None:
            WidgetAccessor.set_enabled(self._save_button, valid)

    def get_values(self) -> FormState:
        """Get current form values.

        Returns:
            Current form state
        """
        return FormState(
            jyutping=WidgetAccessor.get_text(self._jy_widget),
            hanzi=WidgetAccessor.get_text(self._hz_widget),
            meanings=WidgetAccessor.get_text(self._mn_widget),
            category=WidgetAccessor.get_text(self._cat_widget),
            saving=self._saving,
            manual_hanzi=self._manual_hanzi_mode,
        )

    def set_values(
        self,
        *,
        jyutping: str = "",
        hanzi: str = "",
        meanings: str = "",
        category: str = "",
        block_signals: bool = True,
    ) -> None:
        """Set form values.

        Args:
            jyutping: Jyutping value
            hanzi: Hanzi value
            meanings: Meanings value
            category: Category value
            block_signals: Whether to block signals during update
        """
        widgets = [self._jy_widget, self._hz_widget, self._mn_widget, self._cat_widget]

        if block_signals:
            with SignalBlocker(*widgets):
                self._set_values_impl(jyutping, hanzi, meanings, category)
        else:
            self._set_values_impl(jyutping, hanzi, meanings, category)

        # Update form state
        self._update_form_state()

    def _set_values_impl(self, jy: str, hz: str, mn: str, cat: str) -> None:
        """Implementation of set_values (without signal blocking)."""
        WidgetAccessor.set_text(self._jy_widget, jy)
        WidgetAccessor.set_text(self._hz_widget, hz)
        WidgetAccessor.set_text(self._mn_widget, mn)
        WidgetAccessor.set_text(self._cat_widget, cat)

    def clear(self) -> None:
        """Clear all form fields."""
        self.set_values(jyutping="", hanzi="", meanings="", category="")
        self._manual_hanzi_mode = False
        self._update_form_state()

    def is_valid(self) -> bool:
        """Check if form is currently valid.

        Returns:
            True if form can be saved
        """
        state = self.get_values()
        return self._form_controller.is_valid(state)

    def _update_form_state(self) -> None:
        """Update form state controller."""
        state = self.get_values()
        self._form_controller.update(state)

    def validate(self) -> dict[str, str]:
        """Validate all fields and return errors.

        Returns:
            Dictionary mapping field names to error messages (empty if valid)
        """
        state = self.get_values()
        errors = {}

        # Validate each field
        results = self._validator.validate_all(
            jyutping=state.jyutping,
            hanzi=state.hanzi,
            meanings=state.meanings,
            category=state.category,
        )

        for field, result in results.items():
            if not result.valid and result.error_message:
                errors[field] = result.error_message

        # Check reserved categories
        if not self._form_controller.is_category_valid(state.category):
            errors["category"] = f"Cannot save with category '{state.category}'"

        return errors

    def save(self) -> AddEditResult:
        """Save current form values.

        Returns:
            Result with success status and entry or error
        """
        if self._saving:
            return AddEditResult(success=False, error="Save already in progress")

        self._saving = True
        self._update_form_state()

        try:
            state = self.get_values()

            # Validate
            errors = self.validate()
            if errors:
                error_msg = "; ".join(f"{k}: {v}" for k, v in errors.items())
                if self._on_error:
                    self._on_error(error_msg)
                return AddEditResult(success=False, error=error_msg)

            # Save via service
            try:
                entry = self._vocab_service.add_entry(
                    jyutping=state.jyutping,
                    hanzi=state.hanzi,
                    meanings=state.meanings,
                    categories=state.category,
                )

                # Success callback
                if self._on_save:
                    self._on_save(entry)

                return AddEditResult(success=True, entry=entry)

            except DuplicateEntryError as e:
                error_msg = str(e)
                if self._on_error:
                    self._on_error(error_msg)
                return AddEditResult(success=False, error=error_msg)

            except (JyutpingValidationError, ValidationError) as e:
                error_msg = str(e)
                if self._on_error:
                    self._on_error(error_msg)
                return AddEditResult(success=False, error=error_msg)

        finally:
            self._saving = False
            self._update_form_state()

    def focus_field(self, field: str, *, select_all: bool = True) -> bool:
        """Focus a specific field.

        Args:
            field: Field name ('jyutping', 'hanzi', 'meanings', 'category')
            select_all: Whether to select all text

        Returns:
            True if focus was set
        """
        widget_map = {
            "jyutping": self._jy_widget,
            "hanzi": self._hz_widget,
            "meanings": self._mn_widget,
            "category": self._cat_widget,
        }

        widget = widget_map.get(field)
        if widget is None:
            return False

        return WidgetAccessor.focus(widget, select_all=select_all)

    def set_hanzi_readonly(self, readonly: bool) -> None:
        """Set Hanzi field read-only state.

        Args:
            readonly: True for read-only, False for editable
        """
        if self._hz_widget is None:
            return

        try:
            if hasattr(self._hz_widget, 'setReadOnly'):
                self._hz_widget.setReadOnly(readonly)
        except (RuntimeError, AttributeError):
            pass

    def enter_manual_hanzi_mode(self) -> None:
        """Enter manual Hanzi entry mode."""
        self._manual_hanzi_mode = True
        self.set_hanzi_readonly(False)
        WidgetAccessor.clear_text(self._hz_widget)
        self.focus_field("hanzi", select_all=True)
        self._update_form_state()

    def exit_manual_hanzi_mode(self) -> None:
        """Exit manual Hanzi entry mode."""
        self._manual_hanzi_mode = False
        self.set_hanzi_readonly(True)
        self._update_form_state()


__all__ = [
    "AddEditPanel",
    "AddEditResult",
]
