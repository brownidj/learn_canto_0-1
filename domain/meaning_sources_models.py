"""Meaning resolver and facade models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from domain.meaning_sources_cleaning import GlossList, _best_effort_clean_glosses, _clean_list
from domain.meaning_sources_cccanto import _cc_glosses_for
from domain.meaning_sources_cedict import _cedict_meanings_for


@dataclass(frozen=True)
class SelectedCandidate:
    hanzi: str
    source: str
    meanings: list[str]
    label: str


@dataclass(frozen=True)
class MeaningResolver:
    """Pure-ish meaning resolver with lazy backing sources."""

    cc_glosses_for: Optional[Callable[[str], Sequence[str]]] = None
    cedict_meanings_for: Optional[Callable[[str], Sequence[str]]] = None

    def clean_glosses(self, glosses: Sequence[str] | object) -> GlossList:
        return _best_effort_clean_glosses(glosses)

    def glosses_for(self, hanzi: str, *, limit: int = 6) -> GlossList:
        hz = hanzi.strip() if isinstance(hanzi, str) else ""
        if not hz:
            return []

        lim = max(1, int(limit))

        if callable(self.cc_glosses_for):
            try:
                cc = _clean_list(list(self.cc_glosses_for(hz)))
                if cc:
                    return self.clean_glosses(cc)[:lim]
            except Exception:
                pass

        if callable(self.cedict_meanings_for):
            try:
                ce = _clean_list(list(self.cedict_meanings_for(hz)))
                if ce:
                    return self.clean_glosses(ce)[:lim]
            except Exception:
                pass

        return []

    def meanings_for(self, hanzi: str, *, limit: int = 3) -> GlossList:
        return self.glosses_for(hanzi, limit=limit)


class MeaningFacade:
    """Domain façade: resolve meanings and return a display-ready list."""

    def __init__(self, resolver=None, cleaner=None):
        self._resolver = resolver
        self._cleaner = cleaner

    def meanings_for(self, hanzi: str) -> list[str]:
        hz = (hanzi or "").strip()
        if not hz:
            return []
        r = self._resolver
        if r is None:
            return []
        try:
            out = r.meanings_for(hz)
        except Exception:
            return []
        return [str(x) for x in (out or []) if str(x).strip()]

    def meanings_for_display(self, hanzi: str) -> list[str]:
        items = self.meanings_for(hanzi)
        if not items:
            return []
        c = self._cleaner
        if callable(c):
            try:
                cleaned = c(items)
                return [str(x) for x in (cleaned or []) if str(x).strip()]
            except Exception:
                pass
        return items

    def preview_for_display(self, hanzi: str, max_items: int = 2) -> list[str]:
        items = self.meanings_for_display(hanzi)
        if not items:
            return []
        try:
            n = int(max_items)
        except Exception:
            n = 2
        if n <= 0:
            n = 2
        return items[:n]

    def _pick_display_glosses(self, glosses: object, max_items: int) -> list[str]:
        try:
            n = int(max_items)
        except Exception:
            n = 2
        if n <= 0:
            n = 2

        try:
            seq = glosses if isinstance(glosses, (list, tuple)) else []
            raw = [str(x).strip() for x in seq if str(x).strip()]
        except Exception:
            return []

        clean = [g for g in raw if "[" not in g and "(" not in g]
        return clean[:n] if clean else raw[:n]

    def candidate_label(
        self,
        hanzi: str,
        source: str,
        *,
        preferred: bool = False,
        max_items: int = 2,
    ) -> str:
        hz = (hanzi or "").strip()
        if not hz:
            return ""

        try:
            n = int(max_items)
        except Exception:
            n = 2
        if n <= 0:
            n = 2

        try:
            glosses = list(self.meanings_for_display(hz) or [])
        except Exception:
            glosses = []

        try:
            plain = [g for g in glosses if isinstance(g, str) and g.strip() and "[" not in g and "(" not in g]
        except Exception:
            plain = []

        shown = (plain[:n] if plain else glosses[:n])

        try:
            from domain.category_rules import abbr_for_source
            tag = abbr_for_source(source)
        except Exception:
            tag = "UNK"

        core = f"{hz} — {', '.join(shown)} ({tag})" if shown else f"{hz} ({tag})"
        return f"✓ {core}" if preferred else core

    def select_candidate(
        self,
        hanzi: str,
        source: str,
        *,
        preferred: bool = False,
        max_items: int = 2,
    ) -> SelectedCandidate:
        hz = (hanzi or "").strip()
        src = (source or "").strip()
        try:
            meanings = list(self.meanings_for_display(hz) or [])
        except Exception:
            meanings = []

        label = self.candidate_label(hz, src, preferred=preferred, max_items=max_items)
        return SelectedCandidate(hanzi=hz, source=src, meanings=meanings, label=label)


def default_resolver() -> MeaningResolver:
    return MeaningResolver(cc_glosses_for=_cc_glosses_for, cedict_meanings_for=_cedict_meanings_for)

