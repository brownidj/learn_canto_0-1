"""Domain rules for Category Manager.

This module is intentionally UI-free and side-effect free so it can be unit-tested.

It centralises:
- category placeholder detection
- Save button gating
- whether to show the "enter my own Hanzi" path
- choosing between two meanings lists
"""

from __future__ import annotations

from typing import Any, List


# Public constant used by UI and tests
CATEGORY_PLACEHOLDER_TEXT = "— choose category —"


def is_category_placeholder(category: Any) -> bool:
    """Return True if `category` is a UI placeholder/sentinel rather than a real choice."""
    if category is None or not isinstance(category, str):
        return True

    cat_norm = category.strip().lower()
    if not cat_norm:
        return True

    # Normalise dash variants so placeholder comparisons are stable.
    cat_norm = cat_norm.replace("—", "-").replace("–", "-")

    # Reject placeholder / sentinel patterns (tolerant)
    if "choose category" in cat_norm:
        return True

    if cat_norm in {"- choose category -", "choose category", "-- choose category --"}:
        return True

    return False


def save_enabled_gate(jyut: Any, hanzi: Any, meanings: Any, category: Any) -> bool:
    """Pure gate: return True if Save should be enabled for the given Add/Edit inputs."""
    if not isinstance(jyut, str) or not jyut.strip():
        return False

    if not isinstance(hanzi, str) or not hanzi.strip():
        return False

    if not isinstance(meanings, list) or not meanings:
        return False

    if not any(isinstance(m, str) and m.strip() for m in meanings):
        return False

    if is_category_placeholder(category):
        return False

    return True


def should_show_custom_hanzi_button(candidates: Any) -> bool:
    """Return True when the UI should show the 'None of these / enter my own Hanzi' path."""
    if candidates is None:
        return True

    if not isinstance(candidates, list):
        return True

    usable = [c for c in candidates if isinstance(c, str) and c.strip()]
    return len(usable) == 0


def prefer_meanings(primary: Any, fallback: Any) -> List[str]:
    """Prefer `primary` meanings if they contain any non-blank entries; otherwise use `fallback`."""
    out: List[str] = []

    if isinstance(primary, list):
        out = [m.strip() for m in primary if isinstance(m, str) and m.strip()]

    if out:
        return out

    if isinstance(fallback, list):
        return [m.strip() for m in fallback if isinstance(m, str) and m.strip()]

    return []

class HanziStyleIndex:
    """Lightweight loader for data/hanzi_style.yaml.

    UI-free (no Qt) and low-side-effect (reads YAML on demand).
    """

    def __init__(self, project_dir: str):
        self._project_dir = project_dir
        self._cache: dict[str, dict] = {}
        self._loaded = False

    def _candidate_paths(self) -> list[str]:
        base_dir = self._project_dir
        return [
            os.path.join(base_dir, "data", "hanzi_style.yaml"),
            os.path.join(os.path.dirname(base_dir), "data", "hanzi_style.yaml"),
        ]

    def load(self) -> dict:
        if self._loaded and isinstance(self._cache, dict) and self._cache:
            return self._cache

        self._loaded = True
        self._cache = {}

        path = None
        for p in self._candidate_paths():
            if os.path.exists(p):
                path = p
                break

        if not path:
            return self._cache

        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        except Exception:
            raw = {}

        if not isinstance(raw, dict):
            return self._cache

        cleaned: dict[str, dict] = {}
        for k, v in raw.items():
            hk = (str(k) or "").strip()
            if not hk:
                continue
            if isinstance(v, dict):
                cleaned[hk] = v
            else:
                cleaned[hk] = {"style": "unknown"}

        self._cache = cleaned
        return self._cache

    def style_for(self, hanzi: str) -> str:
        try:
            m = self.load()
            v = m.get(hanzi)
            if isinstance(v, dict):
                return str(v.get("style") or "unknown").strip().lower()
        except Exception:
            pass
        return "unknown"

    def is_colloquial(self, hanzi: str) -> bool:
        st = self.style_for(hanzi)
        return "colloquial" in (st or "")


class CandidateCurator:
    """Curates Hanzi candidates for display and selection."""

    def __init__(self, style_index: HanziStyleIndex, max_candidates: int):
        self._style_index = style_index
        self._max = int(max_candidates) if max_candidates else 10

    def curate(self, ranked: list[str]) -> list[str]:
        if not ranked:
            return []
        try:
            colloq = [hz for hz in ranked if self._style_index.is_colloquial(hz)]
        except Exception:
            colloq = []
        chosen = colloq if colloq else ranked
        return chosen[: self._max]


def abbr_for_source(src: str) -> str:
    s = (src or "").strip().lower()
    mapping = {
        "cccanto": "CC",
        "cedict": "CE",
        "andys_list": "AN",
        "builtin": "BL",
        "hkcancor": "HK",
        "subtitles": "SUB",
        "pycantonese": "PY",
        "reverse_manual": "RM",
        "reverse_cache": "RC",
        "tier2-char-ranked": "T2",
        "tier2": "T2",
    }
    if s in mapping:
        return mapping[s]
    s3 = "".join(ch for ch in s if ch.isalnum())[:3].upper()
    return s3 or "UNK"


__all__ = [
    "CATEGORY_PLACEHOLDER_TEXT",
    "is_category_placeholder",
    "save_enabled_gate",
    "should_show_custom_hanzi_button",
    "prefer_meanings",
    "HanziStyleIndex",
    "CandidateCurator",
    "abbr_for_source",
]