

"""
Pure ambiguity rules tests for category/domain logic.

These tests ensure that ambiguous Hanzi candidate situations are detected
cleanly and consistently, without any UI dependencies.
"""

import pytest

from domain.category_rules import (
    should_show_custom_hanzi_button,
    prefer_meanings,
)


def test_no_candidates_triggers_custom_hanzi_path():
    """If there are no usable candidates, the UI should offer manual Hanzi entry."""
    assert should_show_custom_hanzi_button([])
    assert should_show_custom_hanzi_button(None)
    assert should_show_custom_hanzi_button(["", "  "])


def test_single_candidate_does_not_trigger_custom_hanzi():
    """A single valid candidate should not be treated as ambiguous."""
    assert not should_show_custom_hanzi_button(["白"])


def test_multiple_candidates_does_not_force_custom_hanzi():
    """
    Multiple candidates alone are not ambiguity.
    Ambiguity is handled elsewhere (ranking / user choice),
    not by forcing manual Hanzi.
    """
    assert not should_show_custom_hanzi_button(["白", "百"])


def test_prefer_meanings_primary_wins_when_non_empty():
    primary = ["white", "bright"]
    fallback = ["pale"]
    assert prefer_meanings(primary, fallback) == ["white", "bright"]


def test_prefer_meanings_fallback_used_when_primary_empty():
    primary = ["", "  "]
    fallback = ["white"]
    assert prefer_meanings(primary, fallback) == ["white"]


def test_prefer_meanings_handles_none_gracefully():
    assert prefer_meanings(None, ["white"]) == ["white"]
    assert prefer_meanings(None, None) == []