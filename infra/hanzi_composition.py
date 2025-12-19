from __future__ import annotations

"""Tier-2 Hanzi candidate composition and shortlisting.

This module is part of the infrastructure layer.

Responsibilities:
- Compose Hanzi candidates from a Jyutping phrase using a Unihan char->readings map.
- Provide a deterministic shortlisting helper for UI orchestration.

Important:
- This module must remain Qt-free.
- This module must not import from `domain.*`.
"""

from itertools import product
from typing import Dict, List, Tuple


def _is_cjk(ch: str) -> bool:
    if not isinstance(ch, str) or len(ch) != 1:
        return False
    try:
        cp = ord(ch)
    except Exception:
        return False
    # Common CJK Unified Ideographs + Extension A (broad, safe).
    return (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF)


# Note: cap_per_syl increased to 200 and deterministic ordering added so common pairs
# like 伯伯 (baak3 baak3) are not pruned by early caps. cap_combos still limits total output.
def compose_candidates_from_chars(jy: str, char_map: Dict[str, List[str]], cap_per_syl: int = 200, cap_combos: int = 300) -> List[str]:
    """Compose Hanzi candidates for a Jyutping phrase using a char->readings map.

    Strategy per syllable:
      1) Try exact tone match (e.g., 'baa4').
      2) If none, relax tone: match by base (strip digits) against any reading with same base.

    Then take a limited Cartesian product across syllables.

    Returns a list[str] of composed Hanzi strings.
    """
    if not jy:
        return []
    parts = " ".join(str(jy).strip().lower().split()).split()
    if not parts or not isinstance(char_map, dict) or not char_map:
        return []

    def _base(s: str) -> str:
        return "".join(c for c in s if not c.isdigit())

    def _match_syl(syl: str) -> List[str]:
        exact: List[str] = []
        relaxed: List[str] = []
        base = _base(syl)

        # collect all exact matches first (deterministic order)
        for ch in sorted((char_map or {}).keys()):
            if not _is_cjk(ch):
                continue
            try:
                readings = char_map.get(ch) or []
                if syl in readings:
                    exact.append(ch)
            except Exception:
                continue
        if exact:
            return exact[:cap_per_syl]

        # tone-relaxed fallback (deterministic order)
        for ch in sorted((char_map or {}).keys()):
            if not _is_cjk(ch):
                continue
            try:
                readings = char_map.get(ch) or []
                for r in readings:
                    if _base(str(r)) == base:
                        relaxed.append(ch)
                        break
            except Exception:
                continue
        return relaxed[:cap_per_syl]

    per: List[List[str]] = []
    for syl in parts:
        bucket = _match_syl(syl)
        if not bucket:
            return []
        per.append(bucket)

    out: List[str] = []
    seen: set[str] = set()
    for tup in product(*per):
        hz = "".join(tup)
        if hz and hz not in seen:
            out.append(hz)
            seen.add(hz)
            if len(out) >= cap_combos:
                break
    return out


def shortlist_candidates(*, jyut: str, combos: List[str], top_n: int = 10) -> List[Tuple[str, int]]:
    """Deterministically rank composed candidates.

    This is an infra-level heuristic intended for Tier-2 fallback only.
    It must not affect domain scoring/ranking; it only helps the UI avoid
    presenting an unbounded/unordered list.

    Returns: list[(hanzi, score_int)] sorted by score descending, then hanzi.

    Current scoring (simple, stable):
    - Prefer candidates whose character count matches the syllable count.
    - Prefer all-CJK candidates.
    - Prefer shorter (within same syllable count) as a mild tie-break.
    """
    try:
        syls = " ".join(str(jyut).strip().lower().split()).split()
        n_syl = len(syls)
    except Exception:
        n_syl = 0

    scored: List[Tuple[str, int]] = []
    for hz in (combos or []):
        s = str(hz)
        if not s:
            continue
        score = 0

        # Length match to syllable count is a strong signal.
        try:
            if n_syl > 0 and len(s) == n_syl:
                score += 100
        except Exception:
            pass

        # All CJK is a moderate signal.
        try:
            if all(_is_cjk(ch) for ch in s):
                score += 20
        except Exception:
            pass

        # Mild preference for shorter strings (within same match bucket).
        try:
            score -= max(0, len(s) - max(n_syl, 1))
        except Exception:
            pass

        scored.append((s, int(score)))

    scored.sort(key=(lambda t: (-t[1], t[0])))
    try:
        lim = int(top_n)
    except Exception:
        lim = 10
    return scored[: max(0, lim)]