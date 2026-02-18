import pytest

from domain.jyutping_cue import cue_for_syllable, hint_for_syllable

pytestmark = pytest.mark.pure


def test_cue_for_syllable_basic():
    assert cue_for_syllable("hoi1") == "HOY¹"
    assert cue_for_syllable("nei5") == "NAY⁵"


def test_hint_for_syllable_examples():
    assert hint_for_syllable("hoi1") == "OY like “boy”"
    assert hint_for_syllable("nei5") == "AY like “say”"


def test_hint_for_syllable_checked_coda():
    assert hint_for_syllable("sik1") == "EE like “see”, checked -k"
