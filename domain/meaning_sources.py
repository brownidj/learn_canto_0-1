"""Meaning sources and gloss cleaning.

This module centralises the logic for resolving meanings for a Hanzi string.

Design goals
- UI-free and side-effect free at import time.
- Lazy-load heavy indexes (CC-Canto / CEDICT) only when a resolver is used.
- Provide a small, explicit API that CategoryManagerDialog (and tests) can call.

NOTE: We keep imports tolerant because this project has evolved over time.
If a backing source is unavailable, the resolver degrades gracefully.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, List

import yaml

from domain.storage_paths import (
    cccanto_meanings_map_path,
    cedict_meanings_map_json_path,
    cedict_meanings_map_yaml_path,
)

GlossList = List[str]


def _clean_list(xs: object) -> GlossList:
    if not isinstance(xs, list):
        return []
    out: GlossList = []
    for x in xs:
        if isinstance(x, str):
            s = x.strip()
            if s:
                out.append(s)
    return out


def _best_effort_clean_glosses(glosses: Sequence[str] | object) -> GlossList:
    """Best-effort gloss cleaning suitable for UI labels/tooltips.

    Domain policy: keep this module UI-free and independent of `utils`.
    We apply conservative, deterministic cleaning only.
    """
    if isinstance(glosses, (list, tuple)):
        return _clean_list(list(glosses))
    return []


def clean_glosses_for_display(glosses: Sequence[str] | object) -> GlossList:
    """Public cleaning helper for UI labels/tooltips.

    Prefer calling `MeaningResolver.clean_glosses()` from UI code.
    This function remains for backwards compatibility.
    """
    return _best_effort_clean_glosses(glosses)


@dataclass(frozen=True)
class SelectedCandidate:
    hanzi: str
    source: str
    meanings: list[str]
    label: str


@dataclass(frozen=True)
class MeaningResolver:
    """Pure-ish meaning resolver with lazy backing sources.

    You can inject callables in tests; production typically uses `default_resolver()`.
    """

    cc_glosses_for: Optional[Callable[[str], Sequence[str]]] = None
    cedict_meanings_for: Optional[Callable[[str], Sequence[str]]] = None

    def clean_glosses(self, glosses: Sequence[str] | object) -> GlossList:
        """Clean gloss strings for display (UI-safe)."""
        return _best_effort_clean_glosses(glosses)

    def glosses_for(self, hanzi: str, *, limit: int = 6) -> GlossList:
        """Return best-effort glosses for `hanzi`.

        Preference order:
        1) CC-Canto glosses (if available)
        2) CEDICT meanings (if available)

        Returned list is cleaned and truncated.
        """
        hz = hanzi.strip() if isinstance(hanzi, str) else ""
        if not hz:
            return []

        lim = max(1, int(limit))

        # CC-Canto first
        if callable(self.cc_glosses_for):
            try:
                cc = _clean_list(list(self.cc_glosses_for(hz)))
                if cc:
                    return self.clean_glosses(cc)[:lim]
            except Exception:
                pass

        # Then CEDICT
        if callable(self.cedict_meanings_for):
            try:
                ce = _clean_list(list(self.cedict_meanings_for(hz)))
                if ce:
                    return self.clean_glosses(ce)[:lim]
            except Exception:
                pass

        return []

    def meanings_for(self, hanzi: str, *, limit: int = 3) -> GlossList:
        """Return preferred meanings for `hanzi`.

        This is a narrower alias for `glosses_for()`.
        """
        return self.glosses_for(hanzi, limit=limit)


class MeaningFacade:
    """Domain façade: resolve meanings and return a display-ready list.

    Keeps UI layers free of dictionary resolution and cleaning rules.
    """

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
        """Prefer glosses without bracketed/parenthetical metadata.

        Historical UI behaviour:
        - prefer items that do NOT contain '[' or '('
        - take up to `max_items`
        - if filtering removes everything, fall back to the unfiltered list
        """
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
        """Return a UI-ready label for a Hanzi candidate.

        Must preserve historical UI semantics:
          - meanings are resolved
          - display cleaning is applied
          - additionally, entries containing '[' or '(' are excluded for the short label
            (this used to live in the dialog)
          - the remaining entries are preview-sliced to `max_items`
        """
        hz = (hanzi or "").strip()
        if not hz:
            return ""

        try:
            n = int(max_items)
        except Exception:
            n = 2
        if n <= 0:
            n = 2

        # Resolve meanings (already cleaned by meanings_for_display)
        try:
            glosses = list(self.meanings_for_display(hz) or [])
        except Exception:
            glosses = []

        # Old UI behaviour: prefer short, plain glosses (no brackets/parentheses)
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
        """Domain façade for candidate selection.

        Returns a payload that the UI can apply without re-implementing
        meaning resolution or display cleaning.
        """
        hz = (hanzi or "").strip()
        src = (source or "").strip()

        # Meanings list is the full display-cleaned list (not preview)
        try:
            meanings = list(self.meanings_for_display(hz) or [])
        except Exception:
            meanings = []

        label = self.candidate_label(hz, src, preferred=preferred, max_items=max_items)
        return SelectedCandidate(hanzi=hz, source=src, meanings=meanings, label=label)


def default_facade() -> MeaningFacade:
    """Best-effort default façade used by UI orchestration."""
    resolver = None
    try:
        if callable(default_resolver):
            resolver = default_resolver()
    except Exception:
        resolver = None

    cleaner = None
    try:
        if callable(clean_glosses_for_display):
            cleaner = clean_glosses_for_display
    except Exception:
        cleaner = None

    return MeaningFacade(resolver=resolver, cleaner=cleaner)


# ---------------------------
# Lazy, file-backed sources
# ---------------------------

_CC_CANTO_MEANINGS_MAP: dict[str, list[str]] | None = None
_CEDICT_MEANINGS_MAP: dict[str, list[str]] | None = None


def _project_root() -> Path:
    """Best-effort project root: assumes `domain/` lives directly under root."""
    try:
        return Path(__file__).resolve().parents[1]
    except Exception:
        return Path(".")


def _first_existing_path(candidates: list[Path]) -> Path | None:
    for p in candidates:
        try:
            if p.exists() and p.is_file():
                return p
        except Exception:
            pass
    return None


def _load_yaml_dict(path: Path) -> dict[str, list[str]]:
    if yaml is None:
        return {}
    try:
        obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in obj.items():
        if not isinstance(k, str):
            continue
        if isinstance(v, list):
            out[k] = [str(x).strip() for x in v if str(x).strip()]
        elif isinstance(v, str) and v.strip():
            out[k] = [v.strip()]
    return out


def _load_json_dict(path: Path) -> dict[str, list[str]]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in obj.items():
        if not isinstance(k, str):
            continue
        if isinstance(v, list):
            out[k] = [str(x).strip() for x in v if str(x).strip()]
        elif isinstance(v, str) and v.strip():
            out[k] = [v.strip()]
    return out


def _get_cc_canto_meanings_map() -> dict[str, list[str]]:
    global _CC_CANTO_MEANINGS_MAP
    if isinstance(_CC_CANTO_MEANINGS_MAP, dict):
        return _CC_CANTO_MEANINGS_MAP

    p = cccanto_meanings_map_path()
    _CC_CANTO_MEANINGS_MAP = _load_yaml_dict(p) if p is not None else {}
    return _CC_CANTO_MEANINGS_MAP


def _get_cedict_meanings_map() -> dict[str, list[str]]:
    global _CEDICT_MEANINGS_MAP
    if isinstance(_CEDICT_MEANINGS_MAP, dict):
        return _CEDICT_MEANINGS_MAP

    pj = cedict_meanings_map_json_path()
    if pj is not None:
        _CEDICT_MEANINGS_MAP = _load_json_dict(pj)
        return _CEDICT_MEANINGS_MAP

    py = cedict_meanings_map_yaml_path()
    _CEDICT_MEANINGS_MAP = _load_yaml_dict(py) if py is not None else {}
    return _CEDICT_MEANINGS_MAP


def _cc_glosses_for(hz: str) -> Sequence[str]:
    mp = _get_cc_canto_meanings_map()
    try:
        val = mp.get(hz)
        return val if isinstance(val, list) else []
    except Exception:
        return []


def _cedict_meanings_for(hz: str) -> Sequence[str]:
    mp = _get_cedict_meanings_map()
    try:
        val = mp.get(hz)
        return val if isinstance(val, list) else []
    except Exception:
        return []


def default_resolver() -> MeaningResolver:
    """Construct a resolver wired to the project's available sources (lazy)."""
    return MeaningResolver(cc_glosses_for=_cc_glosses_for, cedict_meanings_for=_cedict_meanings_for)


__all__ = [
    "MeaningResolver",
    "default_resolver",
    "clean_glosses_for_display",
    "MeaningFacade",
    "default_facade",
]
