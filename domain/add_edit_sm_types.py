"""Add/Edit state machine types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Optional, Tuple


class AddEditState(Enum):
    EMPTY = auto()
    JY_EDITING = auto()
    JY_REJECTED = auto()
    JY_ACCEPTED = auto()
    CATEGORY_COMMITTED = auto()
    CANDIDATES_AVAILABLE = auto()
    MANUAL_HANZI = auto()
    READY_TO_SAVE = auto()


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


class Event(Enum):
    JY_CHANGED = auto()
    JY_COMMIT = auto()

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

    @property
    def type(self) -> str:  # noqa: D401
        _m = {
            Effect.FOCUS_JY: "focus_jyutping",
            Effect.FOCUS_CATEGORY: "focus_category",
            Effect.FOCUS_CANDIDATES: "focus_candidates",
            Effect.FOCUS_HANZI: "focus_hanzi",
            Effect.FOCUS_MEANING: "focus_meaning",
            Effect.SHOW_WARNING: "show_warning",
            Effect.LOAD_CANDIDATES: "fill_candidates",
            Effect.ENABLE_SAVE: "refresh_save",
            Effect.RESET_FORM: "reset_form",
        }
        return _m.get(self.effect, "")
