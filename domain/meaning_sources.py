"""Meaning sources and gloss cleaning (facade module)."""

from __future__ import annotations

from domain.meaning_sources_cleaning import clean_glosses_for_display, GlossList
from domain.meaning_sources_models import (
    MeaningResolver,
    MeaningFacade,
    SelectedCandidate,
    default_resolver,
)
from domain.meaning_sources_cccanto import get_cccanto_glosses_for, reset_cccanto_cache
from domain.meaning_sources_cedict import get_cedict_meanings_for, reset_cedict_cache, cedict_ts_path


def reset_meaning_source_caches() -> None:
    """Clear lazy-loaded meaning source caches."""
    reset_cccanto_cache()
    reset_cedict_cache()


def default_facade() -> MeaningFacade:
    """Best-effort default façade used by UI orchestration."""
    resolver = None
    try:
        resolver = default_resolver()
    except Exception:
        resolver = None

    cleaner = None
    try:
        cleaner = clean_glosses_for_display
    except Exception:
        cleaner = None

    return MeaningFacade(resolver=resolver, cleaner=cleaner)


__all__ = [
    "MeaningResolver",
    "default_resolver",
    "clean_glosses_for_display",
    "MeaningFacade",
    "default_facade",
    "get_cedict_meanings_for",
    "get_cccanto_glosses_for",
    "reset_meaning_source_caches",
    "cedict_ts_path",
    "SelectedCandidate",
    "GlossList",
]
