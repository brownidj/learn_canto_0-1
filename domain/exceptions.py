"""Domain-specific exceptions for vocabulary management.

All exceptions provide user-friendly messages and structured context
for UI presentation and logging.
"""

from __future__ import annotations
from typing import Any


class VocabularyError(Exception):
    """Base exception for all vocabulary-related errors.

    Attributes:
        message: Human-readable error message suitable for UI display
        context: Additional structured data for logging/debugging
    """

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self) -> str:
        return self.message


class ValidationError(VocabularyError):
    """Validation failed for an input field."""

    def __init__(
        self,
        field: str,
        value: str,
        reason: str,
        context: dict[str, Any] | None = None
    ):
        message = f"Invalid {field}: {reason}"
        ctx = {"field": field, "value": value, "reason": reason}
        if context:
            ctx.update(context)
        super().__init__(message, ctx)
        self.field = field
        self.value = value
        self.reason = reason


class JyutpingValidationError(ValidationError):
    """Jyutping validation failed."""

    def __init__(self, jyutping: str, reason: str):
        super().__init__(
            field="Jyutping",
            value=jyutping,
            reason=reason
        )


class DuplicateEntryError(VocabularyError):
    """Entry already exists in vocabulary."""

    def __init__(
        self,
        jyutping: str,
        hanzi: str | None = None,
        context: dict[str, Any] | None = None
    ):
        if hanzi:
            message = f"Entry already exists: {hanzi} ({jyutping})"
        else:
            message = f"Jyutping already exists: {jyutping}"

        ctx = {"jyutping": jyutping, "hanzi": hanzi}
        if context:
            ctx.update(context)

        super().__init__(message, ctx)
        self.jyutping = jyutping
        self.hanzi = hanzi


class CategoryError(VocabularyError):
    """Category-related error."""
    pass


class UnknownCategoryError(CategoryError):
    """Attempted to use a category that doesn't exist."""

    def __init__(self, category: str, context: dict[str, Any] | None = None):
        message = f"Unknown category: {category}"
        ctx = {"category": category}
        if context:
            ctx.update(context)
        super().__init__(message, ctx)
        self.category = category


class InvalidCategoryError(CategoryError):
    """Category name is invalid (e.g., reserved names)."""

    def __init__(self, category: str, reason: str):
        message = f"Invalid category '{category}': {reason}"
        super().__init__(message, {"category": category, "reason": reason})
        self.category = category
        self.reason = reason


class MeaningResolutionError(VocabularyError):
    """Failed to resolve meanings for a Hanzi candidate."""

    def __init__(self, hanzi: str, reason: str | None = None):
        message = f"Could not resolve meanings for {hanzi}"
        if reason:
            message += f": {reason}"
        super().__init__(message, {"hanzi": hanzi, "reason": reason})
        self.hanzi = hanzi


__all__ = [
    "VocabularyError",
    "ValidationError",
    "JyutpingValidationError",
    "DuplicateEntryError",
    "CategoryError",
    "UnknownCategoryError",
    "InvalidCategoryError",
    "MeaningResolutionError",
]
