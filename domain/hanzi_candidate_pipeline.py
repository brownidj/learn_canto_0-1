"""Hanzi candidate pipeline (facade module)."""

from __future__ import annotations

from domain.hanzi_candidate_types import HanziCandidate
from domain.hanzi_candidate_ranker import rerank_candidates_with_meanings
from domain.hanzi_candidate_pipeline_core import HanziCandidatePipeline, build_pipeline_from_category_manager

__all__ = [
    "HanziCandidate",
    "HanziCandidatePipeline",
    "build_pipeline_from_category_manager",
    "rerank_candidates_with_meanings",
]
