

import re


def normalize_jyut(text: str | None) -> str:
    """Return a canonical Jyutping key for reverse lookups.

    Rules (pure, deterministic):
      - None -> ""
      - strip leading/trailing whitespace
      - lowercase
      - treat common separators as syllable boundaries
      - normalise dash variants (—, –) and then treat hyphens as boundaries
      - collapse repeated whitespace to a single space

    Validation (e.g., tone digits, legal syllables) is intentionally *not* handled here;
    that belongs in the UI/validation layer.
    """
    if not text:
        return ""

    s = text.strip().lower()

    # Normalise dash variants
    s = s.replace("—", "-").replace("–", "-")

    # Treat common separators as boundaries
    # - hyphen is common when people type multi-syllable forms
    # - slash / middle dot / underscore appear in copied data sometimes
    for ch in ("-", "/", "·", "_", "\t", "\n", "\r"):
        s = s.replace(ch, " ")

    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()

    return s


def test_normalize_none_and_empty():
    assert normalize_jyut(None) == ""
    assert normalize_jyut("") == ""
    assert normalize_jyut("   ") == ""


def test_normalize_whitespace_and_case():
    assert normalize_jyut("  FAN2   HUNG4 ") == "fan2 hung4"
    assert normalize_jyut("Fe1") == "fe1"


def test_normalize_dash_variants_and_hyphenated():
    assert normalize_jyut("fan2—hung4") == "fan2 hung4"
    assert normalize_jyut("fan2–hung4") == "fan2 hung4"
    assert normalize_jyut("fan2-hung4") == "fan2 hung4"


def test_normalize_other_separators():
    assert normalize_jyut("fan2/hung4") == "fan2 hung4"
    assert normalize_jyut("fan2·hung4") == "fan2 hung4"
    assert normalize_jyut("fan2_hung4") == "fan2 hung4"


def test_normalize_multisyllable_phrase_stability():
    s = "jat1 gin6 waan4 jat1 gin6"
    assert normalize_jyut(s) == s
    assert normalize_jyut("  jat1  gin6\nwaan4\tjat1  gin6 ") == s


def test_normalize_does_not_try_to_validate():
    # This is intentionally not rejected here; validation happens elsewhere.
    assert normalize_jyut("fan hung") == "fan hung"
    assert normalize_jyut("fan2  hung") == "fan2 hung"