from dataclasses import dataclass
from typing import Literal, Optional, Callable
FocusTarget = Literal["jy", "hz", "mn", "cat"]


@dataclass(frozen=True)
class AddEditInputs:
    jyutping: str
    hanzi: str
    meaning: str
    category: str
    saving: bool = False

    # Optional environment
    validate_jy: Optional[Callable[[str], bool]] = None
    valid_categories: Optional[set[str]] = None


@dataclass(frozen=True)
class AddEditResult:
    preview: dict
    ready: bool
    show_save: bool = False
    clear_fields: bool = False
    focus_target: Optional[FocusTarget] = None
    commit: bool = False

    def to_dict(self) -> dict:
        """Return a stable, test-friendly dict contract."""
        preview_payload = self.preview if isinstance(self.preview, dict) else {}
        commit_payload = preview_payload if self.commit else None
        return {
            "preview_payload": preview_payload,
            "commit_payload": commit_payload,
            "ready": bool(self.ready),
            "show_save": bool(self.show_save),
            "clear_fields": bool(self.clear_fields),
            "focus_target": self.focus_target,
            "commit": bool(self.commit),
        }


class AddEditController:
    """
    Pure decision-making for the Add/Edit flow.
    No Qt. No side effects. Deterministic.
    """

    # ---------- core validity ----------

    @staticmethod
    def is_ready(inp: AddEditInputs) -> bool:
        if inp.saving:
            return False

        if not inp.jyutping or not inp.hanzi or not inp.meaning or not inp.category:
            return False

        if inp.valid_categories is not None:
            if inp.category not in inp.valid_categories:
                return False

        if inp.validate_jy is not None:
            try:
                if not inp.validate_jy(inp.jyutping):
                    return False
            except (TypeError, ValueError):
                return False

        return True

    # ---------- meaning-enter decision ----------

    @staticmethod
    def on_meaning_enter(
            *args,
            fields: dict | None = None,
            # vocab: dict | None = None,
            cats: dict | None = None,
            decision: str = "edit",
            preview: dict | None = None,
            inp: AddEditInputs | None = None,
            **kwargs,
    ) -> dict:
        """
        Decisioning for Meaning-Enter.

        Supports both call styles:
          - UI style: on_meaning_enter(preview=..., decision=..., inp=...)
          - Test style: on_meaning_enter(fields=..., cats=..., decision=...)
        """

        # Positional tolerance: on_meaning_enter(fields_dict, ...)
        if fields is None and args:
            if isinstance(args[0], dict):
                fields = args[0]

        # Normalise decision
        try:
            decision = str(decision or "edit").strip().lower()
        except (TypeError, AttributeError, ValueError):
            decision = "edit"

        # If tests provided fields, build canonical preview from canonical keys only.
        # IMPORTANT: do NOT accept aliases here (no 'gloss', no 'categories').
        if fields is not None and isinstance(fields, dict):
            try:
                jy = str(fields.get("jyutping", "") or "").strip()
            except (TypeError, AttributeError, ValueError):
                jy = ""
            try:
                hz = str(fields.get("hanzi", "") or "").strip()
            except (TypeError, AttributeError, ValueError):
                hz = ""
            try:
                mn = str(fields.get("meaning", "") or "").strip()
            except (TypeError, AttributeError, ValueError):
                mn = ""
            try:
                cat = str(fields.get("category", "") or "").strip()
            except (TypeError, AttributeError, ValueError):
                cat = ""

            preview = {"jyutping": jy, "hanzi": hz, "meaning": mn, "category": cat}

        if preview is None:
            preview = {}

        # If the caller didn't provide AddEditInputs, synthesise it (pure-python safe).
        if inp is None:
            try:
                valid_categories = set((cats or {}).keys()) if isinstance(cats, dict) else None
            except (TypeError, AttributeError):
                valid_categories = None

            # If AddEditInputs exists in this file already, use it.
            inp = AddEditInputs(
                jyutping=str(preview.get("jyutping", "") or "").strip(),
                hanzi=str(preview.get("hanzi", "") or "").strip(),
                meaning=str(preview.get("meaning", "") or "").strip(),
                category=str(preview.get("category", "") or "").strip(),
                saving=bool(kwargs.get("saving", False)),
                validate_jy=kwargs.get("validate_jy"),
                valid_categories=valid_categories,
            )

        # It should continue to use: preview, decision, inp

        ready = AddEditController.is_ready(inp)

        if decision == "edit":
            return AddEditResult(
                preview=preview,
                ready=ready,
                show_save=True,
                focus_target=None,
            ).to_dict()

        if decision == "cancel":
            return AddEditResult(
                preview=preview,
                ready=False,
                clear_fields=True,
                focus_target="jy",
            ).to_dict()

        # decision == "save"
        if ready:
            return AddEditResult(
                preview=preview,
                ready=True,
                commit=True,
                clear_fields=True,
                focus_target="jy",
            ).to_dict()

        # Save requested but not ready → fall back to edit
        return AddEditResult(
            preview=preview,
            ready=False,
            show_save=True,
        ).to_dict()
