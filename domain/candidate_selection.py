"""Candidate selection domain helpers.

This module is UI-free. It provides small, testable functions/classes that help the
CategoryManagerDialog remain an orchestrator only.

It intentionally does not import Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


Candidate = tuple[str, str, int]  # (hanzi, source, score/freq)


@dataclass(frozen=True)
class CandidateLabel:
    hanzi: str
    source: str
    label: str


@dataclass(frozen=True)
class CandidateSelectionResult:
    """Display-ready outcome for a chosen Hanzi candidate."""

    hanzi: str
    source: str
    meanings: list[str]
    label: str


class CandidateSelectionFacade:
    """Domain façade for candidate selection.

    The dialog should:
      - ask the pipeline for candidates
      - ask this façade for labels and selection results
      - apply the returned strings to widgets

    The façade delegates meaning resolution + display cleaning to `MeaningFacade`.
    """

    def __init__(self, meaning_facade: object | None = None):
        self._meaning_facade = meaning_facade

    def build_labels(
            self,
            cands: Sequence[Candidate],
            *,
            preferred_hanzi: str | None = None,
            max_items: int = 2,
    ) -> list[CandidateLabel]:
        out: list[CandidateLabel] = []
        pref = (preferred_hanzi or "").strip()

        mf = self._meaning_facade
        for hz, src, _score in (cands or []):
            hz_s = (hz or "").strip()
            src_s = (src or "").strip()
            if not hz_s:
                continue

            preferred = bool(pref and hz_s == pref)

            label = ""
            if mf is not None and hasattr(mf, "candidate_label") and callable(getattr(mf, "candidate_label")):
                try:
                    label = str(
                        mf.candidate_label(hz_s, src_s, preferred=preferred, max_items=max_items)  # type: ignore[attr-defined]
                        or ""
                    ).strip()
                except Exception:
                    label = ""

            # Last resort: keep label non-empty and stable.
            if not label:
                label = f"{hz_s}"

            out.append(CandidateLabel(hanzi=hz_s, source=src_s, label=label))

        return out

    def selection_result(
            self,
            hanzi: str,
            source: str,
            *,
            preferred: bool = False,
            max_items: int = 2,
    ) -> CandidateSelectionResult:
        hz = (hanzi or "").strip()
        src = (source or "").strip()

        mf = self._meaning_facade
        meanings: list[str] = []
        if mf is not None and hasattr(mf, "preview_for_display") and callable(getattr(mf, "preview_for_display")):
            try:
                meanings = list(mf.preview_for_display(hz, max_items=max_items) or [])  # type: ignore[attr-defined]
            except Exception:
                meanings = []

        label = ""
        if mf is not None and hasattr(mf, "candidate_label") and callable(getattr(mf, "candidate_label")):
            try:
                label = str(mf.candidate_label(hz, src, preferred=preferred, max_items=max_items) or "").strip()  # type: ignore[attr-defined]
            except Exception:
                label = ""

        if not label:
            label = f"{hz}" if hz else ""

        return CandidateSelectionResult(hanzi=hz, source=src, meanings=meanings, label=label)


def pick_preferred_hanzi(cands: Iterable[Candidate]) -> str:
    """Return the top candidate Hanzi or empty string."""
    try:
        first = next(iter(cands))
    except Exception:
        return ""

    try:
        hz = (first[0] or "").strip()
    except Exception:
        hz = ""

    return hz