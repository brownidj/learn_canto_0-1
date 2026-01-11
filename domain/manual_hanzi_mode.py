"""
manual_hanzi_mode.py

UI-free policy for deciding when the Add/Edit dialog should allow manual Hanzi entry.

This module MUST NOT import any Qt/PySide UI types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


FocusTarget = Literal["jy", "cat", "cand", "hz", "mn", "save", "none"]


@dataclass(frozen=True)
class ManualHanziModeDecision:
    """
    Result of evaluating whether the user should be placed into manual Hanzi entry mode.

    - enable_manual_mode: if True, the UI should make the Hanzi field editable.
    - focus_target: where focus should go next (typically 'hz').
    - reason: optional short reason string for debug logs/tests.
    """
    enable_manual_mode: bool
    focus_target: FocusTarget = "none"
    reason: str = ""


class ManualHanziModePolicy:
    """
    Pure decision logic.

    Current rule (regression-locked):
      - If the Hanzi field is read-only AND there are zero candidates, we must not dead-end.
        Enable manual Hanzi mode and focus the Hanzi field so the user can type.
    """

    @staticmethod
    def decide(*, hanzi_read_only: bool, candidates_n: int) -> ManualHanziModeDecision:
        try:
            n = int(candidates_n)
        except (TypeError, ValueError, OverflowError):
            n = 0

        if bool(hanzi_read_only) and n <= 0:
            return ManualHanziModeDecision(
                enable_manual_mode=True,
                focus_target="hz",
                reason="no_candidates_hz_read_only",
            )

        return ManualHanziModeDecision(enable_manual_mode=False, focus_target="none", reason="not_required")