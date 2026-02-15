"""Pure Jyutping validation utilities.

This module must contain no UI or orchestration logic.
"""

from __future__ import annotations

import re


# Conservative Jyutping syllable pattern: letters followed by a final tone digit.
# Accept 1–6 as standard and allow 0 as a pragmatic "neutral/unknown" tone used in some datasets.
_SYLLABLE_RE = re.compile(r"^[a-z]+[0-6]$", re.IGNORECASE)


def _split_syllables(text: str) -> list[str]:
    # Treat hyphen as a separator (e.g. "zi6-ji2")
    text = text.replace("-", " ")
    return [p for p in re.split(r"\s+", text) if p]


def validate_jyut_syllables(jy: str) -> tuple[bool, str | None]:
    """Validate that a Jyutping string is composed of tone-marked syllables.

    Returns:
        (ok, reason): ok=True if valid; otherwise ok=False with a human-readable reason.

    Notes:
        - This is a *pure* check intended for detailed 'why invalid' messaging.
        - Attestation/structural allowances are handled by domain.category_rules.attested_or_structural_ok.
    """
    if jy is None:
        return False, "Jyutping is missing"

    text = str(jy).strip()
    if not text:
        return False, "Jyutping is empty"

    parts = _split_syllables(text)
    if not parts:
        return False, "Jyutping is empty"

    for i, part in enumerate(parts, start=1):
        token = part.strip()
        if not token:
            continue

        # Common punctuation sometimes appears in copied text; reject explicitly with a clear message.
        if any(ch in token for ch in [",", ".", ";", ":", "!", "?", "（", "）", "(", ")"]):
            return False, "Unexpected punctuation in syllable %d: %s" % (i, token)

        # If any digit exists but the token doesn't match, provide a more specific tone message.
        if re.search(r"\d", token) and not _SYLLABLE_RE.match(token):
            return False, "Tone digit must be at the end of syllable %d: %s" % (i, token)

        if not _SYLLABLE_RE.match(token):
            # Targeted message about missing tone digit, since this is the most frequent issue.
            if re.match(r"^[A-Za-z]+$", token):
                return False, "Missing tone digit (0–6) in syllable %d: %s" % (i, token)
            return False, "Invalid Jyutping syllable %d: %s" % (i, token)

    return True, None


__all__ = [
    "normalize_jyutping",
    "validate_jyut_syllables",
]


def normalize_jyutping(jy: str) -> str:
    """Normalize Jyutping: trim, lowercase, collapse whitespace.

    This is intentionally conservative and does not alter tone digits.
    """
    text = (jy or "").strip().lower()
    return " ".join(text.split())
