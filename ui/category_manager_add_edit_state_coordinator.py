from __future__ import annotations

from ui.category_manager_add_edit_state_service import AddEditStateService
from ui.category_manager_helpers import CategoryManagerHelpers
from ui.category_manager_state_derivation import AddEditStateDerivation
from ui.category_manager_state_reactions import AddEditStateReactions


class AddEditStateCoordinator:
    """Thin coordinator for Add/Edit state derivation + reactions."""

    def __init__(self, dialog_or_adapter):
        self._state = AddEditStateService(dialog_or_adapter)
        self._reactions = AddEditStateReactions(self._state._dlg)

    def update_from_fields(
        self,
        *,
        jy: str,
        hanzi: str,
        meaning: str,
        category: str,
        jy_ok: bool,
        saving: bool,
    ) -> None:
        derived = AddEditStateDerivation.derive(
            jy=jy,
            hanzi=hanzi,
            meaning=meaning,
            category=category,
            jy_ok=bool(jy_ok),
            saving=bool(saving),
        )

        # Preserve existing jy if empty
        try:
            vm = self._state.get_state()
            existing_jy = str(getattr(vm, "jy", "") or "").strip() if vm is not None else ""
        except (TypeError, AttributeError, RuntimeError):
            existing_jy = ""
        update_jy = derived.jy if (derived.jy or not existing_jy) else existing_jy

        self._state.update_vm(
            jy=update_jy,
            jy_ok=derived.jy_ok,
            hanzi=derived.hanzi,
            hz_ok=derived.hz_ok,
            meaning=derived.meaning,
            mn_ok=derived.mn_ok,
            category=derived.category,
            cat_ok=derived.cat_ok,
            saving=derived.saving,
        )
        self._state.sync_ctx()
        self._reactions.apply_ready_state(
            ready=derived.ready_to_save,
            hz_ok=derived.hz_ok,
        )

    def update_from_dialog(self, dialog) -> None:
        """Read UI fields from dialog and update state."""
        try:
            jy, hz, mn, cat = CategoryManagerHelpers.read_add_fields(dialog)()
        except (TypeError, AttributeError, RuntimeError):
            jy, hz, mn, cat = "", "", "", ""

        jy_s = (jy or "").strip()
        hz_s = (hz or "").strip()
        mn_s = (mn or "").strip()
        cat_s = (cat or "").strip()
        if not cat_s:
            try:
                cats_multi = list(getattr(dialog, "_selected_categories", []) or [])
            except Exception:
                cats_multi = []
            if cats_multi:
                cat_s = str(cats_multi[0] or "").strip()

        vm = self._state.get_state()
        try:
            jy_ok = bool(getattr(vm, "jy_ok", False)) if vm is not None else False
        except (TypeError, AttributeError, RuntimeError):
            jy_ok = False

        if not jy_ok:
            if jy_s:
                try:
                    from domain.jyutping_validation import validate_jyut_syllables
                    jy_ok, _ = validate_jyut_syllables(jy_s)
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    jy_ok = True
            else:
                jy_ok = False

        try:
            saving = bool(self._state._dlg.get("_saving_now", False)) or bool(getattr(vm, "saving", False))
        except (TypeError, AttributeError, RuntimeError):
            saving = bool(self._state._dlg.get("_saving_now", False))

        self.update_from_fields(
            jy=jy_s,
            hanzi=hz_s,
            meaning=mn_s,
            category=cat_s,
            jy_ok=bool(jy_ok),
            saving=bool(saving),
        )
