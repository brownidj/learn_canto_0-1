"""Pure tests for EntryValidator - no Qt dependencies."""

import pytest
from domain.entry_validation import EntryValidator, ValidationResult

pytestmark = pytest.mark.pure


def test_validate_valid_jyutping():
    """Should validate correct Jyutping."""
    validator = EntryValidator()
    result = validator.validate_jyutping("nei5 hou2")

    assert result.valid
    assert result.field == "jyutping"
    assert result.value == "nei5 hou2"
    assert result.error_message is None


def test_validate_empty_jyutping():
    """Should reject empty Jyutping."""
    validator = EntryValidator()
    result = validator.validate_jyutping("")

    assert not result.valid
    assert result.field == "jyutping"
    assert "required" in result.error_message.lower()


def test_validate_invalid_jyutping():
    """Should reject invalid Jyutping."""
    validator = EntryValidator()
    result = validator.validate_jyutping("invalid")

    assert not result.valid
    assert "tone" in result.error_message.lower()


def test_validate_hanzi():
    """Should validate Hanzi."""
    validator = EntryValidator()
    result = validator.validate_hanzi("你好")

    assert result.valid
    assert result.value == "你好"


def test_validate_empty_hanzi():
    """Should reject empty Hanzi."""
    validator = EntryValidator()
    result = validator.validate_hanzi("")

    assert not result.valid
    assert "required" in result.error_message.lower()


def test_validate_meanings_string():
    """Should validate comma-separated meanings."""
    validator = EntryValidator()
    result = validator.validate_meanings("hello, hi")

    assert result.valid
    assert result.value == "hello, hi"


def test_validate_meanings_list():
    """Should validate list of meanings."""
    validator = EntryValidator()
    result = validator.validate_meanings(["hello", "hi"])

    assert result.valid
    assert result.value == "hello, hi"


def test_validate_empty_meanings():
    """Should reject empty meanings."""
    validator = EntryValidator()
    result = validator.validate_meanings("")

    assert not result.valid
    assert "required" in result.error_message.lower()


def test_validate_category():
    """Should validate category."""
    validator = EntryValidator()
    result = validator.validate_category("greetings")

    assert result.valid
    assert result.value == "greetings"


def test_validate_empty_category():
    """Should allow empty category (defaults to unassigned)."""
    validator = EntryValidator()
    result = validator.validate_category("")

    assert result.valid


def test_validate_reserved_category():
    """Should reject reserved category names."""
    validator = EntryValidator()
    result = validator.validate_category("all")

    assert not result.valid
    assert "reserved" in result.error_message.lower()


def test_validate_against_valid_categories():
    """Should validate against provided category set."""
    validator = EntryValidator(valid_categories={"greetings", "verbs"})

    # Known category
    result1 = validator.validate_category("greetings")
    assert result1.valid

    # Unknown category
    result2 = validator.validate_category("unknown")
    assert not result2.valid
    assert "unknown" in result2.error_message.lower()


def test_validate_all_valid():
    """Should validate all fields successfully."""
    validator = EntryValidator()
    results = validator.validate_all(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )

    assert all(r.valid for r in results.values())
    assert set(results.keys()) == {"jyutping", "hanzi", "meanings", "category"}


def test_validate_all_with_errors():
    """Should return all validation errors."""
    validator = EntryValidator()
    results = validator.validate_all(
        jyutping="",
        hanzi="",
        meanings="",
        category="all"
    )

    assert not results["jyutping"].valid
    assert not results["hanzi"].valid
    assert not results["meanings"].valid
    assert not results["category"].valid


def test_is_valid_entry_true():
    """Should return True for valid entry."""
    validator = EntryValidator()
    assert validator.is_valid_entry(
        jyutping="nei5 hou2",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )


def test_is_valid_entry_false():
    """Should return False for invalid entry."""
    validator = EntryValidator()
    assert not validator.is_valid_entry(
        jyutping="",
        hanzi="你好",
        meanings="hello",
        category="greetings"
    )


def test_validation_result_ok():
    """Should create success result."""
    result = ValidationResult.ok("test", "value")
    assert result.valid
    assert result.field == "test"
    assert result.value == "value"
    assert result.error_message is None


def test_validation_result_error():
    """Should create error result."""
    result = ValidationResult.error("test", "value", "error msg")
    assert not result.valid
    assert result.field == "test"
    assert result.value == "value"
    assert result.error_message == "error msg"
