from __future__ import annotations

from typing import Iterable

from domain.jyutping_validation import normalize_jyutping
from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_ui_services import CategoryManagerUIService


def _adapter(dialog_or_adapter) -> CategoryManagerDialogAdapter:
    if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
        return dialog_or_adapter
    return CategoryManagerDialogAdapter(dialog_or_adapter)


def normalize_jyutping_text(jy: str) -> str:
    return normalize_jyutping(jy)


def validate_jyutping(dialog_or_adapter, jy_s: str) -> bool:
    dlg = _adapter(dialog_or_adapter)
    try:
        vocab_svc = dlg.get("_vocab_service")
        if vocab_svc is not None and hasattr(vocab_svc, "validate_jyutping"):
            vocab_svc.validate_jyutping(jy_s)
            return True
    except (TypeError, AttributeError, RuntimeError, ValueError):
        return False

    try:
        from domain.jyutping_validation import validate_jyut_syllables
        ok, _ = validate_jyut_syllables(jy_s)
        return bool(ok)
    except (TypeError, AttributeError, RuntimeError, ValueError):
        return True


def check_duplicate_jyutping(dialog_or_adapter, jy_s: str) -> bool:
    dlg = _adapter(dialog_or_adapter)
    try:
        vocab_svc = dlg.get("_vocab_service")
        if vocab_svc is not None and hasattr(vocab_svc, "check_duplicate_jyutping"):
            return bool(vocab_svc.check_duplicate_jyutping(jy_s))
    except (TypeError, AttributeError, RuntimeError, ValueError):
        return False
    return False


def get_candidates(dialog_or_adapter, jy_s: str) -> list:
    dlg = _adapter(dialog_or_adapter)
    try:
        prov = dlg.get("_candidate_provider")
    except (TypeError, AttributeError, RuntimeError, ValueError):
        prov = None
    try:
        print(f"DBG[CAND] provider={type(prov).__name__ if prov is not None else 'None'} jy='{jy_s}'")
    except Exception:
        pass
    if prov is not None and hasattr(prov, "get_candidates"):
        try:
            out = list(prov.get_candidates(jy_s) or [])
            try:
                print(f"DBG[CAND] provider returned {len(out)} candidates")
            except Exception:
                pass
            return out
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return []
    return []


def preferred_hanzi_for_category(
    dialog_or_adapter,
    cands_list: Iterable,
    category: str | None,
) -> str:
    dlg = _adapter(dialog_or_adapter)
    cat_s = str(category or "").strip()
    if not cat_s:
        return ""

    members = None
    try:
        cats_map = dlg.get("_cats")
        members = cats_map.get(cat_s) if isinstance(cats_map, dict) else None
    except (TypeError, AttributeError, RuntimeError, ValueError):
        members = None

    if not isinstance(members, (list, tuple, set)):
        return ""

    member_set = {str(x).strip() for x in list(members) if str(x).strip()}
    if not member_set:
        return ""

    for row in cands_list:
        hz0 = str((row[0] if isinstance(row, (list, tuple)) and len(row) >= 1 else row) or "").strip()
        if hz0 and hz0 in member_set:
            return hz0
    return ""




def apply_cantonese_cache(dialog_or_adapter, *, hanzi: str, jyutping: str) -> bool:
    dlg = _adapter(dialog_or_adapter)
    try:
        ctrl = dlg.get("_canto_ctrl")
        if ctrl is None:
            return False
        applied = False
        try:
            applied = bool(ctrl.apply_cached_if_available(hanzi=hanzi, jyutping=jyutping))
        except (TypeError, AttributeError, RuntimeError, ValueError):
            applied = False
        if not applied:
            ctrl.request(hanzi=hanzi, jyutping=jyutping)
        return applied
    except (TypeError, AttributeError, RuntimeError, ValueError):
        return False
