"""Utility helpers for Hanzi candidate pipeline."""

from __future__ import annotations

from typing import Sequence

from domain.hanzi_candidate_types import HanziCandidate


def _norm_space(text: str) -> str:
    return " ".join(text.split())


def _split_syllables(jy_norm: str) -> list[str]:
    jy_norm = _norm_space(jy_norm)
    return jy_norm.split() if jy_norm else []


def _coerce_candidates(raw: object, default_source: str) -> list[HanziCandidate]:
    """Normalise diverse candidate return shapes into `HanziCandidate` objects."""
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
    """A stable, conservative ordering."""
    return sorted(
        list(cands),
        key=lambda c: (-float(c.freq or 0.0), str(c.source), c.hanzi),
    )
