

"""Pure (non-Qt) tests for candidate ranking / list hygiene.

These tests deliberately avoid importing PySide/PyQt.
They define small reference helpers locally. Once you extract the real
helpers from `category_manager.py`, swap the local helpers for imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class Cand:
    hanzi: str
    style_rank: int  # lower = better (colloquial first)
    cat_score: float


def dedupe_preserve_order(items: Sequence[str]) -> List[str]:
    """Return unique items, keeping first occurrence order."""
    seen = set()
    out: List[str] = []
    for s in items:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def cap_after_dedupe(items: Sequence[str], n: int) -> List[str]:
    """Deduplicate, then cap to top-n."""
    return dedupe_preserve_order(items)[: max(0, int(n))]


def rank_by_style_then_score(cands: Iterable[Cand], active_cat: str | None) -> List[str]:
    """Rank candidates with style first, then category score.

    - style_rank: lower wins (colloquial-first)
    - cat_score: higher wins, but only if active_cat is not 'unassigned'

    Returns list of hanzi in ranked order.
    """
    cat_norm = (active_cat or "").strip().lower()
    use_cat = bool(cat_norm) and cat_norm != "unassigned"

    def key(c: Cand):
        # Python sorts ascending; we want:
        #   style_rank ascending
        #   cat_score descending (if enabled)
        score = c.cat_score if use_cat else 0.0
        return (c.style_rank, -score, c.hanzi)

    ranked = sorted(list(cands), key=key)
    return [c.hanzi for c in ranked]


def test_dedupe_preserves_first_occurrence_order():
    items = ["粉紅", "粉紅", "粉", "粉紅"]
    assert dedupe_preserve_order(items) == ["粉紅", "粉"]


def test_cap_is_applied_after_dedupe():
    items = ["a", "b", "a", "c", "d", "e", "f", "g", "h", "i", "j", "k", "k", "k"]
    # Unique sequence is a,b,c,d,e,f,g,h,i,j,k => 11 unique; cap to 10
    assert cap_after_dedupe(items, 10) == ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]


def test_colloquial_beats_both_beats_written_even_if_score_lower():
    # style_rank: 0=colloquial, 1=both, 2=written
    cands = [
        Cand("甲", style_rank=2, cat_score=0.99),
        Cand("乙", style_rank=1, cat_score=0.99),
        Cand("丙", style_rank=0, cat_score=0.01),
    ]
    assert rank_by_style_then_score(cands, active_cat="colors")[:3] == ["丙", "乙", "甲"]


def test_category_context_breaks_ties_within_style():
    # Same style_rank; higher cat_score should come first when category is active
    cands = [
        Cand("紅", style_rank=0, cat_score=0.2),
        Cand("熊", style_rank=0, cat_score=0.9),
        Cand("洪", style_rank=0, cat_score=0.1),
    ]
    assert rank_by_style_then_score(cands, active_cat="animals")[:3] == ["熊", "紅", "洪"]


def test_unassigned_disables_category_score_influence():
    # Same style_rank but different cat_score; when unassigned, cat_score ignored
    cands = [
        Cand("紅", style_rank=0, cat_score=0.2),
        Cand("熊", style_rank=0, cat_score=0.9),
    ]
    # With category: 熊 first
    assert rank_by_style_then_score(cands, active_cat="animals")[:2] == ["熊", "紅"]
    # Unassigned: score ignored; stable tie-breaker is hanzi
    assert rank_by_style_then_score(cands, active_cat="unassigned")[:2] == ["熊", "紅"]


def test_cap_after_ranking_and_dedupe_pipeline_smoke():
    # Simulate a ranking output that contains duplicates due to upstream sources
    ranked = ["粉紅", "粉紅", "粉", "粉", "紅", "紅色", "粉紅"]
    top = cap_after_dedupe(ranked, 3)
    assert top == ["粉紅", "粉", "紅"]