"""Gloss cleaning utilities for meaning sources."""

from __future__ import annotations

from typing import Sequence, List

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
    """Best-effort gloss cleaning suitable for UI labels/tooltips."""
    if isinstance(glosses, (list, tuple)):
        return _clean_list(list(glosses))
    return []


def clean_glosses_for_display(glosses: Sequence[str] | object) -> GlossList:
    """Public cleaning helper for UI labels/tooltips."""
    return _best_effort_clean_glosses(glosses)
