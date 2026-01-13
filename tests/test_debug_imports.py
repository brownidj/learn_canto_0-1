"""Debug test to see what's failing."""

import sys
import traceback
import pytest

pytestmark = pytest.mark.pure


def test_import_exceptions_debug():
    """Debug exceptions import."""
    try:
        from domain.exceptions import VocabularyError
        print(f"✓ VocabularyError imported: {VocabularyError}")
        assert VocabularyError is not None
    except Exception as e:
        print(f"✗ Failed to import VocabularyError:")
        traceback.print_exc()
        raise


def test_import_vocabulary_service_debug():
    """Debug vocabulary service import."""
    try:
        from domain.vocabulary_service import VocabularyService
        print(f"✓ VocabularyService imported: {VocabularyService}")
        assert VocabularyService is not None
    except Exception as e:
        print(f"✗ Failed to import VocabularyService:")
        traceback.print_exc()
        raise


def test_import_entry_validation_debug():
    """Debug entry validation import."""
    try:
        from domain.entry_validation import EntryValidator
        print(f"✓ EntryValidator imported: {EntryValidator}")
        assert EntryValidator is not None
    except Exception as e:
        print(f"✗ Failed to import EntryValidator:")
        traceback.print_exc()
        raise


def test_create_service_debug():
    """Debug service instantiation."""
    try:
        from domain.vocabulary_service import VocabularyService
        service = VocabularyService({}, {})
        print(f"✓ VocabularyService created: {service}")
        assert service is not None
    except Exception as e:
        print(f"✗ Failed to create VocabularyService:")
        traceback.print_exc()
        raise
