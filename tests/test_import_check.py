"""Quick import check to verify Week 1 modules work."""

import pytest

pytestmark = pytest.mark.pure


def test_import_exceptions():
    """Should import domain exceptions."""
    from domain.exceptions import (
        VocabularyError,
        ValidationError,
        JyutpingValidationError,
        DuplicateEntryError,
    )
    assert VocabularyError
    assert ValidationError
    assert JyutpingValidationError
    assert DuplicateEntryError


def test_import_vocabulary_service():
    """Should import vocabulary service."""
    from domain.vocabulary_service import VocabularyService, VocabEntry
    assert VocabularyService
    assert VocabEntry


def test_import_entry_validation():
    """Should import entry validation."""
    from domain.entry_validation import EntryValidator, ValidationResult
    assert EntryValidator
    assert ValidationResult


def test_quick_service_instantiation():
    """Should create service instance."""
    from domain.vocabulary_service import VocabularyService
    service = VocabularyService({}, {})
    assert service is not None
