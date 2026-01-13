"""Centralized focus management for Add/Edit workflows.

Replaces scattered _defer_focus(), _apply_focus_policy() calls with a single
state-driven focus controller.
"""

from __future__ import annotations
from typing import Literal, Callable, Any
from enum import Enum, auto

FocusTarget = Literal["jy", "hz", "mn", "cat", "cand"]


class FocusPolicy(Enum):
    """Focus movement policies."""
    ALLOW = auto()      # Always allow focus change
    BLOCK = auto()      # Never change focus
    DEFER = auto()      # Defer to next event loop tick


class FocusState:
    """Immutable focus state for decision making."""

    def __init__(
        self,
        *,
        user_action: bool = False,
        manual_mode: bool = False,
        hanzi_committed: bool = False,
        combo_has_focus: bool = False,
        view_has_focus: bool = False,
    ):
        self.user_action = user_action
        self.manual_mode = manual_mode
        self.hanzi_committed = hanzi_committed
        self.combo_has_focus = combo_has_focus
        self.view_has_focus = view_has_focus


class FocusManager:
    """Manages focus transitions for Add/Edit workflow.

    Responsibilities:
    - Decides when focus moves are allowed
    - Defers focus changes to avoid signal races
    - Provides clean API for UI controllers

    Non-responsibilities:
    - Doesn't know about Qt widgets directly
    - Doesn't emit signals
    - Doesn't modify state
    """

    def __init__(
        self,
        *,
        focus_jy: Callable[[], None],
        focus_hz: Callable[[], None],
        focus_mn: Callable[[], None],
        focus_cat: Callable[[bool], None],  # takes show_popup arg
        focus_cand: Callable[[], None],
        defer: Callable[[Callable[[], None]], None] | None = None,
    ):
        """
        Args:
            focus_jy: Function to focus Jyutping field
            focus_hz: Function to focus Hanzi field
            focus_mn: Function to focus Meanings field
            focus_cat: Function to focus Category field (with popup flag)
            focus_cand: Function to focus Candidate combo
            defer: Optional function to defer callbacks (e.g., QTimer.singleShot)
        """
        self._focus_jy = focus_jy
        self._focus_hz = focus_hz
        self._focus_mn = focus_mn
        self._focus_cat = focus_cat
        self._focus_cand = focus_cand
        self._defer = defer or self._immediate

    @staticmethod
    def _immediate(callback: Callable[[], None]) -> None:
        """Immediate execution (no deferral)."""
        callback()

    def should_allow_focus_change(self, state: FocusState) -> bool:
        """Decide if focus change is allowed based on current state.

        Rules:
        - User actions always allowed
        - Manual mode blocks auto-focus
        - Combo/view focus blocks stealing
        - Committed Hanzi blocks re-focus

        Args:
            state: Current focus state

        Returns:
            True if focus change allowed
        """
        # User explicitly triggered action - always allow
        if state.user_action:
            return True

        # Manual mode: user is typing Hanzi manually, don't interrupt
        if state.manual_mode:
            return False

        # Hanzi already committed, don't steal focus back
        if state.hanzi_committed:
            return False

        # Combo or its popup has focus - don't steal during selection
        if state.combo_has_focus or state.view_has_focus:
            return False

        return True

    def focus(
        self,
        target: FocusTarget,
        *,
        state: FocusState | None = None,
        policy: FocusPolicy = FocusPolicy.ALLOW,
        show_popup: bool = False,
    ) -> bool:
        """Move focus to target field if allowed.

        Args:
            target: Where to move focus
            state: Current focus state (for decision making)
            policy: Focus policy to apply
            show_popup: For category, whether to show dropdown

        Returns:
            True if focus was moved
        """
        # Check policy
        if policy == FocusPolicy.BLOCK:
            return False

        # Check state-based rules
        if state is not None:
            if not self.should_allow_focus_change(state):
                return False

        # Apply focus (possibly deferred)
        def _apply():
            if target == "jy":
                self._focus_jy()
            elif target == "hz":
                self._focus_hz()
            elif target == "mn":
                self._focus_mn()
            elif target == "cat":
                self._focus_cat(show_popup)
            elif target == "cand":
                self._focus_cand()

        if policy == FocusPolicy.DEFER:
            self._defer(_apply)
        else:
            _apply()

        return True

    def focus_next_in_sequence(
        self,
        current: FocusTarget,
        *,
        state: FocusState | None = None,
        show_popup: bool = False,
    ) -> bool:
        """Move to next field in Add/Edit sequence.

        Sequence: jy → cat → cand/hz → mn

        Args:
            current: Current field
            state: Focus state for decision making
            show_popup: Whether to show category popup

        Returns:
            True if focus was moved
        """
        sequence: dict[FocusTarget, FocusTarget] = {
            "jy": "cat",
            "cat": "cand",  # or "hz" if no candidates
            "cand": "mn",
            "hz": "mn",
            "mn": "jy",  # Loop back after save
        }

        next_target = sequence.get(current)
        if next_target is None:
            return False

        return self.focus(
            next_target,
            state=state,
            policy=FocusPolicy.DEFER,
            show_popup=(show_popup and next_target == "cat"),
        )


__all__ = [
    "FocusManager",
    "FocusState",
    "FocusTarget",
    "FocusPolicy",
]
