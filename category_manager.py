# -----------------------------------------------------------------------------
# category_manager.py - Add & Edit Vocabulary Dialog (Refactored Architecture)
#
# This dialog coordinates 12+ specialized controllers to manage vocabulary
# and category operations. The main dialog class acts as a thin orchestrator,
# delegating all business logic to domain/UI controllers.
#
# Architecture principles:
#   - Single Meaning Resolver Rule: All meaning resolution flows through
#     MeaningFacade.select_candidate(...) or MeaningFacade.meanings_for_display(...)
#   - No inline business logic in the dialog class
#   - Best-effort UI operations (never raise, always degrade gracefully)
#   - State management via AddEditContext and controllers
#
# Controller breakdown:
#   - CategoryManagerInitializer: Data/cache initialization
#   - CategoryManagerFocusController: Focus management and policy
#   - CategoryManagerTypographyController: Font/typography setup
#   - CategoryManagerAddEditFlowController: Add/Edit workflow orchestration
#   - CategoryManagerMeaningResolver: Meaning resolution facade adapter
#   - CategoryManagerCategoryOpsController: Category CRUD operations
#   - CategoryManagerCandidatePipeline: Hanzi candidate ranking
#   - CategoryManagerManualHanziController: Manual Hanzi entry mode
#   - CategoryManagerFieldResetController: Field clear/reset operations
#   - CategoryManagerSaveCommitController: Save/commit orchestration
#   - CategoryManagerPreviewConfirmController: Preview/confirmation dialogs
#   - CategoryManagerSignalWiring: Qt signal/slot wiring
#   - CategoryManagerUIBuilder: Widget construction
#   - CategoryManagerHelpers: Standalone utility functions
#
# See docs/category_manager_architecture.md for detailed design documentation.
# -----------------------------------------------------------------------------

# ----------------------------------------
# Standard library imports
# ----------------------------------------
import logging
from typing import TYPE_CHECKING

# ----------------------------------------
# PySide6 imports
# ----------------------------------------
from PySide6.QtWidgets import QDialog, QVBoxLayout

# ----------------------------------------
# Domain imports
# ----------------------------------------
from ui.category_manager_helpers import CategoryManagerHelpers

# ----------------------------------------
# Third-party imports
# ----------------------------------------
# ----------------------------------------
# UI utilities imports
# ----------------------------------------


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ui.cantonese_meaning_controller import CantoneseMeaningController


class CategoryManagerDialog(QDialog):
    _canto_ctrl: "CantoneseMeaningController"
    _root: QVBoxLayout
    _vocab: dict
    _cats: dict
    # ------------------------------
    # Category dropdown refresh
    # ------------------------------

    @staticmethod
    def _perf_start(name: str) -> float:
        return CategoryManagerHelpers.perf_start(name)

    @staticmethod
    def _perf_end(name: str, t0: float) -> None:
        CategoryManagerHelpers.perf_end(name, t0)

    """Add/Edit vocabulary dialog orchestrator.

    See docs/category_manager_architecture.md for the full workflow and design notes.
    """
    MAX_HANZI_CANDIDATES = 10
    # Hanzi-specific typography tuning (easy to adjust)
    # NOTE: These are treated as absolute point sizes (pt), not deltas.
    _HANZI_TEXT_DELTA_PT = 60       # Hanzi main display font size (pt)
    _HANZI_COMBO_DELTA_PT = 24      # Hanzi candidate combobox font size (pt)
    # Typography deltas for the Add/Edit panel (dialog-local; do not affect the rest of the app)
    _LABEL_FONT_DELTA_PT = 4
    _INPUT_FONT_DELTA_PT = 3
    _FORM_VERTICAL_SPACING_PX = 40

    def __init__(self, parent, vocab_items: dict, categories_map: dict, candidate_provider=None):
        super().__init__(parent)
        self._parent = parent
        self._candidate_provider = candidate_provider

        self.setWindowTitle("Add & Edit Items")
        logger.debug("CategoryManagerDialog: init start (building UI and wiring)")
        _t_init = self._perf_start("CategoryManagerDialog.__init__")

        # ---- Dialog sizing (best-effort, no UI failure) ----
        pw = ph = 0
        if parent is not None:
            try:
                pw = int(parent.width())
                ph = int(parent.height())
            except (TypeError, ValueError, AttributeError):
                pw = ph = 0

        if pw > 0 and ph > 0:
            dlg_w = max(pw, ph)
            dlg_h = min(pw, ph)
        else:
            dlg_w, dlg_h = 1280, 720

        try:
            self.setMinimumSize(dlg_w, dlg_h)
            self.resize(dlg_w, dlg_h)
            logger.debug(
                "CategoryManagerDialog: sized to %dx%d (parent=%dx%d)",
                dlg_w, dlg_h, pw, ph,
            )
        except RuntimeError as e:
            logger.debug("Dialog resize skipped: %s", e)

        self._hanzi_committed = False

        # ---- Composition root (controllers + services) ----
        from ui.category_manager_composition import CategoryManagerComposition
        composition = CategoryManagerComposition(self)
        composition.build()

        # ---- Data / caches initialization (delegated) ----
        self._initializer.initialize_all(vocab_items, categories_map)

        # ---- UI Construction (delegated to builder) ----
        composition.build_ui()

        # ---- Signal wiring (delegated) ----
        composition.wire_signals()

        # ---- Finalise init ----
        logger.debug("CategoryManagerDialog: init complete")
        self._perf_end("CategoryManagerDialog.__init__", _t_init)

        # ---- Required controllers (fail fast) ----
        for _name in (
            "_initializer",
            "_focus_ctrl",
            "_typography_ctrl",
            "_add_edit_flow",
            "_category_ops",
            "_manual_hanzi",
            "_field_reset",
            "_save_commit",
            "_preview_confirm",
            "_state_svc",
            "_state_coord",
            "_canto_ctrl",
        ):
            if getattr(self, _name, None) is None:
                raise RuntimeError(f"CategoryManagerDialog missing controller: {_name}")

        # Add/Edit wiring is handled by CategoryManagerSignalWiring during init.

    # ---- UI intent / focus policy (delegated to controller) ----
    def _apply_focus_policy(
        self,
        *,
        target: str,
        reason: str = "",
        user_action: bool = False,
        show_popup: bool = False,
        select_all: bool = True,
    ) -> None:
        """Apply a focus move if permitted by policy."""
        self._focus_ctrl.apply_focus_policy(
            target=target,
            reason=reason,
            user_action=user_action,
            show_popup=show_popup,
            select_all=select_all,
        )

    # ---- Add & Edit: Jyutping validation + reverse lookup wiring ----

    def _update_save_enabled(self) -> None:
        """Update validity state for Add/Edit form."""
        self._state_coord.update_from_dialog(self)

    def _sync_add_edit_ctx(self) -> None:
        """Sync SM context from the ViewModel."""
        self._state_svc.sync_ctx()

    def _update_add_edit_state(self, **kwargs):
        """Update ViewModel fields and sync SM context."""
        self._state_svc.update_vm(**kwargs)
        self._state_svc.sync_ctx()
        return self._state_svc.get_state()

    # ---- Add/Edit UI wiring (delegated to signal wiring controller) ----
    # Note: _setup_add_edit_ui is now called automatically during __init__
    # via CategoryManagerSignalWiring.wire_add_edit_signals()

    # ---- Widget accessor helpers ----
    # Note: Widget access is handled via ui.widget_utils.WidgetAccessor utility methods
    # throughout this class (get_text, set_text, focus, set_visible, etc.)
