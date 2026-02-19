from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResetPlan:
    clear_jy: bool = True
    clear_hz: bool = True
    clear_mn: bool = True
    clear_notes: bool = True
    reset_category: bool = True
    hide_candidates: bool = True
    reset_state: bool = True
    reset_manual_mode: bool = True
    reset_hanzi_committed: bool = True
    reset_state_machine: bool = False


def plan_clear_add_entry_fields() -> ResetPlan:
    return ResetPlan(
        clear_jy=True,
        clear_hz=True,
        clear_mn=True,
        clear_notes=True,
        reset_category=True,
        hide_candidates=True,
        reset_state=True,
        reset_manual_mode=True,
        reset_hanzi_committed=False,
        reset_state_machine=False,
    )


def plan_reset_add_panel_pre_validation() -> ResetPlan:
    return ResetPlan(
        clear_jy=False,
        clear_hz=True,
        clear_mn=True,
        clear_notes=True,
        reset_category=True,
        hide_candidates=True,
        reset_state=True,
        reset_manual_mode=True,
        reset_hanzi_committed=True,
        reset_state_machine=False,
    )


def plan_reset_to_initial_state() -> ResetPlan:
    return ResetPlan(
        clear_jy=True,
        clear_hz=True,
        clear_mn=True,
        clear_notes=True,
        reset_category=True,
        hide_candidates=True,
        reset_state=True,
        reset_manual_mode=True,
        reset_hanzi_committed=True,
        reset_state_machine=True,
    )
