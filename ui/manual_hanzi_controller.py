"""
manual_hanzi_controller.py

UI-free orchestration for entering manual Hanzi mode.

This module MUST NOT import any Qt/PySide UI types. The dialog supplies callables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

# Import path is intentionally tolerant because these modules may live either at
# repo-root (flat module) or under `domain/` depending on build layout.
#
# IMPORTANT:
#   Use importlib (string-based) to avoid IDE/typechecker “unresolved import”
#   warnings when builds choose a different module layout.
import importlib

ManualHanziModePolicy = None  # type: ignore[assignment]
for _mod_name in ("manual_hanzi_mode", "domain.manual_hanzi_mode"):
    try:
        _m = importlib.import_module(_mod_name)
        _p = getattr(_m, "ManualHanziModePolicy", None)
        if _p is not None:
            ManualHanziModePolicy = _p  # type: ignore[assignment]
            break
    except ():  # pragma: no cover
        continue


@dataclass(frozen=True)
class ManualHanziUIHooks:
    """
    Callbacks supplied by the UI layer (CategoryManagerDialog).

    All callables must be best-effort and must not raise; controller treats them defensively.
    """
    set_hanzi_read_only: Callable[[bool], None]
    focus_hanzi: Callable[[], None]
    select_all_hanzi: Optional[Callable[[], None]] = None


class ManualHanziController:
    def __init__(self, hooks: ManualHanziUIHooks):
        self._hooks = hooks

    def ensure_manual_mode_if_needed(self, *, hanzi_read_only: bool, candidates_n: int) -> bool:
        """
        If policy says manual mode is required, make Hanzi editable and focus it.

        Returns True if manual mode was entered; False otherwise.
        """
        if ManualHanziModePolicy is None:
            return False
        decision = ManualHanziModePolicy.decide(hanzi_read_only=hanzi_read_only, candidates_n=candidates_n)
        if not decision.enable_manual_mode:
            return False

        try:
            self._hooks.set_hanzi_read_only(False)
        except (TypeError, AttributeError, RuntimeError):
            # Best-effort contract: if we cannot toggle RO, still attempt focus.
            pass

        try:
            if callable(self._hooks.select_all_hanzi):
                self._hooks.select_all_hanzi()  # type: ignore[misc]
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

        try:
            self._hooks.focus_hanzi()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

        return True