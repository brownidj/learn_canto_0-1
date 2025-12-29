

"""
Add/Edit State Machine (Domain Layer)

Pure, UI-free reducer for the Add/Edit workflow.
CategoryManagerDialog should:
  - translate UI signals into Events
  - maintain UI widgets
  - apply Effects emitted by this reducer

This module must remain:
  - deterministic
  - side-effect free
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

    CATEGORY_COMMIT = auto()

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

    # Jyutping accepted but category not yet committed/valid
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
    evt: EventPayload,
) -> tuple[AddEditState, AddEditContext, List[EffectPayload]]:

    effects: List[EffectPayload] = []

    # ---- RESET ----
    if evt.event == Event.RESET:
        return (
            AddEditState.EMPTY,
            AddEditContext(),
            [EffectPayload(Effect.RESET_FORM), EffectPayload(Effect.FOCUS_JY)],
        )

    # ---- EMPTY ----
    if state == AddEditState.EMPTY:
        if evt.event == Event.JY_CHANGED and str(evt.value or "").strip():
            return (
                AddEditState.JY_EDITING,
                replace(ctx, jy=str(evt.value)),
                [],
            )
        return state, ctx, effects

    # ---- JY_EDITING ----
    if state == AddEditState.JY_EDITING:
        if evt.event == Event.JY_CHANGED:
            return state, replace(ctx, jy=str(evt.value)), effects

        if evt.event == Event.JY_COMMIT:
            if not ctx.jy_ok:
                return (
                    AddEditState.JY_REJECTED,
                    ctx,
                    [EffectPayload(Effect.SHOW_WARNING, "Invalid Jyutping"),
                     EffectPayload(Effect.FOCUS_JY)],
                )
            return (
                AddEditState.JY_ACCEPTED,
                replace(
                    ctx,
                    category="",
                    cat_ok=False,
                    hanzi="",
                    hz_ok=False,
                    meaning="",
                    mn_ok=False,
                    candidates=(),
                ),
                [EffectPayload(Effect.FOCUS_CATEGORY)],
            )

    # ---- JY_REJECTED ----
    if state == AddEditState.JY_REJECTED:
        if evt.event == Event.JY_CHANGED:
            return (
                AddEditState.JY_EDITING,
                replace(ctx, jy=str(evt.value)),
                [],
            )

    # ---- JY_ACCEPTED ----
    if state == AddEditState.JY_ACCEPTED:
        if evt.event == Event.CATEGORY_COMMIT:
            if not ctx.cat_ok:
                return (
                    state,
                    ctx,
                    [EffectPayload(Effect.SHOW_WARNING, "Select a category"),
                     EffectPayload(Effect.FOCUS_CATEGORY)],
                )
            return (
                AddEditState.CATEGORY_COMMITTED,
                ctx,
                [EffectPayload(Effect.LOAD_CANDIDATES, ctx.jy)],
            )

        if evt.event == Event.JY_CHANGED:
            return (
                AddEditState.JY_EDITING,
                replace(ctx, jy=str(evt.value)),
                [],
            )

    # ---- CATEGORY_COMMITTED ----
    if state == AddEditState.CATEGORY_COMMITTED:
        if evt.event == Event.CANDIDATES_LOADED:
            cands = tuple(evt.value or ())
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

    # ---- CANDIDATES_AVAILABLE ----
    if state == AddEditState.CANDIDATES_AVAILABLE:
        if evt.event == Event.CANDIDATE_SELECTED:
            hz = str(evt.value or "").strip()
            new_ctx = replace(ctx, hanzi=hz, hz_ok=bool(hz))
            if _is_ready(new_ctx):
                effects.append(EffectPayload(Effect.ENABLE_SAVE, True))
                return AddEditState.READY_TO_SAVE, new_ctx, effects
            return state, new_ctx, [EffectPayload(Effect.FOCUS_MEANING)]

        if evt.event == Event.MANUAL_HANZI_ENABLED:
            return (
                AddEditState.MANUAL_HANZI,
                replace(ctx, manual_hanzi=True, candidates=()),
                [EffectPayload(Effect.FOCUS_HANZI)],
            )

    # ---- MANUAL_HANZI ----
    if state == AddEditState.MANUAL_HANZI:
        if evt.event == Event.HANZI_CHANGED:
            hz = str(evt.value or "").strip()
            new_ctx = replace(ctx, hanzi=hz, hz_ok=bool(hz))
            if _is_ready(new_ctx):
                return AddEditState.READY_TO_SAVE, new_ctx, [EffectPayload(Effect.ENABLE_SAVE, True)]
            return state, new_ctx, []

    # ---- READY_TO_SAVE ----
    if state == AddEditState.READY_TO_SAVE:
        if evt.event == Event.MEANING_CHANGED:
            mn = str(evt.value or "").strip()
            new_ctx = replace(ctx, meaning=mn, mn_ok=bool(mn))
            if not _is_ready(new_ctx):
                return AddEditState.CANDIDATES_AVAILABLE, new_ctx, [EffectPayload(Effect.ENABLE_SAVE, False)]
            return state, new_ctx, []

        if evt.event == Event.SAVE_CLICKED:
            return (
                state,
                replace(ctx, saving=True),
                [],
            )

        if evt.event == Event.SAVE_RESULT and evt.value is True:
            return (
                AddEditState.EMPTY,
                AddEditContext(),
                [EffectPayload(Effect.RESET_FORM), EffectPayload(Effect.FOCUS_JY)],
            )

    return state, ctx, effects