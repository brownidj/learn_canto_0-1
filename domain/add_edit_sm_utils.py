"""Add/Edit state machine helpers."""

from __future__ import annotations

from typing import Any

from domain.add_edit_sm_types import AddEditContext, Event


def _is_ready(ctx: AddEditContext) -> bool:
    return (
        ctx.jy_ok
        and ctx.cat_ok
        and ctx.hz_ok
        and ctx.mn_ok
        and not ctx.saving
        and ctx.duplicate != "JY_HZ"
    )


def _unpack_event_payload(evt: Any) -> tuple[Any, Any]:
    """Return (event_enum, value) from EventPayload-like objects, dict payloads, or tuple/list payloads."""
    if evt is None:
        return None, None

    if isinstance(evt, dict):
        return evt.get("event"), evt.get("value")

    ev = getattr(evt, "event", None)
    val = getattr(evt, "value", None)
    if ev is not None or val is not None:
        return ev, val

    if isinstance(evt, (tuple, list)) and evt:
        ev2 = evt[0]
        val2 = evt[1] if len(evt) >= 2 else None
        return ev2, val2

    return None, None


def _should_regenerate_candidates(ctx: AddEditContext) -> bool:
    return (not ctx.manual_hanzi) and (not ctx.hz_ok) and (not ctx.candidates)


def _normalize_event(ev: Any):
    if isinstance(ev, Event):
        return ev

    name = None
    try:
        name = getattr(ev, "name", None)
    except Exception:
        name = None
    if name is None and isinstance(ev, str):
        name = ev

    if isinstance(name, str):
        key = name.strip().upper()
        legacy_map = {
            "JYUTPING_COMMITTED": "JY_COMMIT",
            "JYUTPING_ACCEPTED": "JY_COMMIT",
            "JY_COMMITTED": "JY_COMMIT",
            "JY_ACCEPTED": "JY_COMMIT",
            "JY_EDITING": "JY_CHANGED",
            "HANZI_EDITED": "HANZI_CHANGED",
            "HANZI_TYPED": "HANZI_CHANGED",
            "HZ_CHANGED": "HANZI_CHANGED",
            "HZ_EDITED": "HANZI_CHANGED",
            "MEANINGS_CHANGED": "MEANING_CHANGED",
            "MEANING_EDITED": "MEANING_CHANGED",
            "MEANINGS_EDITED": "MEANING_CHANGED",
            "MN_CHANGED": "MEANING_CHANGED",
            "CAT_CHANGED": "CATEGORY_COMMITTED",
            "CATEGORY_CHANGED": "CATEGORY_COMMITTED",
        }
        key = legacy_map.get(key, key)
        try:
            return Event[key]
        except Exception:
            return None
    return None


def _norm(s: Any) -> str:
    try:
        return str(s or "").strip()
    except Exception:
        return ""


def _is_valid_jyutping(jy: str) -> bool:
    """Minimal, deterministic Jyutping validator."""
    j = (jy or "").strip().lower()
    if not j:
        return False
    if len(j) < 2:
        return False
    tone = j[-1]
    base = j[:-1]
    if tone not in "123456":
        return False
    if not base.isalpha():
        return False
    return True
