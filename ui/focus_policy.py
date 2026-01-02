"""
Pure focus / regeneration policy helpers.

This module contains **no Qt imports** and no dialog state.
It is safe to unit-test in isolation.
"""

from __future__ import annotations


def should_regenerate_candidates(
        *,
        manual_mode: bool = False,
        hanzi_committed: bool = False,
) -> bool:
    """
    Decide whether Hanzi candidates may be regenerated.

    Central rule:
    - Never regenerate after an explicit user choice.
    """
    if manual_mode:
        return False
    if hanzi_committed:
        return False
    return True


def should_steal_focus(*args, **kwargs) -> bool:
    """Decide whether the UI is allowed to steal focus.

    This function is intentionally permissive in its call signature so it can be
    used across refactors and older call sites.

    Supported calling conventions:
      1) Keyword style (preferred):
           should_steal_focus(
               reason="...",
               user_action=...,
               manual_mode=...,
               hanzi_committed=...,
               combo_has_focus=...,
               view_has_focus=...,
           )

      2) Positional fallback used by tests:
           (user_action, combo_has_focus, view_has_focus, manual_mode, hanzi_committed)

    Policy:
      - If `user_action` is True, allow (explicit intent override).
      - Otherwise, never steal focus when manual mode is active, Hanzi is committed,
        or the candidate UI already has focus.
    """

    # ---- Parse positional fallback first (used by tests) ----
    if args:
        # Expected order: (user_action, combo_has_focus, view_has_focus, manual_mode, hanzi_committed)
        user_action = bool(args[0]) if len(args) > 0 else False
        combo_has_focus = bool(args[1]) if len(args) > 1 else False
        view_has_focus = bool(args[2]) if len(args) > 2 else False
        manual_mode = bool(args[3]) if len(args) > 3 else False
        hanzi_committed = bool(args[4]) if len(args) > 4 else False
        # `reason` is ignored for policy; it exists for debugging/telemetry only.
    else:
        # ---- Keyword style (preferred) ----
        user_action = bool(kwargs.get("user_action", False))

        # Accept both new and older keyword names.
        manual_mode = bool(kwargs.get("manual_mode", False))
        hanzi_committed = bool(kwargs.get("hanzi_committed", False))

        combo_has_focus = bool(
            kwargs.get("combo_has_focus", kwargs.get("candidate_combo_has_focus", False))
        )
        view_has_focus = bool(
            kwargs.get("view_has_focus", kwargs.get("candidate_view_has_focus", False))
        )
        # `reason` is ignored for policy; it exists for debugging/telemetry only.

    # Explicit intent override.
    if user_action:
        return True

    # Guardrails.
    if manual_mode or hanzi_committed:
        return False

    if combo_has_focus or view_has_focus:
        return False

    return False


# ---- Backwards-compatible aliases (tests accept any of these) ----

allow_focus_steal = should_steal_focus
can_steal_focus = should_steal_focus
focus_should_steal = should_steal_focus

allow_regenerate_candidates = should_regenerate_candidates
can_regenerate_candidates = should_regenerate_candidates
regenerate_should_run = should_regenerate_candidates