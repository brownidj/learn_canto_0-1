from __future__ import annotations

"""
Compatibility shim.

`utils.utils` remains only to avoid breaking legacy imports.
New code should import from:
- domain.category_rules (policy / rules)
- infra.* (file-backed and composition infrastructure)
"""

from typing import Sequence, List


# ---- Category / UI gates ----
try:
    # Preferred home for these policies (or wherever you currently keep them).
    from domain.category_rules import (
        is_category_placeholder,
        should_show_custom_hanzi_button,
        prefer_meanings,
    )
except Exception:
    # Safe fallbacks (tests will tell you if these need to be stricter).
    def is_category_placeholder(_s: str) -> bool:
        return False

    def should_show_custom_hanzi_button(*_args, **_kwargs) -> bool:
        return True

    def prefer_meanings(items: Sequence[str] | object) -> List[str]:
        try:
            seq = items if isinstance(items, (list, tuple)) else []
            return [str(x).strip() for x in seq if str(x).strip()]
        except Exception:
            return []


# ---- Tier-2 composition / shortlist ----
try:
    from infra.hanzi_composition import compose_candidates_from_chars, shortlist_candidates
except Exception:
    def compose_candidates_from_chars(*_args, **_kwargs):
        return []

    def shortlist_candidates(*_args, **_kwargs):
        return []


# ---- Unihan loading (delegated) ----
try:
    from infra.unihan import load_unihan_char_map  # type: ignore
except Exception:
    def load_unihan_char_map(*_args, **_kwargs):
        return {}