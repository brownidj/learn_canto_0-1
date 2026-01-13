# -----------------------------------------------------------------------------
# category_manager_helpers.py
#
# Helper utilities for CategoryManagerDialog.
# Extracted to reduce main dialog file size and improve maintainability.
# -----------------------------------------------------------------------------

import logging
import time

from domain.jyutping_validation import validate_jyut_syllables

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
        from ui.widget_utils import WidgetAccessor
        return (
            WidgetAccessor.get_text(getattr(dialog, "_add_jy", None)),
            WidgetAccessor.get_text(getattr(dialog, "_add_hz", None)),
            WidgetAccessor.get_text(getattr(dialog, "_add_mn", None)),
            WidgetAccessor.get_text(getattr(dialog, "_add_cat", None)),
        )

    @staticmethod
    def ensure_category_combo_editable(dialog) -> None:
        """Ensure the Add/Edit category combobox is editable (best-effort)."""
        try:
            w_cat = getattr(dialog, "_add_cat", None)
            if w_cat is not None and hasattr(w_cat, "setEditable"):
                w_cat.setEditable(True)
        except (TypeError, AttributeError, RuntimeError):
            return

    @staticmethod
    def set_notes(dialog, text: str, *, source: str = "") -> None:
        """Set the Notes field (best-effort; never raises)."""
        try:
            w = getattr(dialog, "_add_notes", None)
        except (TypeError, AttributeError, RuntimeError):
            w = None

        if w is None:
            return

        msg = str(text or "")

        # QLineEdit
        try:
            if hasattr(w, "setText"):
                w.setText(msg)
                return
        except (TypeError, AttributeError, RuntimeError):
            pass

        # QTextEdit
        try:
            if hasattr(w, "setPlainText"):
                w.setPlainText(msg)
                return
        except (TypeError, AttributeError, RuntimeError):
            pass

        return

    @staticmethod
    def on_add_jy_user_edited(dialog, *args, **kwargs) -> None:
        """Slot: user edited Jyutping; reset dependent fields to placeholders."""
        try:
            dialog._reset_add_panel_pre_validation()
        except (TypeError, AttributeError, RuntimeError):
            return

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
            w = getattr(dialog, "_add_mn", None)
        except (TypeError, AttributeError, RuntimeError):
            w = None

        try:
            mn = (w.text() or "").strip() if w is not None else ""
        except (TypeError, AttributeError, RuntimeError):
            mn = ""

        try:
            ctx = getattr(dialog, "_add_edit_ctx", None)
        except (TypeError, AttributeError, RuntimeError):
            ctx = None

        if ctx is not None:
            try:
                ctx.meaning = mn
            except (TypeError, AttributeError, RuntimeError):
                pass
            try:
                setattr(ctx, "mn_ok", bool(mn))
            except (TypeError, AttributeError, RuntimeError):
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
            w = getattr(dialog, "_add_jy", None)
            if w is not None:
                w.setFocus()
                try:
                    w.selectAll()
                except (TypeError, AttributeError, RuntimeError):
                    pass
        except (TypeError, AttributeError, RuntimeError):
            pass
