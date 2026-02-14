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
#   - CategoryManagerVocabDisplay: Table/vocab display operations
#
# See docs/category_manager_architecture.md for detailed design documentation.
# -----------------------------------------------------------------------------

# ----------------------------------------
# Standard library imports
# ----------------------------------------
import logging
import os
import time
import threading
from dataclasses import dataclass

from domain.add_edit_controller import AddEditInputs, AddEditController
from ui.category_manager_helpers import CategoryManagerHelpers
from ui.category_manager_vocab_display import CategoryManagerVocabDisplay

# ------------------------------
# Candidate source labels (UI)
# ------------------------------
FRIENDLY_SOURCE_LABELS = {
    "reverse_jyut": "ATT",
    "tier2-char": "PHON",
}

HANZI_CANDIDATE_TOOLTIP = (
    "ATT = Attested & ranked (highest confidence)\n"
    "• From reverse_jyut.yaml\n"
    "• Explicitly attested for this Jyutping\n"
    "• Has a frequency / ordering signal\n"
    "• Meanings resolved automatically\n\n"
    "PHON = Phonetic fallback (no ranking)\n"
    "• Usually from Unihan-only data\n"
    "• No reverse-index frequency signal\n"
    "• Score = 0 (many ties)\n\n"
    "✓ indicates the best automatic choice.\n"
    "Fallbacks are shown so you can override if needed."
)

# ----------------------------------------
# Third-party imports
# ----------------------------------------
import yaml
from typing import cast

# ----------------------------------------
# UI utilities imports
# ----------------------------------------
from ui.widget_utils import WidgetAccessor, SignalBlocker
from ui.focus_manager import FocusManager, FocusState, FocusPolicy
from ui.form_state_controller import FormState, FormStateController
from ui.vocabulary_table_controller import VocabularyTableController

# ----------------------------------------
# PySide6 imports
# ----------------------------------------
from PySide6.QtCore import Qt as _Qt
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtCore import Slot
from PySide6.QtGui import (
    QFont,
    QFontMetrics,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QPushButton,
    QLabel,
    QTableWidget,
    QSizePolicy,
    QMessageBox,
    QAbstractItemView,
    QTextEdit,
    QProxyStyle,
    QStyle,
)

# ----------------------------------------
# Domain imports
# ----------------------------------------
from domain.category_rules import (
    HanziStyleIndex,
    CandidateCurator,
)

from domain.hanzi_candidate_pipeline import HanziCandidatePipeline, build_pipeline_from_category_manager
from domain.jyutping_validation import validate_jyut_syllables
from domain.meaning_sources import default_facade
from domain.storage_paths import categories_yaml_path
from domain.add_edit_sm import AddEditState, AddEditContext
from ui.candidate_combo import CandidateComboController

from infra.paths import project_root

from ui.focus_policy import should_steal_focus
from ui.category_combo import CategoryComboController
from services.cantonese_language_service import CantoneseInfo

from persistence.categories_store import persist_categories_yaml
from table_scroll_slider_controller import TableScrollSliderController
from category_repo import CategoryRepo
from category_commit import CategoryCommitService

logger = logging.getLogger(__name__)


# ---------------------------
# Add/Edit preview dataclasses
# ---------------------------

@dataclass(frozen=True)
class AddEntryPreview:
    jyutping: str = ""
    hanzi: str = ""
    meaning: str = ""
    category: str = ""

    def to_payload(self) -> dict:
        jy = (self.jyutping or "").strip()
        hz = (self.hanzi or "").strip()
        mn = (self.meaning or "").strip()
        cat = (self.category or "").strip()

        # Canonical keys are always present.
        payload = {
            "jyutping": jy,
            "hanzi": hz,
            "meaning": mn,
            "category": cat,
        }

        # Required legacy/test aliases.
        payload["gloss"] = mn
        payload["categories"] = ([cat] if cat else [])

        return payload


class AddEntryPreviewBuilder:
    """
    Best-effort preview builder for the Add/Edit entry flow.

    Goals:
      - Deterministic in offscreen tests
      - Minimal, predictable fallbacks
      - No long attribute-fishing ladders
    """

    @staticmethod
    def _resolve_vocab(dialog) -> dict | None:
        # Canonical store is `_vocab`.
        try:
            v = getattr(dialog, "_vocab", None)
        except (TypeError, AttributeError, RuntimeError):
            v = None
        return v if isinstance(v, dict) else None

    @staticmethod
    def _meaning_from_vocab(vocab: dict | None, hanzi: str) -> str:
        if not isinstance(vocab, dict):
            return ""
        hz = (hanzi or "").strip()
        if not hz or hz not in vocab:
            return ""
        row = vocab.get(hz)
        if not isinstance(row, (list, tuple)) or len(row) < 1:
            return ""
        meanings = row[0]
        if not isinstance(meanings, (list, tuple)):
            return ""
        out = []
        for g in meanings:
            try:
                s = str(g).strip()
            except (TypeError, AttributeError, RuntimeError, ValueError):
                s = ""
            if s:
                out.append(s)
        return ", ".join(out)


    @staticmethod
    def build(dialog) -> AddEntryPreview:
        """Canonical Add/Edit preview builder.

        Pipeline:
          1) Read raw UI fields directly from widgets (captures latest user edits)
          2) Normalise (strip; Jyutping via dialog normaliser when available)
          3) Enrich (only from SM context if widgets are blank)
          4) Emit AddEntryPreview (canonical keys)
        """
        # 1) Primary: Read directly from widgets to capture latest user edits
        jy = hz = mn = cat = ""

        # Direct widget read - highest priority for capturing user edits
        try:
            from ui.widget_utils import WidgetAccessor

            # Try WidgetAccessor first
            jy_widget = getattr(dialog, "_add_jy", None)
            hz_widget = getattr(dialog, "_add_hz", None)
            mn_widget = getattr(dialog, "_add_mn", None)
            cat_widget = getattr(dialog, "_add_cat", None)

            if jy_widget is not None:
                jy = WidgetAccessor.get_text(jy_widget) or ""
            if hz_widget is not None:
                # FORCE it to be editable
                hz_widget.setReadOnly(False)

                # Add a simple test handler
                def test_enter():
                    print("*** ENTER PRESSED ON HANZI FIELD! ***")

                # Connect it directly
                try:
                    hz_widget.returnPressed.connect(test_enter)
                    print("  - Connection: SUCCESS")
                except Exception as e:
                    print(f"  - Connection: FAILED - {e}")
                hz = WidgetAccessor.get_text(hz_widget) or ""
            if mn_widget is not None:
                mn = WidgetAccessor.get_text(mn_widget) or ""
            if cat_widget is not None:
                cat = WidgetAccessor.get_text(cat_widget) or ""

        except (TypeError, AttributeError, RuntimeError, ValueError, ImportError):
            pass

        # Fallback: direct widget text() method
        if not jy and not hz and not mn and not cat:
            try:
                jy_w = getattr(dialog, "_add_jy", None)
                if jy_w is not None and hasattr(jy_w, "text"):
                    jy = jy_w.text() or ""

                hz_w = getattr(dialog, "_add_hz", None)
                if hz_w is not None and hasattr(hz_w, "text"):
                    hz = hz_w.text() or ""

                mn_w = getattr(dialog, "_add_mn", None)
                if mn_w is not None:
                    if hasattr(mn_w, "toPlainText"):
                        mn = mn_w.toPlainText() or ""
                    elif hasattr(mn_w, "text"):
                        mn = mn_w.text() or ""

                cat_w = getattr(dialog, "_add_cat", None)
                if cat_w is not None:
                    if hasattr(cat_w, "currentText"):
                        cat = cat_w.currentText() or ""
                    elif hasattr(cat_w, "text"):
                        cat = cat_w.text() or ""
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Final fallback: legacy reader
        if not jy and not hz and not mn and not cat:
            try:
                fn = getattr(dialog, "_read_add_fields", None)
                if callable(fn):
                    jy, hz, mn, cat = fn()
            except (TypeError, AttributeError, RuntimeError, ValueError):
                jy = hz = mn = cat = ""

        # Normalise raw strings
        try:
            jy = str(jy or "").strip()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            jy = ""
        try:
            hz = str(hz or "").strip()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            hz = ""
        try:
            mn = str(mn or "").strip()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            mn = ""
        try:
            cat = str(cat or "").strip()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            cat = ""

        # 2) Normalise Jyutping using the dialog normaliser when available
        # if jy:
        #     try:
        #         norm = getattr(dialog, "_normalize_jy", None)
        #         if callable(norm):
        #             jy = str(norm(jy) or "").strip()
        #         else:
        #             jy = " ".join(jy.lower().split())
        #     except (TypeError, AttributeError, RuntimeError, ValueError):
        #         jy = " ".join(str(jy or "").strip().lower().split())

        if jy:
            try:
                # Explicit normalization
                norm = getattr(dialog, "_normalize_jy", lambda x: x)
                normalized_jy = norm(jy).strip().lower()

                # Ensure tone is preserved
                tone_match = next((char for char in jy if char.isdigit()), '')
                if tone_match and not any(char.isdigit() for char in normalized_jy):
                    normalized_jy += tone_match

                jy = normalized_jy
            except Exception:
                jy = ""

        # 3) Enrich from SM context only when widgets are blank
        ctx = None
        try:
            ctx = getattr(dialog, "_add_edit_ctx", None)
        except (TypeError, AttributeError, RuntimeError):
            ctx = None

        if ctx is not None:
            if not jy:
                try:
                    jy = str(getattr(ctx, "jy", "") or "").strip()
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    jy = ""
            if not hz:
                try:
                    hz = str(getattr(ctx, "hanzi", "") or "").strip()
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    hz = ""
            if not mn:
                try:
                    mn = str(getattr(ctx, "meaning", "") or "").strip()
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    mn = ""
            if not cat:
                try:
                    cat = str(getattr(ctx, "category", "") or "").strip()
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    cat = ""

        # If Hanzi still blank, allow candidate combobox currentText (widget state, not vocab inference)
        if not hz:
            try:
                combo = getattr(dialog, "_cand_combo", None)
                if combo is not None and hasattr(combo, "currentText"):
                    txt = str((combo.currentText() or "")).strip()
                    if txt and not txt.startswith("—"):
                        hz = txt
            except (TypeError, AttributeError, RuntimeError, ValueError):
                hz = hz or ""

        # 4) Enrich meaning ONLY if the widget is completely blank
        # (Don't override user edits with auto-resolved meanings)
        if not mn and hz:
            resolved = []
            try:
                fn_resolve = getattr(dialog, "_resolve_meanings_for_candidate", None)
            except (TypeError, AttributeError, RuntimeError):
                fn_resolve = None

            if callable(fn_resolve):
                try:
                    resolved = fn_resolve(hz, "") or []
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    resolved = []

            if isinstance(resolved, (list, tuple)):
                try:
                    parts = [str(x).strip() for x in resolved if str(x).strip()]
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    parts = []
                if parts:
                    mn = ", ".join(parts)

            # Final fallback: vocab-derived meanings (only if still blank)
            if not mn:
                vocab = AddEntryPreviewBuilder._resolve_vocab(dialog)
                mn = AddEntryPreviewBuilder._meaning_from_vocab(vocab, hz)

        return AddEntryPreview(jyutping=jy, hanzi=hz, meaning=mn, category=cat)


class HanziComboBoxProxyStyle(QProxyStyle):
    """
    Proxy style to prevent macOS combo edit-field rect from collapsing vertically.

    Some Qt/macOS styles compute SC_ComboBoxEditField with a very small height,
    which forces the internal line edit / paint rect to be tiny, causing clipped CJK glyphs.
    """

    def subControlRect(self, control, option, subControl, widget=None):  # noqa: N802
        rect = super().subControlRect(control, option, subControl, widget)
        try:
            if (
                    control == QStyle.ComplexControl.CC_ComboBox
                    and subControl == QStyle.SubControl.SC_ComboBoxEditField
            ):
                full = option.rect
                inset = 2  # keep a little breathing room for the border
                rect.setY(int(full.y() + inset))
                rect.setHeight(int(max(0, full.height() - (inset * 2))))
        except (TypeError, AttributeError, ValueError, RuntimeError):
            pass
        return rect


# ---- ComboBox subclass to reposition popup below ----
class PopupBelowComboBox(QComboBox):
    """QComboBox that repositions its popup so it starts below the control.

    On macOS (and some styles), the popup can overlap the control itself, visually
    obscuring the focus ring. This class keeps the popup aligned to the combobox
    bottom-left in global coordinates.

    Best-effort only: must never raise.
    """

    def showPopup(self) -> None:  # noqa: N802
        # Let Qt create/show the popup first.
        try:
            super().showPopup()
        except (TypeError, AttributeError, RuntimeError):
            return

        # Defer repositioning until after Qt has finalised popup geometry.
        try:
            QTimer.singleShot(0, self._reposition_popup_below)
            QTimer.singleShot(20, self._reposition_popup_below)
        except (TypeError, AttributeError, RuntimeError):
            return

    def _popup_container(self):
        """Return the top-level popup container for this combobox's view (best-effort)."""
        try:
            view = self.view()
        except (TypeError, AttributeError, RuntimeError):
            return None

        w = view
        try:
            # Walk up the widget chain to find the actual Qt.Popup window.
            while w is not None:
                try:
                    if w.isWindow() and (w.windowFlags() & _Qt.WindowType.Popup):
                        return w
                except (TypeError, AttributeError, RuntimeError):
                    pass
                try:
                    w = w.parentWidget()
                except (TypeError, AttributeError, RuntimeError):
                    break
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Fallback: whatever window() returns.
        try:
            return view.window() if view is not None else None
        except (TypeError, AttributeError, RuntimeError):
            return None

    def _reposition_popup_below(self) -> None:
        """Best-effort: keep the popup below the combobox (no overlap) when space permits."""
        try:
            view = self.view()
        except (TypeError, AttributeError, RuntimeError):
            return

        popup = self._popup_container()
        if popup is None:
            return

        try:
            # Gap to keep the macOS focus ring and popup shadow from touching.
            gap = 14
            desired = self.mapToGlobal(QPoint(0, int(self.height() + gap)))
            desired_x = int(desired.x())
            desired_y = int(desired.y())

            # If there isn't enough space below, do not force it (Qt will place above).
            try:
                screen = self.screen()
            except (TypeError, AttributeError, RuntimeError):
                screen = None
            if screen is None:
                try:
                    screen = QApplication.primaryScreen()
                except (TypeError, AttributeError, RuntimeError):
                    screen = None

            if screen is not None:
                try:
                    avail = screen.availableGeometry()
                    popup_h = int(popup.frameGeometry().height())
                    if desired_y + popup_h > int(avail.y() + avail.height()):
                        return
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    pass

            # Compute decoration offset: frameGeometry top-left vs client top-left.
            try:
                frame_tl = popup.frameGeometry().topLeft()
                client_tl = popup.geometry().topLeft()
                # For top-level widgets, geometry().topLeft() corresponds to popup.pos().
                deco_dx = int(frame_tl.x() - client_tl.x())
                deco_dy = int(frame_tl.y() - client_tl.y())
            except (TypeError, AttributeError, RuntimeError, ValueError):
                deco_dx = 0
                deco_dy = 0

            # Move the *client* position so that the *frame* starts at (desired_x, desired_y).
            target_x = int(desired_x - deco_dx)
            target_y = int(desired_y - deco_dy)
            popup.move(target_x, target_y)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return


class CategoryManagerDialog(QDialog):
    # ------------------------------
    # Category dropdown refresh
    # ------------------------------

    @staticmethod
    def _perf_start(name: str) -> float:
        return CategoryManagerHelpers.perf_start(name)

    @staticmethod
    def _perf_end(name: str, t0: float) -> None:
        CategoryManagerHelpers.perf_end(name, t0)

    @staticmethod
    def _validate_jyut_syllables(jy: str) -> tuple[bool, str | None]:
        return CategoryManagerHelpers.validate_jyut_syllables(jy)

    """
    Dialog for adding and editing vocabulary items.

    Learner-facing workflow (Add panel):
      1. User types Jyutping and presses Enter.
      2. Jyutping is validated; focus moves to Category.
      3. Category initially shows the placeholder “Not yet assigned”.
         The user must choose a real category, or 'unassigned' if unsure.
      4. Confirming a real category triggers reverse lookup:
         Jyutping → ranked Hanzi candidates (category-aware).
      5. If exactly one candidate, Hanzi and meanings are autofilled and focus moves to Meanings.
         If multiple candidates, the Hanzi dropdown opens for user selection, then meanings update.
      6. Save is enabled only when Jyutping, Category, Hanzi, and at least one Meaning are all present
         and structurally valid.

    In-app "Add & Edit" manager for vocab + categories.

    High-level model
    ----------------
    - The table on the right shows all current vocab entries:
      - Hanzi, Jyutping, Meanings, Categories (via MultiCategoryCombo).
    - The "Add Item" panel at the top/left is a unified editor:
      - In ADD mode, it creates a new vocab entry and category membership.
      - In EDIT mode, it updates an existing entry selected from the table.
      - The panel always writes to:
          - self._vocab        (hanzi -> [meanings, jyut])
          - self._cats         (category -> [hanzi])
          - data/andys_list.yaml    (vocab content)
          - categories.yaml    (category listing)

    Core workflows
    --------------
    ADD:
      1. User types Jyutping in self._add_jy and presses Enter.
         - _is_valid_jyut(...) checks structure.
         - _is_attested_jyut(...) checks corpora (vocab + CSVs).
         - _reverse_candidates_for_jy(...) proposes Hanzi candidates.
         - self._add_hz and self._cand_combo are populated; meanings are
           pre-filled via CC-Canto / dictionaries where possible.
      2. User edits Meanings + Category.
         - Category text is normalised (_canon_cat_name) and may trigger
           _add_new_category(...) if it does not exist yet.
      3. Save (or Enter in the Add panel) calls _on_add_item_enter():
         - Re-checks Jyutping validity + attestation.
         - Ensures meanings and category are present.
         - Ensures Hanzi is resolved.
         - Updates self._vocab[hanzi] = [meanings, jyut].
         - Updates category membership in self._cats (and removes from
           'unassigned' if needed).
         - Persists to data/andys_list.yaml + categories.yaml.
         - Refreshes the table via _populate_rows().

    EDIT:
      - The table model is considered the "live view" of vocab + categories.
      - When a row is selected for editing (handled elsewhere), that row’s
        Hanzi/Jyut/Meanings/Category are pushed back into the Add panel
        widgets (self._add_jy, self._add_hz, self._add_mn, self._add_cat).
      - The same pipeline as ADD is used on Save:
          - _on_add_item_enter() mutates self._vocab and self._cats based
            on the current Hanzi key, then repopulates the table.
      - The table’s category column uses MultiCategoryCombo; changes there
        are handled by _on_combo_changed() and autosaved via _do_autosave().

    Category autosave + live resort
    --------------------------------
    - Category edits in the table are debounced:
        - _on_combo_changed() queues _do_live_resort() to rebuild rows
          sorted by (first_category, meaning, hanzi).
        - It also queues _do_autosave() to write categories.yaml and
          refresh the main window’s category combobox.
    - 'unassigned' is treated specially:
        - _aggregate_categories() removes items from 'unassigned' if they
          appear in any other category.
        - When editing category combos, moving an item out of 'unassigned'
          can optionally jump focus to the next unassigned row.
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

    def __init__(self, parent, vocab_items: dict, categories_map: dict):
        super().__init__(parent)
        self._parent = parent

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

        # ---- Data / caches initialization (delegated) ----
        from ui.category_manager_initializer import CategoryManagerInitializer
        initializer = CategoryManagerInitializer(self)
        initializer.initialize_all(vocab_items, categories_map)

        # ---- Focus controller ----
        from ui.category_manager_focus import CategoryManagerFocusController
        self._focus_ctrl = CategoryManagerFocusController(self)

        # ---- Typography controller ----
        from ui.category_manager_typography import CategoryManagerTypographyController
        self._typography_ctrl = CategoryManagerTypographyController(self)

        # ---- Add/Edit flow controller ----
        from ui.category_manager_add_edit_flow import CategoryManagerAddEditFlowController
        self._add_edit_flow = CategoryManagerAddEditFlowController(self)

        # ---- Meaning resolver ----
        from ui.category_manager_meaning_resolver import CategoryManagerMeaningResolver
        self._meaning_resolver = CategoryManagerMeaningResolver(self)

        # ---- Category operations controller ----
        from ui.category_manager_category_ops import CategoryManagerCategoryOpsController
        self._category_ops = CategoryManagerCategoryOpsController(self)

        # ---- Candidate pipeline controller ----
        from ui.category_manager_candidate_pipeline import CategoryManagerCandidatePipeline
        self._candidate_pipeline = CategoryManagerCandidatePipeline(self)

        # ---- Manual Hanzi controller ----
        from ui.category_manager_manual_hanzi import CategoryManagerManualHanziController
        self._manual_hanzi_ctrl = CategoryManagerManualHanziController(self)

        # ---- Field reset controller ----
        from ui.category_manager_field_reset import CategoryManagerFieldResetController
        self._field_reset = CategoryManagerFieldResetController(self)

        # ---- Save/commit controller ----
        from ui.category_manager_save_commit import CategoryManagerSaveCommitController
        self._save_commit = CategoryManagerSaveCommitController(self)

        # ---- Preview/confirmation controller ----
        from ui.category_manager_preview_confirm import CategoryManagerPreviewConfirmController
        self._preview_confirm = CategoryManagerPreviewConfirmController(self)

        # ---- UI Construction (delegated to builder) ----
        from ui.category_manager_ui_builder import CategoryManagerUIBuilder
        ui_builder = CategoryManagerUIBuilder(self)
        ui_builder.build_ui()

        # ---- Signal wiring (delegated) ----
        from ui.category_manager_signal_wiring import CategoryManagerSignalWiring
        signal_wiring = CategoryManagerSignalWiring(self)
        signal_wiring.wire_add_edit_signals()

        # ---- Finalise init ----
        logger.debug("CategoryManagerDialog: init complete")
        self._perf_end("CategoryManagerDialog.__init__", _t_init)

        # Initialise Add/Edit state machine baseline
        self._add_edit_state = AddEditState.EMPTY
        self._add_edit_ctx = AddEditContext(
            jy="",
            jy_ok=False,
            duplicate=None,
            hanzi="",
            hz_ok=False,
            manual_hanzi=False,
            meaning="",
            mn_ok=False,
            category="",
            cat_ok=False,
            saving=False,
        )

        # Ensure Add/Edit wiring is active (Enter in Meaning, Save gating, etc.)
        try:
            self._setup_add_edit_ui()
        except (AttributeError, TypeError, ValueError, RuntimeError):
            pass

    def _connect_unique(self, signal, slot) -> None:
        """Signal connection (internal use - prefer signal wiring controller for new code)."""
        from ui.category_manager_signal_wiring import CategoryManagerSignalWiring
        wiring = CategoryManagerSignalWiring(self)
        wiring._connect_unique(signal, slot)

    def _try_connect(self, signal, slot) -> None:
        """Signal connection (internal use - prefer signal wiring controller for new code)."""
        from ui.category_manager_signal_wiring import CategoryManagerSignalWiring
        wiring = CategoryManagerSignalWiring(self)
        wiring._try_connect(signal, slot)

    def _wire_line_edit_common(self, w, *, on_enter=None, on_change=None) -> None:
        """Line edit wiring (internal use - prefer signal wiring controller for new code)."""
        from ui.category_manager_signal_wiring import CategoryManagerSignalWiring
        wiring = CategoryManagerSignalWiring(self)
        wiring._wire_line_edit_common(w, on_enter=on_enter, on_change=on_change)

    def _wire_combo_common(self, w, *, on_change=None, on_activate=None) -> None:
        """Combo wiring (internal use - prefer signal wiring controller for new code)."""
        from ui.category_manager_signal_wiring import CategoryManagerSignalWiring
        wiring = CategoryManagerSignalWiring(self)
        wiring._wire_combo_common(w, on_change=on_change, on_activate=on_activate)

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

    @staticmethod
    def _flatten_vocab_meanings(raw_meanings) -> list[str]:
        """Flatten vocab meanings into a simple list of non-empty strings."""
        return CategoryManagerVocabDisplay.flatten_vocab_meanings(raw_meanings)

    def _resolve_meanings_for_candidate(
            self,
            hz: str,
            src: str = "",
            *,
            preferred: bool = False,
            max_items: int = 2,
            # allow_pipeline: bool = False,
    ) -> list[str]:
        """Single meaning-resolution path for the UI.

        Rule: all meaning resolutions shown in this dialog must flow through this method.

        Authoritative source:
          1) MeaningFacade.select_candidate(...).meanings

        Fallback:
          2) MeaningFacade.meanings_for_display(hanzi)

        Display cleaning (applied exactly once here):
          - strip whitespace
          - drop empty entries
          - prefer entries without '[' or '(' (but fall back to the original list if that removes everything)
          - cap to `max_items`

        NOTE:
            UI must not call pipeline gloss resolvers directly.
            Any pipeline involvement must be encapsulated inside the facade.
        """

        # Prefer the user's vocab meanings first when we have an exact Hanzi match.
        # This prevents external/heuristic dictionaries from overriding colloquial glosses.
        hz_key = (hz or "").strip()
        try:
            v = getattr(self, "_vocab", None)
            if isinstance(v, dict) and hz_key:
                entry = v.get(hz_key)
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    raw_meanings = entry[0]
                    entry_jy = entry[1]

                    # Flatten meanings: vocab stores meanings as a list of lists.
                    flat = self._flatten_vocab_meanings(raw_meanings)

                    # Compare normalized Jyutping where possible (but do not block vocab meanings
                    # if we can't compare reliably).
                    try:
                        jy_widget = getattr(self, "_add_jy", None)
                        cand_jy = (jy_widget.text() or "").strip() if jy_widget is not None else ""
                    except (TypeError, AttributeError, RuntimeError):
                        cand_jy = ""

                    try:
                        norm = getattr(self, "_normalize_jy", None)
                        n_cand = str(norm(cand_jy) if callable(norm) else cand_jy).strip()
                        n_entry = str(norm(entry_jy) if callable(norm) else entry_jy).strip()
                    except (TypeError, AttributeError, RuntimeError, ValueError):
                        n_cand = str(cand_jy or "").strip()
                        n_entry = str(entry_jy or "").strip()

                    if flat and (not n_cand or not n_entry or n_cand == n_entry):
                        if isinstance(max_items, int) and max_items > 0:
                            return flat[:max_items]
                        return flat
        except (TypeError, AttributeError, RuntimeError, ValueError):
            # Never allow meaning preference to break UI flow.
            pass

        hz_s = (hz or "").strip()
        if not hz_s:
            return []

        try:
            n = int(max_items or 2)
        except (TypeError, ValueError):
            n = 2
        if n < 1:
            n = 1

        def _clean(items: list[str] | None) -> list[str]:
            if not items:
                return []

            raw: list[str] = []
            for x in items:
                s = str(x).strip()
                if s:
                    raw.append(s)

            if not raw:
                return []

            preferred_items = [g for g in raw if ("[" not in g and "(" not in g)]
            out = preferred_items if preferred_items else raw
            return out[:n]

        # 1) Domain façade (authoritative)
        facade = getattr(self, "_meaning_facade", None)
        if facade is not None and hasattr(facade, "select_candidate"):
            try:
                selected = facade.select_candidate(
                    hz_s,
                    (src or "").strip(),
                    preferred=bool(preferred),
                    max_items=n,
                )
                ms_obj = getattr(selected, "meanings", None) if selected is not None else None
                ms_list = list(ms_obj) if ms_obj is not None else []
                cleaned = _clean([str(x) for x in ms_list])
                if cleaned:
                    return cleaned
            except (TypeError, AttributeError, RuntimeError) as e:
                try:
                    logger.debug("MeaningFacade.select_candidate failed for %r (%s): %s", hz_s, src, e)
                except (RuntimeError, TypeError, AttributeError):
                    pass

        # 2) Final fallback: meanings_for_display for Hanzi
        try:
            ms2 = self._meanings_for_hanzi(hz_s) or []
        except (TypeError, AttributeError, RuntimeError) as e:
            try:
                logger.debug("_meanings_for_hanzi failed for %r: %s", hz_s, e)
            except (RuntimeError, TypeError, AttributeError):
                pass
            ms2 = []

        return _clean([str(x) for x in (ms2 or [])])

    def _on_add_category_changed(self, *args, **kwargs) -> None:
        """Category text changed while typing.

        IMPORTANT: Do NOT treat this as a commit. Users must be able to type-to-select
        categories without triggering candidate recomputation or focus changes.

        Commit happens via Enter / editingFinished / activated.
        """
        CategoryManagerHelpers.on_add_category_changed(self, *args, **kwargs)

    # ---- Add & Edit: Jyutping validation + reverse lookup wiring ----

    @staticmethod
    def _normalize_jy(s: str) -> str:
        text = (s or "").strip().lower()
        # Collapse runs of whitespace to single spaces.
        return " ".join(text.split())

    def _update_save_enabled(self) -> None:
        """Update validity state for Add/Edit form.

        Note: The inline Save button is no longer part of the normal workflow.
        Entry confirmation happens via the Enter-triggered dialog.
        This method maintains state consistency for any legacy code paths.
        """
        # Read current UI fields (authoritative)
        try:
            jy, hz, mn, cat = CategoryManagerHelpers.read_add_fields(self)()
        except (TypeError, AttributeError, RuntimeError):
            jy, hz, mn, cat = "", "", "", ""

        jy_s = (jy or "").strip()
        hz_s = (hz or "").strip()
        mn_s = (mn or "").strip()
        cat_s = (cat or "").strip()

        # Pull SM ctx if present (best-effort) and keep it coherent
        ctx = getattr(self, "_add_edit_ctx", None)

        # --- Compute validity flags (robust to missing ctx / missing helpers) ---
        # Jyutping validity: prefer SM ctx if already validated, otherwise validate if possible.
        try:
            jy_ok = bool(getattr(ctx, "jy_ok", False))
        except (TypeError, AttributeError, RuntimeError):
            jy_ok = False

        if not jy_ok:
            if jy_s:
                try:
                    vfn = getattr(self, "_validate_jyut_syllables", None)
                    if callable(vfn):
                        jy_ok = bool(vfn(jy_s))
                    else:
                        jy_ok = True
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    jy_ok = True
            else:
                jy_ok = False

        hz_ok = bool(hz_s)
        mn_ok = bool(mn_s)

        # Category must be explicitly chosen; treat 'unassigned' and 'all' as not OK for save
        cat_l = cat_s.lower()
        cat_ok = bool(cat_s) and cat_l not in ("unassigned", "all")

        # Saving flag (prevent Save while committing)
        try:
            saving = bool(getattr(self, "_saving_now", False)) or bool(getattr(ctx, "saving", False))
        except (TypeError, AttributeError, RuntimeError):
            saving = bool(getattr(self, "_saving_now", False))

        ready = bool(jy_ok and hz_ok and mn_ok and cat_ok and not saving)

        # Update ctx fields best-effort so downstream logic stays consistent.
        if ctx is not None:
            # Do not overwrite an already-committed Jyutping with "" just because the
            # widget momentarily reads empty (offscreen tests / signal ordering).
            try:
                existing_jy = str(getattr(ctx, "jy", "") or "").strip()
            except (TypeError, AttributeError, RuntimeError):
                existing_jy = ""
            try:
                if jy_s or not existing_jy:
                    ctx.jy = jy_s
            except (TypeError, AttributeError, RuntimeError):
                pass
            try:
                ctx.jy_ok = bool(jy_ok)
            except (TypeError, AttributeError, RuntimeError):
                pass
            try:
                ctx.hanzi = hz_s
            except (TypeError, AttributeError, RuntimeError):
                pass
            try:
                ctx.hz_ok = bool(hz_ok)
            except (TypeError, AttributeError, RuntimeError):
                pass
            try:
                ctx.meaning = mn_s
            except (TypeError, AttributeError, RuntimeError):
                pass
            for _k, _v in (
                    ("mn_ok", bool(mn_ok)),
                    ("category", cat_s),
                    ("cat_ok", bool(cat_ok)),
                    ("saving", bool(saving)),
            ):
                try:
                    setattr(ctx, _k, _v)
                except (TypeError, AttributeError, RuntimeError):
                    pass

        # Ensure state reflects readiness
        try:
            if ready:
                self._add_edit_state = AddEditState.READY_TO_SAVE
                # Treat any non-empty Hanzi as committed for state tracking
                try:
                    if hz_ok:
                        self._hanzi_committed = True
                except (TypeError, AttributeError, RuntimeError):
                    pass
                try:
                    fn = getattr(self, "_mark_hanzi_committed", None)
                    if callable(fn) and hz_ok:
                        fn(True)
                except (TypeError, AttributeError, RuntimeError):
                    pass
            else:
                # Do not force a specific non-ready state; just avoid claiming READY.
                if getattr(self, "_add_edit_state", None) == AddEditState.READY_TO_SAVE:
                    self._add_edit_state = AddEditState.CATEGORY_COMMITTED
        except (TypeError, AttributeError, RuntimeError):
            pass

    # ---- Add/Edit UI wiring (delegated to signal wiring controller) ----
    # Note: _setup_add_edit_ui is now called automatically during __init__
    # via CategoryManagerSignalWiring.wire_add_edit_signals()

    def _meanings_for_hanzi(self, hz: str) -> list[str]:
        """Hanzi-only meaning lookup fallback.

        This is intentionally conservative:
          1) If the MeaningFacade provides meanings_for_display(hz), use it.
          2) Else, fall back to the current vocab entry (if present).
        """
        hz_s = str(hz or "").strip()
        if not hz_s:
            return []

        facade = getattr(self, "_meaning_facade", None)
        if facade is not None and hasattr(facade, "meanings_for_display"):
            try:
                ms = facade.meanings_for_display(hz_s)
                out = []
                if ms is not None:
                    for x in list(ms):
                        s = str(x or "").strip()
                        if s:
                            out.append(s)
                return out
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Vocab fallback
        try:
            v = getattr(self, "_vocab", None)
            if isinstance(v, dict) and hz_s in v:
                row = v.get(hz_s)
                if isinstance(row, (list, tuple)) and len(row) >= 1:
                    meanings = row[0]
                    return self._flatten_vocab_meanings(meanings)
        except (TypeError, AttributeError, RuntimeError):
            pass

        return []

    # ---- Add/Edit signal handler delegation methods ----
    # These delegate to the flow controller and are wired by CategoryManagerSignalWiring

    def _on_jyut_enter(self) -> None:
        """Delegate Jyutping Enter to flow controller."""
        try:
            flow = getattr(self, "_add_edit_flow", None)
            if flow is not None and hasattr(flow, "on_jyut_enter"):
                flow.on_jyut_enter()
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _on_meaning_enter_committed(self) -> None:
        """Delegate Meaning Enter to flow controller."""
        try:
            flow = getattr(self, "_add_edit_flow", None)
            if flow is not None and hasattr(flow, "on_meaning_enter_committed"):
                flow.on_meaning_enter_committed()
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _on_add_jy_user_edited(self, *args, **kwargs) -> None:
        """Handle Jyutping user edits (clear dependent fields)."""
        try:
            CategoryManagerHelpers.on_add_jy_user_edited(self, *args, **kwargs)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _on_add_jy_editing_finished(self, *args, **kwargs) -> None:
        """Handle Jyutping edit commit (focus Category)."""
        try:
            CategoryManagerHelpers.on_add_jy_editing_finished(self, *args, **kwargs)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _on_candidate_index_activated(self, *args) -> None:
        """Delegate candidate selection to flow controller."""
        try:
            flow = getattr(self, "_add_edit_flow", None)
            if flow is not None and hasattr(flow, "on_candidate_index_activated"):
                flow.on_candidate_index_activated(*args)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _on_add_category_committed(self, *args, **kwargs) -> None:
        """Delegate category commit to category ops controller."""
        try:
            cat_ops = getattr(self, "_category_ops", None)
            if cat_ops is not None and hasattr(cat_ops, "on_add_category_committed"):
                cat_ops.on_add_category_committed(*args, **kwargs)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _on_add_category_changed(self, *args, **kwargs) -> None:
        """Delegate category text change to category ops controller."""
        try:
            cat_ops = getattr(self, "_category_ops", None)
            if cat_ops is not None and hasattr(cat_ops, "on_add_category_changed"):
                cat_ops.on_add_category_changed(*args, **kwargs)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _fetch_canto_info_async(self, *, hanzi: str, jyutping: str = "") -> None:
        """Fetch Cantonese info via service and apply meaning if still empty."""
        try:
            svc = getattr(self, "_canto_service", None)
        except (TypeError, AttributeError, RuntimeError):
            svc = None
        if svc is None:
            try:
                logger.debug("CANTO: service unavailable")
            except Exception:
                pass
            try:
                fn_notes = getattr(self, "_set_notes", None)
                if callable(fn_notes):
                    fn_notes("Cantonese service unavailable", source="canto-service")
            except Exception:
                pass
            return

        hz = str(hanzi or "").strip()
        jy = str(jyutping or "").strip()
        if not hz:
            return

        key = "hz:" + hz if hz else "jy:" + jy
        try:
            inflight = getattr(self, "_canto_inflight", None)
            if not isinstance(inflight, set):
                inflight = set()
                self._canto_inflight = inflight
            if key in inflight:
                logger.debug("CANTO: inflight skip key=%r", key)
                return
            inflight.add(key)
        except Exception:
            pass

        # Surface status in Notes while fetching.
        try:
            fn_notes = getattr(self, "_set_notes", None)
            if callable(fn_notes):
                fn_notes("Fetching colloquial meaning… please wait", source="canto-service")
        except Exception:
            pass
        try:
            logger.debug("CANTO: fetch start hanzi=%r jyutping=%r", hz, jy)
        except Exception:
            pass

        def _worker() -> None:
            info: CantoneseInfo | None = None
            try:
                logger.debug("CANTO: worker lookup hanzi=%r", hz)
                info = svc.lookup(hanzi=hz, jyutping=jy)
            except Exception:
                logger.debug("CANTO: worker lookup failed", exc_info=True)
                info = None

            if info is None:
                def _clear_note() -> None:
                    try:
                        fn_notes = getattr(self, "_set_notes", None)
                        if callable(fn_notes):
                            fn_notes("", source="canto-service")
                    except Exception:
                        pass
                try:
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, _clear_note)
                except Exception:
                    _clear_note()
                try:
                    logger.debug("CANTO: lookup returned None")
                except Exception:
                    pass
                try:
                    inflight = getattr(self, "_canto_inflight", None)
                    if isinstance(inflight, set):
                        inflight.discard(key)
                except Exception:
                    pass
                return

            try:
                logger.debug("CANTO: worker result hanzi=%r meaning=%r", hz, info.meaning_colloquial)
            except Exception:
                pass

            try:
                self._canto_pending = (hz, key, info.meaning_colloquial or "")
            except Exception:
                pass

            try:
                from PySide6.QtCore import QMetaObject, Qt
                try:
                    logger.debug("CANTO: scheduling apply (invokeMethod)")
                except Exception:
                    pass
                QMetaObject.invokeMethod(self, "_apply_canto_pending", Qt.ConnectionType.QueuedConnection)
            except Exception:
                try:
                    from PySide6.QtCore import QTimer
                    try:
                        logger.debug("CANTO: scheduling apply (QTimer)")
                    except Exception:
                        pass
                    QTimer.singleShot(0, self._apply_canto_pending)
                except Exception:
                    try:
                        logger.debug("CANTO: scheduling apply failed, running inline", exc_info=True)
                    except Exception:
                        pass
                    self._apply_canto_pending()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    @Slot()
    def _apply_canto_pending(self) -> None:
        """Apply the most recent Cantonese meaning result on the UI thread."""
        try:
            pending = getattr(self, "_canto_pending", None)
        except Exception:
            pending = None
        if not pending or not isinstance(pending, tuple) or len(pending) != 3:
            return

        hz, key, meaning_raw = pending
        meaning = str(meaning_raw or "").strip()
        try:
            logger.debug("CANTO: apply start hanzi=%r", hz)
        except Exception:
            pass

        w_mn = getattr(self, "_add_mn", None)
        if w_mn is None:
            return
        w_hz = getattr(self, "_add_hz", None)
        if w_hz is not None:
            try:
                current_hz = WidgetAccessor.get_text(w_hz)
            except Exception:
                current_hz = ""
            try:
                logger.debug("CANTO: apply current_hz=%r", current_hz)
            except Exception:
                pass
            if current_hz and current_hz != hz:
                try:
                    fn_notes = getattr(self, "_set_notes", None)
                    if callable(fn_notes):
                        fn_notes("", source="canto-service")
                except Exception:
                    pass
                return

        current = WidgetAccessor.get_text(w_mn)
        try:
            logger.debug("CANTO: apply current=%r", current)
        except Exception:
            pass
        if current:
            try:
                fn_notes = getattr(self, "_set_notes", None)
                if callable(fn_notes):
                    fn_notes("", source="canto-service")
            except Exception:
                pass
            try:
                logger.debug("CANTO: skip apply (meaning already present) hanzi=%r", hz)
            except Exception:
                pass
            try:
                inflight = getattr(self, "_canto_inflight", None)
                if isinstance(inflight, set):
                    inflight.discard(key)
            except Exception:
                pass
            return

        try:
            logger.debug("CANTO: apply meaning=%r", meaning)
        except Exception:
            pass
        if not meaning:
            try:
                fn_notes = getattr(self, "_set_notes", None)
                if callable(fn_notes):
                    fn_notes("", source="canto-service")
            except Exception:
                pass
            try:
                logger.debug("CANTO: empty meaning_colloquial hanzi=%r", hz)
            except Exception:
                pass
            try:
                inflight = getattr(self, "_canto_inflight", None)
                if isinstance(inflight, set):
                    inflight.discard(key)
            except Exception:
                pass
            return

        WidgetAccessor.set_text(w_mn, meaning)
        try:
            fn_notes = getattr(self, "_set_notes", None)
            if callable(fn_notes):
                fn_notes("", source="canto-service")
        except Exception:
            pass
        try:
            logger.debug("CANTO: applied meaning hanzi=%r meaning=%r", hz, meaning)
        except Exception:
            pass
        try:
            inflight = getattr(self, "_canto_inflight", None)
            if isinstance(inflight, set):
                inflight.discard(key)
        except Exception:
            pass

    def _fill_hanzi_candidates(self, jy: str, category: str | None = None) -> None:
        """Delegate Hanzi candidate filling to flow controller."""
        try:
            logger.debug("_fill_hanzi_candidates called: jy=%r category=%r", jy, category)
            flow = getattr(self, "_add_edit_flow", None)
            if flow is not None and hasattr(flow, "fill_hanzi_candidates"):
                flow.fill_hanzi_candidates(jy, category)
            else:
                logger.debug("_fill_hanzi_candidates: flow controller not available")
        except (TypeError, AttributeError, RuntimeError) as e:
            logger.debug("_fill_hanzi_candidates failed: %s", e)

    def _mark_hanzi_committed(self, committed: bool = True) -> None:
        """Mark whether the Hanzi has been committed by the user.

        This tracks whether the user has explicitly selected a Hanzi candidate,
        which affects whether the Save button should be enabled.
        """
        try:
            self._hanzi_committed = bool(committed)
            logger.debug("_mark_hanzi_committed: %s", committed)
        except (TypeError, AttributeError, RuntimeError) as e:
            logger.debug("_mark_hanzi_committed failed: %s", e)

    def _read_add_fields(self) -> tuple[str, str, str, str]:
        """Read current Add/Edit field values (jyutping, hanzi, meaning, category)."""
        try:
            return CategoryManagerHelpers.read_add_fields(self)()
        except (TypeError, AttributeError, RuntimeError):
            return "", "", "", ""

    def _check_duplicate_jyutping(self, jyutping: str) -> tuple[bool, str | None]:
        """Check if jyutping already exists in vocabulary.

        Args:
            jyutping: Jyutping to check

        Returns:
            Tuple of (is_duplicate, existing_hanzi)
        """
        if not jyutping:
            return False, None

        normalized_jy = self._normalize_jy(jyutping)

        try:
            vocab = getattr(self, "_vocab", None)
            if not isinstance(vocab, dict):
                return False, None

            # Check in existing vocab
            for hanzi, entry in vocab.items():
                if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                    continue

                existing_jy = entry[1]
                normalized_existing = self._normalize_jy(existing_jy)

                if normalized_existing == normalized_jy:
                    return True, hanzi

        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

        return False, None

    def _clear_add_entry_fields(self) -> None:
        """Clear all Add/Edit fields in the Entry panel."""
        try:
            ctrl = getattr(self, "_field_reset", None)
            if ctrl is not None and hasattr(ctrl, "clear_add_entry_fields"):
                ctrl.clear_add_entry_fields()
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _reset_add_panel_pre_validation(self) -> None:
        """Reset Add/Edit panel to pre-validation state (clear dependent fields)."""
        try:
            ctrl = getattr(self, "_field_reset", None)
            if ctrl is not None and hasattr(ctrl, "reset_add_panel_pre_validation"):
                ctrl.reset_add_panel_pre_validation()
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _reset_to_initial_state(self) -> None:
        """Reset both Entry and Hanzi panels to initial state (as on dialog open).

        This clears:
          - All Entry panel fields (Jyutping, Hanzi, Meaning, Category)
          - Hanzi candidate combo (hidden and cleared)
          - Internal state flags and context
        """
        # Clear Entry panel fields
        self._clear_add_entry_fields()

        # Hide and clear Hanzi candidate combo
        try:
            combo = getattr(self, "_cand_combo", None)
            if combo is not None:
                try:
                    with SignalBlocker(combo):
                        WidgetAccessor.set_visible(combo, False)
                        combo.clear()
                except (TypeError, AttributeError, RuntimeError):
                    pass
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Reset state flags
        try:
            self._hanzi_committed = False
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Reset state machine to initial state
        try:
            from domain.add_edit_sm import AddEditState, AddEditContext
            self._add_edit_state = AddEditState.EMPTY
            self._add_edit_ctx = AddEditContext(
                jy="",
                jy_ok=False,
                duplicate=None,
                hanzi="",
                hz_ok=False,
                manual_hanzi=False,
                meaning="",
                mn_ok=False,
                category="",
                cat_ok=False,
                saving=False,
            )
        except (TypeError, AttributeError, RuntimeError, ImportError):
            pass

    def _focus_jyutping(self, *, select_all: bool = True) -> None:
        """Focus the Jyutping field."""
        try:
            w = getattr(self, "_add_jy", None)
            if w is not None:
                WidgetAccessor.focus(w, select_all=select_all)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _on_save_clicked(self) -> None:
        """Handle Save button click."""
        try:
            ctrl = getattr(self, "_save_commit", None)
            if ctrl is not None and hasattr(ctrl, "on_save_clicked"):
                ctrl.on_save_clicked()
        except (TypeError, AttributeError, RuntimeError):
            pass

    # ---- Preview and confirmation delegation methods ----

    def _build_add_entry_preview(self) -> dict:
        """Build preview payload for pending add/edit entry."""
        try:
            ctrl = getattr(self, "_preview_confirm", None)
            if ctrl is not None and hasattr(ctrl, "build_add_entry_preview"):
                return ctrl.build_add_entry_preview()
        except (TypeError, AttributeError, RuntimeError):
            pass
        return {}

    def _confirm_add_entry(self, preview: dict) -> str:
        """Show confirmation dialog for entry. Returns 'save', 'edit', or 'cancel'."""
        try:
            ctrl = getattr(self, "_preview_confirm", None)
            if ctrl is not None and hasattr(ctrl, "confirm_add_entry"):
                return ctrl.confirm_add_entry(preview)
        except (TypeError, AttributeError, RuntimeError):
            pass
        return "edit"

    def _set_save_button_visible(self, visible: bool) -> None:
        """Show/hide the Save button."""
        try:
            ctrl = getattr(self, "_preview_confirm", None)
            if ctrl is not None and hasattr(ctrl, "set_save_button_visible"):
                ctrl.set_save_button_visible(visible)
        except (TypeError, AttributeError, RuntimeError):
            pass

    # ---- Widget accessor helpers ----
    # Note: Widget access is handled via ui.widget_utils.WidgetAccessor utility methods
    # throughout this class (get_text, set_text, focus, set_visible, etc.)
