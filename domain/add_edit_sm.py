"""
Add/Edit State Machine (Domain Layer)

Pure, UI-free reducer for the Add/Edit workflow.
CategoryManagerDialog should:
  - translate UI signals into Events
  - maintain UI widgets
  - apply Effects emitted by this reducer

This module must remain:
  - deterministic
  - side effect free
  - unit-testable
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum, auto
from typing import Any, List, Optional, Tuple


# -------------------------
# States
# -------------------------

class AddEditState(Enum):
    EMPTY = auto()
    JY_EDITING = auto()
    JY_REJECTED = auto()
    JY_ACCEPTED = auto()
    CATEGORY_COMMITTED = auto()
    CANDIDATES_AVAILABLE = auto()
    MANUAL_HANZI = auto()
    READY_TO_SAVE = auto()


# -------------------------
# Context
# -------------------------

@dataclass(frozen=True)
class AddEditContext:
    jy: str = ""
    jy_ok: bool = False

    duplicate: Optional[str] = None  # None | "JY" | "JY_HZ"

    category: str = ""
    cat_ok: bool = False

    candidates: Tuple[Tuple[str, str, float], ...] = ()

    hanzi: str = ""
    hz_ok: bool = False
    manual_hanzi: bool = False

    meaning: str = ""
    mn_ok: bool = False

    saving: bool = False


# -------------------------
# Events
# -------------------------

class Event(Enum):
    JY_CHANGED = auto()
    JY_COMMIT = auto()

    # Category commit event (primary name) + aliases for legacy/tests
    CATEGORY_COMMITTED = auto()
    CATEGORY_COMMIT = CATEGORY_COMMITTED
    CAT_COMMITTED = CATEGORY_COMMITTED
    CATEGORY_ACCEPTED = CATEGORY_COMMITTED

    CANDIDATES_LOADED = auto()
    CANDIDATE_SELECTED = auto()

    MANUAL_HANZI_ENABLED = auto()
    HANZI_CHANGED = auto()

    MEANING_CHANGED = auto()

    SAVE_CLICKED = auto()
    SAVE_RESULT = auto()

    RESET = auto()


@dataclass(frozen=True)
class EventPayload:
    event: Event
    value: Any = None


# -------------------------
# Effects (UI instructions)
# -------------------------

class Effect(Enum):
    FOCUS_JY = auto()
    FOCUS_CATEGORY = auto()
    FOCUS_CANDIDATES = auto()
    FOCUS_HANZI = auto()
    FOCUS_MEANING = auto()

    SHOW_WARNING = auto()

    LOAD_CANDIDATES = auto()
    ENABLE_SAVE = auto()

    RESET_FORM = auto()


@dataclass(frozen=True)
class EffectPayload:
    effect: Effect
    value: Any = None

    # Back-compat: some tests and UI adapters expect an attribute named `type`
    # (or dict key "type") describing the effect as a string.
    @property
    def type(self) -> str:  # noqa: D401
        _m = {
            Effect.FOCUS_JY: "focus_jyutping",
            Effect.FOCUS_CATEGORY: "focus_category",
            Effect.FOCUS_CANDIDATES: "focus_candidates",
            Effect.FOCUS_HANZI: "focus_hanzi",
            Effect.FOCUS_MEANING: "focus_meaning",
            Effect.SHOW_WARNING: "show_warning",
            # The dialog historically calls this `fill_candidates`.
            Effect.LOAD_CANDIDATES: "fill_candidates",
            Effect.ENABLE_SAVE: "refresh_save",
            Effect.RESET_FORM: "reset_form",
        }
        return _m.get(self.effect, "")


# -------------------------
# Reducer helpers
# -------------------------


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

    # Dict fallback used by some UI adapters
    if isinstance(evt, dict):
        return evt.get("event"), evt.get("value")

    # Object payload
    ev = getattr(evt, "event", None)
    val = getattr(evt, "value", None)
    if ev is not None or val is not None:
        return ev, val

    # Tuple/list fallback
    if isinstance(evt, (tuple, list)) and evt:
        ev2 = evt[0]
        val2 = evt[1] if len(evt) >= 2 else None
        return ev2, val2

    return None, None


def _should_regenerate_candidates(ctx: AddEditContext) -> bool:
    """Decide whether the reducer should request (re)loading Hanzi candidates.

    Source of truth is SM context only:
      - If the user is in manual Hanzi mode, never regenerate.
      - If a Hanzi value is already present/OK, never regenerate.
      - If candidates are already present, do not regenerate (keeps UI stable).

    This intentionally avoids UI-layer guards and exception-heavy logic.
    """
    return (not ctx.manual_hanzi) and (not ctx.hz_ok) and (not ctx.candidates)


# -------------------------
# Derivation (pure)
# -------------------------

def derive_state(ctx: AddEditContext) -> AddEditState:
    """Derive an Add/Edit state from context only.

    This is intentionally conservative and pure. It is used by tests and
    any UI code that wants a simple, deterministic snapshot.
    """
    # Reset-like base
    if not (ctx.jy or "").strip():
        return AddEditState.EMPTY

    # While typing / before validation accepts
    if not ctx.jy_ok:
        return AddEditState.JY_EDITING

    # Jyutping accepted, but category not yet committed/valid
    if not ctx.cat_ok:
        return AddEditState.JY_ACCEPTED

    # Category committed; awaiting candidates or manual hanzi path
    if ctx.manual_hanzi:
        # Manual path; ready only once meaning is also OK
        if _is_ready(ctx):
            return AddEditState.READY_TO_SAVE
        return AddEditState.MANUAL_HANZI

    # Candidates path
    if ctx.candidates:
        if _is_ready(ctx):
            return AddEditState.READY_TO_SAVE
        return AddEditState.CANDIDATES_AVAILABLE

    # Category committed but candidates not loaded yet
    return AddEditState.CATEGORY_COMMITTED


# Back-compat aliases (older tests/tools may import these names)
_derive_state = derive_state
derive = derive_state


# -------------------------
# Reducer
# -------------------------

def reduce(
    state: AddEditState,
    ctx: AddEditContext,
    evt: Any,
) -> tuple[AddEditState, AddEditContext, List[EffectPayload]]:
    effects: List[EffectPayload] = []

    # Support legacy/UI adapter payload shapes (dict / tuple / EventPayload)
    ev, val = _unpack_event_payload(evt)

    # Normalize event values coming from UI adapters.
    # UI code may pass:
    #   - this module's `Event`
    #   - an Enum from another module with the same `.name`
    #   - a string name
    #   - legacy names like "JYUTPING_COMMITTED"
    if ev is None:
        return state, ctx, effects

    if not isinstance(ev, Event):
        name = None
        try:
            name = getattr(ev, "name", None)
        except Exception:
            name = None
        if name is None and isinstance(ev, str):
            name = ev

        if isinstance(name, str):
            key = name.strip().upper()
            # Map common legacy/adapter names onto reducer events.
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
                ev = Event[key]
            except Exception:
                # Unknown event name: fail soft.
                return state, ctx, effects
        else:
            # Unknown event type: fail soft.
            return state, ctx, effects

    def _norm(s: Any) -> str:
        try:
            return str(s or "").strip()
        except Exception:
            return ""

    def _is_valid_jyutping(jy: str) -> bool:
        """Minimal, deterministic Jyutping validator.

        Accepts simple syllable+tone digit forms like 'leng3'.
        Domain/UI layers may apply richer validation; this is a safe baseline.
        """
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

    # ---- RESET ----
    if ev == Event.RESET:
        return (
            AddEditState.EMPTY,
            AddEditContext(),
            [EffectPayload(Effect.RESET_FORM), EffectPayload(Effect.FOCUS_JY)],
        )

    # ---- Global Jyutping typing ----
    if ev == Event.JY_CHANGED:
        jy_typed = _norm(val)
        if not jy_typed:
            return AddEditState.EMPTY, replace(ctx, jy="", jy_ok=False, duplicate=None), effects
        # While typing, treat as not-yet-validated
        return AddEditState.JY_EDITING, replace(ctx, jy=jy_typed, jy_ok=False, duplicate=None), effects

    # ---- Global Jyutping commit ----
    if ev == Event.JY_COMMIT:
        jy_committed = _norm(val) or _norm(getattr(ctx, "jy", ""))
        new_ctx = replace(ctx, jy=jy_committed)

        # Validate deterministically here so SM can advance even when UI did not pre-validate.
        jy_ok = _is_valid_jyutping(jy_committed)
        new_ctx = replace(new_ctx, jy_ok=jy_ok)

        if not jy_ok:
            return (
                AddEditState.JY_REJECTED,
                new_ctx,
                [
                    EffectPayload(Effect.SHOW_WARNING, "Invalid Jyutping"),
                    EffectPayload(Effect.FOCUS_JY),
                ],
            )

        # Accepted: clear downstream fields and steer to category
        accepted_ctx = replace(
            new_ctx,
            category="",
            cat_ok=False,
            hanzi="",
            hz_ok=False,
            meaning="",
            mn_ok=False,
            candidates=(),
            manual_hanzi=False,
        )
        return (
            AddEditState.JY_ACCEPTED,
            accepted_ctx,
            [EffectPayload(Effect.FOCUS_CATEGORY)],
        )

    # ---- JY_EDITING ----
    if state == AddEditState.JY_EDITING:
        # Non-Jyutping events are ignored until Jyutping is accepted.
        return state, ctx, effects

    # ---- JY_REJECTED ----
    if state == AddEditState.JY_REJECTED:
        # After rejection, only a new Jyutping change/commit can advance.
        # Those are handled by the global JY_CHANGED/JY_COMMIT handlers above.
        return state, ctx, effects

    # ---- JY_ACCEPTED ----
    if state == AddEditState.JY_ACCEPTED:
        if ev in (
            Event.CATEGORY_COMMITTED,
            Event.CATEGORY_COMMIT,
            Event.CAT_COMMITTED,
            Event.CATEGORY_ACCEPTED,
        ):
            cat = _norm(val)
            new_ctx = replace(
                ctx,
                category=cat,
                cat_ok=bool(cat) and cat.lower() != "all",
            )

            if not new_ctx.cat_ok:
                return (
                    state,
                    new_ctx,
                    [
                        EffectPayload(Effect.SHOW_WARNING, "Select a category"),
                        EffectPayload(Effect.FOCUS_CATEGORY),
                    ],
                )

            # Candidate loading policy is SM-owned (no UI guards).
            effects2: List[EffectPayload] = []
            if _should_regenerate_candidates(new_ctx):
                effects2.append(EffectPayload(Effect.LOAD_CANDIDATES, new_ctx.jy))

            # If everything is ready after category commit, allow Save immediately.
            if _is_ready(new_ctx):
                effects2.append(EffectPayload(Effect.ENABLE_SAVE, True))
                return AddEditState.READY_TO_SAVE, new_ctx, effects2

            return AddEditState.CATEGORY_COMMITTED, new_ctx, effects2

        return state, ctx, effects

    # ---- CATEGORY_COMMITTED ----
    if state == AddEditState.CATEGORY_COMMITTED:
        if ev == Event.CANDIDATES_LOADED:
            cands = tuple(val or ())
            if not cands:
                return (
                    AddEditState.MANUAL_HANZI,
                    replace(ctx, manual_hanzi=True),
                    [EffectPayload(Effect.FOCUS_HANZI)],
                )
            return (
                AddEditState.CANDIDATES_AVAILABLE,
                replace(ctx, candidates=cands),
                [EffectPayload(Effect.FOCUS_CANDIDATES)],
            )
        return state, ctx, effects

    # ---- CANDIDATES_AVAILABLE ----
    if state == AddEditState.CANDIDATES_AVAILABLE:
        if ev == Event.MEANING_CHANGED:
            mn = _norm(val)
            new_ctx = replace(ctx, meaning=mn, mn_ok=bool(mn))
            if _is_ready(new_ctx):
                return AddEditState.READY_TO_SAVE, new_ctx, [EffectPayload(Effect.ENABLE_SAVE, True)]
            return state, new_ctx, []
        if ev == Event.CANDIDATE_SELECTED:
            hz = _norm(val)
            new_ctx = replace(ctx, hanzi=hz, hz_ok=bool(hz))
            if _is_ready(new_ctx):
                return AddEditState.READY_TO_SAVE, new_ctx, [EffectPayload(Effect.ENABLE_SAVE, True)]
            return state, new_ctx, [EffectPayload(Effect.FOCUS_MEANING)]

        if ev == Event.MANUAL_HANZI_ENABLED:
            return (
                AddEditState.MANUAL_HANZI,
                replace(ctx, manual_hanzi=True, candidates=()),
                [EffectPayload(Effect.FOCUS_HANZI)],
            )

        return state, ctx, effects

    # ---- MANUAL_HANZI ----
    if state == AddEditState.MANUAL_HANZI:
        if ev == Event.MEANING_CHANGED:
            mn = _norm(val)
            new_ctx = replace(ctx, meaning=mn, mn_ok=bool(mn))
            if _is_ready(new_ctx):
                return AddEditState.READY_TO_SAVE, new_ctx, [EffectPayload(Effect.ENABLE_SAVE, True)]
            return state, new_ctx, []
        if ev == Event.HANZI_CHANGED:
            hz = _norm(val)
            new_ctx = replace(ctx, hanzi=hz, hz_ok=bool(hz))
            if _is_ready(new_ctx):
                return AddEditState.READY_TO_SAVE, new_ctx, [EffectPayload(Effect.ENABLE_SAVE, True)]
            return state, new_ctx, []
        return state, ctx, effects

    # ---- READY_TO_SAVE ----
    if state == AddEditState.READY_TO_SAVE:
        if ev == Event.MEANING_CHANGED:
            mn = _norm(val)
            new_ctx = replace(ctx, meaning=mn, mn_ok=bool(mn))
            if not _is_ready(new_ctx):
                return AddEditState.CANDIDATES_AVAILABLE, new_ctx, [EffectPayload(Effect.ENABLE_SAVE, False)]
            return state, new_ctx, []

        if ev == Event.SAVE_CLICKED:
            return state, replace(ctx, saving=True), []

        if ev == Event.SAVE_RESULT and val is True:
            return (
                AddEditState.EMPTY,
                AddEditContext(),
                [EffectPayload(Effect.RESET_FORM), EffectPayload(Effect.FOCUS_JY)],
            )

        return state, ctx, effects

    return state, ctx, effects