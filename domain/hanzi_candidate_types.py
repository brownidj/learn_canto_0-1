"""Types for Hanzi candidate pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


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
