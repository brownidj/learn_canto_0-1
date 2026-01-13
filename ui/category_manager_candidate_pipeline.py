"""
CategoryManager candidate pipeline extracted for maintainability.

Handles Hanzi candidate lookup, style detection, and curation.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerCandidatePipeline:
    """Manages Hanzi candidate pipeline for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog

    def reverse_candidates_for_jy(self, jy: str) -> list[tuple[str, str, int]]:
        """Return Tier-1 reverse candidates for a Jyutping (deterministic, test-friendly)."""
        jy_s = str(jy or "").strip()
        if not jy_s:
            return []

        # Locate reverse index (multiple historical attribute names)
        rev = None
        for attr in ("_reverse_index", "_rev_index", "_reverse_jyut_index"):
            try:
                v = getattr(self.dialog, attr, None)
            except (TypeError, AttributeError, RuntimeError):
                v = None
            if isinstance(v, dict):
                rev = v
                break

        items = []
        if isinstance(rev, dict):
            try:
                items = rev.get(jy_s) or []
            except (TypeError, AttributeError, RuntimeError):
                items = []

        out: list[tuple[str, str, int]] = []
        try:
            for row in list(items):
                # Expected shapes: (hz, src, score) or (hz, src)
                if isinstance(row, (list, tuple)) and len(row) >= 3:
                    hz, src, score = row[0], row[1], row[2]
                elif isinstance(row, (list, tuple)) and len(row) == 2:
                    hz, src, score = row[0], row[1], 0
                else:
                    hz, src, score = row, "", 0

                hz_s2 = str(hz or "").strip()
                if not hz_s2:
                    continue
                src_s = str(src or "").strip()

                try:
                    score_i = int(score)
                except (TypeError, ValueError):
                    try:
                        score_i = int(float(score))
                    except (TypeError, ValueError):
                        score_i = 0

                out.append((hz_s2, src_s, score_i))
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return []

        return out

    def load_hanzi_style_map(self) -> dict:
        """Lazy-load data/hanzi_style.yaml (Hanzi -> {style, source, notes}).

        Back-compat wrapper around the internal _HanziStyleIndex.
        """
        try:
            style_index = getattr(self.dialog, "_style_index", None)
            if style_index is not None and hasattr(style_index, "load"):
                return style_index.load()
        except (AttributeError, OSError, TypeError, ValueError, RuntimeError):
            pass
        return {}

    def hanzi_style(self, hanzi: str) -> str:
        """Back-compat wrapper for style lookup."""
        try:
            style_index = getattr(self.dialog, "_style_index", None)
            if style_index is not None and hasattr(style_index, "style_for"):
                return style_index.style_for(hanzi)
        except (AttributeError, OSError, TypeError, ValueError, RuntimeError):
            pass
        return "unknown"

    def is_colloquial_hanzi(self, hanzi: str) -> bool:
        """Back-compat wrapper for colloquial detection."""
        try:
            style_index = getattr(self.dialog, "_style_index", None)
            if style_index is not None and hasattr(style_index, "is_colloquial"):
                return style_index.is_colloquial(hanzi)
        except (AttributeError, OSError, TypeError, ValueError, RuntimeError):
            pass
        return False

    def curate_top_hanzi_candidates(self, ranked: list[str]) -> list[str]:
        """Back-compat wrapper to curate the top candidates for the UI."""
        try:
            curator = getattr(self.dialog, "_candidate_curator", None)
            if curator is not None and hasattr(curator, "curate"):
                return curator.curate(ranked)
        except (AttributeError, OSError, TypeError, ValueError, RuntimeError):
            pass

        max_candidates = getattr(self.dialog, "MAX_HANZI_CANDIDATES", 10)
        return (ranked or [])[:max_candidates]
