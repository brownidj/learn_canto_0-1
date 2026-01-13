# -----------------------------------------------------------------------------
# Developer note: Single Meaning Resolver Rule
#
# The UI must NEVER:
#   - call pipeline gloss resolvers directly
#   - call CCCanto / CEDICT helpers
#   - clean or filter glosses itself
#
# All meaning resolution flows through:
#   MeaningFacade.select_candidate(...)
#   MeaningFacade.meanings_for_display(...)
#
# This guarantees:
#   - consistent gloss selection
#   - consistent filtering/formatting
#   - testable, domain-owned behaviour
#
# Any future meaning logic belongs in the facade, not the dialog.
# ---------------------------------------------------------------------
# Developer note (ARCH-MEANINGS)
# ---------------------------------------------------------------------
# Single resolver rule:
#   CategoryManagerDialog must not resolve/clean meanings in multiple places.
#   Any UI display of meanings (candidate preview, selection, autofill, tooltips)
#   must go through `_resolve_meanings_for_candidate(...)` (authoritative) or
#   `_meanings_for_hanzi(...)` (Hanzi-only fallback), which apply the ONE
#   display-cleaning policy.
# ---------------------------------------------------------------------

# ----------------------------------------
# Standard library imports
# ----------------------------------------
import logging
import os
import time
from dataclasses import dataclass

from domain.add_edit_controller import AddEditInputs, AddEditController

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

from persistence.categories_store import persist_categories_yaml
from table_scroll_slider_controller import TableScrollSliderController
from category_repo import CategoryRepo
from category_commit import CategoryCommitService

logger = logging.getLogger(__name__)


# ------------------------------
# Internal helpers (UI-free)
# ------------------------------


# Minimal state diagram (conceptual)
#
#   [Idle]  --open dialog-->  [AddMode, table loaded]
#
#   AddMode:
#       type Jyutping + Enter  --> candidates loaded (Hanzi + glosses)
#       edit meanings/category --> Save (valid) --> vocab + cats mutated,
#                                          files persisted,
#                                          table repopulated, back to AddMode
#
#   EditMode:
#       select row in table     --> fields pushed into Add panel
#       change cats in combos   --> _on_combo_changed() -> live resort + autosave
#       modify Jy/Meanings/Cat  --> same Save path as AddMode
#
#   Close dialog:
#       Accept/Cancel --> control returns to main window, which refreshes
#       its own category combobox from categories.yaml.


# ---------------------------
# Add/Edit controller (pure)
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
          1) Read raw UI fields (widgets only)
          2) Normalise (strip; Jyutping via dialog normaliser when available)
          3) Enrich (only from SM context and vocab meaning lookup)
          4) Emit AddEntryPreview (canonical keys)
        """
        # 1) Primary: legacy safe reader (widgets)
        jy = hz = mn = cat = ""
        selected_hz = ""
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
        if jy:
            try:
                norm = getattr(dialog, "_normalize_jy", None)
                if callable(norm):
                    jy = str(norm(jy) or "").strip()
                else:
                    jy = " ".join(jy.lower().split())
            except (TypeError, AttributeError, RuntimeError, ValueError):
                jy = " ".join(str(jy or "").strip().lower().split())

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

        # 4) Enrich meaning using the dialog's single-authority resolver when available.
        # Only fall back to vocab-derived meanings if the resolver is unavailable.
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

            # Final fallback: vocab-derived meanings.
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

    def _refresh_category_dropdown_from_cats(self, *, selected: str = "") -> None:
        """Refresh the Add/Edit category dropdown from the authoritative in-memory map.

        Contract:
          - `_cats` is the single source of truth.
          - `_all_cats` is a sorted view derived from `_cats`.
          - The Add/Edit category combobox items must reflect `_all_cats`.

        Best-effort only: must never raise.
        """
        combo = None
        idx = -1
        try:
            cats_map = getattr(self, "_cats", None)
        except (TypeError, AttributeError, RuntimeError):
            cats_map = None

        if not isinstance(cats_map, dict):
            return

        # Rebuild derived list
        try:
            keys = [str(k).strip() for k in cats_map.keys() if str(k).strip()]
        except (TypeError, ValueError):
            keys = []

        try:
            keys = [k for k in keys if k.lower() != "all"]
        except (TypeError, ValueError):
            pass

        if not any((k.lower() == "unassigned") for k in keys):
            keys.append("unassigned")

        try:
            self._all_cats = sorted(set(keys), key=lambda s: str(s).lower())
        except (TypeError, ValueError):
            try:
                self._all_cats = list(dict.fromkeys(keys))
            except (TypeError, ValueError):
                return

        # Repopulate combobox items
        try:
            combo = getattr(self, "_add_cat", None)
        except (TypeError, AttributeError, RuntimeError):
            combo = None

        if combo is None or not hasattr(combo, "clear") or not hasattr(combo, "addItems"):
            return

        with SignalBlocker(combo):
            try:
                combo.clear()
            except (TypeError, AttributeError, RuntimeError):
                pass

            try:
                combo.addItems(self._all_cats)
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Preserve selection where possible
        sel = (selected or "").strip()
        if sel:
            try:
                if hasattr(combo, "findText") and int(combo.findText(sel)) < 0 and hasattr(combo, "addItem"):
                    combo.addItem(sel)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass
            try:
                combo.setCurrentText(sel)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                try:
                    idx = int(combo.findText(sel))
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    pass
        else:
            try:
                combo.setCurrentIndex(-1)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

        try:
            combo.blockSignals(False)
        except (TypeError, AttributeError, RuntimeError):
            pass

    @staticmethod
    def _perf_start(name: str) -> float:
        t0 = time.perf_counter()
        logger.debug("PERF start: %s", name)
        return t0

    @staticmethod
    def _perf_end(name: str, t0: float) -> None:
        if not t0:
            return
        dt_ms = (time.perf_counter() - float(t0)) * 1000.0
        logger.debug("PERF end: %s (%.1f ms)", name, dt_ms)

    @staticmethod
    def _validate_jyut_syllables(jy: str) -> tuple[bool, str | None]:
        try:
            return validate_jyut_syllables(jy)
        except (ImportError, AttributeError, TypeError, ValueError, RuntimeError) as e:
            # Best-effort: do not hard-fail UI if validator is unavailable.
            try:
                logger.debug("Jyutping validator unavailable (%s); allowing input", e)
            except (TypeError, ValueError):
                pass
            return True, None

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
    _FORM_VERTICAL_SPACING_PX = 12

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

        # ---- Root layout ----
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(12, 12, 12, 12)
        self._root.setSpacing(10)

        # ---- Header (Close button) ----
        header = QHBoxLayout()
        header.addStretch(1)
        btn_close = QPushButton("Close", self)
        btn_close.setDefault(False)
        btn_close.setAutoDefault(False)
        btn_close.clicked.connect(self.accept)
        header.addWidget(btn_close, 0, _Qt.AlignmentFlag.AlignTop | _Qt.AlignmentFlag.AlignRight)
        self._root.addLayout(header)

        # ---- Main row ----
        row = QHBoxLayout()
        row.setSpacing(12)

        # ---- Save header ----
        header_row = QHBoxLayout()
        self.btn_save = QPushButton("Save")
        self.btn_save.setObjectName("btn_save")
        if callable(getattr(self, "_on_save_clicked", None)):
            self.btn_save.clicked.connect(self._on_save_clicked)
        self.btn_save.setDefault(False)
        self.btn_save.setAutoDefault(False)
        self.btn_save.setEnabled(False)
        self.btn_save.setToolTip("Save Hanzi + Jyutping + Category")

        # Stage-2: hide legacy inline Save button by default (only shown on 'Edit')
        try:
            self._set_save_button_visible(False)
        except (AttributeError, TypeError, ValueError, RuntimeError):
            pass

        header_row.addStretch(1)
        header_row.addWidget(self.btn_save, 0, _Qt.AlignmentFlag.AlignRight)
        self._root.addLayout(header_row)

        # ---- Entry group ----
        group_entry = QGroupBox("Entry", self)
        form_entry = QFormLayout(group_entry)
        form_entry.setLabelAlignment(_Qt.AlignmentFlag.AlignRight | _Qt.AlignmentFlag.AlignVCenter)
        form_entry.setFormAlignment(_Qt.AlignmentFlag.AlignLeft | _Qt.AlignmentFlag.AlignTop)
        form_entry.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._add_jy = QLineEdit(group_entry)
        self._add_jy.setPlaceholderText("e.g. nei5 hou2")
        self._add_jy.setClearButtonEnabled(True)

        self._add_mn = QLineEdit(group_entry)
        self._add_mn.setPlaceholderText("comma-separated meanings, e.g. hello, hi")
        self._add_mn.setClearButtonEnabled(True)

        self._add_notes = QLineEdit(group_entry)
        self._add_notes.setReadOnly(True)
        self._add_notes.setPlaceholderText("Notes (auto; shown only when ambiguous)")
        self._add_notes.setToolTip(
            "Shown only when an entry is ambiguous or needs confirmation. "
            "Auto-default entries never keep notes."
        )

        form_entry.addRow("Jyutping:", self._add_jy)
        form_entry.addRow("Meanings:", self._add_mn)
        form_entry.addRow("Notes:", self._add_notes)

        # ---- Category combobox ----
        self._add_cat = QComboBox(group_entry)
        self._add_cat.setObjectName("comboAddCategories")
        self._add_cat.setEditable(True)
        self._add_cat.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._add_cat.addItems(self._all_cats)
        self._add_cat.setCurrentIndex(-1)

        _le = getattr(self._add_cat, "lineEdit", None)
        le_cat = cast(QLineEdit | None, _le() if callable(_le) else None)

        if le_cat is not None:
            le_cat.setPlaceholderText("Type category")
            le_cat.setClearButtonEnabled(True)
            # IMPORTANT: do NOT connect returnPressed/editingFinished directly to the dialog handler.
            # CategoryComboController owns commit wiring and will call `on_commit`.

        _on_cat_commit = getattr(self, "_on_add_category_committed", None)
        self._cat_combo_ctrl = CategoryComboController(
            combo=self._add_cat,
            on_commit=_on_cat_commit if callable(_on_cat_commit) else None,
            on_add_new=None,
        )

        form_entry.addRow("Category:", self._add_cat)

        # Back-compat aliases
        self.editJyut = self._add_jy
        self.editMeanings = self._add_mn
        self.comboCategory = self._add_cat

        # ---- Hanzi group ----
        group_hanzi = QGroupBox("Hanzi", self)
        form_hanzi = QFormLayout(group_hanzi)

        self._add_hz = QLineEdit(group_hanzi)
        self._add_hz.setReadOnly(True)
        self._add_hz.setPlaceholderText("Auto, after reverse lookup")
        form_hanzi.addRow(self._add_hz)

        self._cand_combo = QComboBox(group_hanzi)
        self._cand_combo.setObjectName("comboHanziCandidates")
        self._cand_combo.setVisible(False)
        self._cand_combo.setToolTip(HANZI_CANDIDATE_TOOLTIP)
        if self._cand_combo.view() is not None:
            self._cand_combo.view().setToolTip(HANZI_CANDIDATE_TOOLTIP)

        form_hanzi.addRow("Candidates:", self._cand_combo)

        self._btn_custom_hz = QPushButton("Enter my own Hanzi", self)
        self._btn_custom_hz.setDefault(False)
        self._btn_custom_hz.setAutoDefault(False)
        # Always wire the Manual Hanzi button. Handler is best-effort and must never raise.
        try:
            self._btn_custom_hz.clicked.connect(self._on_btn_custom_hz_clicked)
        except (TypeError, AttributeError, RuntimeError):
            pass
        form_hanzi.addWidget(self._btn_custom_hz)

        self.comboCandidates = self._cand_combo

        # ---- Layout assembly ----
        group_entry.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        group_hanzi.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(group_entry)
        row.addWidget(group_hanzi)
        self._root.addLayout(row)

        # ---- Typography (delegated) ----
        self._typography_ctrl.apply_add_edit_typography(
            group_entry=group_entry,
            form_entry=form_entry,
            group_hanzi=group_hanzi,
            form_hanzi=form_hanzi,
        )

        # ---- Vocab table scroll panel (preferred) ----
        self._table_panel_ctrl = None
        self._table_panel = None
        self._vocab_table_ctrl = None

        if TableScrollSliderController is not None:
            try:
                # Controller owns the panel widget; keep it as the single table/search surface.
                # `create()` is optional; if not present, fall back to direct construction.
                create_fn = getattr(TableScrollSliderController, "create", None)
                if callable(create_fn):
                    self._table_panel_ctrl = create_fn(parent=self)
                else:
                    self._table_panel_ctrl = TableScrollSliderController(parent=self)

                self._table_panel = getattr(self._table_panel_ctrl, "widget", None)

                if self._table_panel is not None:
                    self._root.addWidget(self._table_panel, 1)

                    # Back-compat aliases: expose search/table under the dialog's legacy names.
                    # Tests and existing dialog code refer to `self._search` and `self._table`.
                    try:
                        self._search = self._table_panel.findChild(QLineEdit, "editTableSearch")
                    except ():
                        self._search = None

                    # The panel may provide either QTableWidget or QTableView; keep it generic.
                    try:
                        self._table = self._table_panel.findChild(object, "tableVocab")
                    except ():
                        self._table = None

                    # Wire legacy search handler if present.
                    try:
                        fn_search = getattr(self, "_on_search_changed", None)
                        if callable(fn_search) and self._search is not None and hasattr(self._search, "textChanged"):
                            self._search.textChanged.connect(fn_search)
                    except (TypeError, AttributeError, RuntimeError):
                        pass

                    # Initialize vocabulary table controller
                    if self._table is not None:
                        try:
                            self._vocab_table_ctrl = VocabularyTableController(
                                table=self._table,
                                vocab=self._vocab,
                                categories=self._cats,
                            )
                            self._vocab_table_ctrl.populate()
                        except (TypeError, AttributeError, RuntimeError):
                            self._vocab_table_ctrl = None

                    # Table already populated by VocabularyTableController above
                    try:
                        tbl = getattr(self, "_table", None)
                        if tbl is not None:
                            try:
                                rows = int(tbl.rowCount()) if hasattr(tbl, "rowCount") else None
                            except (TypeError, AttributeError, RuntimeError):
                                rows = None
                            logger.debug(
                                "Table populated via VocabularyTableController: rows=%s",
                                rows if rows is not None else "?",
                            )
                    except (TypeError, AttributeError, RuntimeError):
                        pass
            except (TypeError, AttributeError, RuntimeError):
                # Controller failed: fall back to legacy widgets.
                self._table_panel_ctrl = None
                self._table_panel = None

        # ---- Legacy Search + Table (fallback) ----
        if self._table_panel is None:
            self._search = QLineEdit(self)
            self._search.setPlaceholderText("Search (Hanzi / Jyutping / meaning)…")
            self._search.setClearButtonEnabled(True)
            try:
                fn_search = getattr(self, "_on_search_changed", None)
                if callable(fn_search):
                    self._search.textChanged.connect(fn_search)
            except (TypeError, AttributeError, RuntimeError):
                pass
            self._root.addWidget(self._search)

            self._table = QTableWidget(self)
            self._table.setColumnCount(4)
            self._table.setHorizontalHeaderLabels(["Hanzi", "Jyutping", "Meanings", "Categories"])
            self._table.horizontalHeader().setStretchLastSection(True)
            self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self._root.addWidget(self._table, 1)

            # Initialize table controller for legacy path too
            try:
                self._vocab_table_ctrl = VocabularyTableController(
                    table=self._table,
                    vocab=self._vocab,
                    categories=self._cats,
                )
                self._vocab_table_ctrl.populate()
            except (TypeError, AttributeError, RuntimeError):
                self._vocab_table_ctrl = None

            try:
                rows = int(self._table.rowCount()) if hasattr(self._table, "rowCount") else 0
                logger.debug("Legacy table ready: rows=%d", rows)
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Final back-compat: ensure attributes exist even if the panel did not expose widgets as expected.
        if not hasattr(self, "_search"):
            self._search = None
        if not hasattr(self, "_table"):
            self._table = None

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

    def _load_hanzi_style_map(self) -> dict:
        """Lazy-load style map (delegated to candidate pipeline)."""
        return self._candidate_pipeline.load_hanzi_style_map()

    def _hanzi_style(self, hanzi: str) -> str:
        """Style lookup (delegated to candidate pipeline)."""
        return self._candidate_pipeline.hanzi_style(hanzi)

    def _is_colloquial_hanzi(self, hanzi: str) -> bool:
        """Colloquial detection (delegated to candidate pipeline)."""
        return self._candidate_pipeline.is_colloquial_hanzi(hanzi)

    def _curate_top_hanzi_candidates(self, ranked: list[str]) -> list[str]:
        """Curate candidates (delegated to candidate pipeline)."""
        return self._candidate_pipeline.curate_top_hanzi_candidates(ranked)

    def _focus_jyutping(self, *, select_all: bool = True) -> None:
        """Focus Jyutping field."""
        self._focus_ctrl.focus_jyutping(select_all=select_all)

    def _focus_meanings(self, *, select_all: bool = True) -> None:
        """Focus Meanings field."""
        self._focus_ctrl.focus_meanings(select_all=select_all)

    def _focus_hanzi(self, *, select_all: bool = True) -> None:
        """Focus Hanzi field."""
        self._focus_ctrl.focus_hanzi(select_all=select_all)

    def _focus_category(self, *, select_all: bool = True, show_popup: bool = False) -> None:
        """Focus category combobox."""
        self._focus_ctrl.focus_category(select_all=select_all, show_popup=show_popup)


    def _connect_unique(self, signal, slot) -> None:
        """Best-effort signal connect without duplicate wiring."""
        if signal is None or not callable(slot):
            return

        try:
            from PySide6.QtCore import Qt
            signal.connect(slot, Qt.ConnectionType.UniqueConnection)
            return
        except (ImportError, TypeError, AttributeError, RuntimeError):
            pass

        try:
            signal.connect(slot)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _try_connect(self, signal, slot) -> None:
        """Connect a signal to a callable slot (best-effort, no duplicates)."""
        if signal is None or slot is None or not callable(slot):
            return
        try:
            self._connect_unique(signal, slot)
        except (TypeError, AttributeError, RuntimeError):
            # Be conservative: wiring must never break dialog construction.
            pass

    def _wire_line_edit_common(self, w, *, on_enter=None, on_change=None) -> None:
        """Common wiring for QLineEdit-like widgets.

        - on_enter: connected to returnPressed
        - on_change: connected to editingFinished and textChanged
        """
        if w is None:
            return

        if on_enter is not None and callable(on_enter):
            self._try_connect(getattr(w, "returnPressed", None), on_enter)

        if on_change is not None and callable(on_change):
            self._try_connect(getattr(w, "editingFinished", None), on_change)
            self._try_connect(getattr(w, "textChanged", None), on_change)

    def _wire_combo_common(self, w, *, on_change=None, on_activate=None) -> None:
        """Common wiring for QComboBox-like widgets (best-effort).

        - on_change: connected to currentTextChanged
        - on_activate: connected to activated

        Notes:
          - This is intentionally tolerant of missing signals across bindings.
          - Use `_try_connect`, which prefers UniqueConnection where available.
        """
        if w is None:
            return

        if on_change is not None and callable(on_change):
            self._try_connect(getattr(w, "currentTextChanged", None), on_change)

        if on_activate is not None and callable(on_activate):
            self._try_connect(getattr(w, "activated", None), on_activate)
        # Do not auto-wire activated to on_change. Activated is a commit signal and must be wired explicitly.

    # ---- UI intent / focus policy (delegated to controller) ----
    def _user_has_committed_hanzi(self) -> bool:
        return self._focus_ctrl.user_has_committed_hanzi()

    def _user_is_in_manual_hanzi_mode(self) -> bool:
        return self._focus_ctrl.user_is_in_manual_hanzi_mode()

    def _mark_hanzi_committed(self, committed: bool = True) -> None:
        self._focus_ctrl.mark_hanzi_committed(committed)

    def _mark_manual_hanzi_mode(self, enabled: bool = True) -> None:
        self._focus_ctrl.mark_manual_hanzi_mode(enabled)

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
        """Flatten vocab meanings into a simple list of non-empty strings.

        The vocab store may contain meanings as a list of lists, or a flat list.
        This helper is intentionally conservative and never raises.
        """
        out: list[str] = []
        try:
            if isinstance(raw_meanings, (list, tuple)):
                for item in raw_meanings:
                    if isinstance(item, (list, tuple)):
                        for sub in item:
                            try:
                                s = str(sub or "").strip()
                            except (TypeError, ValueError):
                                s = ""
                            if s:
                                out.append(s)
                    else:
                        try:
                            s = str(item or "").strip()
                        except (TypeError, ValueError):
                            s = ""
                        if s:
                            out.append(s)
            else:
                try:
                    s = str(raw_meanings or "").strip()
                except (TypeError, ValueError):
                    s = ""
                if s:
                    out.append(s)
        except (TypeError, ValueError):
            return out

        return out

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

    def _defer_focus(self, target: str) -> None:
        """Defer focus movement to the next event-loop tick (best-effort)."""
        self._focus_ctrl.defer_focus(target)

    def _on_btn_custom_hz_clicked(self) -> None:
        """Enter manual Hanzi mode (delegated to manual Hanzi controller)."""
        self._manual_hanzi_ctrl.enter_manual_mode()

    def _on_save_clicked(self) -> None:
        """Legacy inline Save button handler (delegated to save/commit controller)."""
        self._save_commit.on_save_clicked()

    def _ensure_category_services(self):
        """Ensure category services (delegated to category ops controller)."""
        return self._category_ops.ensure_category_services()

    def _add_new_category(self, cat: str) -> bool:
        """Add new category (delegated to category ops controller)."""
        return self._category_ops.add_new_category(cat)

    def _on_add_category_committed(self, *args, user_action: bool = False, **kwargs) -> None:
        """Category commit (delegated to category ops controller)."""
        self._category_ops.on_add_category_committed(*args, user_action=user_action, **kwargs)

    def _original_on_add_category_committed_REPLACED_BY_CONTROLLER(self, *args, user_action: bool = False, **kwargs) -> None:
        """Commit the Add/Edit category selection.

        UI prompting for unknown categories is delegated to the CategoryComboController
        (ui/category_combo.py). This method must remain best-effort and must never raise.

        Adapter responsibilities (Qt boundary):
          - Read widget text
          - If category is unknown, ask the controller to confirm/add
          - Call CategoryCommitService for the core decision + repo mutation
          - Apply UI effects (set text, fill candidates, focus)
        """
        # Guard against re-entrant / duplicate commits caused by QComboBox signal churn.
        try:
            if bool(getattr(self, "_in_cat_commit", False)):
                try:
                    logger.debug("Add/Edit category commit: re-entrant call suppressed")
                except Exception:
                    pass
                return
        except Exception:
            # If we cannot read the guard flag, remain conservative and proceed.
            pass

        try:
            self._in_cat_commit = True
        except Exception:
            pass

        try:
            # 1) Read category text
            try:
                w_cat = getattr(self, "_add_cat", None)
            except (TypeError, AttributeError, RuntimeError):
                w_cat = None

            try:
                cat_raw = (w_cat.currentText() or "").strip() if w_cat is not None else ""
            except (TypeError, AttributeError, RuntimeError):
                cat_raw = ""

            if (not cat_raw) and (w_cat is not None):
                try:
                    le = w_cat.lineEdit() if hasattr(w_cat, "lineEdit") else None
                except (TypeError, AttributeError, RuntimeError):
                    le = None
                if le is not None:
                    try:
                        cat_raw = (le.text() or "").strip()
                    except (TypeError, AttributeError, RuntimeError):
                        cat_raw = cat_raw or ""

            if not cat_raw:
                try:
                    logger.debug(
                        "Add/Edit category commit: raw=%r user_action=%s",
                        str(cat_raw or ""),
                        bool(user_action),
                    )
                except (TypeError, AttributeError, RuntimeError):
                    pass

                try:
                    fn_gate = getattr(self, "_update_save_enabled", None)
                    if callable(fn_gate):
                        _gate = fn_gate  # type-narrow for linters
                        _gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
                return

            # 2) Jyutping present?
            try:
                w_jy = getattr(self, "_add_jy", None)
                jy = (w_jy.text() or "").strip() if w_jy is not None else ""
            except (TypeError, AttributeError, RuntimeError):
                jy = ""
            has_jy = bool(jy)

            # 3) Acquire repo + service (lazy init; UI-free). If unavailable, fail safe.
            try:
                repo, svc = self._ensure_category_services()
            except (TypeError, AttributeError, RuntimeError, ValueError):
                repo, svc = None, None

            if repo is None or svc is None:
                try:
                    fn_gate = getattr(self, "_update_save_enabled", None)
                    if callable(fn_gate):
                        _gate = fn_gate  # type-narrow for linters
                        _gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
                return

            # UI-only helper: clear category input and refocus
            def _clear_and_refocus() -> None:
                try:
                    ctrl2 = getattr(self, "_cat_combo_ctrl", None)
                except (TypeError, AttributeError, RuntimeError):
                    ctrl2 = None

                if ctrl2 is not None and hasattr(ctrl2, "clear_and_refocus"):
                    try:
                        ctrl2.clear_and_refocus()
                        return
                    except (TypeError, AttributeError, RuntimeError, ValueError):
                        pass

                try:
                    w = getattr(self, "_add_cat", None)
                except (TypeError, AttributeError, RuntimeError):
                    w = None

                if w is not None:
                    try:
                        w.blockSignals(True)
                    except (TypeError, AttributeError, RuntimeError):
                        pass

                    try:
                        le2 = w.lineEdit() if hasattr(w, "lineEdit") else None
                    except (TypeError, AttributeError, RuntimeError):
                        le2 = None

                    if le2 is not None:
                        try:
                            le2.clear()
                        except (TypeError, AttributeError, RuntimeError):
                            pass

                    try:
                        w.setCurrentIndex(-1)
                    except (TypeError, AttributeError, RuntimeError):
                        try:
                            w.setCurrentText("")
                        except (TypeError, AttributeError, RuntimeError):
                            pass

                    try:
                        w.blockSignals(False)
                    except (TypeError, AttributeError, RuntimeError):
                        pass

                try:
                    self._focus_category(select_all=True, show_popup=True)
                except (TypeError, AttributeError, RuntimeError):
                    pass

            # 4) Determine confirmation only if unknown
            user_confirmed_add = False

            try:
                canon = repo.canon(cat_raw)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                canon = str(cat_raw or "").strip()
            # ---- DBG[B1]: category commit inputs ----
            try:
                logger.debug(
                    "DBG[B1] cat_commit: cat_raw=%r canon=%r user_action=%s",
                    str(cat_raw or ""),
                    str(canon or ""),
                    bool(user_action),
                )
            except Exception:
                pass

            try:
                exists_now = bool(canon) and bool(repo.exists(canon))
            except (TypeError, AttributeError, RuntimeError, ValueError):
                exists_now = False
            # ---- DBG[B2]: existence check ----
            try:
                logger.debug(
                    "DBG[B2] cat_commit: exists_now=%s repo=%s repo_has_exists=%s",
                    bool(exists_now),
                    type(repo).__name__ if repo is not None else None,
                    bool(callable(getattr(repo, "exists", None))),
                )
            except Exception:
                pass

            try:
                logger.debug(
                    "Add/Edit category commit: canon=%r exists_now=%s",
                    str(canon or ""),
                    bool(exists_now),
                )
            except (TypeError, AttributeError, RuntimeError):
                pass

            if not exists_now:
                # UI confirmation lives at the adapter boundary (tests monkeypatch QMessageBox.question).
                user_confirmed_add = False
                try:
                    from PySide6.QtWidgets import QMessageBox
                except (ImportError, ModuleNotFoundError):
                    QMessageBox = None

                if QMessageBox is not None:
                    try:
                        resp = QMessageBox.question(
                            self,
                            "Add category?",
                            "Add new category ‘{0}’?".format(str(canon or "")),
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.Yes,
                        )
                        user_confirmed_add = bool(resp == QMessageBox.StandardButton.Yes)
                    except (TypeError, AttributeError, RuntimeError, ValueError):
                        user_confirmed_add = False

                try:
                    logger.debug(
                        "Add/Edit category commit: unknown category confirmation -> confirmed=%s (canon=%r)",
                        bool(user_confirmed_add),
                        str(canon or ""),
                    )
                except (TypeError, AttributeError, RuntimeError):
                    pass
            # Insert guard after unknown category confirmation
            if (not exists_now) and (not bool(user_confirmed_add)):
                _clear_and_refocus()
                try:
                    fn_gate = getattr(self, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
                return

            # 5) Core commit (pure decision + repo mutation)
            try:
                logger.debug(
                    "Add/Edit category commit: calling svc.commit(requested=%r has_jy=%s confirmed_add=%s)",
                    str(canon or ""),
                    bool(has_jy),
                    bool(user_confirmed_add),
                )
            except (TypeError, AttributeError, RuntimeError):
                pass
            try:
                res = self._cat_commit_svc.commit(
                    requested=canon,
                    has_jy=has_jy,
                    confirmed_add=bool(user_confirmed_add),
                )
            except (TypeError, AttributeError, RuntimeError, ValueError):
                _clear_and_refocus()
                try:
                    fn_gate = getattr(self, "_update_save_enabled", None)
                    if callable(fn_gate):
                        _gate = fn_gate  # type-narrow for linters
                        _gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
                return
            # ---- DBG[B3]: post-commit authoritative map state ----
            try:
                cats_dbg = getattr(self, "_cats", None)
                ok_dbg = bool(getattr(res, "ok", False))
                cat_dbg = str(getattr(res, "category", "") or "").strip()
                logger.debug(
                    "DBG[B3] cat_commit: res.ok=%s res.category=%r self._cats_has=%s self._cats_n=%s",
                    bool(ok_dbg),
                    str(cat_dbg or ""),
                    bool(isinstance(cats_dbg, dict) and bool(cat_dbg) and (cat_dbg in cats_dbg)),
                    (len(cats_dbg) if isinstance(cats_dbg, dict) else None),
                )
            except Exception:
                pass

            try:
                logger.debug(
                    "Add/Edit category commit: svc result ok=%s category=%r should_fill=%s",
                    bool(getattr(res, "ok", False)),
                    str(getattr(res, "category", "") or ""),
                    bool(getattr(res, "should_fill_candidates", False)),
                )
            except Exception:
                pass

            if not bool(getattr(res, "ok", False)):
                _clear_and_refocus()
                try:
                    fn_gate = getattr(self, "_update_save_enabled", None)
                    if callable(fn_gate):
                        _gate = fn_gate  # type-narrow for linters
                        _gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
                return

            try:
                cat = str(getattr(res, "category", "") or "").strip()
            except (TypeError, AttributeError, RuntimeError, ValueError):
                cat = ""

            if not cat:
                _clear_and_refocus()
                try:
                    fn_gate = getattr(self, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
                return

            # Regression guard: ensure authoritative in-memory map records brand-new categories.
            try:
                if (not bool(exists_now)) and bool(user_confirmed_add):
                    cats_map_auth = getattr(self, "_cats", None)
                    if isinstance(cats_map_auth, dict) and cat not in cats_map_auth:
                        cats_map_auth[cat] = []
            except Exception:
                pass

            try:
                if isinstance(getattr(self, "_cats", None), dict) and cat and (cat not in self._cats):
                    self._cats[cat] = []
            except (TypeError, AttributeError, RuntimeError):
                pass

            # ---- UI list sync (ensure new categories appear in the dropdown) ----
            try:
                all_cats = getattr(self, "_all_cats", None)
            except (TypeError, AttributeError, RuntimeError):
                all_cats = None

            try:
                if isinstance(all_cats, list) and cat and (cat not in all_cats):
                    all_cats.append(cat)
                    all_cats.sort(key=lambda s: str(s).lower())
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

            # Ensure the combobox model contains the category as an item (not just edit text).
            if w_cat is not None:
                try:
                    existing = []
                    try:
                        n = int(w_cat.count())
                    except (TypeError, AttributeError, RuntimeError, ValueError):
                        n = 0
                    for i in range(max(0, n)):
                        try:
                            t = str(w_cat.itemText(i) or "").strip()
                        except (TypeError, AttributeError, RuntimeError, ValueError):
                            t = ""
                        if t:
                            existing.append(t)

                    if cat and (cat not in existing):
                        # Rebuild items in sorted order (keeps list stable with InsertPolicy.NoInsert).
                        merged = sorted(set(existing + [cat]), key=lambda s: str(s).lower())
                        try:
                            w_cat.blockSignals(True)
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                        try:
                            w_cat.clear()
                            w_cat.addItems(list(merged))
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                        try:
                            w_cat.setEditable(True)
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                        try:
                            w_cat.blockSignals(False)
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    pass

            # Debug: verify repo/_cats now contains the committed category
            try:
                cats_map_dbg = getattr(self, "_cats", None)
                in_cats = bool(isinstance(cats_map_dbg, dict) and cat in cats_map_dbg)
                # Safety: ensure the authoritative in-memory map reflects the committed category.
                if isinstance(cats_map_dbg, dict) and cat and (cat not in cats_map_dbg):
                    cats_map_dbg[cat] = []
                    in_cats = True
                logger.debug(
                    "Add/Edit category commit: after commit cat=%r in _cats=%s cats_n=%s",
                    str(cat or ""),
                    bool(in_cats),
                    (len(cats_map_dbg) if isinstance(cats_map_dbg, dict) else "?"),
                )
                if isinstance(cats_map_dbg, dict) and not in_cats:
                    logger.debug(
                        "Add/Edit category commit: _cats keys sample=%s",
                        sorted(list(cats_map_dbg.keys()))[:30],
                    )
            except Exception:
                pass

            try:
                logger.debug(
                    "Add/Edit category commit: repo.exists(%r)=%s",
                    str(cat or ""),
                    bool(repo.exists(cat) if hasattr(repo, "exists") else False),
                )
            except Exception:
                pass

            # 6) Apply success effects
            try:
                if w_cat is not None and hasattr(w_cat, "setCurrentText"):
                    w_cat.setCurrentText(cat)
            except (TypeError, AttributeError, RuntimeError):
                pass

            # If we just created a new category, refresh the derived list + dropdown
            # from the authoritative map so it remains available after field clears.
            try:
                if not bool(exists_now):
                    self._refresh_category_dropdown_from_cats(selected=cat)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

            try:
                ctx = getattr(self, "_add_edit_ctx", None)
            except (TypeError, AttributeError, RuntimeError):
                ctx = None

            try:
                cat_l = cat.lower()
                cat_ok = bool(cat) and cat_l not in ("unassigned", "all")
            except Exception:
                cat_ok = False

            if ctx is not None:
                try:
                    setattr(ctx, "category", cat)
                except (TypeError, AttributeError, RuntimeError):
                    pass
                try:
                    setattr(ctx, "cat_ok", bool(cat_ok))
                except (TypeError, AttributeError, RuntimeError):
                    pass

            # Candidate fill should happen whenever we have Jyutping and a committed category.
            # Relying solely on the service flag has caused regressions where candidates
            # fail to populate in UI flows.
            try:
                should_fill = bool(has_jy)
            except (TypeError, AttributeError, RuntimeError):
                should_fill = False

            if bool(should_fill):
                try:
                    fn_fill = getattr(self, "_fill_hanzi_candidates", None)
                except (TypeError, AttributeError, RuntimeError):
                    fn_fill = None

                if callable(fn_fill):
                    try:
                        fn_fill(jy, category=cat)
                    except TypeError:
                        try:
                            fn_fill(jy)
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                    except (TypeError, AttributeError, RuntimeError):
                        pass

            try:
                fn_gate = getattr(self, "_update_save_enabled", None)
                if callable(fn_gate):
                    _gate = fn_gate  # type-narrow for linters
                    _gate()
            except (TypeError, AttributeError, RuntimeError):
                pass

            # 7) Focus advance
            # If candidate Hanzi are available, show + focus the candidate combobox.
            # Otherwise, fall back to the Hanzi field.
            try:
                combo = getattr(self, "_cand_combo", None)
            except (TypeError, AttributeError, RuntimeError):
                combo = None

            focused = False
            n_items = 0
            if combo is not None:
                try:
                    n_items = int(combo.count())
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    n_items = 0

            if n_items > 0:
                focused = True
                # Defer focus so later QComboBox signals don't steal it back.
                self._defer_focus("cand")
            else:
                # Candidate list empty (or missing): move to the Hanzi field so the user can proceed.
                self._defer_focus("hz")

        finally:
            try:
                self._in_cat_commit = False
            except Exception:
                pass

        return

    def _build_add_entry_preview(self) -> dict:
        """Build entry preview (delegated to preview/confirm controller)."""
        return self._preview_confirm.build_add_entry_preview()

    def _confirm_add_entry(self, preview: dict) -> str:
        """Confirmation dialog (delegated to preview/confirm controller)."""
        return self._preview_confirm.confirm_add_entry(preview)

    def _set_save_button_visible(self, visible: bool) -> None:
        """Set Save button visibility (delegated to preview/confirm controller)."""
        self._preview_confirm.set_save_button_visible(visible)

    def _clear_add_entry_fields(self) -> None:
        """Clear Add/Edit fields (delegated to field reset controller)."""
        self._field_reset.clear_add_entry_fields()

    def _reset_add_panel_pre_validation(self) -> None:
        """Reset Add/Edit panel to pre-validation state (delegated to field reset controller)."""
        self._field_reset.reset_add_panel_pre_validation()

    def _on_add_jy_user_edited(self, *args, **kwargs) -> None:
        """Slot: user edited Jyutping; reset dependent fields to placeholders."""
        try:
            self._reset_add_panel_pre_validation()
        except (TypeError, AttributeError, RuntimeError):
            return

    def _on_add_category_changed(self, *args, **kwargs) -> None:
        """Category text changed while typing.

        IMPORTANT: Do NOT treat this as a commit. Users must be able to type-to-select
        categories without triggering candidate recomputation or focus changes.

        Commit happens via Enter / editingFinished / activated.
        """
        return

    def _focus_jy(self) -> None:
        try:
            w = getattr(self, "_add_jy", None)
            if w is not None:
                w.setFocus()
                try:
                    w.selectAll()
                except (TypeError, AttributeError, RuntimeError):
                    pass
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _on_meaning_enter_committed(self) -> None:
        """Handle Enter/commit in Meaning field (delegated to flow controller)."""
        self._add_edit_flow.on_meaning_enter_committed()

    # ---- Add & Edit: Jyutping validation + reverse lookup wiring ----

    @staticmethod
    def _normalize_jy(s: str) -> str:
        text = (s or "").strip().lower()
        # Collapse runs of whitespace to single spaces.
        return " ".join(text.split())

    def _warn_duplicate_jy_and_reset(self, jy: str) -> None:
        """Warn about duplicate (delegated to flow controller)."""
        self._add_edit_flow._warn_duplicate_jy_and_reset(jy)

    def _read_add_fields(self) -> tuple[str, str, str, str]:
        """Read Add/Edit panel fields safely (legacy compatibility)."""
        return (
            WidgetAccessor.get_text(getattr(self, "_add_jy", None)),
            WidgetAccessor.get_text(getattr(self, "_add_hz", None)),
            WidgetAccessor.get_text(getattr(self, "_add_mn", None)),
            WidgetAccessor.get_text(getattr(self, "_add_cat", None)),
        )

    def _ensure_category_combo_editable(self) -> None:
        """Ensure the Add/Edit category combobox is editable (best-effort)."""
        try:
            w_cat = getattr(self, "_add_cat", None)
            if w_cat is not None and hasattr(w_cat, "setEditable"):
                w_cat.setEditable(True)
        except (TypeError, AttributeError, RuntimeError):
            return

    def _fill_hanzi_candidates(self, jy: str, category: str | None = None) -> None:
        """Fill Hanzi candidates (delegated to flow controller)."""
        self._add_edit_flow.fill_hanzi_candidates(jy, category)

    def _on_meanings_text_changed(self, *args, **kwargs) -> None:
        """Meaning text changed (user or programmatic).
        Keeps Add/Edit context in sync and refreshes Save gating. Must never raise.
        """
        try:
            w = getattr(self, "_add_mn", None)
        except (TypeError, AttributeError, RuntimeError):
            w = None

        try:
            mn = (w.text() or "").strip() if w is not None else ""
        except (TypeError, AttributeError, RuntimeError):
            mn = ""

        try:
            ctx = getattr(self, "_add_edit_ctx", None)
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
            fn_gate = getattr(self, "_update_save_enabled", None)
            if callable(fn_gate):
                fn_gate()
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _save_add_item(self) -> None:
        """Legacy save entry point (delegated to save/commit controller)."""
        self._save_commit.save_add_item()

    def _update_save_enabled(self) -> None:
        """Enable/disable Save based on current Add/Edit validity.

        Single source of truth for Save gating.
        Must work even when some events/signals are missed (offscreen tests,
        programmatic setText, etc.).
        """
        # Read current UI fields (authoritative)
        try:
            jy, hz, mn, cat = self._read_add_fields()
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

        # Ensure state reflects readiness (READY_TO_SAVE should make the inline Save button enabled when visible)
        try:
            if ready:
                self._add_edit_state = AddEditState.READY_TO_SAVE
                # Treat any non-empty Hanzi as committed for Save gating.
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

        # Locate Save button (canonical)
        btn = getattr(self, "btn_save", None)

        if btn is None:
            if QPushButton is not None:
                try:
                    # Common objectNames
                    for obj_name in ("btnSave", "btn_save", "buttonSave", "saveButton"):
                        b = self.findChild(QPushButton, obj_name)
                        if b is not None:
                            btn = b
                            break
                except (TypeError, AttributeError, RuntimeError):
                    pass

        # --- Fallback enablement (regression guard) ---
        # If the fields are plainly valid, do not allow a missed signal/ctx flag to keep Save disabled.
        try:
            btn = getattr(self, "btn_save", None)
        except Exception:
            btn = None

        if btn is not None:
            try:
                jy2, hz2, mn2, cat2 = self._read_add_fields()
            except Exception:
                jy2 = hz2 = mn2 = cat2 = ""

            jy2s = str(jy2 or "").strip()
            hz2s = str(hz2 or "").strip()
            mn2s = str(mn2 or "").strip()
            cat2s = str(cat2 or "").strip()

            try:
                cat2ok = bool(cat2s) and str(cat2s).lower() not in ("unassigned", "all")
            except Exception:
                cat2ok = False

            try:
                if jy2s and hz2s and mn2s and cat2ok and not bool(getattr(self, "_saving_now", False)):
                    btn.setEnabled(True)
            except Exception:
                pass

        # Apply enabled state
        if btn is not None:
            try:
                btn.setEnabled(bool(ready))
            except (TypeError, AttributeError, RuntimeError):
                pass
            try:
                btn.setDefault(bool(ready))
                btn.setAutoDefault(bool(ready))
            except (TypeError, AttributeError, RuntimeError):
                pass

    # ---- Add/Edit UI wiring ----
    def _setup_add_edit_ui(self) -> None:
        """Wire Add or Edit widgets for Enter/validation.

        Rules:
          - Meaning Enter triggers the Save/Edit/Cancel confirmation flow.
          - The legacy inline Save button is hidden by default and only shown
            when the user chooses 'Edit' from the confirmation dialog.

        Notes:
          - Use UniqueConnection where available (via _connect_unique).
          - Wiring is idempotent via _add_edit_wired to avoid duplicate connects.
        """

        if bool(getattr(self, "_add_edit_wired", False)):
            return

        try:
            # --- Hide legacy inline Save by default ---
            try:
                self._set_save_button_visible(False)
            except (TypeError, AttributeError, RuntimeError):
                pass

            fn_gate = getattr(self, "_update_save_enabled", None)

            # --- Jyutping wiring ---
            w_jy = getattr(self, "_add_jy", None)
            fn_jy_enter = getattr(self, "_on_jyut_enter", None)
            try:
                self._wire_line_edit_common(
                    w_jy,
                    on_enter=fn_jy_enter,
                    on_change=fn_gate,
                )
            except (TypeError, AttributeError, RuntimeError):
                pass

            # Reset dependent fields only on genuine user edits (not programmatic setText)
            try:
                fn_reset = getattr(self, "_on_add_jy_user_edited", None)
                if w_jy is not None and callable(fn_reset):
                    self._try_connect(getattr(w_jy, "textEdited", None), fn_reset)
            except (TypeError, AttributeError, RuntimeError):
                pass

            # --- Meaning wiring ---
            w_mn = getattr(self, "_add_mn", None)
            fn_mn_enter = getattr(self, "_on_meaning_enter_committed", None)
            try:
                self._wire_line_edit_common(
                    w_mn,
                    on_enter=fn_mn_enter,
                    on_change=fn_gate,
                )
            except (TypeError, AttributeError, RuntimeError):
                pass

            # --- Category wiring ---
            w_cat = getattr(self, "_add_cat", None)

            # Ensure editable (required for new category entry)
            try:
                if w_cat is not None and hasattr(w_cat, "setEditable"):
                    w_cat.setEditable(True)
            except (TypeError, AttributeError, RuntimeError):
                pass

            # Ensure we have the UI-only controller. It owns Return/Enter wiring and the add-category popup.
            try:
                ctrl = getattr(self, "_cat_combo_ctrl", None)
            except (TypeError, AttributeError, RuntimeError):
                ctrl = None

            if ctrl is None:
                try:
                    from ui.category_combo import CategoryComboController
                except Exception:
                    CategoryComboController = None

                try:
                    if CategoryComboController is not None and w_cat is not None:
                        self._cat_combo_ctrl = CategoryComboController(
                            combo=w_cat,
                            on_commit=(lambda: self._on_add_category_committed(user_action=True)),
                            on_add_new=None,
                        )
                    else:
                        self._cat_combo_ctrl = None
                except Exception:
                    self._cat_combo_ctrl = None

            # Save gating can observe changes; must not commit or move focus.
            try:
                self._wire_combo_common(w_cat, on_change=fn_gate)
            except (TypeError, AttributeError, RuntimeError):
                pass

            # Commit only when the user explicitly selects from popup (activated).
            fn_cat_commit = getattr(self, "_on_add_category_committed", None)
            if w_cat is not None and callable(fn_cat_commit):
                try:
                    sig = getattr(w_cat, "activated", None)
                    if sig is not None:
                        try:
                            sig_int = sig[int] if hasattr(sig, "__getitem__") else sig
                            self._try_connect(sig_int, fn_cat_commit)
                        except (TypeError, AttributeError, RuntimeError):
                            self._try_connect(sig, fn_cat_commit)
                except (TypeError, AttributeError, RuntimeError):
                    pass

            # --- Hanzi candidate combobox wiring ---
            try:
                combo = getattr(self, "_cand_combo", None)
            except (TypeError, AttributeError, RuntimeError):
                combo = None

            try:
                if combo is not None:
                    self._cand_combo_ctrl = CandidateComboController(combo)
                else:
                    self._cand_combo_ctrl = None
            except (TypeError, AttributeError, RuntimeError, ImportError):
                self._cand_combo_ctrl = None

            if combo is not None:
                try:
                    fn_pick = getattr(self, "_on_candidate_index_activated", None)
                    if callable(fn_pick):
                        sig = getattr(combo, "currentIndexChanged", None)
                        if sig is not None:
                            try:
                                sig_int = sig[int] if hasattr(sig, "__getitem__") else sig
                                self._try_connect(sig_int, fn_pick)
                            except (TypeError, AttributeError, RuntimeError):
                                self._try_connect(sig, fn_pick)

                        sig2 = getattr(combo, "activated", None)
                        if sig2 is not None:
                            try:
                                sig2_int = sig2[int] if hasattr(sig2, "__getitem__") else sig2
                                self._try_connect(sig2_int, fn_pick)
                            except (TypeError, AttributeError, RuntimeError):
                                self._try_connect(sig2, fn_pick)
                except (TypeError, AttributeError, RuntimeError):
                    pass

            if callable(fn_gate):
                try:
                    _gate = fn_gate  # type-narrow for linters
                    _gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass

        finally:
            self._add_edit_wired = True

        return

    def _reverse_candidates_for_jy(self, jy: str) -> list[tuple[str, str, int]]:
        """Reverse candidate lookup (delegated to candidate pipeline)."""
        return self._candidate_pipeline.reverse_candidates_for_jy(jy)

    def _on_jyut_enter(self) -> None:
        """Commit Jyutping entry (delegated to flow controller)."""
        self._add_edit_flow.on_jyut_enter()

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

    def _set_notes(self, text: str, *, source: str = "") -> None:
        """Set the Notes field (best-effort; never raises)."""
        try:
            w = getattr(self, "_add_notes", None)
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


    def _on_candidate_index_activated(self, *args) -> None:
        """Handle candidate selection (delegated to flow controller)."""
        self._add_edit_flow.on_candidate_index_activated(*args)

    def _on_candidate_text_changed(self, text: str) -> None:
        """Handle candidate text change (delegated to flow controller)."""
        self._add_edit_flow.on_candidate_text_changed(text)

    def _refresh_table(self) -> None:
        """Refresh vocabulary table display."""
        if self._vocab_table_ctrl is not None:
            try:
                self._vocab_table_ctrl.refresh_from_data()
            except (TypeError, AttributeError, RuntimeError):
                pass
        else:
            # Fallback: legacy rebuild if controller not available
            try:
                fn = getattr(self, "_rebuild_items_model", None)
                if callable(fn):
                    fn()
            except (TypeError, AttributeError, RuntimeError):
                pass

    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        if self._vocab_table_ctrl is not None:
            try:
                self._vocab_table_ctrl.set_search_filter(text)
            except (TypeError, AttributeError, RuntimeError):
                pass

    # ---- Widget accessor helpers ----
    # Note: Widget access is handled via ui.widget_utils.WidgetAccessor utility methods
    # throughout this class (get_text, set_text, focus, set_visible, etc.)