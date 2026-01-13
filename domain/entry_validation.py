"""Consolidated validation rules for vocabulary entries.

Pure validation logic - no UI, no side effects.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from domain.jyutping_validation import validate_jyut_syllables


@dataclass(frozen=True)
class ValidationResult:
    """Result of field validation."""
    valid: bool
    field: str
    value: str
    error_message: str | None = None

    @classmethod
    def ok(cls, field: str, value: str) -> ValidationResult:
        """Create success result."""
        return cls(valid=True, field=field, value=value)

    @classmethod
    def error(cls, field: str, value: str, message: str) -> ValidationResult:
        """Create error result."""
        return cls(valid=False, field=field, value=value, error_message=message)


class EntryValidator:
    """Validates vocabulary entry fields.

    All methods are pure - they don't modify state or have side effects.
    """

    def __init__(
        self,
        normalize_jy: Callable[[str], str] | None = None,
        valid_categories: set[str] | None = None,
    ):
        """
        Args:
            normalize_jy: Optional Jyutping normalizer
            valid_categories: Optional set of valid category names
        """
        self._normalize_jy = normalize_jy or self._default_normalize
        self._valid_categories = valid_categories

    @staticmethod
    def _default_normalize(jy: str) -> str:
        return " ".join((jy or "").strip().lower().split())

    def validate_jyutping(self, jyutping: str) -> ValidationResult:
        """Validate Jyutping field.

        Returns:
            ValidationResult with normalized Jyutping if valid
        """
        jy = (jyutping or "").strip()

        if not jy:
            return ValidationResult.error("jyutping", jy, "Jyutping is required")

        ok, reason = validate_jyut_syllables(jy)
        if not ok:
            return ValidationResult.error("jyutping", jy, reason or "Invalid format")

        normalized = self._normalize_jy(jy)
        return ValidationResult.ok("jyutping", normalized)

    def validate_hanzi(self, hanzi: str) -> ValidationResult:
        """Validate Hanzi field."""
        hz = (hanzi or "").strip()

        if not hz:
            return ValidationResult.error("hanzi", hz, "Hanzi is required")

        # Could add more checks (e.g., character range validation)
        return ValidationResult.ok("hanzi", hz)

    def validate_meanings(self, meanings: str | list[str]) -> ValidationResult:
        """Validate meanings field."""
        if isinstance(meanings, str):
            mn_list = [m.strip() for m in meanings.split(",") if m.strip()]
            mn_str = meanings.strip()
        else:
            mn_list = [str(m).strip() for m in (meanings or []) if str(m).strip()]
            mn_str = ", ".join(mn_list)

        if not mn_list:
            return ValidationResult.error(
                "meanings",
                mn_str,
                "At least one meaning required"
            )

        return ValidationResult.ok("meanings", mn_str)

    def validate_category(self, category: str) -> ValidationResult:
        """Validate category field."""
        cat = (category or "").strip()

        # Empty is allowed (will default to 'unassigned')
        if not cat:
            return ValidationResult.ok("category", "")

        # Check reserved names
        if cat.lower() in ("all",):
            return ValidationResult.error(
                "category",
                cat,
                "Reserved category name"
            )

        # Check against valid categories if provided
        if self._valid_categories is not None:
            if cat not in self._valid_categories:
                return ValidationResult.error(
                    "category",
                    cat,
                    f"Unknown category: {cat}"
                )

        return ValidationResult.ok("category", cat)

    def validate_all(
        self,
        jyutping: str,
        hanzi: str,
        meanings: str | list[str],
        category: str,
    ) -> dict[str, ValidationResult]:
        """Validate all fields at once.

        Returns:
            Dictionary mapping field names to ValidationResults
        """
        return {
            "jyutping": self.validate_jyutping(jyutping),
            "hanzi": self.validate_hanzi(hanzi),
            "meanings": self.validate_meanings(meanings),
            "category": self.validate_category(category),
        }

    def is_valid_entry(
        self,
        jyutping: str,
        hanzi: str,
        meanings: str | list[str],
        category: str,
    ) -> bool:
        """Quick check if all fields are valid.

        Returns:
            True if all fields pass validation
        """
        results = self.validate_all(jyutping, hanzi, meanings, category)
        return all(r.valid for r in results.values())


__all__ = [
    "ValidationResult",
    "EntryValidator",
]
