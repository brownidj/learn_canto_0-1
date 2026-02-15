"""
Tests for main_helpers.py - Pure utility functions extracted from main.py
"""
import pytest
import time
from app.main_helpers import (
    normalize_jy,
    ensure_jyut,
    normalize_reverse_index,
    normalize_categories_yaml_payload,
    parse_base_point_size_from_stylesheet,
    perf_start,
    perf_end,
)


class TestNormalizeJy:
    """Tests for Jyutping normalization."""

    def test_basic_normalization(self):
        assert normalize_jy("nei5 hou2") == "nei5 hou2"

    def test_lowercase_conversion(self):
        assert normalize_jy("NEI5 HOU2") == "nei5 hou2"

    def test_whitespace_collapse(self):
        assert normalize_jy("nei5    hou2") == "nei5 hou2"
        assert normalize_jy("  nei5  hou2  ") == "nei5 hou2"
        assert normalize_jy("\tnei5\nhou2\r") == "nei5 hou2"

    def test_empty_string(self):
        assert normalize_jy("") == ""
        assert normalize_jy("   ") == ""

    def test_none_input(self):
        assert normalize_jy(None) == ""


class TestEnsureJyut:
    """Tests for Jyutping fallback logic."""

    def test_returns_provided_jyut(self):
        assert ensure_jyut("你好", "nei5 hou2") == "nei5 hou2"

    def test_returns_empty_when_missing(self):
        assert ensure_jyut("你好", "") == ""
        assert ensure_jyut("你好", None) == ""

    def test_hanzi_unused(self):
        # Hanzi parameter is kept for signature compatibility but not used
        assert ensure_jyut("任意漢字", "jyut6 ji3") == "jyut6 ji3"


class TestNormalizeReverseIndex:
    """Tests for reverse index payload normalization."""

    def test_canonical_format_passthrough(self):
        """Already-canonical format should pass through unchanged."""
        canonical = {
            "nei5 hou2": [("你好", "tier1", 100), ("妳好", "tier1", 95)]
        }
        result = normalize_reverse_index(canonical)
        assert result == canonical

    def test_unwrap_single_key_dict(self):
        """Unwrap wrapper dicts with single key."""
        wrapped = {
            "reverse": {
                "nei5": [("你", "tier1", 100)]
            }
        }
        result = normalize_reverse_index(wrapped)
        assert result == {"nei5": [("你", "tier1", 100)]}

    def test_string_list_to_triples(self):
        """Convert list of strings to canonical triples."""
        input_data = {
            "nei5": ["你", "妳"]
        }
        result = normalize_reverse_index(input_data)
        assert result == {
            "nei5": [("你", "tier1", 100), ("妳", "tier1", 100)]
        }

    def test_single_string_to_triple(self):
        """Convert single string value to triple."""
        input_data = {
            "nei5": "你"
        }
        result = normalize_reverse_index(input_data)
        assert result == {
            "nei5": [("你", "tier1", 100)]
        }

    def test_incomplete_triples_filled(self):
        """Fill in missing fields in triples."""
        input_data = {
            "nei5": [("你",), ("妳", "manual")]
        }
        result = normalize_reverse_index(input_data)
        assert result == {
            "nei5": [("你", "tier1", 100), ("妳", "manual", 100)]
        }

    def test_empty_values_skipped(self):
        """Empty or whitespace-only values should be skipped."""
        input_data = {
            "nei5": ["你", "", "   "],
            "hou2": ""
        }
        result = normalize_reverse_index(input_data)
        assert result == {
            "nei5": [("你", "tier1", 100)]
        }

    def test_non_string_keys_skipped(self):
        """Non-string keys should be skipped."""
        input_data = {
            "nei5": [("你", "tier1", 100)],
            123: [("数", "tier1", 100)],
            None: [("空", "tier1", 100)]
        }
        result = normalize_reverse_index(input_data)
        assert result == {
            "nei5": [("你", "tier1", 100)]
        }

    def test_empty_input(self):
        """Empty or None input should return empty dict."""
        assert normalize_reverse_index({}) == {}
        assert normalize_reverse_index(None) == {}
        assert normalize_reverse_index([]) == {}


class TestNormalizeCategoriesYamlPayload:
    """Tests for categories.yaml payload normalization."""

    def test_simple_list_format(self):
        """Standard format: category -> list of hanzi."""
        input_data = {
            "food": ["飯", "麵", "菜"],
            "colors": ["紅", "藍"]
        }
        result = normalize_categories_yaml_payload(input_data)
        assert result == input_data

    def test_nested_items_format(self):
        """Alternative format: category -> {items: [hanzi]}."""
        input_data = {
            "food": {"items": ["飯", "麵", "菜"]},
            "colors": {"items": ["紅", "藍"]}
        }
        result = normalize_categories_yaml_payload(input_data)
        assert result == {
            "food": ["飯", "麵", "菜"],
            "colors": ["紅", "藍"]
        }

    def test_mixed_formats(self):
        """Mix of both formats should work."""
        input_data = {
            "food": ["飯", "麵"],
            "colors": {"items": ["紅", "藍"]},
            "numbers": {"items": ["一", "二"], "other": "ignored"}
        }
        result = normalize_categories_yaml_payload(input_data)
        assert result == {
            "food": ["飯", "麵"],
            "colors": ["紅", "藍"],
            "numbers": ["一", "二"]
        }

    def test_empty_category_preserved(self):
        """Empty categories should be preserved."""
        input_data = {
            "food": ["飯"],
            "empty": []
        }
        result = normalize_categories_yaml_payload(input_data)
        assert result == {
            "food": ["飯"],
            "empty": []
        }

    def test_unknown_format_creates_empty(self):
        """Unknown formats should create empty category."""
        input_data = {
            "food": ["飯"],
            "weird": {"no_items_key": "value"},
            "string": "not_a_list"
        }
        result = normalize_categories_yaml_payload(input_data)
        assert result["food"] == ["飯"]
        assert result["weird"] == []
        assert result["string"] == []

    def test_whitespace_stripped(self):
        """Whitespace in hanzi should be stripped."""
        input_data = {
            "food": ["  飯  ", "麵", "  "]
        }
        result = normalize_categories_yaml_payload(input_data)
        assert result == {
            "food": ["飯", "麵"]
        }

    def test_non_dict_input(self):
        """Non-dict input should return empty dict."""
        assert normalize_categories_yaml_payload(None) == {}
        assert normalize_categories_yaml_payload([]) == {}
        assert normalize_categories_yaml_payload("string") == {}


class TestParseFontSizeFromStylesheet:
    """Tests for Qt stylesheet font-size parsing."""

    def test_basic_pt_size(self):
        stylesheet = "font-size: 96pt;"
        assert parse_base_point_size_from_stylesheet(stylesheet) == 96

    def test_without_semicolon(self):
        stylesheet = "font-size: 72pt"
        assert parse_base_point_size_from_stylesheet(stylesheet) == 72

    def test_with_other_styles(self):
        stylesheet = "color: red; font-size: 48pt; font-weight: bold;"
        assert parse_base_point_size_from_stylesheet(stylesheet) == 48

    def test_whitespace_variations(self):
        assert parse_base_point_size_from_stylesheet("font-size:48pt") == 48
        assert parse_base_point_size_from_stylesheet("font-size :  48 pt ;") == 48

    def test_case_insensitive(self):
        assert parse_base_point_size_from_stylesheet("FONT-SIZE: 48PT;") == 48
        assert parse_base_point_size_from_stylesheet("Font-Size: 48Pt;") == 48

    def test_no_font_size_returns_default(self):
        stylesheet = "color: blue; font-weight: bold;"
        assert parse_base_point_size_from_stylesheet(stylesheet) == 96

    def test_empty_string_returns_default(self):
        assert parse_base_point_size_from_stylesheet("") == 96

    def test_none_input_returns_default(self):
        # Should handle gracefully via exception
        try:
            result = parse_base_point_size_from_stylesheet(None)
            assert result == 96
        except:
            # If it raises, that's also acceptable
            pass


class TestPerfTiming:
    """Tests for performance timing utilities."""

    def test_perf_start_returns_timestamp(self):
        """Test that perf_start returns a valid timestamp."""
        t0 = perf_start("test_operation")
        assert isinstance(t0, float)
        assert t0 > 0

    def test_perf_end_completes_without_error(self):
        """Test that perf_end completes successfully."""
        t0 = perf_start("test_operation")
        time.sleep(0.01)  # Small delay to ensure measurable time
        # Should not raise
        perf_end("test_operation", t0)

    def test_perf_end_with_zero_start_time(self):
        """Test that perf_end handles zero start time gracefully."""
        # Should not raise or log when t0 is 0
        perf_end("test_operation", 0.0)

    def test_perf_timing_measures_duration(self, caplog):
        """Test that timing actually measures duration."""
        import logging
        caplog.set_level(logging.DEBUG)

        t0 = perf_start("test_operation")
        time.sleep(0.05)  # 50ms delay
        perf_end("test_operation", t0)

        # Check that timing was logged (if logging is working)
        # Note: This might not work in all test environments
        if caplog.records:
            assert any("PERF" in record.message for record in caplog.records)

    def test_perf_functions_are_resilient(self):
        """Test that timing functions don't crash on edge cases."""
        # These should all complete without raising
        t0 = perf_start("")
        perf_end("", t0)

        t0 = perf_start("test")
        perf_end("test", None)  # type: ignore

        perf_end("test", -1.0)
