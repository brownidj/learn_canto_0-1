"""ViewModel for Add/Edit state (UI layer)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from domain.add_edit_sm import AddEditContext


@dataclass
class AddEditViewModel:
    """Mutable view-model representing the current Add/Edit state."""

    jy: str = ""
    jy_ok: bool = False
    duplicate: str | None = None

    category: str = ""
    cat_ok: bool = False

    candidates: Tuple[Tuple[str, str, float], ...] = ()

    hanzi: str = ""
    hz_ok: bool = False
    manual_hanzi: bool = False

    meaning: str = ""
    mn_ok: bool = False
    meaning_source: str = ""

    saving: bool = False

    @classmethod
    def from_context(cls, ctx: AddEditContext | None) -> "AddEditViewModel":
        if ctx is None:
            return cls()
        return cls(
            jy=ctx.jy,
            jy_ok=ctx.jy_ok,
            duplicate=ctx.duplicate,
            category=ctx.category,
            cat_ok=ctx.cat_ok,
            candidates=ctx.candidates,
            hanzi=ctx.hanzi,
            hz_ok=ctx.hz_ok,
            manual_hanzi=ctx.manual_hanzi,
            meaning=ctx.meaning,
            mn_ok=ctx.mn_ok,
            saving=ctx.saving,
        )

    def to_context(self) -> AddEditContext:
        return AddEditContext(
            jy=self.jy,
            jy_ok=self.jy_ok,
            duplicate=self.duplicate,
            category=self.category,
            cat_ok=self.cat_ok,
            candidates=self.candidates,
            hanzi=self.hanzi,
            hz_ok=self.hz_ok,
            manual_hanzi=self.manual_hanzi,
            meaning=self.meaning,
            mn_ok=self.mn_ok,
            saving=self.saving,
        )
