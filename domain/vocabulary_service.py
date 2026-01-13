"""Pure vocabulary service - no UI dependencies.

Manages vocabulary CRUD operations with proper validation and error handling.
"""

from __future__ import annotations
from typing import Callable, Any
from dataclasses import dataclass

from domain.exceptions import (
    DuplicateEntryError,
    JyutpingValidationError,
    ValidationError,
)
from domain.jyutping_validation import validate_jyut_syllables
from domain.duplicate_rules import is_duplicate_jy, is_exact_duplicate_entry


@dataclass(frozen=True)
class VocabEntry:
    """Immutable vocabulary entry."""
    jyutping: str
    hanzi: str
    meanings: list[str]
    categories: list[str]
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Export to dictionary format."""
        return {
            "jyutping": self.jyutping,
            "hanzi": self.hanzi,
            "meaning": ", ".join(self.meanings),
            "gloss": ", ".join(self.meanings),  # Legacy alias
            "categories": list(self.categories),
            "category": self.categories[0] if self.categories else "",
            "notes": self.notes,
        }


class VocabularyService:
    """Domain service for vocabulary operations.

    Pure Python, no Qt dependencies. All operations return results
    or raise specific exceptions - never silent failures.
    """

    def __init__(
        self,
        vocab: dict[str, Any],
        categories: dict[str, list[str]],
        normalize_jy: Callable[[str], str] | None = None,
    ):
        """
        Args:
            vocab: Vocabulary data structure (mutable, owned by caller)
            categories: Category memberships (mutable, owned by caller)
            normalize_jy: Optional Jyutping normalizer
        """
        self._vocab = vocab
        self._categories = categories
        self._normalize_jy = normalize_jy or self._default_normalize

    @staticmethod
    def _default_normalize(jy: str) -> str:
        """Default Jyutping normalization."""
        return " ".join((jy or "").strip().lower().split())

    def validate_jyutping(self, jyutping: str) -> str:
        """Validate and normalize Jyutping.

        Args:
            jyutping: Raw Jyutping input

        Returns:
            Normalized Jyutping

        Raises:
            JyutpingValidationError: If validation fails
        """
        jy = (jyutping or "").strip()
        if not jy:
            raise JyutpingValidationError("", "Jyutping is empty")

        ok, reason = validate_jyut_syllables(jy)
        if not ok:
            raise JyutpingValidationError(jy, reason or "Invalid format")

        return self._normalize_jy(jy)

    def validate_entry(
        self,
        jyutping: str,
        hanzi: str,
        meanings: list[str] | str,
        categories: list[str] | str,
    ) -> VocabEntry:
        """Validate all entry fields.

        Returns:
            Validated VocabEntry

        Raises:
            ValidationError: If any field is invalid
        """
        # Jyutping
        jy_norm = self.validate_jyutping(jyutping)

        # Hanzi
        hz = (hanzi or "").strip()
        if not hz:
            raise ValidationError("hanzi", hz, "Hanzi is required")

        # Meanings
        if isinstance(meanings, str):
            mn_list = [m.strip() for m in meanings.split(",") if m.strip()]
        else:
            mn_list = [str(m).strip() for m in (meanings or []) if str(m).strip()]

        if not mn_list:
            raise ValidationError("meanings", str(meanings), "At least one meaning required")

        # Categories
        if isinstance(categories, str):
            cat_list = [categories.strip()] if categories.strip() else []
        else:
            cat_list = [str(c).strip() for c in (categories or []) if str(c).strip()]

        # Allow empty categories (will default to 'unassigned')
        # But validate that provided categories are not reserved
        for cat in cat_list:
            if cat.lower() in ("all",):
                raise ValidationError(
                    "category",
                    cat,
                    "Reserved category name"
                )

        return VocabEntry(
            jyutping=jy_norm,
            hanzi=hz,
            meanings=mn_list,
            categories=cat_list or ["unassigned"],
        )

    def check_duplicate_jyutping(self, jyutping: str) -> bool:
        """Check if Jyutping already exists.

        Returns:
            True if duplicate exists
        """
        return is_duplicate_jy(
            jyutping,
            vocab=self._vocab,
            normalize=self._normalize_jy
        )

    def check_exact_duplicate(self, jyutping: str, hanzi: str) -> bool:
        """Check if exact (jyutping, hanzi) pair exists.

        Returns:
            True if exact duplicate exists
        """
        return is_exact_duplicate_entry(
            self._vocab,
            jyutping,
            hanzi,
            normalize=self._normalize_jy
        )

    def add_entry(
        self,
        jyutping: str,
        hanzi: str,
        meanings: list[str] | str,
        categories: list[str] | str,
        allow_duplicate_jy: bool = False,
        notes: str = "",
    ) -> VocabEntry:
        """Add a new vocabulary entry.

        Args:
            jyutping: Jyutping pronunciation
            hanzi: Chinese characters
            meanings: Meanings (list or comma-separated string)
            categories: Categories (list or single string)
            allow_duplicate_jy: If False, raise on duplicate Jyutping
            notes: Optional notes

        Returns:
            Created VocabEntry

        Raises:
            DuplicateEntryError: If entry already exists
            ValidationError: If validation fails
        """
        # Validate all fields
        entry = self.validate_entry(jyutping, hanzi, meanings, categories)

        # Check duplicates
        if not allow_duplicate_jy and self.check_duplicate_jyutping(entry.jyutping):
            raise DuplicateEntryError(entry.jyutping, entry.hanzi)

        if self.check_exact_duplicate(entry.jyutping, entry.hanzi):
            raise DuplicateEntryError(
                entry.jyutping,
                entry.hanzi,
                {"reason": "Exact entry already exists"}
            )

        # Add to vocab (legacy format: hanzi -> [meanings, jyutping])
        self._vocab[entry.hanzi] = (entry.meanings, entry.jyutping)

        # Add to categories
        for cat in entry.categories:
            if cat not in self._categories:
                self._categories[cat] = []
            if entry.hanzi not in self._categories[cat]:
                self._categories[cat].append(entry.hanzi)

        # Remove from 'unassigned' if now in real category
        if len(entry.categories) > 0 and entry.categories != ["unassigned"]:
            if "unassigned" in self._categories:
                try:
                    self._categories["unassigned"].remove(entry.hanzi)
                except ValueError:
                    pass

        return entry

    def update_entry(
        self,
        original_hanzi: str,
        jyutping: str,
        hanzi: str,
        meanings: list[str] | str,
        categories: list[str] | str,
        notes: str = "",
    ) -> VocabEntry:
        """Update an existing vocabulary entry.

        Args:
            original_hanzi: Current Hanzi key (may change)
            jyutping: New Jyutping
            hanzi: New Hanzi
            meanings: New meanings
            categories: New categories
            notes: New notes

        Returns:
            Updated VocabEntry

        Raises:
            ValidationError: If validation fails
        """
        # Validate
        entry = self.validate_entry(jyutping, hanzi, meanings, categories)

        # Remove old entry
        if original_hanzi != hanzi and original_hanzi in self._vocab:
            del self._vocab[original_hanzi]

        # Remove from old categories
        for cat_members in self._categories.values():
            try:
                cat_members.remove(original_hanzi)
            except ValueError:
                pass

        # Add new entry
        self._vocab[entry.hanzi] = (entry.meanings, entry.jyutping)

        # Add to new categories
        for cat in entry.categories:
            if cat not in self._categories:
                self._categories[cat] = []
            if entry.hanzi not in self._categories[cat]:
                self._categories[cat].append(entry.hanzi)

        return entry


__all__ = [
    "VocabEntry",
    "VocabularyService",
]
