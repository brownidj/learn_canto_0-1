# -----------------------------------------------------------------------------
# category_manager_helpers.py
#
# Helper utilities for CategoryManagerDialog.
# Extracted to reduce main dialog file size and improve maintainability.
# -----------------------------------------------------------------------------

import logging
import time

from domain.jyutping_validation import validate_jyut_syllables
from ui.category_manager_ui_services import CategoryManagerUIService

logger = logging.getLogger(__name__)


class CategoryManagerHelpers:
    """Helper utilities for CategoryManagerDialog.

    These methods are extracted from the main dialog class to improve
    code organization and maintainability. They are primarily stateless
    or minimally stateful utilities.
    """

    @staticmethod
    def perf_start(name: str) -> float:
        """Start performance timer."""
        t0 = time.perf_counter()
        logger.debug("PERF start: %s", name)
        return t0

    @staticmethod
    def perf_end(name: str, t0: float) -> None:
        """End performance timer and log duration."""
        if not t0:
            return
        dt_ms = (time.perf_counter() - float(t0)) * 1000.0
        logger.debug("PERF end: %s (%.1f ms)", name, dt_ms)

    @staticmethod
    def validate_jyut_syllables(jy: str) -> tuple[bool, str | None]:
        """Validate Jyutping syllables (best-effort)."""
        try:
            return validate_jyut_syllables(jy)
        except (ImportError, AttributeError, TypeError, ValueError, RuntimeError) as e:
            # Best-effort: do not hard-fail UI if validator is unavailable.
            try:
                logger.debug("Jyutping validator unavailable (%s); allowing input", e)
            except (TypeError, ValueError):
                pass
            return True, None

    @staticmethod
    def read_add_fields(dialog) -> tuple[str, str, str, str]:
        """Read Add/Edit panel fields safely (legacy compatibility)."""
        ui = CategoryManagerUIService(dialog)
        return (
            ui.get_text("add_jy"),
            ui.get_text("add_hz"),
            ui.get_text("add_mn"),
            ui.get_text("add_cat"),
        )

    @staticmethod
    def ensure_category_combo_editable(dialog) -> None:
        """Ensure the Add/Edit category combobox is editable (best-effort)."""
        try:
            ui = CategoryManagerUIService(dialog)
            w_cat = ui.widget("add_cat")
            if w_cat is not None and hasattr(w_cat, "setEditable"):
                w_cat.setEditable(True)
        except (TypeError, AttributeError, RuntimeError):
            return

    @staticmethod
    def set_notes(dialog, text: str, *, source: str = "") -> None:
        """Set the Notes field (best-effort; never raises)."""
        try:
            ui = CategoryManagerUIService(dialog)
            ui.set_notes(str(text or ""), source=source)
        except (TypeError, AttributeError, RuntimeError):
            return

    @staticmethod
    def on_add_jy_user_edited(dialog, *args, **kwargs) -> None:
        """Slot: user edited Jyutping; reset dependent fields to placeholders."""
        try:
            ctrl = getattr(dialog, "_field_reset", None)
            if ctrl is not None:
                ctrl.reset_add_panel_pre_validation()
        except (TypeError, AttributeError, RuntimeError):
            return

    @staticmethod
    def on_add_jy_editing_finished(dialog, *args, **kwargs) -> None:
        """Slot: Jyutping edit committed; focus Category."""
        try:
            ui = CategoryManagerUIService(dialog)
            jy = ui.get_text("add_jy")
        except (TypeError, AttributeError, RuntimeError, ImportError, ValueError):
            jy = ""

        if not str(jy or "").strip():
            return

        try:
            ctrl = getattr(dialog, "_focus_ctrl", None)
            if ctrl is not None and hasattr(ctrl, "focus_category"):
                ctrl.focus_category(select_all=True, show_popup=True)
                return
        except (TypeError, AttributeError, RuntimeError):
            pass

        try:
            ctrl2 = getattr(dialog, "_cat_combo_ctrl", None)
            if ctrl2 is not None and hasattr(ctrl2, "focus"):
                ctrl2.focus(select_all=True, show_popup=True)
        except (TypeError, AttributeError, RuntimeError):
            pass

    @staticmethod
    def on_add_category_changed(dialog, *args, **kwargs) -> None:
        """Category text changed while typing.

        IMPORTANT: Do NOT treat this as a commit. Users must be able to type-to-select
        categories without triggering candidate recomputation or focus changes.

        Commit happens via Enter / editingFinished / activated.
        """
        return

    @staticmethod
    def on_meanings_text_changed(dialog, *args, **kwargs) -> None:
        """Meaning text changed (user or programmatic).
        Keeps Add/Edit context in sync and refreshes Save gating. Must never raise.
        """
        try:
            ui = CategoryManagerUIService(dialog)
            mn = str(ui.get_text("add_mn") or "").strip()
        except (TypeError, AttributeError, RuntimeError):
            mn = ""

        try:
            dialog._update_add_edit_state(meaning=mn, mn_ok=bool(mn))
        except Exception:
            pass

        try:
            fn_gate = getattr(dialog, "_update_save_enabled", None)
            if callable(fn_gate):
                fn_gate()
        except (TypeError, AttributeError, RuntimeError):
            pass

    @staticmethod
    def focus_jy(dialog) -> None:
        """Focus the Jyutping input field."""
        try:
            ctrl = getattr(dialog, "_focus_ctrl", None)
            if ctrl is not None and hasattr(ctrl, "focus_jyutping"):
                ctrl.focus_jyutping(select_all=True)
        except (TypeError, AttributeError, RuntimeError):
            pass
