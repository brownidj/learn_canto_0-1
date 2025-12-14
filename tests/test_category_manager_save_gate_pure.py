import pytest

from domain.category_rules import save_enabled_gate as save_enabled
from utils.utils import is_category_placeholder
from utils.utils import should_show_custom_hanzi_button
from utils.utils import prefer_meanings


# ----------------------------
# Tests
# ----------------------------


@pytest.mark.parametrize(
    "placeholder",
    [
        "— choose category —",
        "- choose category -",
        "– choose category –",
        "Choose Category",
        "  — choose category —  ",
        "-- choose category --",
        "please CHOOSE category",
    ],
)

def test_placeholder_category_disables_save(placeholder: str):
    assert not save_enabled("ng5", "五", ["five"], placeholder)


@pytest.mark.parametrize("bad_cat", [None, "", "   "])

def test_missing_category_disables_save(bad_cat):
    assert not save_enabled("ng5", "五", ["five"], bad_cat)


@pytest.mark.parametrize(
    "meanings",
    [
        [],
        [""],
        ["   "],
        ["", "  "],
    ],
)

def test_meanings_must_have_nonblank_entry(meanings):
    assert not save_enabled("ng5", "五", meanings, "numbers")


@pytest.mark.parametrize("jyut", ["", "   ", None])

def test_jyut_required(jyut):
    assert not save_enabled(jyut, "五", ["five"], "numbers")


@pytest.mark.parametrize("hanzi", ["", "   ", None])

def test_hanzi_required(hanzi):
    assert not save_enabled("ng5", hanzi, ["five"], "numbers")


def test_unassigned_is_valid_choice_when_explicitly_chosen():
    # We still allow the user to choose unassigned explicitly.
    assert save_enabled("ng5", "五", ["five"], "unassigned")


def test_normal_category_enables_save():
    assert save_enabled("ng5", "五", ["five"], "numbers")


def test_category_whitespace_is_trimmed():
    assert save_enabled("ng5", "五", ["five"], "  numbers  ")


def test_category_dash_variants_normalised():
    # These should be treated as placeholder because they include the phrase.
    assert not save_enabled("ng5", "五", ["five"], "— CHOOSE CATEGORY —")


def test_multiple_meanings_ok():
    assert save_enabled("ng5", "五", ["five", "the number 5"], "numbers")


def test_meanings_with_some_blank_ok_if_any_nonblank():
    assert save_enabled("ng5", "五", ["", "five", "  "], "numbers")


def test_regression_category_placeholder_leakage_disables_save():
    # Previously, placeholder text could accidentally be treated as a valid category.
    assert is_category_placeholder("— choose category —")
    assert not save_enabled("ng5", "五", ["five"], "— choose category —")


def test_regression_auto_none_of_these_should_not_trigger_when_candidates_exist():
    # Guard against the 'auto-None-of-these' behavior: when candidates exist, we should not
    # present the custom-Hanzi path as the default.
    assert not should_show_custom_hanzi_button(["粉紅", "紅色"])


def test_regression_show_none_of_these_when_no_candidates():
    assert should_show_custom_hanzi_button([])
    assert should_show_custom_hanzi_button(["", "  "])


def test_regression_wrong_meanings_must_not_overwrite_primary_glosses():
    # Guard against 'meaning overwrite' where fallback meanings replace better glosses.
    primary = ["now", "for now", "up to now"]
    fallback = ["(onom.) sound of singing, cheering etc", "(phonetic)", "(dialect) to chat"]
    assert prefer_meanings(primary, fallback) == primary