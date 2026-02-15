"""Duplicate detection helpers (pure domain)."""

from __future__ import annotations

from domain.jyutping_validation import normalize_jyutping


def find_duplicate_jyutping(vocab: dict, jyutping: str) -> tuple[bool, str | None]:
    """Check if Jyutping already exists in vocab.

    Returns:
        (is_duplicate, existing_hanzi)
    """
    if not jyutping:
        return False, None

    if not isinstance(vocab, dict):
        return False, None

    normalized_jy = normalize_jyutping(jyutping)

    for hanzi, entry in vocab.items():
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        existing_jy = entry[1]
        if normalize_jyutping(existing_jy) == normalized_jy:
            return True, hanzi

    return False, None
