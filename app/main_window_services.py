"""Main window service wiring helpers."""

from __future__ import annotations

from typing import Any, Tuple

from infra.paths import project_root
from services.vocab_loader import (
    load_vocab_from_unified_yaml as _load_vocab_from_unified_yaml,
    load_categories_from_disk as _load_categories_from_disk,
    load_categories_map as _load_categories_map,
)
from services.reverse_lookup_service import ReverseLookupService
from services.tts_service import TTSService
from domain.candidate_provider import CallableCandidateProvider
from main_helpers import normalize_reverse_index as _normalize_reverse_index, perf_start as _perf_start, perf_end as _perf_end

try:
    from infra.hanzi_composition import compose_candidates_from_chars, shortlist_candidates
except Exception:
    compose_candidates_from_chars = None
    shortlist_candidates = None

try:
    from infra.reverse_index import load_reverse_index_files
except Exception:
    load_reverse_index_files = None

try:
    from infra.unihan import load_unihan_char_map
except Exception:
    load_unihan_char_map = None


def load_vocab_and_categories() -> Tuple[dict, dict]:
    vocab, categories_map = _load_vocab_from_unified_yaml()
    try:
        cats_disk = _load_categories_from_disk()
    except Exception:
        cats_disk = {}
    if isinstance(cats_disk, dict) and cats_disk:
        categories_map = cats_disk
    return vocab, categories_map


def refresh_categories_map(window, categories_map: dict) -> dict:
    try:
        cats_best = _load_categories_map()
    except Exception:
        cats_best = categories_map
    if isinstance(cats_best, dict) and cats_best:
        categories_map = cats_best
    try:
        setattr(window, "_categories_map", categories_map)
    except Exception:
        pass
    return categories_map


def ensure_char_map(window) -> None:
    _t_cmap = 0.0
    try:
        cmap = {}
        prev = getattr(window, "_char_map", None)
        _t_cmap = _perf_start("load_unihan_char_map")
        if isinstance(prev, dict) and prev:
            cmap = prev
        else:
            if callable(load_unihan_char_map):
                cmap = load_unihan_char_map(project_root()) or {}
            else:
                cmap = {}
        setattr(window, "_char_map", cmap if isinstance(cmap, dict) else {})
        _perf_end("load_unihan_char_map", _t_cmap)
    except Exception:
        _perf_end("load_unihan_char_map", _t_cmap)
        setattr(window, "_char_map", {})


def ensure_reverse_index(window) -> None:
    try:
        prev_idx = getattr(window, "_reverse_index", None)
    except Exception:
        prev_idx = None
    try:
        if isinstance(prev_idx, dict) and prev_idx:
            window._reverse_index = _normalize_reverse_index(prev_idx)
        else:
            _t_rev = _perf_start("load_reverse_index_files")
            try:
                if callable(load_reverse_index_files):
                    window._reverse_index = _normalize_reverse_index(load_reverse_index_files(project_root()))
                else:
                    window._reverse_index = {}
            except Exception:
                window._reverse_index = {}
            _perf_end("load_reverse_index_files", _t_rev)
    except Exception:
        window._reverse_index = {}


def build_reverse_lookup(window) -> ReverseLookupService:
    return ReverseLookupService(
        reverse_index=getattr(window, "_reverse_index", {}),
        char_map=getattr(window, "_char_map", {}),
        compose_fn=compose_candidates_from_chars,
        shortlist_fn=shortlist_candidates,
    )


def attach_candidate_provider(window, reverse_lookup: ReverseLookupService) -> None:
    try:
        window._candidate_provider = CallableCandidateProvider(
            reverse_lookup.candidates_for_jyutping
        )
    except Exception:
        pass


def create_tts_service(window) -> TTSService:
    return TTSService(window)
