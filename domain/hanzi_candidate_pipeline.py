"""Hanzi candidate pipeline.

This module centralises the Hanzi-candidate generation steps that were previously
spread across `category_manager.py`.

Design goals
- UI-free (no Qt imports)
- Dependency-injected (callers pass maps / callables)
- Small, readable stages with clear contracts

It is intentionally conservative:
- Tier-2 (Unihan char-map composition) is only applied to *single-syllable* jyutping
  to avoid bogus one-character suggestions for phrases.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Mapping

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HanziCandidate:
    """A single Hanzi candidate with provenance."""

    hanzi: str
    source: str  # e.g. "tier1", "tier2-char", "manual", "vocab", "cedict"
    freq: float = 0.0
    glosses: tuple[str, ...] = ()

    def with_glosses(self, glosses: Sequence[str]) -> "HanziCandidate":
        clean = tuple([g.strip() for g in glosses if isinstance(g, str) and g.strip()])
        return HanziCandidate(self.hanzi, self.source, self.freq, clean)


def _norm_space(text: str) -> str:
    return " ".join(text.split())


def _split_syllables(jy_norm: str) -> list[str]:
    jy_norm = _norm_space(jy_norm)
    return jy_norm.split() if jy_norm else []


def _coerce_candidates(raw: object, default_source: str) -> list[HanziCandidate]:
    """Normalise diverse candidate return shapes into `HanziCandidate` objects.

    Supported shapes:
    - ["漢", "字", ...]
    - [("漢", "src", 1.23), ...]
    - [("漢", "src"), ...]
    - [("漢", 1.23), ...]  -> uses default_source
    """

    if raw is None:
        return []

    out: list[HanziCandidate] = []

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(HanziCandidate(item.strip(), default_source, 0.0))
                continue

            if isinstance(item, (tuple, list)) and len(item) >= 1:
                h = item[0]
                if not isinstance(h, str) or not h.strip():
                    continue
                hanzi = h.strip()

                src = default_source
                freq = 0.0

                if len(item) >= 2:
                    if isinstance(item[1], str) and item[1].strip():
                        src = item[1].strip()
                    elif isinstance(item[1], (int, float)):
                        freq = float(item[1])

                if len(item) >= 3 and isinstance(item[2], (int, float)):
                    freq = float(item[2])

                out.append(HanziCandidate(hanzi, src, freq))

    return out


def _dedupe_keep_first(cands: Sequence[HanziCandidate]) -> list[HanziCandidate]:
    seen: set[str] = set()
    out: list[HanziCandidate] = []
    for c in cands:
        if c.hanzi in seen:
            continue
        seen.add(c.hanzi)
        out.append(c)
    return out


def _simple_rank(cands: Sequence[HanziCandidate]) -> list[HanziCandidate]:
    """A stable, conservative ordering.

    - higher freq first
    - then source name (to stabilise)
    - then hanzi

    Note: callers can inject a richer ranker/curator; this is a safe fallback.
    """

    return sorted(
        list(cands),
        key=lambda c: (-float(c.freq or 0.0), str(c.source), c.hanzi),
    )


def rerank_candidates_with_meanings(
        cands: Sequence[tuple[str, str, float]],
        *,
        meanings_for_hanzi: Callable[[str], Sequence[str]],
        active_category: str = "",
        category_profiles: Optional[Mapping[str, Mapping[str, float]]] = None,
) -> list[tuple[str, str, float]]:
    """Rerank (hanzi, source, freq) candidates using meanings-derived heuristics.

    This is a direct, UI-free extraction of the CategoryManager heuristics.

    Heuristics (descending priority):
      0) Prefer Cantonese/colloquial (`yue`) register, then neutral, then literary-only.
      1) Slight nudge toward the active category based on token overlap with a
         data-driven category profile.
      2) Prefer candidates with "clean" glosses (no bracket tags / parentheses).
      3) Prefer candidates with any phrase-level gloss.
      4) Prefer colloquial forms such as 阿…
      5) Higher frequency.
      6) Stronger sources.

    Returns a new list; stable for ties.
    """

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
            return 1  # neutral by default

        text = " ".join(str(g) for g in glosses).lower()

        # Cantonese/colloquial markers
        yue_markers = ["[yue]", "[粵]", "[粵語]", " cantonese ", "(cantonese)", "(colloquial)"]
        is_yue = any(m in text for m in yue_markers)

        # Literary/written markers
        lit_markers = ["[lit]", " literary ", "(literary)", "(written)"]
        is_lit = any(m in text for m in lit_markers)

        if is_yue and not is_lit:
            return 2
        if is_yue and is_lit:
            return 2
        if (not is_yue) and is_lit:
            return 0
        return 1

    scored: list[tuple[tuple[float, int, int, int, int, int, int], tuple[str, str, float]]] = []

    for (hz, src, freq) in list(cands or []):
        try:
            glosses = list(meanings_for_hanzi(hz) or [])
        except Exception:
            glosses = []

        reg_score = register_score_from_resolved_glosses(glosses)
        cat_score = category_score_for_glosses(glosses, active_cat)

        clean, _tagged = split_clean(glosses)
        has_clean_phrase = 1 if clean else 0

        # phrase-level gloss: anything not explicitly a per-character tag
        has_any_phrase = 1 if glosses and any("[char]" not in str(g) for g in glosses) else 0

        colloquial_bonus = 1 if (hz[:1] == "阿") else 0

        try:
            freq_i = int(freq or 0)
        except Exception:
            freq_i = 0

        score_tuple = (
            float(reg_score),
            int(cat_score > 0.0),
            has_clean_phrase,
            has_any_phrase,
            colloquial_bonus,
            freq_i,
            source_score(str(src)),
        )

        scored.append((score_tuple, (hz, src, float(freq or 0.0))))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [item for _s, item in scored]


class HanziCandidatePipeline:
    """Orchestrates candidate generation for a jyutping string."""

    def __init__(
            self,
            *,
            normalize_jyutping: Callable[[str], str],
            # Tier-1 input (either a callable or a dict-based reverse index)
            tier1_reverse_candidates: Optional[Callable[[str], object]] = None,
            reverse_index: Optional[dict] = None,
            # Tier-2 composer: (jy_norm, char_map) -> list[tuple[str, str, float]] | list[str]
            tier2_compose: Optional[Callable[[str, dict], object]] = None,
            tier2_shortlist: Optional[Callable[[object], object]] = None,
            char_map: Optional[dict] = None,
            # Meaning/gloss sources (optional)
            cc_glosses_for: Optional[Callable[[str], Sequence[str]]] = None,
            cedict_meanings_for: Optional[Callable[[str], Sequence[str]]] = None,
            gloss_cleaner: Optional[Callable[[Sequence[str]], Sequence[str]]] = None,
            # Optional curator (final truncation / ordering)
            curate: Optional[Callable[[Sequence[HanziCandidate]], Sequence[HanziCandidate]]] = None,
            max_candidates: int = 10,
            **_ignored: object,
    ):
        self._normalize = normalize_jyutping

        # Backwards-compatible tier-1 wiring:
        # - prefer explicit callable
        # - otherwise, if a dict reverse_index is provided, use it as a lookup
        if tier1_reverse_candidates is None and isinstance(reverse_index, dict):
            def _tier1_from_index(jy_norm: str) -> object:
                try:
                    return reverse_index.get(jy_norm, [])
                except Exception:
                    return []

            self._tier1 = _tier1_from_index
        else:
            self._tier1 = tier1_reverse_candidates

        self._tier2_compose = tier2_compose
        self._tier2_shortlist = tier2_shortlist
        self._char_map = char_map or {}
        self._cc_glosses_for = cc_glosses_for
        self._cedict_meanings_for = cedict_meanings_for
        self._gloss_cleaner = gloss_cleaner
        self._curate = curate
        try:
            m = int(max_candidates)
        except Exception:
            m = 10
        self._max = m if m > 0 else 10

    def run(self, jyut: str, *, manual_hanzi_mode: bool = False) -> list[tuple[str, str, float]]:
        """Compatibility wrapper.

        Returns the candidate list in the legacy tuple shape: (hanzi, source, freq).
        """
        cands = self.candidates_for(jyut, manual_hanzi_mode=manual_hanzi_mode)
        return [(c.hanzi, c.source, float(c.freq or 0.0)) for c in cands]

    def candidates_for(self, jyut: str, *, manual_hanzi_mode: bool = False) -> list[HanziCandidate]:
        """Return ranked Hanzi candidates for the given Jyutping.

        If `manual_hanzi_mode` is True, returns an empty list (caller should not
        overwrite the user's manual entry).
        """

        if manual_hanzi_mode:
            logger.debug("HanziCandidatePipeline: manual Hanzi mode; skipping auto candidates")
            return []

        jy_norm = self._normalize(jyut or "")
        syllables = _split_syllables(jy_norm)
        n_syllables = len(syllables)

        # ---- Stage A: Tier-1 reverse lookup (phrase-aware) ----
        raw_tier1: object = []
        if callable(self._tier1):
            try:
                raw_tier1 = self._tier1(jy_norm) or []
            except Exception:
                raw_tier1 = []

        cands = _coerce_candidates(raw_tier1, default_source="tier1")

        # ---- Stage B: Tier-2 fallback (single-syllable only) ----
        if (not cands) and n_syllables == 1 and callable(self._tier2_compose) and isinstance(self._char_map,
                                                                                             dict) and self._char_map:
            try:
                raw_tier2 = self._tier2_compose(jy_norm, self._char_map) or []
            except Exception:
                raw_tier2 = []

            try:
                if callable(self._tier2_shortlist) and raw_tier2:
                    raw_tier2 = self._tier2_shortlist(raw_tier2) or raw_tier2
            except Exception:
                pass

            cands = _coerce_candidates(raw_tier2, default_source="tier2-char")

        # ---- Stage C: de-dupe & rank ----
        cands = _dedupe_keep_first(cands)

        if callable(self._curate):
            try:
                curated = self._curate(cands)
                cands = list(curated) if curated is not None else cands
            except Exception:
                # Fall back to simple ranking if curator fails
                cands = _simple_rank(cands)
        else:
            cands = _simple_rank(cands)

        # Final cap
        if len(cands) > self._max:
            cands = cands[: self._max]

        return cands

    def glosses_for_candidate(self, hanzi: str) -> list[str]:
        hz = (hanzi or "").strip()
        if not hz:
            return []

        out: list[str] = []

        # 1) CC-Canto first (best for colloquial Cantonese)
        cc = getattr(self, "_cc_glosses_for", None)
        if callable(cc):
            try:
                out = list(cc(hz) or [])
            except Exception:
                out = []

        # 2) CEDICT fallback
        if not out:
            ced = getattr(self, "_cedict_meanings_for", None)
            if callable(ced):
                try:
                    out = list(ced(hz) or [])
                except Exception:
                    out = []

        # 3) Normalise strings
        try:
            out = [str(x).strip() for x in (out or []) if str(x).strip()]
        except Exception:
            out = []

        # 4) Optional cleaning (display-safe)
        cleaner = getattr(self, "_gloss_cleaner", None)
        if callable(cleaner):
            try:
                cleaned = cleaner(out)
                out = [str(x).strip() for x in (cleaned or []) if str(x).strip()]
            except Exception:
                pass

        try:
            import logging
            logging.getLogger(__name__).debug(
                "PipelineGlossAudit: hz=%r cc=%s cedict=%s out_n=%d sample=%r",
                hz,
                bool(callable(getattr(self, "_cc_glosses_for", None))),
                bool(callable(getattr(self, "_cedict_meanings_for", None))),
                len(out),
                (out[:3] if out else []),
            )
        except Exception:
            pass

        return out

    def attach_glosses(self, cands: Sequence[HanziCandidate]) -> list[HanziCandidate]:
        """Attach glosses to candidates using `glosses_for_candidate`.

        Safe default: failures return candidates unchanged.
        """

        out: list[HanziCandidate] = []
        for c in cands:
            try:
                glosses = self.glosses_for_candidate(c.hanzi)
                out.append(c.with_glosses(glosses))
            except Exception:
                out.append(c)
        return out


def build_pipeline_from_category_manager(dialog: object) -> HanziCandidatePipeline:
    """Convenience factory to build a pipeline from an existing CategoryManagerDialog.

    This keeps all the injection logic in one place when migrating code.

    The `dialog` is treated as a duck-typed provider of:
    - _normalize_jy(str) -> str
    - _reverse_candidates_for_jy(str) -> object
    - _char_map (dict)
    - optional meaning helpers (e.g. get_cccanto_glosses_for)
    - optional curator: _candidate_curator with method curate(seq)
    """

    normalize = getattr(dialog, "_normalize_jy", None)
    if not callable(normalize):
        raise TypeError("dialog must provide callable _normalize_jy")

    tier1 = getattr(dialog, "_reverse_candidates_for_jy", None)

    # Tier-2 composer/shortlister: ONLY via dialog-provided callables.
    # The domain layer must not import from utils.
    compose_fn = None
    shortlist_fn = None

    get_comp = getattr(dialog, "_get_compose_and_rank", None)
    if callable(get_comp):
        try:
            compose_fn, shortlist_fn = get_comp()
        except Exception:
            compose_fn, shortlist_fn = None, None

    if not callable(compose_fn):
        # Accept a few duck-typed alternatives.
        compose_fn = getattr(dialog, "compose_candidates_from_chars", None)
        if not callable(compose_fn):
            compose_fn = getattr(dialog, "_compose_candidates_from_chars", None)

    if not callable(shortlist_fn):
        shortlist_fn = getattr(dialog, "shortlist_hanzi_candidates", None)
        if not callable(shortlist_fn):
            shortlist_fn = getattr(dialog, "_shortlist_hanzi_candidates", None)

    char_map = getattr(dialog, "_char_map", None)
    if not isinstance(char_map, dict):
        char_map = {}

    # Meaning providers: ONLY via dialog-provided callables.
    cc_glosses_for = getattr(dialog, "get_cccanto_glosses_for", None)
    if not callable(cc_glosses_for):
        cc_glosses_for = getattr(dialog, "_cc_glosses_for", None)

    cedict_for = getattr(dialog, "get_cedict_meanings_for", None)
    if not callable(cedict_for):
        cedict_for = getattr(dialog, "_cedict_meanings_for", None)

    # Gloss cleaning is a domain concern for this pipeline; do not accept UI-provided cleaners.
    try:
        from domain.meaning_sources import clean_glosses_for_display as gloss_cleaner
    except Exception:
        gloss_cleaner = None

    curate = None
    curator = getattr(dialog, "_candidate_curator", None)
    if curator is not None and hasattr(curator, "curate") and callable(getattr(curator, "curate")):
        curate = getattr(curator, "curate")

    max_cands = getattr(dialog, "MAX_HANZI_CANDIDATES", 10)

    return HanziCandidatePipeline(
        normalize_jyutping=normalize,
        tier1_reverse_candidates=tier1 if callable(tier1) else None,
        tier2_compose=compose_fn if callable(compose_fn) else None,
        tier2_shortlist=shortlist_fn if callable(shortlist_fn) else None,
        char_map=char_map,
        cc_glosses_for=cc_glosses_for,
        cedict_meanings_for=cedict_for,
        gloss_cleaner=gloss_cleaner,
        curate=curate,
        max_candidates=int(max_cands) if isinstance(max_cands, int) else 10,
    )


__all__ = [
    "HanziCandidate",
    "HanziCandidatePipeline",
    "build_pipeline_from_category_manager",
    "rerank_candidates_with_meanings",
]
