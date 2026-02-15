"""Add/Edit state machine reducer and derivation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, List

from domain.add_edit_sm_types import (
    AddEditContext,
    AddEditState,
    Effect,
    EffectPayload,
    Event,
)
from domain.add_edit_sm_utils import (
    _is_ready,
    _unpack_event_payload,
    _should_regenerate_candidates,
    _normalize_event,
    _norm,
    _is_valid_jyutping,
)


def derive_state(ctx: AddEditContext) -> AddEditState:
    if not (ctx.jy or "").strip():
        return AddEditState.EMPTY
    if not ctx.jy_ok:
        return AddEditState.JY_EDITING
    if not ctx.cat_ok:
        return AddEditState.JY_ACCEPTED
    if ctx.manual_hanzi:
        if _is_ready(ctx):
            return AddEditState.READY_TO_SAVE
        return AddEditState.MANUAL_HANZI
    if ctx.candidates:
        if _is_ready(ctx):
            return AddEditState.READY_TO_SAVE
        return AddEditState.CANDIDATES_AVAILABLE
    return AddEditState.CATEGORY_COMMITTED


_derive_state = derive_state
derive = derive_state


def reduce(
    state: AddEditState,
    ctx: AddEditContext,
    evt: Any,
) -> tuple[AddEditState, AddEditContext, List[EffectPayload]]:
    effects: List[EffectPayload] = []

    ev, val = _unpack_event_payload(evt)
    ev = _normalize_event(ev)
    if ev is None:
        return state, ctx, effects

    if ev == Event.RESET:
        return (
            AddEditState.EMPTY,
            AddEditContext(),
            [EffectPayload(Effect.RESET_FORM), EffectPayload(Effect.FOCUS_JY)],
        )

    if ev == Event.JY_CHANGED:
        jy_typed = _norm(val)
        if not jy_typed:
            return AddEditState.EMPTY, replace(ctx, jy="", jy_ok=False, duplicate=None), effects
        return AddEditState.JY_EDITING, replace(ctx, jy=jy_typed, jy_ok=False, duplicate=None), effects

    if ev == Event.JY_COMMIT:
        jy_committed = _norm(val) or _norm(getattr(ctx, "jy", ""))
        new_ctx = replace(ctx, jy=jy_committed)
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

    if state == AddEditState.JY_EDITING:
        return state, ctx, effects

    if state == AddEditState.JY_REJECTED:
        return state, ctx, effects

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

            effects2: List[EffectPayload] = []
            if _should_regenerate_candidates(new_ctx):
                effects2.append(EffectPayload(Effect.LOAD_CANDIDATES, new_ctx.jy))

            if _is_ready(new_ctx):
                effects2.append(EffectPayload(Effect.ENABLE_SAVE, True))
                return AddEditState.READY_TO_SAVE, new_ctx, effects2

            return AddEditState.CATEGORY_COMMITTED, new_ctx, effects2

        return state, ctx, effects

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
