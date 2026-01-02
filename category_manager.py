# -----------------------------------------------------------------------------
# Developer note: Single Meaning Resolver Rule
#
# The UI must NEVER:
#   - call pipeline gloss resolvers directly
#   - call CC-Canto / CEDICT helpers
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
import re
import time

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
# PySide6 imports
# ----------------------------------------
from PySide6.QtCore import Qt, QModelIndex, QTimer as _CatTimer
from PySide6.QtGui import (QFont)
from PySide6.QtWidgets import (
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
)

# ----------------------------------------
# Domain imports
# ----------------------------------------
from domain.category_rules import (
    ambiguity_note,
    HanziStyleIndex,
    CandidateCurator,
    abbr_for_source,
)

from domain.hanzi_candidate_pipeline import HanziCandidatePipeline, build_pipeline_from_category_manager
from domain.jyutping_validation import validate_jyut_syllables
from domain.meaning_sources import default_facade
from domain.storage_paths import categories_yaml_path
from domain.duplicate_rules import is_duplicate_jy
from domain.add_edit_sm import Event, EventPayload, reduce, AddEditState, AddEditContext

from infra.paths import project_root

from ui.focus_policy import should_steal_focus
from ui.category_combo import CategoryComboController

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


# -------------------------
# Typed widget accessors
# -------------------------

def _hz_edit(self) -> QLineEdit | None:
    w = getattr(self, "_add_hz", None)
    return w if isinstance(w, QLineEdit) else None

def _mn_edit(self) -> QLineEdit | None:
    w = getattr(self, "_add_mn", None)
    return w if isinstance(w, QLineEdit) else None

def _jy_edit(self) -> QLineEdit | None:
    w = getattr(self, "_add_jy", None)
    return w if isinstance(w, QLineEdit) else None

def _cat_combo(self) -> QComboBox | None:
    w = getattr(self, "_add_cat", None)
    return w if isinstance(w, QComboBox) else None

def _cand_combo(self) -> QComboBox | None:
    w = getattr(self, "_cand_combo", None)
    return w if isinstance(w, QComboBox) else None

def _notes_edit(self) -> QTextEdit | None:
    w = getattr(self, "_add_notes", None)
    return w if isinstance(w, QTextEdit) else None

def _save_button(self) -> QPushButton | None:
    w = getattr(self, "btn_save", None)
    return w if isinstance(w, QPushButton) else None


class CategoryManagerDialog(QDialog):
    # ------------------------------
    # Init helpers (non-UI)
    # ------------------------------

    def _init_session_state(self) -> None:
        """Initialise flags/caches used across the dialog lifecycle."""
        self._save_pending = False
        self._saving_now = False
        # --- internal edit/session flags (used by combo-change handlers) ---
        self._row_was_unassigned = {}  # hanzi_key -> bool
        self._resort_in_progress = False  # guard to avoid recursive resorting
        self._resort_pending = False  # queue a resort post-change when selection settles
        # Ensure optional dictionaries exist before any loader touches them
        self._rev_manual = {}
        self._cedict = {}
        # Forward-declare candidate combo for type checkers
        self._cand_combo: QComboBox | None = None
        self._cand_gloss_cache = {}
        # Sticky manual-entry mode: when the user chooses to type their own Hanzi,
        # we must not overwrite it with any later auto-fill.
        self._manual_hanzi_mode = False
        self._cat_combo_ctrl = None

    def _init_style_and_curator(self) -> None:
        """Initialise UI-free helpers used for style and candidate curation."""
        try:
            _project_dir = str(project_root())
        except (AttributeError, TypeError, ValueError, RuntimeError):
            _project_dir = os.getcwd()

        self._style_index = HanziStyleIndex(_project_dir)
        self._candidate_curator = CandidateCurator(self._style_index, self.MAX_HANZI_CANDIDATES)

    def _init_vocab_and_categories(self, vocab_items: dict, categories_map: dict) -> None:
        """Normalise in-memory vocab + categories and build the stable category list."""

        # In-memory vocab & categories (shallow copies to avoid mutating callers)
        self._vocab = {
            k: (
                list(v[0]) if isinstance(v, (list, tuple)) and v else [],
                v[1] if isinstance(v, (list, tuple)) and len(v) > 1 else "",
            )
            for k, v in (vocab_items or {}).items()
        }

        self._cats = {
            str(k).strip(): list(v or [])
            for k, v in (categories_map or {}).items()
            if str(k).strip()
        }

        # Drop sentinel 'All' if it is the only category
        if len(self._cats) <= 1:
            for k in list(self._cats):
                if k.lower() == "all":
                    self._cats.pop(k, None)

        # Stable categories list: exclude 'All'
        self._all_cats = sorted(
            (k for k in self._cats if k.lower() != "all"),
            key=lambda s: s.lower(),
        )

        # Ensure 'unassigned' exists
        if "unassigned" not in (c.lower() for c in self._all_cats):
            self._all_cats.append("unassigned")
            self._all_cats.sort(key=lambda s: s.lower())

        # Diagnostics (logging should never break logic)
        logger.debug(
            "AddItem: _cats keys (n=%d): %s",
            len(self._cats),
            sorted(self._cats.keys()),
        )
        logger.debug(
            "AddItem: _all_cats (n=%d): %s",
            len(self._all_cats),
            self._all_cats,
        )

    def _reload_categories_from_disk_if_needed(self) -> None:
        """If categories input is effectively empty, attempt a one-time reload from disk."""

        if len(self._all_cats) <= 1:
            try:
                cat_path = categories_yaml_path()
                if cat_path.exists():
                    with cat_path.open("r", encoding="utf-8") as fh:
                        raw = yaml.safe_load(fh) or {}
            except (OSError, yaml.YAMLError) as e:
                logger.warning("Failed to reload categories from disk: %s", e)
            else:
                if isinstance(raw, dict):
                    keys = [
                        str(k).strip()
                        for k in raw.keys()
                        if str(k).strip() and str(k).lower() != "all"
                    ]
                    if keys:
                        self._all_cats = sorted(
                            set(keys + ["unassigned"]),
                            key=lambda s: s.lower(),
                        )
                        logger.debug(
                            "AddItem: categories reloaded from %s -> %d keys",
                            cat_path,
                            len(self._all_cats),
                        )

        # Final safety: ensure 'unassigned' always exists
        if "unassigned" not in (c.lower() for c in self._all_cats):
            self._all_cats.append("unassigned")
            self._all_cats.sort(key=lambda s: s.lower())

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

    def _init_reverse_lookup_caches(self) -> None:
        parent = getattr(self, "_parent", None)

        # Tier 1: reverse index
        reverse_index = getattr(parent, "_reverse_index", None) if parent is not None else None
        if not isinstance(reverse_index, dict):
            reverse_index = {}
        self._reverse_index = reverse_index

        src = "parent" if parent is not None and isinstance(getattr(parent, "_reverse_index", None), dict) else "empty"
        try:
            size = len(self._reverse_index)
        except TypeError:
            size = 0

        try:
            logger.debug("CacheAudit: reverse_index source=%s size=%d", src, int(size))
        except (TypeError, ValueError):
            # Logging must not interfere with UI startup.
            pass

        # Tier 2: shared Unihan char map
        char_map = getattr(parent, "_char_map", None) if parent is not None else None
        if not isinstance(char_map, dict):
            char_map = {}
        self._char_map = char_map

        # Best-effort: share back to parent so other dialogs can reuse it.
        if parent is not None:
            try:
                setattr(parent, "_char_map", self._char_map)
            except (AttributeError, TypeError):
                pass


    def _init_hanzi_pipeline(self) -> None:
        # Preferred: domain-level factory that reads what it needs from the dialog.
        try:
            self._hanzi_pipeline = build_pipeline_from_category_manager(self)
            return
        except (ImportError, OSError, AttributeError, TypeError, ValueError, RuntimeError) as e:
            logger.warning(
                "HanziCandidatePipeline factory failed; falling back to minimal pipeline: %s",
                e,
            )

        # Always provide a minimal pipeline so call sites never need to guard against None.
        try:
            self._hanzi_pipeline = HanziCandidatePipeline(normalize_jyutping=self._normalize_jy)
        except (AttributeError, TypeError, ValueError, RuntimeError):
            # Last-ditch: keep attribute present even if something is badly wrong.
            self._hanzi_pipeline = HanziCandidatePipeline(
                normalize_jyutping=lambda s: " ".join((s or "").strip().lower().split())
            )

    def _init_meaning_resolver(self) -> None:
        """Initialise the meaning resolver (optional)."""
        self._meaning_facade = None
        try:
            self._meaning_facade = default_facade()
        except (ImportError, OSError, AttributeError, TypeError, ValueError, RuntimeError) as e:
            logger.warning("Meaning facade init failed: %s", e)
            self._meaning_facade = None

        try:
            logger.debug(
                "MeaningFacade init: ok=%s type=%s",
                bool(self._meaning_facade is not None),
                type(self._meaning_facade).__name__ if self._meaning_facade is not None else "None",
            )
        except (TypeError, ValueError):
            # Logging must not interfere with UI startup.
            pass

    def _init_optional_category_profiles(self) -> None:
        """Build optional category semantic profiles from existing vocab."""
        if not isinstance(getattr(self, "_cat_keywords", None), dict):
            self._cat_keywords = {}

        if isinstance(getattr(self, "_vocab", None), dict) and isinstance(getattr(self, "_cats", None), dict):
            builder = getattr(self, "_build_category_profiles", None)
            if callable(builder):
                try:
                    builder()
                except (AttributeError, TypeError, ValueError, RuntimeError):
                    # Optional enrichment must not block UI.
                    self._cat_keywords = {}

    def _validate_jyut_syllables(self, jy: str) -> tuple[bool, str | None]:
        try:
            return validate_jyut_syllables(jy)
        except Exception as e:
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
      5. If exactly one candidate, Hanzi and meanings are auto-filled and focus moves to Meanings.
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
    _HANZI_TEXT_DELTA_PT = 4        # Hanzi QLineEdit (main display)
    _HANZI_COMBO_DELTA_PT = 6       # Hanzi candidate combobox + popup
    # Typography deltas for the Add/Edit panel (dialog-local; do not affect the rest of the app)
    _LABEL_FONT_DELTA_PT = 4
    _INPUT_FONT_DELTA_PT = 3
    _FORM_VERTICAL_SPACING_PX = 12

    def __init__(self, parent, vocab_items: dict, categories_map: dict):
        super().__init__(parent)
        self._parent = parent
        self._init_session_state()

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

        # ---- Data / caches (must not raise) ----
        self._init_style_and_curator()
        self._init_vocab_and_categories(vocab_items, categories_map)
        self._reload_categories_from_disk_if_needed()
        self._init_reverse_lookup_caches()
        self._init_meaning_resolver()
        self._init_hanzi_pipeline()
        self._init_optional_category_profiles()

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
        header.addWidget(btn_close, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self._root.addLayout(header)

        # ---- Main row ----
        row = QHBoxLayout()
        row.setSpacing(12)

        # ---- Save header ----
        header_row = QHBoxLayout()
        self.btn_save = QPushButton("Save")
        self.btn_save.clicked.connect(self._on_save_clicked)
        self.btn_save.setDefault(False)
        self.btn_save.setAutoDefault(False)
        self.btn_save.setEnabled(False)
        self.btn_save.setToolTip("Save Hanzi + Jyutping + Category")
        header_row.addStretch(1)
        header_row.addWidget(self.btn_save, 0, Qt.AlignmentFlag.AlignRight)
        self._root.addLayout(header_row)

        # ---- Entry group ----
        group_entry = QGroupBox("Entry", self)
        form_entry = QFormLayout(group_entry)
        form_entry.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form_entry.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
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
            le_cat.returnPressed.connect(self._on_add_category_committed)
            le_cat.editingFinished.connect(self._on_add_category_committed)

        self._cat_combo_ctrl = CategoryComboController(
            combo=self._add_cat,
            on_commit=self._on_add_category_committed,
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
        self._cand_combo.setMinimumWidth(240)
        self._cand_combo.setMaximumWidth(320)
        self._cand_combo.setToolTip(HANZI_CANDIDATE_TOOLTIP)
        if self._cand_combo.view() is not None:
            self._cand_combo.view().setToolTip(HANZI_CANDIDATE_TOOLTIP)

        form_hanzi.addRow("Candidates:", self._cand_combo)

        self._btn_custom_hz = QPushButton("Enter my own Hanzi", self)
        self._btn_custom_hz.setDefault(False)
        self._btn_custom_hz.setAutoDefault(False)
        self._btn_custom_hz.clicked.connect(self._on_custom_hanzi_clicked)
        form_hanzi.addWidget(self._btn_custom_hz)

        self.comboCandidates = self._cand_combo

        self._cand_combo.activated.connect(self._on_candidate_index_activated)
        self._cand_combo.currentTextChanged.connect(self._on_candidate_text_changed)

        # ---- Layout assembly ----
        group_entry.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        group_hanzi.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(group_entry)
        row.addWidget(group_hanzi)
        self._root.addLayout(row)

        # ---- Typography ----
        self._apply_add_edit_typography(
            group_entry=group_entry,
            form_entry=form_entry,
            group_hanzi=group_hanzi,
            form_hanzi=form_hanzi,
        )

        # ---- Search ----
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Search (Hanzi / Jyutping / meaning)…")
        self._search.setClearButtonEnabled(True)
        if callable(getattr(self, "_on_search_changed", None)):
            self._search.textChanged.connect(self._on_search_changed)
        self._root.addWidget(self._search)

        # ---- Table ----
        self._table = QTableWidget(self)
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Hanzi", "Jyutping", "Meanings", "Categories"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._root.addWidget(self._table, 1)

        if callable(getattr(self, "_rebuild_items_model", None)):
            self._rebuild_items_model()

        # ---- Wiring ----
        if callable(getattr(self, "_on_jyut_enter", None)):
            self._add_jy.returnPressed.connect(self._on_jyut_enter)
            if callable(getattr(self, "_update_save_enabled", None)):
                self._add_jy.editingFinished.connect(self._update_save_enabled)

        self._add_mn.returnPressed.connect(self._on_meanings_enter)

        if callable(getattr(self, "_update_save_enabled", None)):
            # Save gating is SM-only; render Save state when SM transitions are applied.
            # Keep this method available for explicit refreshes only (e.g., after effects).
            pass

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

    def _apply_add_edit_typography(
            self,
            *,
            group_entry: QGroupBox,
            form_entry: QFormLayout,
            group_hanzi: QGroupBox,
            form_hanzi: QFormLayout,
    ) -> None:
        """Apply Add/Edit panel typography in one place.

        - Labels: +_LABEL_FONT_DELTA_PT
        - Input fields (Jyutping, Meanings, Hanzi): +_INPUT_FONT_DELTA_PT
        - Form vertical spacing: _FORM_VERTICAL_SPACING_PX

        Best-effort only: this must never break dialog construction.
        """
        # Spacing first (Qt may raise TypeError on some bindings)
        try:
            form_entry.setVerticalSpacing(int(self._FORM_VERTICAL_SPACING_PX))
        except (TypeError, ValueError, AttributeError):
            pass
        try:
            form_hanzi.setVerticalSpacing(int(self._FORM_VERTICAL_SPACING_PX))
        except (TypeError, ValueError, AttributeError):
            pass

        base_entry = group_entry.font()
        base_hanzi = group_hanzi.font()

        label_entry = QFont(base_entry)
        label_entry.setPointSize(label_entry.pointSize() + int(self._LABEL_FONT_DELTA_PT))

        label_hanzi = QFont(base_hanzi)
        label_hanzi.setPointSize(label_hanzi.pointSize() + int(self._LABEL_FONT_DELTA_PT))

        input_entry = QFont(base_entry)
        input_entry.setPointSize(input_entry.pointSize() + int(self._INPUT_FONT_DELTA_PT))

        input_hanzi = QFont(base_hanzi)
        input_hanzi.setPointSize(
            input_hanzi.pointSize()
            + int(self._INPUT_FONT_DELTA_PT)
            + int(self._HANZI_TEXT_DELTA_PT)
        )

        # Apply label fonts via the QFormLayout label column
        for _r in range(form_entry.rowCount()):
            _it = form_entry.itemAt(_r, QFormLayout.ItemRole.LabelRole)
            _w = _it.widget() if _it is not None else None
            if isinstance(_w, QLabel):
                try:
                    _w.setFont(label_entry)
                except (RuntimeError, TypeError, AttributeError):
                    pass

        for _r in range(form_hanzi.rowCount()):
            _it = form_hanzi.itemAt(_r, QFormLayout.ItemRole.LabelRole)
            _w = _it.widget() if _it is not None else None
            if isinstance(_w, QLabel):
                try:
                    _w.setFont(label_hanzi)
                except (RuntimeError, TypeError, AttributeError):
                    pass

        # Apply input font bumps ONLY to the requested Add/Edit inputs
        jy = getattr(self, "_add_jy", None)
        if jy is not None:
            try:
                jy.setFont(input_entry)
            except (RuntimeError, TypeError, AttributeError):
                pass

        mn = getattr(self, "_add_mn", None)
        if mn is not None:
            try:
                mn.setFont(input_entry)
            except (RuntimeError, TypeError, AttributeError):
                pass

        hz = getattr(self, "_add_hz", None)
        if hz is not None:
            try:
                hz.setFont(input_hanzi)
            except (RuntimeError, TypeError, AttributeError):
                pass

        # Hanzi candidate combobox + popup font
        combo = getattr(self, "_cand_combo", None)
        if combo is not None:
            combo_font = QFont(input_hanzi)
            combo_font.setPointSize(combo_font.pointSize() + int(self._HANZI_COMBO_DELTA_PT))
            try:
                combo.setFont(combo_font)
            except (RuntimeError, TypeError, AttributeError):
                pass
            try:
                view = combo.view()
            except (RuntimeError, AttributeError):
                view = None
            if view is not None:
                try:
                    view.setFont(combo_font)
                except (RuntimeError, TypeError, AttributeError):
                    pass

    def _load_hanzi_style_map(self) -> dict:
        """Lazy-load data/hanzi_style.yaml (Hanzi -> {style, source, notes}).

        Back-compat wrapper around the internal _HanziStyleIndex.
        """
        try:
            return self._style_index.load()  # type: ignore[attr-defined]
        except (AttributeError, OSError, TypeError, ValueError, RuntimeError):
            return {}

    def _hanzi_style(self, hanzi: str) -> str:
        """Back-compat wrapper for style lookup."""
        try:
            return self._style_index.style_for(hanzi)  # type: ignore[attr-defined]
        except (AttributeError, OSError, TypeError, ValueError, RuntimeError):
            return "unknown"

    def _is_colloquial_hanzi(self, hanzi: str) -> bool:
        """Back-compat wrapper for colloquial detection."""
        try:
            return self._style_index.is_colloquial(hanzi)  # type: ignore[attr-defined]
        except (AttributeError, OSError, TypeError, ValueError, RuntimeError):
            return False

    def _curate_top_hanzi_candidates(self, ranked: list[str]) -> list[str]:
        """Back-compat wrapper to curate the top candidates for the UI."""
        try:
            return self._candidate_curator.curate(ranked)  # type: ignore[attr-defined]
        except (AttributeError, OSError, TypeError, ValueError, RuntimeError):
            return (ranked or [])[: self.MAX_HANZI_CANDIDATES]

    @staticmethod
    def _focus_line_edit(le, *, select_all: bool = True) -> None:
        """Best-effort focus helper for QLineEdit-like widgets."""
        if le is None:
            return

        try:
            le.setFocus()
        except (RuntimeError, AttributeError, TypeError):
            return

        if select_all:
            try:
                le.selectAll()
            except (RuntimeError, AttributeError, TypeError):
                pass

    def _focus_jyutping(self, *, select_all: bool = True) -> None:
        self._focus_line_edit(getattr(self, "_add_jy", None), select_all=select_all)

    def _focus_meanings(self, *, select_all: bool = True) -> None:
        self._focus_line_edit(getattr(self, "_add_mn", None), select_all=select_all)

    def _focus_hanzi(self, *, select_all: bool = True) -> None:
        self._focus_line_edit(getattr(self, "_add_hz", None), select_all=select_all)

    def _focus_category(self, *, select_all: bool = True, show_popup: bool = False) -> None:
        ctrl = getattr(self, "_cat_combo_ctrl", None)
        if ctrl is not None:
            ctrl.focus(select_all=select_all, show_popup=show_popup)

    # ---- UI intent / focus policy ----
    def _user_has_committed_hanzi(self) -> bool:
        return bool(getattr(self, "_hanzi_committed", False))

    def _user_is_in_manual_hanzi_mode(self) -> bool:
        return bool(getattr(self, "_manual_hanzi_mode", False))

    def _mark_hanzi_committed(self, committed: bool = True) -> None:
        self._hanzi_committed = bool(committed)

    def _mark_manual_hanzi_mode(self, enabled: bool = True) -> None:
        self._manual_hanzi_mode = bool(enabled)

    def _apply_focus_policy(
        self,
        *,
        target: str,
        reason: str = "",
        user_action: bool = False,
        show_popup: bool = False,
        select_all: bool = True,
    ) -> None:
        """Apply a focus move if permitted by policy.

        target: 'jy' | 'hz' | 'mn' | 'cat'

        IMPORTANT:
            This method must never recurse. It only dispatches to the concrete
            focus helpers.
        """
        # Delegate to pure focus policy (no Qt imports in policy module).
        combo = getattr(self, "_cand_combo", None)

        try:
            _combo_hf = getattr(combo, "hasFocus", None)
            combo_has_focus = bool(combo is not None and callable(_combo_hf) and _combo_hf())
        except (AttributeError, RuntimeError, TypeError):
            combo_has_focus = False

        try:
            view = combo.view() if combo is not None else None
        except (AttributeError, RuntimeError, TypeError):
            view = None

        try:
            _view_hf = getattr(view, "hasFocus", None)
            view_has_focus = bool(view is not None and callable(_view_hf) and _view_hf())
        except (AttributeError, RuntimeError, TypeError):
            view_has_focus = False

        manual_mode = bool(getattr(self, "_manual_hanzi_mode", False))
        hanzi_committed = bool(getattr(self, "_hanzi_committed", False))

        # Support both the keyword-rich and minimal positional policy signatures.
        try:
            allowed = bool(
                should_steal_focus(
                    reason=reason,
                    user_action=bool(user_action),
                    manual_mode=manual_mode,
                    hanzi_committed=hanzi_committed,
                    combo_has_focus=combo_has_focus,
                    view_has_focus=view_has_focus,
                )
            )
        except TypeError:
            # Positional fallback: (user_action, combo_has_focus, view_has_focus, manual_mode, hanzi_committed)
            try:
                allowed = bool(
                    should_steal_focus(
                        bool(user_action),
                        bool(combo_has_focus),
                        bool(view_has_focus),
                        bool(manual_mode),
                        bool(hanzi_committed),
                    )
                )
            except (AttributeError, RuntimeError, TypeError, ValueError):
                allowed = False
        except (AttributeError, RuntimeError, TypeError, ValueError):
            allowed = False

        if not allowed:
            return

        if target == "jy":
            self._focus_jyutping(select_all=select_all)
            return
        if target == "hz":
            self._focus_hanzi(select_all=select_all)
            return
        if target == "mn":
            self._focus_meanings(select_all=select_all)
            return
        if target == "cat":
            self._focus_category(select_all=select_all, show_popup=show_popup)
            return

        # Unknown target: no-op (conservative)
        return

    def _resolve_meanings_for_candidate(
            self,
            hz: str,
            src: str = "",
            *,
            preferred: bool = False,
            max_items: int = 2,
            allow_pipeline: bool = False,
    ) -> list[str]:
        """Single meaning-resolution path for the UI.

        Rule: all meaning resolution shown in this dialog must flow through this method.

        Authoritative source:
          1) MeaningFacade.select_candidate(...).meanings

        Fallback:
          2) MeaningFacade.meanings_for_display(hanzi)

        Display cleaning (applied exactly once here):
          - strip whitespace
          - drop empty entries
          - prefer entries without '[' or '(' (but fall back to original list if that removes everything)
          - cap to `max_items`

        NOTE:
            UI must not call pipeline gloss resolvers directly.
            Any pipeline involvement must be encapsulated inside the facade.
        """
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

    def _read_add_fields(self) -> tuple[str, str, str, str]:
        """Read Add/Edit panel fields safely.

        Returns:
            (jyutping, hanzi, meanings, category)
        """
        jy = ""
        hz = ""
        mn = ""
        cat = ""

        w_jy = getattr(self, "_add_jy", None)
        if w_jy is not None:
            try:
                jy = (w_jy.text() or "").strip()
            except (AttributeError, RuntimeError, TypeError):
                jy = ""

        w_hz = getattr(self, "_add_hz", None)
        if w_hz is not None:
            try:
                hz = (w_hz.text() or "").strip()
            except (AttributeError, RuntimeError, TypeError):
                hz = ""

        w_mn = getattr(self, "_add_mn", None)
        if w_mn is not None:
            try:
                mn = (w_mn.text() or "").strip()
            except (AttributeError, RuntimeError, TypeError):
                mn = ""

        w_cat = getattr(self, "_add_cat", None)
        if w_cat is not None:
            try:
                cat = (w_cat.currentText() or "").strip()
            except (AttributeError, RuntimeError, TypeError):
                cat = ""

        return jy, hz, mn, cat


    # ---- Add & Edit: Jyutping validation + reverse lookup wiring ----
    def _normalize_jy(self, s: str) -> str:
        text = (s or "").strip().lower()
        # Collapse runs of whitespace to single spaces.
        return " ".join(text.split())

    def _warn_duplicate_jy_and_reset(self, jy: str) -> None:
        """Warn that Jyutping already exists, clear the field, and keep focus on Jyutping."""
        try:
            QMessageBox.warning(
                self,
                "Duplicate Jyutping",
                "The Jyutping \u201c{}\u201d already exists in your vocabulary.\n\nPlease enter a different Jyutping.".format(jy),
            )
        except (TypeError, AttributeError, RuntimeError):
            # If the message box cannot be shown (headless / shutdown), continue with field reset.
            pass

        w_jy = getattr(self, "_add_jy", None)
        if w_jy is not None:
            try:
                w_jy.clear()
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Central focus helper already handles best-effort fallbacks.
        self._focus_jyutping(select_all=False)

    def _update_save_enabled(self) -> None:
        """
        Render Save enabled/disabled from the Add/Edit state machine.

        Single source of truth:
            Save is enabled iff the SM reports READY_TO_SAVE.
        """
        enabled = False
        state = getattr(self, "_add_edit_state", None)
        try:
            enabled = state is not None and state.name == "READY_TO_SAVE"
        except (AttributeError, RuntimeError, TypeError):
            enabled = False

        btn = getattr(self, "btn_save", None)

        if btn is not None:
            try:
                btn.setEnabled(bool(enabled))
            except RuntimeError:
                pass
        logger.debug(
                "SaveEnabled(SM)=%s state=%r",
                enabled,
                getattr(state, "name", state),
            )

    def _set_notes(self, text: str, source: str = "auto-default") -> None:
        """
        Set notes text safely.

        Rules:
          - auto-default → notes are suppressed
          - curated/domain → notes allowed (read-only)
        """
        notes = getattr(self, "_add_notes", None)
        if notes is None:
            return

        try:
            if not text or source == "auto-default":
                notes.clear()
                notes.setReadOnly(True)
                return

            notes.setReadOnly(False)
            notes.setText(text)
            notes.setReadOnly(True)
        except RuntimeError:
            # Widget already destroyed
            return

    def _meanings_for_hanzi(self, hanzi: str) -> list[str]:
        hz = (hanzi or "").strip()
        if not hz:
            return []

        facade = getattr(self, "_meaning_facade", None)
        if facade is None:
            return []

        t0 = self._perf_start("MeaningFacade.meanings_for_display")
        try:
            raw = facade.meanings_for_display(hz) or []
            out = [str(x).strip() for x in raw if str(x).strip()]
        except (AttributeError, TypeError, RuntimeError) as e:
            logger.debug("MeaningFacade.meanings_for_display failed for %r: %s", hz, e)
            out = []
        finally:
            self._perf_end("MeaningFacade.meanings_for_display", t0)

        if not out:
            return []

        preferred = [g for g in out if "[" not in g and "(" not in g]
        return preferred if preferred else out

    def _build_category_profiles(self) -> None:
        """
        Build lightweight token-frequency profiles per category from existing vocab meanings.

        Populates self._cat_keywords as:
            {category_name: {token: weight, ...}, ...}
        """
        if not isinstance(self._cats, dict) or not isinstance(self._vocab, dict):
            self._cat_keywords = {}
            return

        token_re = re.compile(r"[a-z]+")
        self._cat_keywords = {}

        for cat, hanzi_list in self._cats.items():
            if not hanzi_list:
                continue

            weights: dict[str, float] = {}
            total = 0.0

            for hz in hanzi_list:
                v = self._vocab.get(hz)
                if not v:
                    continue

                meanings = v[0] if isinstance(v, (list, tuple)) else []
                for g in meanings:
                    for tok in token_re.findall(str(g).lower()):
                        weights[tok] = weights.get(tok, 0.0) + 1.0
                        total += 1.0

            if not weights or total <= 0.0:
                continue

            for t in weights:
                weights[t] = weights[t] / total

            self._cat_keywords[str(cat)] = weights

        logger.debug("Category profiles built for %d categories", len(self._cat_keywords))

    def _meaning_preview_for_hz(self, hz: str, max_items: int = 1) -> str:
        """Return a short, UI-safe meaning preview for a Hanzi (comma-separated).

        Used only for compact candidate labels; does not change domain logic.
        """
        try:
            hz_s = (hz or "").strip()
        except (AttributeError, TypeError):
            hz_s = ""
        if not hz_s:
            return ""

        try:
            glosses = self._meanings_for_hanzi(hz_s) or []
        except (AttributeError, TypeError, RuntimeError):
            glosses = []

        try:
            out = [str(g).strip() for g in glosses if str(g).strip()]
        except (TypeError, AttributeError):
            out = []

        if not out:
            return ""

        try:
            n = int(max_items or 1)
        except (TypeError, ValueError):
            n = 1

        if n < 1:
            n = 1

        try:
            return "; ".join([s.strip() for s in out[:n] if s.strip()])
        except (TypeError, ValueError):
            try:
                return str(out[0])
            except (IndexError, TypeError):
                return ""

    def _populate_candidate_combobox(
            self,
            cands: list[tuple[str, str, int]],
            preferred_hz: str | None,
    ) -> None:
        """Populate the Hanzi candidates combobox with UI-ready labels.

        Dialog remains orchestration-only:
          - meaning resolution + cleaning + formatting is delegated to MeaningFacade.
        """
        try:
            self._cand_combo.blockSignals(True)
            self._cand_combo.clear()
        except (AttributeError, RuntimeError, TypeError):
            return

        if not cands:
            try:
                self._cand_combo.setVisible(False)
            except (AttributeError, RuntimeError, TypeError):
                pass
            try:
                self._cand_combo.blockSignals(False)
            except (AttributeError, RuntimeError, TypeError):
                pass
            return

        facade = getattr(self, "_meaning_facade", None)

        try:
            self._cand_combo.clear()
            placeholder = "— choose a Hanzi —"
            self._cand_combo.addItem(placeholder)
            try:
                m = self._cand_combo.model()
                if m is not None:
                    m.setData(m.index(0, 0), 0, int(Qt.ItemDataRole.UserRole) - 1)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass

            # Debug: confirm incoming candidate shape before we populate UI
            try:
                _sample_in = []
                for _i, (_hz, _src, _sc) in enumerate((cands or [])[:5], start=1):
                    _sample_in.append((_i, str(_hz), str(_src), int(round(float(_sc or 0.0)))))
                logger.debug("PopulateComboAudit: sample_in=%r", _sample_in)
            except (AttributeError, RuntimeError, TypeError):
                pass

            for hz, src, _freq in (cands or []):
                hz_s = (hz or "").strip()
                if not hz_s:
                    continue

                preferred = bool(preferred_hz and hz_s == preferred_hz)

                label = ""
                selected = None
                selected_meanings = []

                # Preferred path: ask the façade to resolve + format the candidate.
                # This keeps the dialog orchestration-only (no direct candidate_label calls).
                if facade is not None and hasattr(facade, "select_candidate"):
                    try:
                        selected = facade.select_candidate(
                            hz_s,
                            src,
                            preferred=preferred,
                            max_items=2,
                        )
                        if selected is not None and hasattr(selected, "label"):
                            label = str(getattr(selected, "label") or "").strip()

                        # Prefer meanings returned by the façade (already resolved/cleaned for display).
                        if selected is not None and hasattr(selected, "meanings"):
                            try:
                                selected_meanings = list(getattr(selected, "meanings") or [])
                            except (AttributeError, TypeError, ValueError, RuntimeError):
                                selected_meanings = []
                    except (AttributeError, TypeError, ValueError, RuntimeError):
                        label = ""
                        selected = None
                        selected_meanings = []


                if not label:
                    # Final fallback: Hanzi + friendly source label
                    try:
                        friendly = FRIENDLY_SOURCE_LABELS.get(src, abbr_for_source(src))
                    except (AttributeError, TypeError, ValueError):
                        friendly = abbr_for_source(src)
                    label = "{} ({})".format(hz_s, friendly)
                    if preferred:
                        label = "✓ {}".format(label)

                # Ensure the combobox shows a brief meaning preview (historical behaviour).
                # Source of truth: the single resolver path.
                preview = ""
                try:
                    meanings_src = self._resolve_meanings_for_candidate(
                        hz_s,
                        src,
                        preferred=preferred,
                        max_items=2,
                        allow_pipeline=False,
                    )
                    if meanings_src:
                        preview = ", ".join([s for s in meanings_src if s])
                except (AttributeError, TypeError, ValueError, RuntimeError):
                    preview = ""
                # Hard cap preview length to prevent the combobox from becoming unreadable.
                try:
                    if isinstance(preview, str) and len(preview) > 80:
                        preview = preview[:77].rstrip() + "…"
                except (TypeError, ValueError):
                    pass

                if preview:
                    # Avoid duplicating if the label already contains a preview separator.
                    try:
                        if " — " not in label:
                            if label.endswith(")") and " (" in label:
                                i = label.rfind(" (")
                                if i > 0:
                                    label = "{} — {}{}".format(label[:i], preview, label[i:])
                                else:
                                    label = "{} — {}".format(label, preview)
                            else:
                                label = "{} — {}".format(label, preview)
                    except (AttributeError, TypeError, ValueError):
                        pass

                # Store (hz, src) so selection handler has source context if needed later
                try:
                    logger.debug("ComboLabelAudit: hz=%r final_label=%r", hz_s, label)
                except (TypeError, ValueError):
                    pass
                self._cand_combo.addItem(label, userData=(hz_s, src))

                # Debug: verify userData shape being stored
                try:
                    if self._cand_combo.count() <= 4:  # only log the first few to avoid noise
                        logger.debug(
                            "PopulateComboAudit: row=%d label=%r userData=%r",
                            self._cand_combo.count() - 1,
                            label,
                            (hz_s, src),
                        )
                except (AttributeError, TypeError, ValueError, RuntimeError):
                    pass

            self._cand_combo.setCurrentIndex(0)
            self._cand_combo.setVisible(True)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass
        finally:
            try:
                self._cand_combo.blockSignals(False)
            except (AttributeError, RuntimeError, TypeError):
                pass

    def _handle_no_hanzi_candidates(self) -> int:
        """UI path when no candidates exist: expose manual Hanzi entry and disable candidate UI."""
        try:
            self._manual_hanzi_mode = False
            for btn_name in ("btn_custom_hanzi", "btn_enter_hanzi", "btn_hanzi_custom"):
                btn = getattr(self, btn_name, None)
                if btn is not None:
                    btn.setVisible(True)
                    break
        except (AttributeError, RuntimeError, TypeError):
            pass

        try:
            logger.debug("AddItem: no candidates; showing custom Hanzi entry option")
        except (TypeError, ValueError):
            pass

        try:
            if getattr(self, "_add_hz", None) is not None:
                self._add_hz.setReadOnly(False)
                try:
                    self._add_hz.setPlaceholderText("Type Hanzi (or paste)")
                except (AttributeError, RuntimeError, TypeError):
                    pass
                self._add_hz.clear()
                self._add_hz.setFocus()
        except (AttributeError, RuntimeError, TypeError):
            pass

        try:
            if getattr(self, "_cand_combo", None) is not None:
                self._cand_combo.setVisible(False)
        except (AttributeError, RuntimeError, TypeError):
            pass

        try:
            if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                self._update_save_enabled()
        except (AttributeError, RuntimeError, TypeError):
            pass

        return 0

    def _set_hanzi_top_candidate(self, cands: list[tuple[str, str, int]]) -> str | None:
        """Set Hanzi edit to the top candidate and return the preferred Hanzi.

        UI-orchestration only. Meaning resolution must flow through
        `_resolve_meanings_for_candidate(...)` (facade-owned), not direct pipeline calls.
        """
        preferred_hz: str | None = None
        preferred_src = ""

        if isinstance(cands, list) and cands:
            try:
                preferred_hz = str(cands[0][0] or "").strip()
            except (IndexError, TypeError, ValueError):
                preferred_hz = None
            try:
                preferred_src = str(cands[0][1] or "").strip()
            except (IndexError, TypeError, ValueError):
                preferred_src = ""

        if not preferred_hz:
            return None

        # Auto-fill does not represent explicit user intent.
        try:
            self._mark_manual_hanzi_mode(False)
        except (AttributeError, RuntimeError, TypeError):
            pass
        try:
            self._mark_hanzi_committed(False)
        except (AttributeError, RuntimeError, TypeError):
            pass

        # Apply preferred Hanzi to the UI
        hz_edit = getattr(self, "_add_hz", None)

        if hz_edit is not None:
            try:
                hz_edit.setText(preferred_hz)
                try:
                    hz_edit.setReadOnly(True)
                except (AttributeError, RuntimeError, TypeError):
                    pass
            except (AttributeError, RuntimeError, TypeError):
                pass

        # If meanings are empty, try to auto-fill via the single resolver path.
        mn_edit = getattr(self, "_add_mn", None)

        try:
            mn_existing = (mn_edit.text() or "").strip() if mn_edit is not None else ""
        except (AttributeError, RuntimeError, TypeError):
            mn_existing = ""

        if mn_edit is not None and not mn_existing:
            meanings: list[str] = []
            try:
                meanings = self._resolve_meanings_for_candidate(
                    preferred_hz,
                    preferred_src,
                    preferred=True,
                    max_items=2,
                    allow_pipeline=False,
                )
            except (AttributeError, RuntimeError, TypeError, ValueError):
                meanings = []

            try:
                if meanings:
                    mn_edit.setText(", ".join([str(x).strip() for x in meanings if str(x).strip()]))
                else:
                    mn_edit.setPlaceholderText("Enter English meaning")
            except (AttributeError, RuntimeError, TypeError):
                pass

        return preferred_hz

    def _clear_candidate_view_highlight(self) -> None:
        try:
            v = self._cand_combo.view()
            if v is not None:
                v.setCurrentIndex(QModelIndex())
        except (AttributeError, RuntimeError, TypeError):
            pass

    def _maybe_autofill_single_candidate_meanings(self, cands: list[tuple[str, str, int]]) -> None:
        """If there is exactly one candidate, populate meanings (best-effort) without stealing focus."""
        if not (isinstance(cands, list) and len(cands) == 1):
            return

        single_hz = None
        try:
            single_hz = cands[0][0]
        except (IndexError, TypeError):
            single_hz = None

        if not single_hz:
            return

        # Auto-fill is not an explicit user commitment.
        try:
            self._mark_manual_hanzi_mode(False)
        except (AttributeError, RuntimeError, TypeError):
            pass
        try:
            self._mark_hanzi_committed(False)
        except (AttributeError, RuntimeError, TypeError):
            pass

        hz_edit = getattr(self, "_add_hz", None)
        if hz_edit is not None:
            try:
                hz_edit.setText(single_hz)
            except (AttributeError, RuntimeError, TypeError):
                pass

        # Meanings are resolved via the MeaningFacade (single source of truth)
        glosses_single = self._resolve_meanings_for_candidate(
            single_hz,
            "",
            preferred=True,
            max_items=2,
            allow_pipeline=False,
        )

        mn_edit = getattr(self, "_add_mn", None)
        if mn_edit is not None:
            try:
                mn_edit.setText(", ".join(glosses_single) if glosses_single else "")
            except (AttributeError, RuntimeError, TypeError):
                pass

        try:
            self._apply_focus_policy(target="mn", reason="single_candidate_autofill", user_action=False)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

        try:
            if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                self._update_save_enabled()
        except (AttributeError, RuntimeError, TypeError):
            pass

        try:
            logger.debug(
                "AddItem: auto-filled meanings for single candidate '%s' -> %r",
                single_hz,
                (glosses_single[:3] if glosses_single else []),
            )
        except (TypeError, ValueError):
            pass

    def _apply_selected_candidate(self, index: int | None = None) -> None:
        combo = getattr(self, "_cand_combo", None)
        if combo is None:
            return

        try:
            idx = combo.currentIndex() if index is None else int(index)
        except (TypeError, ValueError):
            idx = combo.currentIndex()

        if idx <= 0:
            return

        try:
            data = combo.itemData(idx)
        except (RuntimeError, AttributeError):
            return

        logger.debug(
            "CandidateSelectAudit: idx=%d text=%r itemData_type=%s itemData=%r",
            idx,
            combo.currentText(),
            type(data).__name__,
            data,
        )

        hz = ""
        src = ""

        if isinstance(data, (tuple, list)) and len(data) >= 2:
            hz = str(data[0] or "").strip()
            src = str(data[1] or "").strip()
        elif isinstance(data, str):
            hz = data.strip()

        if not hz:
            return

        self._manual_hanzi_mode = False

        # Candidate controller owns user-action inference
        user_action = False
        try:
            ctrl = (
                    getattr(self, "_candidate_controller", None)
                    or getattr(self, "_cand_controller", None)
                    or getattr(self, "_cand_combo_controller", None)
            )
            if ctrl is not None:
                if hasattr(ctrl, "is_user_action"):
                    user_action = bool(ctrl.is_user_action(combo, index))
                elif hasattr(ctrl, "infer_user_action"):
                    user_action = bool(ctrl.infer_user_action(combo, index))
                elif hasattr(ctrl, "user_action"):
                    user_action = bool(ctrl.user_action(combo, index))
                else:
                    user_action = bool(index is not None)
            else:
                user_action = bool(index is not None)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            user_action = bool(index is not None)

        if user_action:
            self._mark_manual_hanzi_mode(True)
            self._mark_hanzi_committed(True)

        hz_edit = getattr(self, "_add_hz", None)
        if hz_edit is not None:
            try:
                hz_edit.setReadOnly(True)
                hz_edit.setText(hz)
            except (RuntimeError, AttributeError):
                pass

        try:
            meanings = self._resolve_meanings_for_candidate(
                hz,
                src,
                preferred=False,
                max_items=2,
                allow_pipeline=False,
            )
        except (RuntimeError, AttributeError, TypeError):
            meanings = []

        mn_edit = getattr(self, "_add_mn", None)
        if mn_edit is not None:
            try:
                if meanings:
                    mn_edit.setText(", ".join(meanings))
                else:
                    mn_edit.setText("")
                    mn_edit.setPlaceholderText("Enter English meaning")
            except (RuntimeError, AttributeError):
                pass

            self._apply_focus_policy(
                target="mn",
                reason="candidate_selected",
                user_action=user_action,
            )

        if callable(getattr(self, "_update_save_enabled", None)):
            self._update_save_enabled()

    def _apply_ambiguity_notes(self, jy_n: str, n_syllables: int, cands: list[tuple[str, str, int]]) -> None:
        top_glosses: list[str] | None = None

        if isinstance(cands, list) and cands:
            top_hz = cands[0][0]
            if isinstance(top_hz, str) and top_hz.strip():
                try:
                    top_glosses = self._meanings_for_hanzi(top_hz)
                except (RuntimeError, AttributeError, TypeError):
                    top_glosses = None

        try:
            note = ambiguity_note(jy_n, n_syllables, cands, top_glosses)
        except (TypeError, ValueError):
            note = None

        note = locals().get("note")
        if note:
            self._set_notes(note, source="domain")
        else:
            self._set_notes("", source="domain")

    def _update_hanzi_tooltip_preview(self, cands: list[tuple[str, str, int]]) -> None:
        hz_edit = getattr(self, "_add_hz", None)
        if hz_edit is None:
            return

        if not cands:
            try:
                hz_edit.setToolTip("No candidates found")
            except (RuntimeError, AttributeError):
                pass
            return

        preview_parts: list[str] = []
        for hz, _src, _freq in cands[:6]:
            try:
                ms = self._meanings_for_hanzi(hz)
                if ms:
                    preview_parts.append(f"{hz} — {', '.join(ms[:2])}")
                else:
                    preview_parts.append(hz)
            except (RuntimeError, AttributeError, TypeError):
                preview_parts.append(hz)

        try:
            hz_edit.setToolTip(", ".join(preview_parts))
        except (RuntimeError, AttributeError):
            pass

    def _make_sm_event(self, event_enum, value=None):
        try:
            return EventPayload(event=event_enum, value=value)
        except TypeError:
            return {"event": event_enum, "value": value}

    def _fill_hanzi_candidates(self, jy: str) -> int:
        """Populate Hanzi candidates for the given Jyutping.

        UI-orchestration only. All candidate generation/ranking lives in:
          - domain.hanzi_candidate_pipeline
          - domain.category_rules
        """
        jy_n = ""
        try:
            jy_n = self._normalize_jy(jy)
            # --- Reverse-index diagnostics (Tier-1) ---
            try:
                _ri = getattr(self, "_reverse_index", None)
                _ri_sz = len(_ri) if isinstance(_ri, dict) else -1
                _has_key = bool(isinstance(_ri, dict) and jy_n in _ri)
                _sample = []
                if _has_key:
                    try:
                        _sample = list((_ri.get(jy_n) or [])[:5])
                    except (AttributeError, TypeError, ValueError):
                        _sample = []
                logger.debug(
                    "ReverseIndexAudit: jy=%r present=%s size=%s sample=%r",
                    jy_n,
                    _has_key,
                    _ri_sz,
                    _sample,
                )
            except (AttributeError, RuntimeError, TypeError):
                pass

            # Tier-1: reverse index is authoritative when present.
            tier1: list[tuple[str, str, float]] = []
            try:
                _ri = getattr(self, "_reverse_index", None)
                if isinstance(_ri, dict):
                    for _hz, _src, _sc in (_ri.get(jy_n) or []):
                        hz_s = (str(_hz) or "").strip()
                        if not hz_s:
                            continue
                        try:
                            sc_f = float(_sc)
                        except (TypeError, ValueError):
                            sc_f = 0.0
                        src_s = (str(_src) or "").strip() or "reverse"
                        tier1.append((hz_s, src_s, sc_f))
            except (AttributeError, TypeError, ValueError):
                tier1 = []

            # Tier-2: pipeline can augment Tier-1, but must never displace it.
            pipeline = getattr(self, "_hanzi_pipeline", None)
            tier2: list[tuple[str, str, float]] = []

            _t_run = self._perf_start("HanziCandidatePipeline.run")
            if pipeline is not None:
                try:
                    raw = pipeline.run(jy_n) or []
                    tier2 = [(str(hz or "").strip(), str(src or "").strip(), float(freq or 0.0)) for (hz, src, freq) in list(raw)]
                    tier2 = [(hz, src or "tier2", sc) for (hz, src, sc) in tier2 if hz]
                except (AttributeError, TypeError, ValueError) as e:
                    try:
                        logger.warning("Hanzi pipeline failed for %r: %s", jy_n, e)
                    except (TypeError, ValueError):
                        pass
                    tier2 = []
            self._perf_end("HanziCandidatePipeline.run", _t_run)

            # Merge (dedupe by hanzi) with Tier-1 priority.
            # If a Hanzi exists in Tier-1, keep the Tier-1 source and the higher score.
            merged: dict[str, tuple[str, float, int]] = {}
            # order index preserves stable ordering when scores tie
            _order = 0
            for (hz, src, sc) in (tier1 or []):
                _order += 1
                prev = merged.get(hz)
                if prev is None:
                    merged[hz] = (src, float(sc or 0.0), _order)
                else:
                    p_src, p_sc, p_ord = prev
                    merged[hz] = (src, max(float(sc or 0.0), float(p_sc or 0.0)), min(p_ord, _order))

            for (hz, src, sc) in (tier2 or []):
                if not hz:
                    continue
                _order += 1
                prev = merged.get(hz)
                if prev is None:
                    merged[hz] = (src, float(sc or 0.0), _order)
                else:
                    # If Tier-1 already supplied this Hanzi, do not replace its source.
                    p_src, p_sc, p_ord = prev
                    keep_src = p_src
                    merged[hz] = (keep_src, max(float(sc or 0.0), float(p_sc or 0.0)), min(p_ord, _order))

            cands = [(hz, merged[hz][0], merged[hz][1]) for hz in merged.keys()]
            # Sort: score desc, then stable insertion order.
            try:
                cands.sort(key=lambda t: (-float(t[2] or 0.0), int(merged.get(t[0], ("", 0.0, 0))[2])))
            except (TypeError, ValueError):
                pass

            # Cap to a sane UI maximum
            try:
                max_n = int(getattr(self, "MAX_HANZI_CANDIDATES", 10) or 10)
            except (AttributeError, TypeError, ValueError):
                max_n = 10
            if isinstance(cands, list) and max_n > 0:
                cands = cands[:max_n]

            # Extra debug: confirm Tier-1 presence and whether Tier-2 was suppressed.
            try:
                if tier1:
                    logger.debug("CandidateMergeAudit: jy=%r tier1_n=%d tier2_n=%d merged_n=%d top=%r", jy_n, len(tier1), len(tier2), len(cands), (cands[0] if cands else None))
            except (TypeError, ValueError):
                pass
            try:
                logger.debug("CacheAudit: candidates n=%d for jy=%r", len(cands), jy_n)
                # --- Candidate ranking diagnostics (post-pipeline) ---
                try:
                    _top = []
                    for _i, (_hz, _src, _sc) in enumerate((cands or [])[:10], start=1):
                        _top.append((_i, str(_hz), str(_src), float(_sc)))
                    logger.debug("CandidateAudit: jy=%r top10=%r", jy_n, _top)
                    if cands:
                        try:
                            _score0 = float(cands[0][2] or 0.0)
                            _tie_n = sum(1 for _c in (cands or []) if abs(float(_c[2] or 0.0) - _score0) < 1e-9)
                            logger.debug("CandidateAudit: jy=%r top_score=%.6f tie_count=%d", jy_n, _score0, _tie_n)
                        except (TypeError, ValueError):
                            pass
                except (TypeError, ValueError):
                    pass
            except ():
                pass

            # No candidates → manual Hanzi affordance
            if not cands:
                return self._handle_no_hanzi_candidates()

            # Set top candidate into Hanzi field
            preferred_hz = self._set_hanzi_top_candidate(cands)  # type: ignore[arg-type]
            try:
                if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                    self._update_save_enabled()
            except (AttributeError, RuntimeError, TypeError):
                pass
            try:
                if preferred_hz:
                    logger.debug("TopCandidateAudit: preferred_hz=%r src=%r score=%r", cands[0][0], cands[0][1],
                                 cands[0][2])
            except (TypeError, ValueError):
                pass

            # Populate candidate dropdown
            self._populate_candidate_combobox(cands, preferred_hz)  # type: ignore[arg-type]

            # Clear any pre-highlight in combobox view
            self._clear_candidate_view_highlight()

            # If exactly one candidate, auto-fill meanings
            self._maybe_autofill_single_candidate_meanings(cands)  # type: ignore[arg-type]

            # Apply ambiguity notes via domain rules
            try:
                n_syllables = len(jy_n.split()) if jy_n else 0
                self._apply_ambiguity_notes(jy_n, n_syllables, cands)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass

            # Tooltip preview for quick glance
            self._update_hanzi_tooltip_preview(cands)  # type: ignore[arg-type]

            # Nudge UI to repaint immediately
            try:
                hz_widget = getattr(self, "_add_hz", None)
                if hz_widget is not None:
                    hz_widget.repaint()
                    hz_widget.update()
            except (AttributeError, RuntimeError, TypeError):
                pass

            return len(cands)

        except Exception as e:
            # Defensive: keep UI consistent even on unexpected failure
            logger.exception("_fill_hanzi_candidates failed for %r: %s", jy_n or jy, e)

            hz_widget = getattr(self, "_add_hz", None)
            if hz_widget is not None:
                hz_widget.clear()
                hz_widget.setToolTip("")
            combo = getattr(self, "_cand_combo", None)
            if combo is not None:
                combo.setVisible(False)

            return 0

    def _on_custom_hanzi_clicked(self):
        """Allow the user to reject all suggestions and type their own Hanzi.

        When invoked:
          - Hide and clear the candidates combobox.
          - Make the Hanzi field editable.
          - Clear any previous Hanzi text (only the first time).
          - Move keyboard focus into the Hanzi field so the user can type or paste.
          - Refresh Save button state to reflect the new (empty) Hanzi value.
        """
        try:
            logger.debug("AddItem: user invoked custom Hanzi entry (None of these).")
        except (TypeError, ValueError):
            pass

        # These are pure Python state flips; they should not raise under normal conditions.
        # Keep defensive guards narrow.
        try:
            self._mark_manual_hanzi_mode(True)
            self._mark_hanzi_committed(True)  # user explicitly chose to take over Hanzi selection
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

        # Manual Hanzi entry is not yet a committed choice until user confirms.
        try:
            self._hanzi_committed = False
        except (AttributeError, TypeError):
            pass

        # Track first entry into manual mode so repeated clicks don't wipe user input
        try:
            if not hasattr(self, "_manual_hanzi_started"):
                self._manual_hanzi_started = False
        except (AttributeError, TypeError):
            pass

        # Hide and clear the candidates combobox so we are no longer in
        # "suggested candidates" mode.
        cand_combo = getattr(self, "_cand_combo", None)
        if cand_combo is not None:
            try:
                cand_combo.blockSignals(True)
                try:
                    cand_combo.clear()
                    cand_combo.setVisible(False)
                finally:
                    cand_combo.blockSignals(False)
            except (AttributeError, RuntimeError, TypeError):
                pass

        # Allow direct editing of the Hanzi field and move focus there.
        hz_edit = getattr(self, "_add_hz", None)
        if hz_edit is not None:
            try:
                hz_edit.setReadOnly(False)
            except (AttributeError, RuntimeError, TypeError):
                pass
            try:
                hz_edit.setPlaceholderText("Type Hanzi (or paste)")
            except (AttributeError, RuntimeError, TypeError):
                pass

            # Only clear Hanzi the first time we enter manual mode.
            if not bool(getattr(self, "_manual_hanzi_started", False)):
                try:
                    hz_edit.clear()
                except (AttributeError, RuntimeError, TypeError):
                    pass
                try:
                    self._manual_hanzi_started = True
                except (AttributeError, TypeError):
                    pass

            # Ensure we only connect these signals once; repeated connections cause repeated firing.
            try:
                if not bool(getattr(self, "_manual_hanzi_signals_connected", False)):
                    try:
                        hz_edit.textChanged.connect(self._on_hanzi_manual_text_changed)
                    except (AttributeError, RuntimeError, TypeError):
                        pass
                    try:
                        hz_edit.textChanged.connect(self._maybe_autofill_meanings_from_hz_manual)
                    except (AttributeError, RuntimeError, TypeError):
                        pass
                    self._manual_hanzi_signals_connected = True
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass

            try:
                hz_edit.setFocus()
                hz_edit.selectAll()
            except (AttributeError, RuntimeError, TypeError):
                pass

        # Finally, refresh Save enabled/disabled state so that once the
        # user types Hanzi and meanings, Save will light up.
        try:
            updater = getattr(self, "_update_save_enabled", None)
            if callable(updater):
                updater()
        except (AttributeError, RuntimeError, TypeError):
            pass

    def _on_hanzi_manual_text_changed(self, _text: str) -> None:
        """Route manual Hanzi typing through the Add/Edit state machine.

        This is connected only when the user enters manual Hanzi mode.
        Save gating remains SM-only.
        """
        # Guard: only meaningful in manual Hanzi mode.
        if not bool(getattr(self, "_manual_hanzi_mode", False)):
            return

        jy, hz, mn, cat = self._read_add_fields()

        # Resolve event constant across versions.
        evt_enum = None
        try:
            for name in ("HANZI_CHANGED", "HANZI_EDITED", "HZ_CHANGED", "HZ_EDITED", "HANZI_TYPED"):
                if hasattr(Event, name):
                    evt_enum = getattr(Event, name)
                    break
        except (AttributeError, TypeError):
            evt_enum = None

        # If the SM doesn't define a Hanzi-edit event yet, fall back to a conservative refresh.
        if evt_enum is None:
            try:
                updater = getattr(self, "_update_save_enabled", None)
                if callable(updater):
                    updater()
            except (AttributeError, RuntimeError, TypeError):
                pass
            return

        ctx = AddEditContext(
            jy=jy,
            jy_ok=bool(getattr(getattr(self, "_add_edit_ctx", None), "jy_ok", False)),
            duplicate=getattr(getattr(self, "_add_edit_ctx", None), "duplicate", None),
            hanzi=hz,
            hz_ok=bool(hz),
            manual_hanzi=True,
            meaning=mn,
            mn_ok=bool(mn),
            category=cat,
            cat_ok=bool(cat),
            saving=bool(getattr(self, "_saving_now", False)),
        )

        state = getattr(self, "_add_edit_state", AddEditState.EMPTY)

        try:
            evt = self._make_sm_event(evt_enum, hz)
            new_state, new_ctx, effects = reduce(state, ctx, evt)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            # Never break the UI on SM failure.
            return

        self._add_edit_state = new_state
        self._add_edit_ctx = new_ctx

        for eff in (effects or []):
            try:
                self._apply_add_edit_effect(eff)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass

        try:
            self._update_save_enabled()
        except (AttributeError, RuntimeError, TypeError):
            pass

    def _maybe_autofill_meanings_from_hz_manual(self) -> None:
        """
        When the user types Hanzi in manual mode, try once to populate meanings
        from available sources. If nothing is found, guide the user to enter
        meanings manually.

        Best-effort only: must never overwrite user-entered meanings.
        """
        # Guard: only active in manual Hanzi mode
        if not bool(getattr(self, "_manual_hanzi_mode", False)):
            return

        hz_edit = getattr(self, "_add_hz", None)
        mn_edit = getattr(self, "_add_mn", None)

        if hz_edit is None or mn_edit is None:
            return

        try:
            hz = (hz_edit.text() or "").strip()
        except (AttributeError, RuntimeError, TypeError):
            return

        if not hz:
            return

        # Do not overwrite user-entered meanings
        try:
            if (mn_edit.text() or "").strip():
                return
        except (AttributeError, RuntimeError, TypeError):
            return

        # Attempt to derive meanings via the single façade path
        try:
            glosses = self._meanings_for_hanzi(hz)
        except (AttributeError, RuntimeError, TypeError) as e:
            try:
                logger.debug("Manual Hanzi meaning lookup failed for %r: %s", hz, e)
            except (TypeError, ValueError):
                pass
            glosses = []

        if glosses:
            try:
                mn_edit.setText(", ".join(glosses))
                mn_edit.selectAll()
            except (AttributeError, RuntimeError, TypeError):
                pass
        else:
            # No glosses found: guide the user explicitly
            try:
                mn_edit.setPlaceholderText("Enter English meaning")
                mn_edit.setFocus()
            except (AttributeError, RuntimeError, TypeError):
                pass

        # Route meaning changes through the SM (Save gating is SM-only)
        try:
            self._on_meanings_text_changed(mn_edit.text() if mn_edit is not None else "")
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

    def _on_meanings_text_changed(self, _text: str) -> None:
        """Route meanings edits through the Add/Edit state machine."""
        jy, hz, mn, cat = self._read_add_fields()

        evt_enum = None
        try:
            for name in ("MEANINGS_CHANGED", "MEANING_CHANGED", "MN_CHANGED", "MEANINGS_EDITED", "MEANING_EDITED"):
                if hasattr(Event, name):
                    evt_enum = getattr(Event, name)
                    break
        except (AttributeError, TypeError):
            evt_enum = None

        # If the SM doesn't define a meanings-edit event yet, fall back to a conservative refresh.
        if evt_enum is None:
            try:
                self._update_save_enabled()
            except (AttributeError, RuntimeError, TypeError):
                pass
            return

        ctx = AddEditContext(
            jy=jy,
            jy_ok=bool(getattr(getattr(self, "_add_edit_ctx", None), "jy_ok", False)),
            duplicate=getattr(getattr(self, "_add_edit_ctx", None), "duplicate", None),
            hanzi=hz,
            hz_ok=bool(hz),
            manual_hanzi=bool(getattr(self, "_manual_hanzi_mode", False)),
            meaning=mn,
            mn_ok=bool(mn),
            category=cat,
            cat_ok=bool(cat),
            saving=bool(getattr(self, "_saving_now", False)),
        )

        state = getattr(self, "_add_edit_state", AddEditState.EMPTY)

        try:
            evt = self._make_sm_event(evt_enum, mn)
            new_state, new_ctx, effects = reduce(state, ctx, evt)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return

        self._add_edit_state = new_state
        self._add_edit_ctx = new_ctx

        for eff in (effects or []):
            try:
                self._apply_add_edit_effect(eff)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass

        try:
            self._update_save_enabled()
        except (AttributeError, RuntimeError, TypeError):
            pass

    def _reset_add_panel(self):
        """Clear Add/Edit fields back to initial state and focus Jyutping."""
        try:
            self._manual_hanzi_mode = False
        except (AttributeError, TypeError):
            pass

        try:
            self._manual_hanzi_started = False
        except (AttributeError, TypeError):
            pass

        cand_combo = getattr(self, "_cand_combo", None)
        if cand_combo is not None:
            try:
                cand_combo.blockSignals(True)
                try:
                    cand_combo.clear()
                    cand_combo.setVisible(False)
                finally:
                    cand_combo.blockSignals(False)
            except (AttributeError, RuntimeError, TypeError):
                pass

        hz = getattr(self, "_add_hz", None)
        if hz is not None:
            try:
                hz.clear()
                hz.setToolTip("")
            except (AttributeError, RuntimeError, TypeError):
                pass

        mn = getattr(self, "_add_mn", None)
        if mn is not None:
            try:
                mn.clear()
            except (AttributeError, RuntimeError, TypeError):
                pass

        cat = getattr(self, "_add_cat", None)
        if cat is not None:
            try:
                # No synthetic placeholder category: require the user to pick a real category.
                cat.setCurrentIndex(-1)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass

            # Ensure Enter/Return in the editable category combobox commits the category.
            try:
                le_factory = getattr(cat, "lineEdit", None)
                le_cat = le_factory() if callable(le_factory) else None
                if le_cat is not None and hasattr(le_cat, "returnPressed"):
                    try:
                        le_cat.returnPressed.disconnect()
                    except (AttributeError, RuntimeError, TypeError):
                        pass
                    try:
                        le_cat.returnPressed.connect(self._on_add_category_committed)
                    except (AttributeError, RuntimeError, TypeError):
                        pass
            except (AttributeError, RuntimeError, TypeError):
                pass

        btn = getattr(self, "btn_save", None)
        if btn is not None:
            try:
                btn.setEnabled(False)
                btn.setDefault(False)
                btn.setAutoDefault(False)
            except (AttributeError, RuntimeError, TypeError):
                pass

        jy = getattr(self, "_add_jy", None)
        if jy is not None:
            try:
                jy.setFocus()
            except (AttributeError, RuntimeError, TypeError):
                pass

    def _on_save_clicked(self):
        """
        Gather the Add panel fields and hand them to the commit callback (if any).

        The payload is a simple dict that the main window can interpret and persist:
            {
                "jyutping": <str>,
                "hanzi": <str>,
                "gloss": <str>,
                "categories": [<str>, ...],
            }
        """
        # Re-check that Save should be enabled (defensive)
        try:
            self._update_save_enabled()
        except (AttributeError, RuntimeError, TypeError):
            pass

        cb = getattr(self, "_commit_callback", None)
        if not callable(cb):
            logger.warning(
                "Save clicked but no commit routine was found; please wire to your add/commit method."
            )
            return

        jy, hz, mn, cat = self._read_add_fields()

        # Basic guard: all fields must be present and category must be something real
        if not jy or not hz or not mn:
            logger.debug(
                "Save aborted: missing required fields (jy=%r, hz=%r, mn=%r)", jy, hz, mn
            )
            return
        if not cat or cat.lower() == "all":
            logger.debug("Save aborted: invalid category %r", cat)
            return

        cats = [cat]

        payload = {
            "jyutping": jy,
            "hanzi": hz,
            "gloss": mn,
            "categories": cats,
        }

        try:
            cb(payload)
        except Exception as e:
            logger.warning("Save commit callback failed for %r: %s", payload, e)
            return

        # If commit succeeds, close the dialog.
        try:
            self.accept()
        except (AttributeError, RuntimeError, TypeError):
            pass

    def _on_meanings_enter(self):
        """When user presses Enter in Meanings, move focus to Category."""
        try:
            self._apply_focus_policy(target="cat", reason="legacy_direct_focus", user_action=False, show_popup=False)
        except (AttributeError, RuntimeError, TypeError):
            pass

    def _is_unassigned_category(self) -> bool:
        try:
            txt = (self._add_cat.currentText() or "").strip().lower()
            return txt == "unassigned"
        except (AttributeError, RuntimeError, TypeError):
            return False

    def _on_jyut_enter(self) -> None:
        """
        UI adapter for Jyutping commit.

        Reads UI state, delegates decision-making to domain.add_edit_sm.reduce,
        and applies returned UI effects.
        """
        jy, hz, mn, cat = self._read_add_fields()

        if not (jy or "").strip():
            try:
                self._focus_jyutping(select_all=False)
            except (AttributeError, RuntimeError, TypeError):
                pass
            return

        # Compute domain-backed validation and duplication flags up-front.
        # The SM expects these to be accurate at commit time.
        try:
            jy_ok = bool(self._validate_jyut_syllables(jy))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            jy_ok = False

        try:
            dup = bool(
                is_duplicate_jy(
                    jy,
                    vocab=getattr(self, "_vocab", {}),
                    normalize=getattr(self, "_normalize_jy", None),
                )
            )
        except (AttributeError, TypeError, ValueError):
            dup = False

        # Duplicate Jyutping must be handled immediately (single warning + focus reset).
        # Do not delegate duplicates into the SM; the SM models the "new entry" flow.
        if dup:
            try:
                QMessageBox.warning(
                    self,
                    "Duplicate Jyutping",
                    "That Jyutping already exists in your vocab.\n\n"
                    "Please change the Jyutping (or edit the existing entry instead).",
                )
            except (AttributeError, RuntimeError, TypeError):
                pass
            try:
                self._focus_jyutping(select_all=True)
            except (AttributeError, RuntimeError, TypeError):
                pass
            try:
                updater = getattr(self, "_update_save_enabled", None)
                if callable(updater):
                    updater()
            except (AttributeError, RuntimeError, TypeError):
                pass
            return

        ctx = AddEditContext(
            jy=jy,
            jy_ok=jy_ok,
            duplicate=dup,
            hanzi=hz,
            hz_ok=bool(hz),
            manual_hanzi=bool(getattr(self, "_manual_hanzi_mode", False)),
            meaning=mn,
            mn_ok=bool(mn),
            category=cat,
            cat_ok=bool(cat),
            saving=False,
        )

        # Resolve event constant across versions
        evt_enum = None
        try:
            for name in (
                "JY_COMMIT",
                "JYUTPING_COMMITTED",
                "JY_COMMITTED",
                "JY_ACCEPTED",
                "JY_EDITING",
            ):
                if hasattr(Event, name):
                    evt_enum = getattr(Event, name)
                    break
        except (AttributeError, TypeError):
            # Defensive: Event may not be a proper enum/namespace in some legacy bindings.
            evt_enum = None

        # Guard: if we cannot resolve a state-machine event, fail soft with legacy behaviour
        if evt_enum is None:
            # Non-duplicate: proceed with existing lookup behaviour
            if self._hanzi_committed:
                return

            try:
                if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                    self._update_save_enabled()
            except (AttributeError, RuntimeError, TypeError):
                pass
            return

        # Defensive: ensure state is never None (Save gating relies on a concrete SM state).
        state = getattr(self, "_add_edit_state", None)
        if state is None:
            state = AddEditState.EMPTY

        # Always persist the latest committed Jyutping context, even if the SM adapter fails.
        # This prevents silent regressions where the UI field changes but `_add_edit_ctx` remains EMPTY.
        try:
            self._add_edit_state = state
            self._add_edit_ctx = ctx
        except (AttributeError, TypeError):
            pass

        try:
            evt = self._make_sm_event(evt_enum, jy)
            new_state, new_ctx, effects = reduce(state, ctx, evt)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            # Fail-soft: keep the UI responsive and preserve the committed ctx above.
            try:
                self._focus_jyutping(select_all=True)
            except (AttributeError, RuntimeError, TypeError):
                pass

            # Still apply the expected UX nudge for valid, non-duplicate Jyutping.
            if bool(getattr(ctx, "jy_ok", False)) and not bool(getattr(ctx, "duplicate", False)):
                try:
                    ctrl = getattr(self, "_cat_combo_ctrl", None)
                    if ctrl is not None and hasattr(ctrl, "focus"):
                        self._call_best_effort(ctrl.focus, True)
                    else:
                        self._apply_focus_policy(
                            target="cat",
                            reason="jyutping_committed",
                            user_action=True,
                            show_popup=True,
                            select_all=True,
                        )
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    pass

            try:
                updater = getattr(self, "_update_save_enabled", None)
                if callable(updater):
                    updater()
            except (AttributeError, RuntimeError, TypeError):
                pass
            return

        self._add_edit_state = new_state
        self._add_edit_ctx = new_ctx

        # Defensive: some legacy paths may not emit focus effects; enforce the
        # expected UX nudge for valid, non-duplicate Jyutping.
        if bool(getattr(new_ctx, "jy_ok", False)) and not bool(getattr(new_ctx, "duplicate", False)):
            try:
                ctrl = getattr(self, "_cat_combo_ctrl", None)
                if ctrl is not None and hasattr(ctrl, "focus"):
                    # Use the controller so tests can spy on the advance signal.
                    self._call_best_effort(ctrl.focus, True)
                else:
                    # Fallback: apply focus policy directly.
                    self._apply_focus_policy(
                        target="cat",
                        reason="jyutping_committed",
                        user_action=True,
                        show_popup=True,
                        select_all=True,
                    )
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass

        for eff in (effects or []):
            try:
                self._apply_add_edit_effect(eff)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass

        # Render Save immediately from SM state (single source of truth)
        updater = getattr(self, "_update_save_enabled", None)
        if callable(updater):
            try:
                updater()
            except (AttributeError, RuntimeError, TypeError):
                pass

    def _on_search_changed(self, _text: str) -> None:
        """Search handler (compat shim)."""
        fn = getattr(self, "_populate_rows", None)
        if callable(fn):
            fn()

    def _rebuild_items_model(self) -> None:
        """Table rebuild hook (compat shim)."""
        fn = getattr(self, "_populate_rows", None)
        if callable(fn):
            fn()

    def _apply_add_edit_effect(self, eff) -> None:
        """Apply a single Add/Edit effect to the UI.

        Effects may be returned either as dict payloads (legacy) or as structured
        objects (newer domain layer). This adapter normalises access.
        """
        if eff is None:
            return

        # Effects may be returned either as dict payloads (legacy) or as structured objects.
        if isinstance(eff, dict):
            etype = eff.get("type")
            jy = eff.get("jy", eff.get("value"))
        else:
            etype = getattr(eff, "type", None)
            jy = getattr(eff, "jy", None) or getattr(eff, "value", None)

        if not etype:
            return

        jy_s = str(jy or "")

        match etype:
            case "warn_duplicate_jy":
                # Safe: method already defensive.
                self._warn_duplicate_jy_and_reset(jy_s)

            case "focus_category":
                self._apply_focus_policy(
                    target="cat",
                    reason="legacy_direct_focus",
                    user_action=False,
                    show_popup=True,
                )

            case "focus_jyutping":
                self._focus_jyutping(select_all=True)

            case "invalidate_hanzi":
                # Pure state flags: no Qt calls.
                self._hanzi_committed = False
                self._manual_hanzi_mode = False

            case "refresh_save":
                self._update_save_enabled()

            case "fill_candidates":
                # Candidate fill is internally defensive/logging.
                self._fill_hanzi_candidates(jy_s)

            case _:
                return

    def _on_add_category_committed(self) -> None:
        """Commit the category from the editable Add-panel combobox.

        This is the handler for Enter/Return on the category line edit.
        It normalises/creates categories and then triggers candidate lookup
        if Jyutping is present and Hanzi is still empty.
        """
        cat_cb = getattr(self, "_add_cat", None)
        if cat_cb is None:
            return

        try:
            text = (cat_cb.currentText() or "").strip()
        except (AttributeError, RuntimeError, TypeError):
            return

        # Require explicit category choice
        if not text:
            try:
                QMessageBox.warning(
                    self,
                    "Category required",
                    "Please choose or type a category for this entry.\n"
                    "If you really cannot decide, you can use ‘unassigned’.",
                )
            except (AttributeError, RuntimeError, TypeError):
                pass

            # Keep focus on the category editor.
            try:
                if getattr(cat_cb, "isEditable", None) and cat_cb.isEditable() and cat_cb.lineEdit():
                    le_cat = cat_cb.lineEdit()
                    le_cat.setFocus()
                    le_cat.selectAll()
                else:
                    cat_cb.setFocus()
            except (AttributeError, RuntimeError, TypeError):
                pass
            return

        # Normalise / reuse / create
        try:
            canon_fn = getattr(self, "_canon_cat_name", None)
            find_fn = getattr(self, "_find_existing_canonical", None)
            if not callable(canon_fn) or not callable(find_fn):
                raise AttributeError("Canonical category helpers not available")

            canon = str(canon_fn(text) or "").strip() or text
            existing = find_fn(canon)

            if existing:
                try:
                    cat_cb.blockSignals(True)
                    try:
                        idx = cat_cb.findText(existing)
                        if idx >= 0:
                            cat_cb.setCurrentIndex(idx)
                        else:
                            cat_cb.setCurrentText(existing)
                    finally:
                        cat_cb.blockSignals(False)
                except (AttributeError, RuntimeError, TypeError):
                    pass
            else:
                is_reserved = getattr(self, "_is_reserved_cat", None)
                if callable(is_reserved) and is_reserved(canon):
                    try:
                        QMessageBox.information(
                            self,
                            "Category",
                            "‘{}’ is a reserved name and cannot be used.".format(canon),
                        )
                    except (AttributeError, RuntimeError, TypeError):
                        pass
                    return

                try:
                    resp = QMessageBox.question(
                        self,
                        "Add Category",
                        "Add new category ‘{}’?".format(canon),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                except (AttributeError, RuntimeError, TypeError):
                    return

                if resp != QMessageBox.StandardButton.Yes:
                    return

                add_new = getattr(self, "_add_new_category", None)
                if callable(add_new):
                    add_new(canon)
                else:
                    cats = getattr(self, "_cats", None)
                    if isinstance(cats, dict) and canon not in cats:
                        cats[canon] = []
                        try:
                            self._all_cats = sorted(set(cats.keys()), key=lambda s: str(s).lower())
                        except (AttributeError, TypeError):
                            self._all_cats = list(cats.keys())

                        try:
                            cat_cb.blockSignals(True)
                            try:
                                cat_cb.clear()
                                cat_cb.addItems(self._all_cats)
                                idx = cat_cb.findText(canon)
                                if idx >= 0:
                                    cat_cb.setCurrentIndex(idx)
                                else:
                                    cat_cb.setCurrentText(canon)
                            finally:
                                cat_cb.blockSignals(False)
                        except (AttributeError, RuntimeError, TypeError):
                            pass
        except (AttributeError, RuntimeError, TypeError):
            # Creation failures should never break the dialog.
            pass

        # After commit, trigger lookup if needed
        jy_txt = ""
        hz_txt = ""

        jy_le = getattr(self, "_add_jy", None)
        if jy_le is not None:
            try:
                jy_txt = (jy_le.text() or "").strip()
            except (AttributeError, RuntimeError, TypeError):
                jy_txt = ""

        hz_le = getattr(self, "_add_hz", None)
        if hz_le is not None:
            try:
                hz_txt = (hz_le.text() or "").strip()
            except (AttributeError, RuntimeError, TypeError):
                hz_txt = ""

        # Category commit must never imply a Hanzi choice.
        # (If a stale `_hanzi_committed` flag is left True, it suppresses candidate fill.)
        try:
            self._hanzi_committed = False
        except (AttributeError, RuntimeError, TypeError):
            pass

        hanzi_committed = bool(getattr(self, "_hanzi_committed", False))

        # Only run lookup if the user has NOT explicitly chosen a Hanzi
        if jy_txt and not hanzi_committed and not hz_txt:
            try:
                _CatTimer.singleShot(0, lambda: self._post_category_fill(jy_txt))
            except (AttributeError, RuntimeError, TypeError):
                # Fallback: run directly if timer is unavailable.
                self._post_category_fill(jy_txt)
            return

        updater = getattr(self, "_update_save_enabled", None)
        if callable(updater):
            try:
                updater()
            except RuntimeError:
                pass

    def _post_category_fill(self, jy_txt: str) -> None:
        """Run reverse lookup after a category has been committed."""
        # Do not steal focus or regenerate candidates after user has committed Hanzi
        if bool(getattr(self, "_hanzi_committed", False)):
            return

        # IMPORTANT: `_fill_hanzi_candidates` normalizes internally.
        # Avoid double-normalisation here (it can change the key shape and break reverse-index hits).
        try:
            n = self._fill_hanzi_candidates(jy_txt)
        except (AttributeError, RuntimeError, TypeError):
            n = 0

        cand_combo = getattr(self, "_cand_combo", None)
        has_candidates = bool(n and n > 0)

        btn_custom = getattr(self, "_btn_custom_hz", None)
        hz_edit = getattr(self, "_add_hz", None)

        try:
            if has_candidates and cand_combo is not None:
                try:
                    cand_combo.setVisible(True)
                    cand_combo.showPopup()
                    cand_combo.setFocus()
                except (AttributeError, RuntimeError, TypeError):
                    pass

                if btn_custom is not None:
                    try:
                        btn_custom.setVisible(False)
                    except (AttributeError, RuntimeError, TypeError):
                        pass
            else:
                if cand_combo is not None:
                    try:
                        cand_combo.blockSignals(True)
                        try:
                            cand_combo.clear()
                            cand_combo.setVisible(False)
                        finally:
                            cand_combo.blockSignals(False)
                    except (AttributeError, RuntimeError, TypeError):
                        pass

                if btn_custom is not None:
                    try:
                        btn_custom.setVisible(True)
                    except (AttributeError, RuntimeError, TypeError):
                        pass

                if hz_edit is not None:
                    try:
                        hz_edit.setFocus()
                        hz_edit.selectAll()
                    except (AttributeError, RuntimeError, TypeError):
                        pass
        finally:
            updater = getattr(self, "_update_save_enabled", None)
            if callable(updater):
                try:
                    updater()
                except RuntimeError:
                    pass

    def _on_candidate_index_activated(self, index: int) -> None:
        """Apply candidate selection triggered by index activation."""
        try:
            self._apply_selected_candidate(index)
        except (RuntimeError, AttributeError, TypeError, ValueError):
            # Best-effort only; UI must remain responsive.
            pass

    def _on_candidate_text_changed(self, _text: str) -> None:
        """Apply candidate selection triggered by text change."""
        try:
            self._apply_selected_candidate(None)
        except (RuntimeError, AttributeError, TypeError):
            pass

    def _call_best_effort(self, fn, *args):
        """Call `fn` with the largest compatible prefix of args.

        Protects against legacy callables with varying signatures.
        """
        if not callable(fn):
            return None

        try:
            import inspect
            sig = inspect.signature(fn)
            params = list(sig.parameters.values())
        except (TypeError, ValueError):
            # Signature introspection failed; fall back to simple call
            try:
                return fn(*args[:1])
            except TypeError:
                return None

        max_n = 0
        for p in params:
            if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                max_n = len(args)
                break
            max_n += 1

        for n in range(min(max_n, len(args)), -1, -1):
            try:
                return fn(*args[:n])
            except TypeError:
                continue

        return None

    def _get_compose_and_rank(self):
        """Return (compose_fn, shortlist_fn) for tier-2 Hanzi candidate generation."""
        try:
            from infra.hanzi_composition import compose_candidates_from_chars as _compose
        except ImportError:
            _compose = None

        try:
            from infra.hanzi_composition import shortlist_candidates as _shortlist
        except ImportError:
            _shortlist = None

        return _compose, _shortlist
