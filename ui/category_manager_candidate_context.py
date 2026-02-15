from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter


@dataclass(frozen=True)
class CandidatePipelineContext:
    reverse_index: dict[str, list] | None = None
    style_index: Any | None = None
    candidate_curator: Any | None = None
    max_candidates: int = 10


def build_candidate_context(dialog_or_adapter) -> CandidatePipelineContext:
    dlg = dialog_or_adapter
    if not isinstance(dlg, CategoryManagerDialogAdapter):
        dlg = CategoryManagerDialogAdapter(dialog_or_adapter)

    reverse_index = None
    found_attr = ""
    for attr in ("_reverse_index", "_rev_index", "_reverse_jyut_index"):
        try:
            v = dlg.get(attr)
        except Exception:
            v = None
        if isinstance(v, dict):
            reverse_index = v
            found_attr = attr
            break
    try:
        if reverse_index is None:
            print("DBG[CAND] reverse_index not found on dialog")
        else:
            print(f"DBG[CAND] reverse_index attr='{found_attr}' size={len(reverse_index)}")
    except Exception:
        pass

    return CandidatePipelineContext(
        reverse_index=reverse_index,
        style_index=dlg.get("_style_index"),
        candidate_curator=dlg.get("_candidate_curator"),
        max_candidates=int(dlg.get("MAX_HANZI_CANDIDATES", 10) or 10),
    )
