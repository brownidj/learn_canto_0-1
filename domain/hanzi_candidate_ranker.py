"""Meaning-aware candidate reranking."""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional, Sequence, Mapping

logger = logging.getLogger(__name__)


def rerank_candidates_with_meanings(
    cands: Sequence[tuple[str, str, float]],
    *,
    meanings_for_hanzi: Callable[[str], Sequence[str]],
    active_category: str = "",
    category_profiles: Optional[Mapping[str, Mapping[str, float]]] = None,
    hk_freq_map: Optional[Mapping[str, float]] = None,
    hk_colloquial: Optional[set[str]] = None,
    hk_attested: Optional[set[str]] = None,
) -> list[tuple[str, str, float]]:
    """Rerank (hanzi, source, freq) candidates using meanings-derived heuristics."""

    active_cat = (active_category or "").strip()
    profiles = category_profiles or {}

    token_re = re.compile(r"[a-z]+")

    def category_score_for_glosses(glosses: Sequence[str], cat_name: str) -> float:
        if not cat_name:
            return 0.0
        kw = profiles.get(cat_name) or profiles.get(str(cat_name).lower())
        if not isinstance(kw, Mapping) or not kw:
            return 0.0

        seen_tokens: set[str] = set()
        score = 0.0
        for g in glosses or []:
            text = str(g).lower()
            for tok in token_re.findall(text):
                if tok in seen_tokens:
                    continue
                seen_tokens.add(tok)
                try:
                    score += float(kw.get(tok, 0.0))
                except Exception:
                    continue

        try:
            logger.debug(
                "CategoryHint: active_cat='%s', gloss_tokens=%r, score=%.4f",
                cat_name,
                list(seen_tokens),
                score,
            )
        except Exception:
            pass

        return score

    def source_score(src: str) -> int:
        order = [
            "andys_list",
            "builtin",
            "hkcancor",
            "subtitles",
            "cccanto",
            "pycantonese",
            "tier2-char-ranked",
            "tier2",
            "tier2-char",
            "tier1",
        ]
        try:
            return len(order) - order.index(src)
        except Exception:
            return 0

    def split_clean(glosses: Sequence[str]) -> tuple[list[str], list[str]]:
        clean: list[str] = []
        tagged: list[str] = []
        for g in glosses or []:
            s = str(g)
            if ("[" in s and "]" in s) or ("(" in s and ")" in s):
                tagged.append(s)
            else:
                clean.append(s)
        return clean, tagged

    def register_score_from_resolved_glosses(glosses: Sequence[str]) -> int:
        if not glosses:
            return 1

        text = " ".join(str(g) for g in glosses).lower()

        yue_markers = ["[yue]", "[粵]", "[粵語]", " cantonese ", "(cantonese)", "(colloquial)"]
        is_yue = any(m in text for m in yue_markers)

        lit_markers = ["[lit]", " literary ", "(literary)", "(written)"]
        is_lit = any(m in text for m in lit_markers)

        if is_yue and not is_lit:
            return 2
        if is_yue and is_lit:
            return 2
        if (not is_yue) and is_lit:
            return 0
        return 1

    scored: list[tuple[tuple[float, int, int, int, int, int, int, int, int, int], tuple[str, str, float]]] = []

    has_hk = bool(hk_freq_map or hk_colloquial or hk_attested)
    hk_freq_map = hk_freq_map or {}
    hk_colloquial = hk_colloquial or set()
    hk_attested = hk_attested or set()

    for (hz, src, freq) in list(cands or []):
        try:
            glosses = list(meanings_for_hanzi(hz) or [])
        except Exception:
            glosses = []

        reg_score = register_score_from_resolved_glosses(glosses)
        cat_score = category_score_for_glosses(glosses, active_cat)

        clean, _tagged = split_clean(glosses)
        has_clean_phrase = 1 if clean else 0
        has_any_phrase = 1 if glosses and any("[char]" not in str(g) for g in glosses) else 0
        colloquial_bonus = 1 if (hz[:1] == "阿") else 0

        try:
            freq_i = int(freq or 0)
        except Exception:
            freq_i = 0

        hk_freq = 0
        try:
            hk_freq = int(hk_freq_map.get(hz, 0) or 0)
        except Exception:
            hk_freq = 0

        hk_col = 1 if hz in hk_colloquial else 0
        if has_hk:
            hk_known = 1 if hz in hk_attested else 0
        else:
            hk_known = 1

        score_tuple = (
            float(reg_score),
            int(cat_score > 0.0),
            hk_col,
            hk_known,
            has_clean_phrase,
            has_any_phrase,
            colloquial_bonus,
            hk_freq,
            freq_i,
            source_score(str(src)),
        )

        scored.append((score_tuple, (hz, src, float(freq or 0.0))))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [item for _s, item in scored]
