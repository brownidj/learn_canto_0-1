"""Pure tests for VocabularyService - no Qt dependencies."""

import pytest
from domain.vocabulary_service import VocabularyService, VocabEntry
from domain.exceptions import (
    DuplicateEntryError,
    JyutpingValidationError,
    ValidationError,
)

pytestmark = pytest.mark.pure


def test_add_valid_entry():
    """Should add valid entry successfully."""
    vocab = {}
    cats = {}
    service = VocabularyService(vocab, cats)

    entry = service.add_entry(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        categories="greetings"
    )

    assert entry.jyutping == "nei5 hou2"
    assert entry.hanzi == "你好"
    assert entry.meanings == ["hello"]
    assert entry.categories == ["greetings"]

    # Check vocab updated
    assert "你好" in vocab
    assert vocab["你好"] == (["hello"], "nei5 hou2")

    # Check categories updated
    assert "greetings" in cats
    assert "你好" in cats["greetings"]


def test_add_entry_with_list_meanings():
    """Should handle list of meanings."""
    vocab = {}
    cats = {}
    service = VocabularyService(vocab, cats)

    entry = service.add_entry(
        jyutping="hou2",
        hanzi="好",
        meanings=["good", "well", "OK"],
        categories="adjectives"
    )

    assert entry.meanings == ["good", "well", "OK"]


def test_add_entry_normalizes_jyutping():
    """Should normalize Jyutping."""
    vocab = {}
    cats = {}
    service = VocabularyService(vocab, cats)

    entry = service.add_entry(
        jyutping="  NEI5   HOU2  ",
        hanzi="你好",
        meanings="hello",
        categories="greetings"
    )

    assert entry.jyutping == "nei5 hou2"


def test_duplicate_jyutping_raises():
    """Should raise on duplicate Jyutping."""
    vocab = {}
    cats = {}
    service = VocabularyService(vocab, cats)

    service.add_entry("nei5 hou2", "你好", "hello", "greetings")

    with pytest.raises(DuplicateEntryError) as exc_info:
        service.add_entry("nei5 hou2", "你好", "hello", "greetings")

    assert "nei5 hou2" in str(exc_info.value)


def test_invalid_jyutping_raises():
    """Should raise on invalid Jyutping."""
    vocab = {}
    cats = {}
    service = VocabularyService(vocab, cats)

    with pytest.raises(JyutpingValidationError) as exc_info:
        service.add_entry("invalid", "你好", "hello", "greetings")

    assert "tone digit" in str(exc_info.value).lower()


def test_empty_meanings_raises():
    """Should raise when meanings are empty."""
    vocab = {}
    cats = {}
    service = VocabularyService(vocab, cats)

    with pytest.raises(ValidationError) as exc_info:
        service.add_entry("nei5 hou2", "你好", "", "greetings")

    assert exc_info.value.field == "meanings"


def test_empty_hanzi_raises():
    """Should raise when Hanzi is empty."""
    vocab = {}
    cats = {}
    service = VocabularyService(vocab, cats)

    with pytest.raises(ValidationError) as exc_info:
        service.add_entry("nei5 hou2", "", "hello", "greetings")

    assert exc_info.value.field == "hanzi"


def test_update_entry():
    """Should update existing entry."""
    vocab = {"你好": (["hello"], "nei5 hou2")}
    cats = {"greetings": ["你好"]}
    service = VocabularyService(vocab, cats)

    entry = service.update_entry(
        original_hanzi="你好",
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings=["hello", "hi"],
        categories="greetings"
    )

    assert entry.meanings == ["hello", "hi"]
    assert vocab["你好"] == (["hello", "hi"], "nei5 hou2")


def test_update_entry_changes_hanzi():
    """Should handle Hanzi changes in updates."""
    vocab = {"你好": (["hello"], "nei5 hou2")}
    cats = {"greetings": ["你好"]}
    service = VocabularyService(vocab, cats)

    entry = service.update_entry(
        original_hanzi="你好",
        jyutping="nei5 hou2",
        hanzi="您好",
        meanings="hello (formal)",
        categories="greetings"
    )

    assert "你好" not in vocab
    assert "您好" in vocab
    assert "您好" in cats["greetings"]
    assert "你好" not in cats["greetings"]


def test_add_entry_removes_from_unassigned():
    """Should remove from 'unassigned' when adding to real category."""
    vocab = {}
    cats = {"unassigned": ["你好"]}
    service = VocabularyService(vocab, cats)

    service.add_entry("nei5 hou2", "你好", "hello", "greetings")

    assert "你好" not in cats.get("unassigned", [])
    assert "你好" in cats["greetings"]


def test_entry_to_dict():
    """Should export entry to dictionary."""
    entry = VocabEntry(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings=["hello", "hi"],
        categories=["greetings"],
    )

    result = entry.to_dict()

    assert result["jyutping"] == "nei5 hou2"
    assert result["hanzi"] == "你好"
    assert result["meaning"] == "hello, hi"
    assert result["gloss"] == "hello, hi"  # Legacy alias
    assert result["categories"] == ["greetings"]
    assert result["category"] == "greetings"


def test_validate_jyutping():
    """Should validate and normalize Jyutping."""
    vocab = {}
    cats = {}
    service = VocabularyService(vocab, cats)

    result = service.validate_jyutping("  NEI5   HOU2  ")
    assert result == "nei5 hou2"


def test_validate_entry():
    """Should validate all fields."""
    vocab = {}
    cats = {}
    service = VocabularyService(vocab, cats)

    entry = service.validate_entry(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello, hi",
        categories="greetings"
    )

    assert entry.jyutping == "nei5 hou2"
    assert entry.hanzi == "你好"
    assert entry.meanings == ["hello", "hi"]
    assert entry.categories == ["greetings"]
