"""
CategoryManager candidate pipeline extracted for maintainability.

Handles Hanzi candidate lookup, style detection, and curation.
"""

import logging
from typing import TYPE_CHECKING

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_candidate_context import CandidatePipelineContext, build_candidate_context

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerCandidatePipeline:
    """Manages Hanzi candidate pipeline for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        self._dlg = CategoryManagerDialogAdapter(dialog)

    def reverse_candidates_for_jy(self, jy: str) -> list[tuple[str, str, int]]:
        """Return Tier-1 reverse candidates for a Jyutping (deterministic, test-friendly)."""
        jy_s = str(jy or "").strip()
        if not jy_s:
            return []
        try:
            from domain.jyutping_validation import normalize_jyutping
            jy_s = normalize_jyutping(jy_s)
        except (ImportError, AttributeError, TypeError, ValueError):
            jy_s = " ".join(jy_s.lower().split())

        items = []
        rev = build_candidate_context(self._dlg).reverse_index
        try:
            print(
                "DBG[CAND] reverse_candidates_for_jy",
                f"jy='{jy_s}'",
                f"rev_none={rev is None}",
                f"rev_size={len(rev) if isinstance(rev, dict) else 'na'}",
            )
        except Exception:
            pass
        if isinstance(rev, dict):
            try:
                items = rev.get(jy_s) or []
            except (TypeError, AttributeError, RuntimeError):
                items = []
        try:
            print(f"DBG[CAND] reverse_candidates_for_jy items={len(items) if items is not None else 'None'}")
        except Exception:
            pass

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


class CandidatePipelineProvider:
    """Adapter to expose candidate lookup via a stable interface."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self._dialog = dialog
        self._dlg = CategoryManagerDialogAdapter(dialog)
        self._ctx = build_candidate_context(self._dlg)

    def get_candidates(self, jy: str) -> list[tuple[str, str, int]]:
        hanzi_pipeline = self._dlg.get("_hanzi_pipeline")
        if hanzi_pipeline is not None and hasattr(hanzi_pipeline, "run"):
            try:
                print(
                    "DBG[CAND] provider pipeline",
                    f"type={type(hanzi_pipeline).__name__}",
                    "mode=hanzi_pipeline",
                )
            except Exception:
                pass
            try:
                return list(hanzi_pipeline.run(jy) or [])
            except Exception:
                return []

        pipeline = self._dlg.get("_candidate_pipeline")
        try:
            print(
                "DBG[CAND] provider pipeline",
                f"type={type(pipeline).__name__ if pipeline is not None else 'None'}",
                f"has_reverse={hasattr(pipeline, 'reverse_candidates_for_jy') if pipeline is not None else False}",
            )
        except Exception:
            pass
        if pipeline is not None and hasattr(pipeline, "reverse_candidates_for_jy"):
            try:
                return list(pipeline.reverse_candidates_for_jy(jy) or [])
            except Exception:
                return []
        return []

    def load_hanzi_style_map(self) -> dict:
        """Lazy-load data/hanzi_style.yaml (Hanzi -> {style, source, notes}).

        Back-compat wrapper around the internal _HanziStyleIndex.
        """
        try:
            style_index = self._ctx.style_index
            if style_index is not None and hasattr(style_index, "load"):
                return style_index.load()
        except (AttributeError, OSError, TypeError, ValueError, RuntimeError):
            pass
        return {}

    def hanzi_style(self, hanzi: str) -> str:
        """Back-compat wrapper for style lookup."""
        try:
            style_index = self._ctx.style_index
            if style_index is not None and hasattr(style_index, "style_for"):
                return style_index.style_for(hanzi)
        except (AttributeError, OSError, TypeError, ValueError, RuntimeError):
            pass
        return "unknown"

    def is_colloquial_hanzi(self, hanzi: str) -> bool:
        """Back-compat wrapper for colloquial detection."""
        try:
            style_index = self._ctx.style_index
            if style_index is not None and hasattr(style_index, "is_colloquial"):
                return style_index.is_colloquial(hanzi)
        except (AttributeError, OSError, TypeError, ValueError, RuntimeError):
            pass
        return False

    def curate_top_hanzi_candidates(self, ranked: list[str]) -> list[str]:
        """Back-compat wrapper to curate the top candidates for the UI."""
        try:
            curator = self._ctx.candidate_curator
            if curator is not None and hasattr(curator, "curate"):
                return curator.curate(ranked)
        except (AttributeError, OSError, TypeError, ValueError, RuntimeError):
            pass

        return (ranked or [])[: self._ctx.max_candidates]
