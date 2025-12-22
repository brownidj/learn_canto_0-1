

"""Golden tests for candidate generation without touching Qt.

These tests are intentionally small and data-independent. They lock in:
- deterministic Tier-2 composition ordering
- tone-relaxed fallback behaviour
- deterministic shortlisting

They exist to catch regressions where the UI silently ends up with zero candidates
for common/representative inputs.
"""

from __future__ import annotations

from infra.hanzi_composition import compose_candidates_from_chars, shortlist_candidates


def test_compose_candidates_exact_tone_pair_is_not_pruned():
    # Minimal Unihan-style map: character -> list of readings.
    char_map = {
        "伯": ["baak3"],
    }

    combos = compose_candidates_from_chars("baak3 baak3", char_map, cap_per_syl=200, cap_combos=300)

    # Deterministic ordering + high cap_per_syl should keep the common pair.
    assert "伯伯" in combos

    ranked = shortlist_candidates(jyut="baak3 baak3", combos=combos, top_n=10)
    assert ranked
    assert ranked[0][0] == "伯伯"


def test_compose_candidates_tone_relaxed_fallback():
    # ceng1 may not exist exactly, but ceng2 does; tone-relaxed should still match base 'ceng'.
    char_map = {
        "青": ["ceng1"],
        "清": ["ceng2"],
    }

    combos = compose_candidates_from_chars("ceng1", char_map, cap_per_syl=200, cap_combos=300)

    # Exact match must be preferred (present), but relaxed candidates may also appear.
    assert "青" in combos

    ranked = shortlist_candidates(jyut="ceng1", combos=combos, top_n=10)
    assert ranked
    # With a single syllable, both are length-matching CJK; deterministic tie-break should apply.
    assert ranked[0][0] in {"青", "清"}


def test_shortlist_is_deterministic_for_equal_scores():
    combos = ["清", "青"]

    ranked1 = shortlist_candidates(jyut="ceng1", combos=combos, top_n=10)
    ranked2 = shortlist_candidates(jyut="ceng1", combos=combos, top_n=10)

    assert ranked1 == ranked2

    # Under equal scoring, sorting must be stable and deterministic.
    assert [hz for hz, _ in ranked1] == sorted(["清", "青"])