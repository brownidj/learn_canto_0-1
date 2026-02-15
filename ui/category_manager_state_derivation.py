from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AddEditDerivedState:
    jy: str = ""
    jy_ok: bool = False
    hanzi: str = ""
    hz_ok: bool = False
    meaning: str = ""
    mn_ok: bool = False
    category: str = ""
    cat_ok: bool = False
    saving: bool = False
    ready_to_save: bool = False


class AddEditStateDerivation:
    """Pure state derivation for Add/Edit save gating."""

    @staticmethod
    def derive(
        *,
        jy: str,
        hanzi: str,
        meaning: str,
        category: str,
        jy_ok: bool,
        saving: bool,
    ) -> AddEditDerivedState:
        jy_s = (jy or "").strip()
        hz_s = (hanzi or "").strip()
        mn_s = (meaning or "").strip()
        cat_s = (category or "").strip()

        hz_ok = bool(hz_s)
        mn_ok = bool(mn_s)

        cat_l = cat_s.lower()
        cat_ok = bool(cat_s) and cat_l not in ("unassigned", "all")

        ready = bool(jy_ok and hz_ok and mn_ok and cat_ok and not saving)

        return AddEditDerivedState(
            jy=jy_s,
            jy_ok=bool(jy_ok),
            hanzi=hz_s,
            hz_ok=bool(hz_ok),
            meaning=mn_s,
            mn_ok=bool(mn_ok),
            category=cat_s,
            cat_ok=bool(cat_ok),
            saving=bool(saving),
            ready_to_save=bool(ready),
        )
