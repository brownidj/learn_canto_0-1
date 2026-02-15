"""Core Hanzi candidate pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Mapping

from domain.hanzi_candidate_types import HanziCandidate
from domain.hanzi_candidate_utils import _split_syllables, _coerce_candidates, _dedupe_keep_first, _simple_rank

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HanziPipelineDeps:
    normalize_jyutping: Callable[[str], str]
    tier1_reverse_candidates: Optional[Callable[[str], object]] = None
    reverse_index: Optional[dict] = None
    tier2_compose: Optional[Callable[[str, dict], object]] = None
    tier2_shortlist: Optional[Callable[[object], object]] = None
    char_map: Optional[dict] = None
    cc_glosses_for: Optional[Callable[[str], Sequence[str]]] = None
    cedict_meanings_for: Optional[Callable[[str], Sequence[str]]] = None
    gloss_cleaner: Optional[Callable[[Sequence[str]], Sequence[str]]] = None
    curate: Optional[Callable[[Sequence[HanziCandidate]], Sequence[HanziCandidate]]] = None
    max_candidates: int = 10


class HanziCandidatePipeline:
    """Orchestrates candidate generation for a jyutping string."""

    def __init__(self, deps: HanziPipelineDeps | None = None, **kwargs: object):
        if deps is None:
            try:
                deps = HanziPipelineDeps(**kwargs)  # type: ignore[arg-type]
            except TypeError as e:
                raise TypeError("HanziCandidatePipeline requires deps or valid kwargs") from e

        self._normalize = deps.normalize_jyutping

        if deps.tier1_reverse_candidates is None and isinstance(deps.reverse_index, dict):
            def _tier1_from_index(jy_norm: str) -> object:
                try:
                    return deps.reverse_index.get(jy_norm, [])
                except Exception:
                    return []

            self._tier1 = _tier1_from_index
        else:
            self._tier1 = deps.tier1_reverse_candidates

        self._tier2_compose = deps.tier2_compose
        self._tier2_shortlist = deps.tier2_shortlist
        self._char_map = deps.char_map or {}
        self._cc_glosses_for = deps.cc_glosses_for
        self._cedict_meanings_for = deps.cedict_meanings_for
        self._gloss_cleaner = deps.gloss_cleaner
        self._curate = deps.curate
        try:
            m = int(deps.max_candidates)
        except Exception:
            m = 10
        self._max = m if m > 0 else 10

    def run(self, jyut: str, *, manual_hanzi_mode: bool = False) -> list[tuple[str, str, float]]:
        cands = self.candidates_for(jyut, manual_hanzi_mode=manual_hanzi_mode)
        return [(c.hanzi, c.source, float(c.freq or 0.0)) for c in cands]

    def candidates_for(self, jyut: str, *, manual_hanzi_mode: bool = False) -> list[HanziCandidate]:
        if manual_hanzi_mode:
            logger.debug("HanziCandidatePipeline: manual Hanzi mode; skipping auto candidates")
            return []

        jy_norm = self._normalize(jyut or "")
        syllables = _split_syllables(jy_norm)
        n_syllables = len(syllables)

        raw_tier1: object = []
        if callable(self._tier1):
            try:
                raw_tier1 = self._tier1(jy_norm) or []
            except Exception:
                raw_tier1 = []

        cands = _coerce_candidates(raw_tier1, default_source="tier1")

        if (not cands) and n_syllables >= 1 and n_syllables <= 4 and callable(self._tier2_compose) and isinstance(self._char_map, dict) and self._char_map:
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

        cands = _dedupe_keep_first(cands)

        if callable(self._curate):
            try:
                curated = self._curate(cands)
                cands = list(curated) if curated is not None else cands
            except Exception:
                cands = _simple_rank(cands)
        else:
            cands = _simple_rank(cands)

        if len(cands) > self._max:
            cands = cands[: self._max]

        return cands

    def glosses_for_candidate(self, hanzi: str) -> list[str]:
        hz = (hanzi or "").strip()
        if not hz:
            return []

        out: list[str] = []

        cc = self._cc_glosses_for
        if callable(cc):
            try:
                out = list(cc(hz) or [])
            except Exception:
                out = []

        if not out:
            ced = self._cedict_meanings_for
            if callable(ced):
                try:
                    out = list(ced(hz) or [])
                except Exception:
                    out = []

        try:
            out = [str(x).strip() for x in (out or []) if str(x).strip()]
        except Exception:
            out = []

        cleaner = self._gloss_cleaner
        if callable(cleaner):
            try:
                cleaned = cleaner(out)
                out = [str(x).strip() for x in (cleaned or []) if str(x).strip()]
            except Exception:
                pass

        return out

    def attach_glosses(self, cands: Sequence[HanziCandidate]) -> list[HanziCandidate]:
        out: list[HanziCandidate] = []
        for c in cands:
            try:
                glosses = self.glosses_for_candidate(c.hanzi)
                out.append(c.with_glosses(glosses))
            except Exception:
                out.append(c)
        return out


def build_pipeline_from_category_manager(dialog: object) -> HanziCandidatePipeline:
    normalize = None
    try:
        normalize = dialog.__dict__.get("_normalize_jy")
    except Exception:
        normalize = None
    if not callable(normalize):
        try:
            from domain.jyutping_validation import normalize_jyutping
            normalize = normalize_jyutping
        except Exception:
            raise TypeError("dialog must provide callable _normalize_jy")

    tier1 = None
    try:
        prov = dialog.__dict__.get("_candidate_provider")
    except Exception:
        prov = None
    if prov is not None:
        try:
            # Avoid recursion when the provider is the dialog's own pipeline adapter.
            if type(prov).__name__ == "CandidatePipelineProvider" and getattr(prov, "__module__", "").endswith("category_manager_candidate_pipeline"):
                prov = None
        except Exception:
            pass
    if prov is not None and hasattr(prov, "get_candidates"):
        try:
            tier1 = prov.get_candidates
        except Exception:
            tier1 = None

    compose_fn = None
    shortlist_fn = None

    try:
        get_comp = dialog.__dict__.get("_get_compose_and_rank")
    except Exception:
        get_comp = None
    if callable(get_comp):
        try:
            compose_fn, shortlist_fn = get_comp()
        except Exception:
            compose_fn, shortlist_fn = None, None

    if not callable(compose_fn):
        compose_fn = getattr(dialog, "compose_candidates_from_chars", None)
        if not callable(compose_fn):
            try:
                compose_fn = dialog.__dict__.get("_compose_candidates_from_chars")
            except Exception:
                compose_fn = None
    if not callable(compose_fn):
        compose_fn = None

    if not callable(shortlist_fn):
        shortlist_fn = getattr(dialog, "shortlist_hanzi_candidates", None)
        if not callable(shortlist_fn):
            try:
                shortlist_fn = dialog.__dict__.get("_shortlist_hanzi_candidates")
            except Exception:
                shortlist_fn = None
    if not callable(shortlist_fn):
        shortlist_fn = None

    try:
        reverse_index = dialog.__dict__.get("_reverse_index")
    except Exception:
        reverse_index = None
    if not isinstance(reverse_index, dict):
        reverse_index = None

    try:
        char_map = dialog.__dict__.get("_char_map")
    except Exception:
        char_map = None
    if not isinstance(char_map, dict):
        char_map = {}

    cc_glosses_for = getattr(dialog, "get_cccanto_glosses_for", None)
    if not callable(cc_glosses_for):
        try:
            cc_glosses_for = dialog.__dict__.get("_cc_glosses_for")
        except Exception:
            cc_glosses_for = None

    cedict_for = getattr(dialog, "get_cedict_meanings_for", None)
    if not callable(cedict_for):
        try:
            cedict_for = dialog.__dict__.get("_cedict_meanings_for")
        except Exception:
            cedict_for = None

    try:
        from domain.meaning_sources import clean_glosses_for_display as gloss_cleaner
    except Exception:
        gloss_cleaner = None

    curate = None
    try:
        curator = dialog.__dict__.get("_candidate_curator")
    except Exception:
        curator = None
    if curator is not None and hasattr(curator, "curate") and callable(getattr(curator, "curate")):
        curate = getattr(curator, "curate")

    try:
        max_cands = dialog.__dict__.get("MAX_HANZI_CANDIDATES", 10)
    except Exception:
        max_cands = 10

    deps = HanziPipelineDeps(
        normalize_jyutping=normalize,
        tier1_reverse_candidates=tier1 if callable(tier1) else None,
        reverse_index=reverse_index,
        tier2_compose=compose_fn if callable(compose_fn) else None,
        tier2_shortlist=shortlist_fn if callable(shortlist_fn) else None,
        char_map=char_map,
        cc_glosses_for=cc_glosses_for,
        cedict_meanings_for=cedict_for,
        gloss_cleaner=gloss_cleaner,
        curate=curate,
        max_candidates=int(max_cands) if isinstance(max_cands, int) else 10,
    )
    return HanziCandidatePipeline(deps)


__all__ = [
    "HanziCandidatePipeline",
    "build_pipeline_from_category_manager",
]
