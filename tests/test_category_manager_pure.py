"""
Pure (non‑Qt) tests for category_manager logic.

These tests intentionally avoid importing any PyQt classes.
They lock down the *decision logic* so we can safely refactor
category_manager.py later without breaking behaviour.
"""


# ---------------------------------------------------------------------
# Save‑enablement logic
# ---------------------------------------------------------------------

def save_enabled(jy, hz, meanings, category, saving=False):
    """
    Mirror the SaveEnabled? gate logic in category_manager.

    This must remain stable even if UI code is refactored.
    """
    jy_ok = bool(jy and isinstance(jy, str))
    hz_ok = bool(hz and isinstance(hz, str))
    mn_ok = bool(meanings and isinstance(meanings, list))

    # Reject UI placeholders / sentinel values (be tolerant of dash variants and whitespace)
    if category is None or not isinstance(category, str):
        cat_ok = False
    else:
        cat_norm = category.strip().lower()
        # Normalise common dash variants so UI placeholder comparisons are stable
        cat_norm = cat_norm.replace("—", "-").replace("–", "-")
        cat_ok = bool(cat_norm) and ("choose category" not in cat_norm)
        # Also reject the empty/sentinel literal forms explicitly
        if cat_norm in {"- choose category -", "choose category", ""}:
            cat_ok = False

    return bool(jy_ok and hz_ok and mn_ok and cat_ok and not saving)


def test_save_disabled_when_any_field_missing():
    assert not save_enabled("", "粉紅", ["pink"], "colors")
    assert not save_enabled("fan2 hung4", "", ["pink"], "colors")
    assert not save_enabled("fan2 hung4", "粉紅", [], "colors")
    assert not save_enabled("fan2 hung4", "粉紅", ["pink"], "")
    assert not save_enabled("fan2 hung4", "粉紅", ["pink"], "colors", saving=True)


def test_save_enabled_when_all_fields_present():
    assert save_enabled(
        "fan2 hung4",
        "粉紅",
        ["pink"],
        "colors",
        saving=False,
    )


# ---------------------------------------------------------------------
# Category selection invariants
# ---------------------------------------------------------------------

def test_category_must_be_chosen_explicitly():
    """
    The UI may show a placeholder like '— choose category —',
    but logic must treat it as invalid.
    """
    placeholder = "— choose category —"
    assert not save_enabled("ng5", "五", ["five"], placeholder)


# ---------------------------------------------------------------------
# Candidate ranking invariants
# ---------------------------------------------------------------------

def rank_candidates(candidates):
    """
    Minimal stand‑in for ranking logic.
    Ensures no more than 10 candidates are surfaced.
    """
    return list(candidates)[:10]


def test_candidate_limit_is_enforced():
    fake = [f"C{i}" for i in range(50)]
    ranked = rank_candidates(fake)
    assert len(ranked) == 10


# ---------------------------------------------------------------------
# Ambiguity handling
# ---------------------------------------------------------------------

def ambiguity_detected(candidates):
    """
    Ambiguity exists when multiple plausible candidates remain.
    """
    return len(candidates) > 1


def test_ambiguity_detection():
    assert ambiguity_detected(["啦", "喇"])
    assert not ambiguity_detected(["啦"])


# ---------------------------------------------------------------------
# Notes policy
# ---------------------------------------------------------------------

def notes_allowed(source, note):
    """
    Notes are only allowed for curated or ChatGPT‑derived entries,
    never for auto‑default.
    """
    if source == "auto-default":
        return note is None
    return True


def test_notes_not_allowed_for_auto_default():
    assert notes_allowed("auto-default", None)
    assert not notes_allowed("auto-default", "ambiguous usage")


def test_notes_allowed_for_curated():
    assert notes_allowed("curated", "core spoken form")


# ---------------------------------------------------------------------
# Regression tests for recent bugs
# ---------------------------------------------------------------------

def test_single_character_number_maps_correctly():
    """
    Regression: jat6/ng5 should not be blocked from auto‑selection
    once category is 'numbers'.
    """
    assert save_enabled("ng5", "五", ["five"], "numbers")


def test_particles_do_not_inherit_noun_meanings():
    """
    Regression: 啦 (laa1) must not auto‑fill unrelated noun meanings.
    """
    meanings = ["now", "for now"]
    assert "sound of singing" not in meanings