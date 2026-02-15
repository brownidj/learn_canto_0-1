"""Candidate provider interface and simple adapters."""

from __future__ import annotations

from typing import Protocol


class CandidateProvider(Protocol):
    def get_candidates(self, jy: str) -> list[tuple[str, str, int]]:
        """Return list of (hanzi, source, score) for given Jyutping."""


class SimpleCandidateProvider:
    """Simple provider backed by a dict mapping jyutping -> candidates."""

    def __init__(self, mapping: dict[str, list[tuple[str, str, int]]]):
        self._mapping = mapping

    def get_candidates(self, jy: str) -> list[tuple[str, str, int]]:
        try:
            return list(self._mapping.get(str(jy or "").strip(), []))
        except Exception:
            return []


class CallableCandidateProvider:
    """Adapter for a lookup function returning candidates."""

    def __init__(self, lookup_fn):
        self._lookup_fn = lookup_fn

    def get_candidates(self, jy: str) -> list[tuple[str, str, int]]:
        try:
            return list(self._lookup_fn(str(jy or "").strip()) or [])
        except Exception:
            return []
