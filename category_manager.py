# ----------------------------------------
# Standard library imports
# ----------------------------------------
import logging
import os
import re
import time
from enum import Enum, auto

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
)

from domain.attestation import is_attested_phrase
# ----------------------------------------
# Domain imports
# ----------------------------------------
from domain.category_rules import (
    ambiguity_note,
    HanziStyleIndex,
    CandidateCurator,
    abbr_for_source,
    attested_or_structural_ok,
)
from domain.hanzi_candidate_pipeline import HanziCandidatePipeline, build_pipeline_from_category_manager
from domain.jyutping_validation import validate_jyut_syllables
from domain.meaning_sources import MeaningFacade, default_facade, clean_glosses_for_display  # type: ignore
from domain.storage_paths import categories_yaml_path
from infra.paths import project_root


logger = logging.getLogger(__name__)


# ------------------------------
# Add/Edit state machine (Qt-free)
# ------------------------------

class AddEditState(Enum):
    """Pure state machine for the Add/Edit panel.

    This enum is intentionally Qt-free so it can be tested in a pure pytest run.
    """

    EMPTY = auto()
    JYUTPING_VALID = auto()
    CANDIDATES_READY = auto()
    HANZI_SELECTED = auto()
    MEANINGS_VALID = auto()
    CATEGORY_SELECTED = auto()
    READY_TO_SAVE = auto()
    SAVING = auto()


def _derive_state(
        *,
        jyutping: str = "",
        jyut_ok: bool | None = None,
        has_candidates: bool | None = None,
        candidates: list | None = None,
        hanzi: str = "",
        meanings: str | list | tuple | None = None,
        category: str = "",
        category_committed: bool | None = None,
        saving: bool | None = None,
        saving_now: bool | None = None,
) -> AddEditState:
    # Saving overrides all other states.
    # Saving overrides everything
    try:
        if bool(saving):
            return AddEditState.SAVING
    except Exception:
        pass

    # Jyutping validity: if a caller supplies `jyut_ok`, treat it as authoritative.
    # Otherwise, fall back to a minimal check (non-empty string). Structural/attestation
    # validation belongs outside this pure function (see `_refresh_add_state()`).
    try:
        jy = str(jyutping or "").strip()
    except Exception:
        jy = ""

    if jyut_ok is None:
        jy_valid = bool(jy)
    else:
        try:
            jy_valid = bool(jyut_ok)
        except Exception:
            jy_valid = False

    if not jy_valid:
        return AddEditState.EMPTY

    # Candidates gate
    if has_candidates is not None:
        try:
            candidates_ready = bool(has_candidates)
        except Exception:
            candidates_ready = False
    else:
        try:
            candidates_ready = bool(candidates)
        except Exception:
            candidates_ready = False

    if not candidates_ready:
        return AddEditState.JYUTPING_VALID

    # Hanzi gate
    try:
        hz = str(hanzi or "").strip()
    except Exception:
        hz = ""

    if not hz:
        return AddEditState.CANDIDATES_READY

    # Meanings gate
    has_meanings = False
    try:
        if isinstance(meanings, str):
            has_meanings = bool((meanings or "").strip())
        elif isinstance(meanings, (list, tuple)):
            has_meanings = any(bool(str(x).strip()) for x in (meanings or []))
        else:
            has_meanings = False
    except Exception:
        has_meanings = False

    if not has_meanings:
        return AddEditState.HANZI_SELECTED

    # Category gate
    try:
        cat = str(category or "").strip()
    except Exception:
        cat = ""

    cat_valid = bool(cat) and (cat.lower() not in ("all",))
    if not cat_valid:
        return AddEditState.MEANINGS_VALID

    # Explicit category commit gate
    try:
        if not bool(category_committed):
            return AddEditState.CATEGORY_SELECTED
    except Exception:
        return AddEditState.CATEGORY_SELECTED

    return AddEditState.READY_TO_SAVE


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
        self._add_state = AddEditState.EMPTY
        self._category_committed = False
        self._last_candidates = []

    def _init_style_and_curator(self) -> None:
        """Initialise UI-free helpers used for style and candidate curation."""
        try:
            _project_dir = str(project_root())
        except Exception:
            _project_dir = os.getcwd()

        self._style_index = HanziStyleIndex(_project_dir)
        self._candidate_curator = CandidateCurator(self._style_index, self.MAX_HANZI_CANDIDATES)

    def _init_vocab_and_categories(self, vocab_items: dict, categories_map: dict) -> None:
        """Normalise in-memory vocab + categories and build the stable category list."""
        # In-memory vocab & categories (make shallow copies to avoid mutating callers)
        self._vocab = {
            k: (
                (list(v[0]) if isinstance(v, (list, tuple)) and v else []),
                (v[1] if isinstance(v, (list, tuple)) and len(v) > 1 else ""),
            )
            for k, v in (vocab_items or {}).items()
        }
        self._cats = {str(k): list(v) for k, v in (categories_map or {}).items()}

        # Normalize category keys and drop sentinel 'All' if present
        try:
            self._cats = {
                str(k).strip(): list(v or [])
                for k, v in self._cats.items()
                if str(k).strip()
            }
            if len(self._cats) <= 1 and any(k.lower() == "all" for k in self._cats):
                self._cats.pop(next(k for k in list(self._cats) if k.lower() == "all"), None)
        except Exception:
            pass

        # Stable categories list: exclude 'All', ensure 'unassigned' exists
        self._all_cats = sorted(
            {k for k in self._cats if str(k).strip() and k.lower() != "all"},
            key=lambda s: s.lower(),
        )

        # Diagnostics for category population
        try:
            logger.debug(f"AddItem: _cats keys (n={len(self._cats)}): {sorted(self._cats.keys())}")
            logger.debug(f"AddItem: _all_cats (n={len(self._all_cats)}): {self._all_cats}")
        except Exception:
            pass

        if "unassigned" not in (c.lower() for c in self._all_cats):
            self._all_cats.append("unassigned")
            self._all_cats = sorted(set(self._all_cats), key=lambda s: s.lower())

    def _reload_categories_from_disk_if_needed(self) -> None:
        """If categories input is effectively empty, attempt a one-time reload from disk."""
        try:
            if len(self._all_cats) <= 1:
                cat_path = categories_yaml_path()
                if cat_path.exists():
                    with cat_path.open("r", encoding="utf-8") as fh:
                        raw = yaml.safe_load(fh) or {}
                    if isinstance(raw, dict):
                        keys = [
                            str(k)
                            for k in raw.keys()
                            if str(k).strip() and str(k).lower() != "all"
                        ]
                        if keys:
                            self._all_cats = sorted(
                                set(keys + ["unassigned"]),
                                key=lambda s: s.lower(),
                            )
                            logger.debug(
                                f"AddItem: categories reloaded from {cat_path} -> {len(self._all_cats)} keys"
                            )
        except Exception:
            pass

        if "unassigned" not in (c.lower() for c in self._all_cats):
            self._all_cats.append("unassigned")
            self._all_cats = sorted(set(self._all_cats), key=lambda s: s.lower())

    def _perf_start(self, name: str) -> float:
        try:
            t0 = time.perf_counter()
            try:
                logger.debug("PERF start: %s", name)
            except Exception:
                pass
            return t0
        except Exception:
            return 0.0

    def _perf_end(self, name: str, t0: float) -> None:
        try:
            if not t0:
                return
            dt_ms = (time.perf_counter() - float(t0)) * 1000.0
            try:
                logger.debug("PERF end: %s (%.1f ms)", name, dt_ms)
            except Exception:
                pass
        except Exception:
            pass

    def _init_reverse_lookup_caches(self) -> None:
        """Initialise reverse-lookup sources (reverse index + Unihan map)."""

        # Reverse lookup caches (Tier 1: reverse index; Tier 2: Unihan char map)
        # Reuse any prebuilt caches from the main window when present
        try:
            self._reverse_index = getattr(self._parent, "_reverse_index", None)
            try:
                src = "parent" if isinstance(getattr(self._parent, "_reverse_index", None), dict) else "empty"
                logger.debug("CacheAudit: reverse_index source=%s size=%d", src, len(self._reverse_index))
            except Exception:
                pass
            if not isinstance(self._reverse_index, dict):
                self._reverse_index = {}
        except Exception:
            self._reverse_index = {}

        # Shared Unihan char map (dict[char] -> [readings...])
        # Dialog remains orchestration-only: reuse a parent-provided cache if present,
        # otherwise leave empty (tier-2 is optional and the domain pipeline can be
        # configured elsewhere to provide this).
        try:
            self._char_map = getattr(self._parent, "_char_map", None)
            if not isinstance(self._char_map, dict):
                self._char_map = {}
            try:
                setattr(self._parent, "_char_map", self._char_map)
            except Exception:
                pass
        except Exception:
            self._char_map = {}

    def _init_hanzi_pipeline(self) -> None:
        """Initialise the HanziCandidatePipeline (single source of candidates).

        PASS 2: pipeline construction is delegated to the domain layer.
        The dialog remains orchestration-only.
        """
        try:
            # Preferred: domain-level factory that reads what it needs from the dialog.
            self._hanzi_pipeline = build_pipeline_from_category_manager(self)
            return
        except Exception as e:
            try:
                logger.warning("HanziCandidatePipeline factory failed; falling back to minimal pipeline: %s", e)
            except Exception:
                pass

        # Always provide a minimal pipeline so call sites never need to guard against None.
        try:
            self._hanzi_pipeline = HanziCandidatePipeline(normalize_jyutping=self._normalize_jy)
        except Exception:
            # Last-ditch: keep attribute present even if something is badly wrong.
            self._hanzi_pipeline = HanziCandidatePipeline(
                normalize_jyutping=lambda s: " ".join((s or "").strip().lower().split()))

    def _init_meaning_resolver(self) -> None:
        """Initialise the meaning resolver (optional)."""
        self._meaning_facade: MeaningFacade | None = None
        try:
            self._meaning_facade = default_facade()
            try:
                logger.debug(
                    "MeaningFacade init: ok=%s type=%s",
                    bool(self._meaning_facade is not None),
                    type(self._meaning_facade).__name__ if self._meaning_facade is not None else "None",
                )
            except Exception:
                pass
        except Exception as e:
            try:
                logger.warning("Meaning facade init failed: %s", e)
            except Exception:
                pass
            self._meaning_facade = None

    def _init_optional_category_profiles(self) -> None:
        """Build optional category semantic profiles from existing vocab."""
        try:
            if not hasattr(self, "_cat_keywords"):
                self._cat_keywords = {}
            if isinstance(self._vocab, dict) and isinstance(self._cats, dict):
                self._build_category_profiles()
        except Exception:
            self._cat_keywords = {}

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

        # Size policy: derive Add/Edit dialog size from the parent "vertical" window, but in landscape.
        # This keeps sizing future-proof if the app's baseline portrait size changes.
        try:
            pw = int(parent.width()) if parent is not None else 0
            ph = int(parent.height()) if parent is not None else 0
        except Exception:
            pw = 0
            ph = 0

        # If parent dimensions are available, force landscape by taking max/min.
        # Otherwise fall back to the intended baseline (720x1280 swapped -> 1280x720).
        if pw > 0 and ph > 0:
            dlg_w = max(pw, ph)
            dlg_h = min(pw, ph)
        else:
            dlg_w = 1280
            dlg_h = 720

        try:
            self.setMinimumSize(dlg_w, dlg_h)
            self.resize(dlg_w, dlg_h)
            logger.debug("CategoryManagerDialog: sized to %dx%d (parent=%dx%d)", dlg_w, dlg_h, pw, ph)
        except Exception:
            pass

        # ---------- Data / caches ----------
        self._init_style_and_curator()
        self._init_vocab_and_categories(vocab_items, categories_map)
        self._reload_categories_from_disk_if_needed()
        self._init_reverse_lookup_caches()
        self._init_meaning_resolver()
        self._init_hanzi_pipeline()
        self._init_optional_category_profiles()

        # ---------- UI skeleton ----------
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(12, 12, 12, 12)
        self._root.setSpacing(10)

        # Top-right Close button (kept above both groups)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addStretch(1)
        btn_close = QPushButton("Close", self)
        try:
            btn_close.setDefault(False)
            btn_close.setAutoDefault(False)
        except Exception:
            pass
        header.addWidget(btn_close, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self._root.addLayout(header)
        btn_close.clicked.connect(self.accept)

        # Row: [ Entry (left) | Hanzi (right) ]
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        row.setStretch(0, 1)
        row.setStretch(1, 1)

        # --- Add Item header with Save button ---
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)

        self.btn_save = QPushButton("Save")
        self.btn_save.clicked.connect(self._on_save_clicked)
        try:
            self.btn_save.setDefault(False)
            self.btn_save.setAutoDefault(False)
        except Exception:
            pass
        self.btn_save.setEnabled(False)  # only enabled when inputs valid
        self.btn_save.setToolTip("Save Hanzi + Jyutping + Category")

        header_row.addStretch(1)
        header_row.addWidget(self.btn_save, 0, Qt.AlignmentFlag.AlignRight)

        self._root.addLayout(header_row)

        # --- Left: Entry group ---
        groupEntry = QGroupBox("Entry", self)
        formEntry = QFormLayout(groupEntry)
        formEntry.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        formEntry.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        formEntry.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        formEntry.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)

        self._add_jy = QLineEdit(groupEntry)
        self._add_jy.setPlaceholderText("e.g. nei5 hou2")
        self._add_jy.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        try:
            self._add_jy.setClearButtonEnabled(True)
        except Exception:
            pass

        self._add_mn = QLineEdit(groupEntry)
        self._add_mn.setPlaceholderText("comma-separated meanings, e.g. hello, hi")
        self._add_mn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        try:
            self._add_mn.setClearButtonEnabled(True)
        except Exception:
            pass

        self._add_notes = QLineEdit(groupEntry)
        self._add_notes.setPlaceholderText("Notes (auto; shown only when ambiguous)")
        self._add_notes.setReadOnly(True)
        self._add_notes.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._add_notes.setToolTip(
            "Shown only when an entry is ambiguous or needs confirmation. "
            "Auto-default entries never keep notes."
        )

        formEntry.addRow("Jyutping:", self._add_jy)
        formEntry.addRow("Meanings:", self._add_mn)
        formEntry.addRow("Notes:", self._add_notes)

        # Category (editable combobox; starts with no selection)
        self._add_cat = QComboBox(groupEntry)
        self._add_cat.setObjectName("comboAddCategories")
        self._add_cat.setEditable(True)  # editable ONLY in Add panel
        self._add_cat.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._add_cat.clear()
        self._add_cat.addItems(self._all_cats)
        # Start with no selected category so the user must explicitly choose one.
        # (This also avoids accidental defaulting to the first category.)
        try:
            self._add_cat.setCurrentIndex(-1)
            if self._add_cat.isEditable() and self._add_cat.lineEdit():
                _le_cat0 = self._add_cat.lineEdit()
                _le_cat0.setText("")
                _le_cat0.setPlaceholderText("None chosen yet — type or choose a category…")
        except Exception:
            pass
        try:
            logger.debug("AddItem: category list populated (n=%d): %s",
                         self._add_cat.count(),
                         [self._add_cat.itemText(i) for i in range(self._add_cat.count())])
        except Exception:
            pass

        # --- enforce sensible popup width and default hidden ---
        try:
            if hasattr(self, "_cand_combo") and self._cand_combo is not None:
                if hasattr(self._cand_combo, "view") and self._cand_combo.view() is not None:
                    self._cand_combo.view().setMinimumWidth(320)
                self._cand_combo.setVisible(False)
        except Exception:
            pass

        # No placeholder "Not yet assigned" is inserted; user must select or type a real category.
        self._add_cat.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        try:
            le = self._add_cat.lineEdit()
            if le:
                le.setPlaceholderText("None chosen yet — type or choose a category…")
                le.setClearButtonEnabled(True)
                le.setToolTip("Select an existing category or type a new one; press Enter to add.")
                # Wire Enter/Return on the editable category line to the commit handler
                try:
                    le.returnPressed.connect(self._on_add_category_committed)
                except Exception:
                    pass
                # On focus-out, just refresh Save state; do not re-run the category commit logic.
                try:
                    if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                        le.editingFinished.connect(self._update_save_enabled)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if self._add_cat.isEditable() and self._add_cat.lineEdit():
                _le_cat = self._add_cat.lineEdit()
                _le_cat.textChanged.connect(self._on_category_dirty)
                _le_cat.editingFinished.connect(self._on_category_committed)

            self._add_cat.activated.connect(self._on_category_committed)
        except Exception:
            pass

        formEntry.addRow("Category:", self._add_cat)

        # ---- Back-compat aliases for legacy code paths ----
        self.editJyut = self._add_jy
        self.editMeanings = self._add_mn

        self.comboCategory = self._add_cat

        # --- Right: Hanzi group (read-only) ---
        groupHanzi = QGroupBox("Hanzi", self)
        formHanzi = QFormLayout(groupHanzi)
        formHanzi.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)

        self._add_hz = QLineEdit(groupHanzi)
        self._add_hz.setReadOnly(True)
        self._add_hz.setPlaceholderText("Auto, after reverse lookup")
        self._add_hz.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        try:
            formHanzi.addRow(self._add_hz)  # span field column (no label)
        except TypeError:
            formHanzi.addRow(QLabel("", groupHanzi), self._add_hz)

        # Candidate dropdown for reverse lookup
        self._cand_combo = QComboBox(groupHanzi)
        self._cand_combo.setObjectName("comboHanziCandidates")
        try:
            if hasattr(QComboBox, "AdjustToContents"):
                self._cand_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        except Exception:
            pass
        self._cand_combo.setVisible(False)
        # Keep the dropdown reasonably wide but allow it to shrink
        self._cand_combo.setMinimumWidth(240)
        self._cand_combo.setMaximumWidth(320)
        # Add shared tooltip for Hanzi candidate combobox and popup view
        self._cand_combo.setToolTip(HANZI_CANDIDATE_TOOLTIP)
        try:
            if self._cand_combo.view() is not None:
                self._cand_combo.view().setToolTip(HANZI_CANDIDATE_TOOLTIP)
        except Exception:
            pass
        try:
            formHanzi.addRow("Candidates:", self._cand_combo)

            # Allow the user to reject all suggestions and type their own Hanzi
            self._btn_custom_hz = QPushButton("Enter my own Hanzi", self)
            self._btn_custom_hz.setObjectName("btnCustomHanzi")
            self._btn_custom_hz.setToolTip("Clear the suggestions and type or paste your own Hanzi.")
            try:
                self._btn_custom_hz.clicked.connect(self._on_custom_hanzi_clicked)
            except Exception:
                # If wiring fails for any reason, the dialog should still be usable.
                pass
            # Never allow this to be the dialog default action (Enter/Return should not trigger it).
            try:
                self._btn_custom_hz.setDefault(False)
                self._btn_custom_hz.setAutoDefault(False)
            except Exception:
                pass
            formHanzi.addWidget(self._btn_custom_hz)
            # Legacy alias after real construction
            self.comboCandidates = self._cand_combo
        except TypeError:
            formHanzi.addRow(QLabel("Candidates:", groupHanzi), self._cand_combo)

        # Connect signals in a way that works across PySide6 variants
        try:
            self._cand_combo.activated.connect(self._on_candidate_index_activated)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            # Also keep text-based updates in sync
            self._cand_combo.currentTextChanged.connect(self._on_candidate_text_changed)  # type: ignore[attr-defined]
        except Exception:
            pass

        # Apply size policies to prevent vertical stacking
        groupEntry.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        groupHanzi.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Typography + spacing (labels already exist at this point)
        try:
            self._apply_add_edit_typography(
                group_entry=groupEntry,
                form_entry=formEntry,
                group_hanzi=groupHanzi,
                form_hanzi=formHanzi,
            )
        except Exception:
            pass

        # Assemble the side-by-side row
        row.addWidget(groupEntry)
        row.addWidget(groupHanzi)
        self._root.addLayout(row)
        try:
            row.setStretch(0, 1)
            row.setStretch(1, 1)
            # Ensure enough horizontal space so the two groups don’t stack
            # (min width now handled by setMinimumSize at dialog level)
            pass
        except Exception:
            pass

        # --- Search (kept above the list) ---
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Search (Hanzi / Jyutping / meaning)…")
        self._search.setClearButtonEnabled(True)
        self._root.addWidget(self._search)

        # Optional: connect search if a filter method exists
        try:
            if hasattr(self, "_on_search_changed"):
                self._search.textChanged.connect(self._on_search_changed)
        except Exception:
            pass

        # --- Editable list area (items + categories column) ---
        # Use a simple table; rows can be rebuilt later by your existing methods.
        self._table = QTableWidget(self)
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Hanzi", "Jyutping", "Meanings", "Categories"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._root.addWidget(self._table, 1)  # stretch to fill

        # If you already have a model-builder, call it; otherwise show empty table safely
        try:
            if hasattr(self, "_rebuild_items_model"):
                self._rebuild_items_model()  # fills self._table
        except Exception:
            pass

        # --- Wiring: Enter on Jyutping / Meanings / Category to add item ---
        if hasattr(self, "_on_jyut_enter") and callable(self._on_jyut_enter):
            # Use Return/Enter on the Jyutping line to trigger the reverse lookup once.
            try:
                self._add_jy.returnPressed.connect(self._on_jyut_enter)  # type: ignore[attr-defined]
            except Exception:
                pass
            # Use focus-out to refresh Save state, but do not re-trigger the lookup.
            try:
                if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                    self._add_jy.editingFinished.connect(self._update_save_enabled)
            except Exception:
                pass

        try:
            self._add_mn.returnPressed.connect(self._on_meanings_enter)
        except Exception:
            pass

        # Keep Save button enabled/disabled live from all relevant fields
        try:
            if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                # Jyutping edits
                self._add_jy.textChanged.connect(self._update_save_enabled)
                # Hanzi edits (allow custom Hanzi entry to influence Save state)
                if getattr(self, "_add_hz", None) is not None:
                    self._add_hz.textChanged.connect(self._update_save_enabled)
                # Meanings edits
                self._add_mn.textChanged.connect(self._update_save_enabled)
                # Candidate selection (Hanzi)
                self._cand_combo.currentIndexChanged.connect(self._update_save_enabled)  # type: ignore[attr-defined]
                self._cand_combo.currentTextChanged.connect(self._update_save_enabled)  # type: ignore[attr-defined]
                # Category edits (editable vs non-editable)
                if self._add_cat.isEditable() and self._add_cat.lineEdit():
                    self._add_cat.lineEdit().textChanged.connect(
                        self._update_save_enabled)  # type: ignore[attr-defined]
                else:
                    self._add_cat.currentTextChanged.connect(self._update_save_enabled)
        except Exception:
            pass

        # Done: dialog is fully constructed and safe even if some helpers are missing
        logger.debug("CategoryManagerDialog: init complete")
        self._perf_end("CategoryManagerDialog.__init__", _t_init)

        try:
            self._refresh_add_state()
        except Exception:
            pass

    def _apply_add_edit_typography(
            self,
            *,
            group_entry: QGroupBox,
            form_entry: QFormLayout,
            group_hanzi: QGroupBox,
            form_hanzi: QFormLayout,
    ) -> None:
        """
        Apply Add/Edit panel typography in one place.

        - Labels: +_LABEL_FONT_DELTA_PT
        - Input fields (Jyutping, Meanings, Hanzi): +_INPUT_FONT_DELTA_PT
        - Form vertical spacing: _FORM_VERTICAL_SPACING_PX
        """
        try:
            # Spacing first
            try:
                form_entry.setVerticalSpacing(int(self._FORM_VERTICAL_SPACING_PX))
            except Exception:
                pass
            try:
                form_hanzi.setVerticalSpacing(int(self._FORM_VERTICAL_SPACING_PX))
            except Exception:
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
                input_hanzi.pointSize() + int(self._INPUT_FONT_DELTA_PT) + int(self._HANZI_TEXT_DELTA_PT)
            )

            # Apply label fonts via the QFormLayout label column
            for _r in range(form_entry.rowCount()):
                _it = form_entry.itemAt(_r, QFormLayout.ItemRole.LabelRole)
                _w = _it.widget() if _it is not None else None
                if isinstance(_w, QLabel):
                    _w.setFont(label_entry)

            for _r in range(form_hanzi.rowCount()):
                _it = form_hanzi.itemAt(_r, QFormLayout.ItemRole.LabelRole)
                _w = _it.widget() if _it is not None else None
                if isinstance(_w, QLabel):
                    _w.setFont(label_hanzi)

            # Apply input font bumps ONLY to the requested Add/Edit inputs
            try:
                if getattr(self, "_add_jy", None) is not None:
                    self._add_jy.setFont(input_entry)
            except Exception:
                pass
            try:
                if getattr(self, "_add_mn", None) is not None:
                    self._add_mn.setFont(input_entry)
            except Exception:
                pass
            try:
                if getattr(self, "_add_hz", None) is not None:
                    self._add_hz.setFont(input_hanzi)
            except Exception:
                pass

            # Hanzi candidate combobox + popup font
            try:
                if getattr(self, "_cand_combo", None) is not None:
                    combo_font = QFont(input_hanzi)
                    combo_font.setPointSize(
                        combo_font.pointSize() + int(self._HANZI_COMBO_DELTA_PT)
                    )
                    self._cand_combo.setFont(combo_font)
                    if self._cand_combo.view() is not None:
                        self._cand_combo.view().setFont(combo_font)
            except Exception:
                pass

        except Exception:
            pass

    def _load_hanzi_style_map(self) -> dict:
        """Lazy-load data/hanzi_style.yaml (Hanzi -> {style, source, notes}).

        Back-compat wrapper around the internal _HanziStyleIndex.
        """
        try:
            return self._style_index.load()  # type: ignore[attr-defined]
        except Exception:
            return {}

    def _hanzi_style(self, hanzi: str) -> str:
        """Back-compat wrapper for style lookup."""
        try:
            return self._style_index.style_for(hanzi)  # type: ignore[attr-defined]
        except Exception:
            return "unknown"

    def _is_colloquial_hanzi(self, hanzi: str) -> bool:
        """Back-compat wrapper for colloquial detection."""
        try:
            return self._style_index.is_colloquial(hanzi)  # type: ignore[attr-defined]
        except Exception:
            return False

    def _curate_top_hanzi_candidates(self, ranked: list[str]) -> list[str]:
        """Back-compat wrapper to curate the top candidates for the UI."""
        try:
            return self._candidate_curator.curate(ranked)  # type: ignore[attr-defined]
        except Exception:
            return (ranked or [])[: self.MAX_HANZI_CANDIDATES]

    # ---- Add & Edit: Jyutping validation + reverse lookup wiring ----
    def _normalize_jy(self, s: str) -> str:
        try:
            return " ".join((s or "").strip().lower().split())
        except Exception:
            return (s or "").strip().lower()

    def _update_save_enabled(self) -> None:
        """State-driven Save gating (single source of truth)."""
        try:
            # Read UI values (best-effort; never raise)
            jy = ""
            hz = ""
            cat = ""
            meanings_list: list[str] = []

            try:
                jy_edit = getattr(self, "_add_jy", None)
                jy = str(jy_edit.text() if jy_edit is not None else "") or ""
            except Exception:
                jy = ""
            jy = jy.strip()

            try:
                hz_edit = getattr(self, "_add_hz", None)
                hz = str(hz_edit.text() if hz_edit is not None else "") or ""
            except Exception:
                hz = ""
            hz = hz.strip()

            # Meanings can be QTextEdit/QPlainTextEdit or QLineEdit depending on wiring
            mn_text = ""
            try:
                mn_edit = getattr(self, "_add_mn", None)
                if mn_edit is not None and hasattr(mn_edit, "toPlainText"):
                    mn_text = str(mn_edit.toPlainText() or "")
                elif mn_edit is not None and hasattr(mn_edit, "text"):
                    mn_text = str(mn_edit.text() or "")
                else:
                    mn_text = ""
            except Exception:
                mn_text = ""

            try:
                parts = [p.strip() for p in (mn_text or "").split(",")]
                meanings_list = [p for p in parts if p]
            except Exception:
                meanings_list = []

            # Category: prefer stored key, fall back to combo text
            try:
                cat = str(getattr(self, "_selected_category", "") or "").strip()
            except Exception:
                cat = ""
            if not cat:
                try:
                    cat_combo = getattr(self, "_cat_combo", None)
                    if cat_combo is not None and hasattr(cat_combo, "currentText"):
                        cat = str(cat_combo.currentText() or "").strip()
                except Exception:
                    cat = ""

            # Candidates object: derive_state only needs “truthy / non-empty” semantics
            try:
                candidates_obj = getattr(self, "_candidates", None)
            except Exception:
                candidates_obj = None

            try:
                saving_flag = bool(getattr(self, "_saving", False))
            except Exception:
                saving_flag = False

            try:
                committed_flag = bool(getattr(self, "_category_committed", False))
            except Exception:
                committed_flag = False

            # Derive and apply
            state = _derive_state(
                jyutping=jy,
                hanzi=hz,
                meanings=meanings_list,
                category=cat,
                candidates=candidates_obj,
                saving=saving_flag,
                category_committed=committed_flag,
            )
            self._set_state(state)

        except Exception:
            # Fail closed but never crash the dialog
            try:
                self._set_state(AddEditState.EMPTY)
            except Exception:
                pass

    def _on_category_dirty(self, *_args) -> None:
        try:
            self._category_committed = False
        except Exception:
            pass
        try:
            self._refresh_add_state()
        except Exception:
            pass

    def _on_category_committed(self, *_args) -> None:
        try:
            self._category_committed = True
        except Exception:
            pass
        try:
            self._refresh_add_state()
        except Exception:
            pass

    def _set_state(self, state: AddEditState) -> None:
        try:
            if getattr(self, "_add_state", None) == state:
                return
        except Exception:
            pass

        try:
            self._add_state = state
        except Exception:
            pass

        # Save gate: ONLY READY_TO_SAVE
        try:
            enable = bool(state == AddEditState.READY_TO_SAVE)
            if getattr(self, "btn_save", None) is not None:
                self.btn_save.setEnabled(enable)
        except Exception:
            pass

        try:
            logger.debug("AddEditState=%s", getattr(state, "name", str(state)))
        except Exception:
            pass

    def _refresh_add_state(self) -> None:
        try:
            jy = (self._add_jy.text() or "").strip() if getattr(self, "_add_jy", None) is not None else ""
            hz = (self._add_hz.text() or "").strip() if getattr(self, "_add_hz", None) is not None else ""
            mn = (self._add_mn.text() or "").strip() if getattr(self, "_add_mn", None) is not None else ""
            cat = (self._add_cat.currentText() or "").strip() if getattr(self, "_add_cat", None) is not None else ""
        except Exception:
            jy, hz, mn, cat = "", "", "", ""

        # Structural jyutping validity (same as before)
        try:
            from domain.attestation import is_attested_phrase as _is_attested_phrase
        except Exception:
            try:
                _is_attested_phrase = is_attested_phrase  # type: ignore[name-defined]
            except Exception:
                _is_attested_phrase = (lambda _s: False)

        try:
            jy_structural_ok = bool(jy) and attested_or_structural_ok(jy, is_attested_phrase=_is_attested_phrase)
        except Exception:
            jy_structural_ok = bool(jy)

        # Candidate availability: prefer last pipeline run; fallback to combo count
        cand_ok = False
        try:
            cand_ok = bool(getattr(self, "_last_candidates", None))
        except Exception:
            cand_ok = False
        if not cand_ok:
            try:
                cand_ok = bool(getattr(self, "_cand_combo", None) is not None and self._cand_combo.count() > 1)
            except Exception:
                cand_ok = False

        try:
            saving = bool(getattr(self, "_saving_now", False))
        except Exception:
            saving = False

        try:
            committed = bool(getattr(self, "_category_committed", False))
        except Exception:
            committed = False

        state = _derive_state(
            jyutping=jy,
            jyut_ok=jy_structural_ok,
            has_candidates=cand_ok,
            hanzi=hz,
            meanings=mn,
            category=cat,
            category_committed=committed,
            saving=saving,
        )
        self._set_state(state)

        # State is the single source of truth for Save gating; do not log legacy *_ok flags.
        try:
            enable = bool(state == AddEditState.READY_TO_SAVE)

            _mn_preview = ""
            try:
                _mn_preview = (mn or "").strip()
                if len(_mn_preview) > 60:
                    _mn_preview = _mn_preview[:57].rstrip() + "…"
            except Exception:
                _mn_preview = ""

            logger.debug(
                "AddEditState=%s save_enabled=%s committed=%s saving=%s cand_ok=%s jy=%r hz=%r mn=%r cat=%r",
                getattr(state, "name", str(state)),
                enable,
                committed,
                saving,
                cand_ok,
                jy,
                hz,
                _mn_preview,
                cat,
            )
        except Exception:
            pass

    def _set_notes(self, text: str, source: str = "auto-default"):
        """
        Set notes text safely.

        Rules:
          - auto-default → notes are suppressed
          - chatgpt-style / curated → notes allowed (read-only)
        """
        try:
            if not text or source == "auto-default":
                self._add_notes.clear()
                self._add_notes.setReadOnly(True)
                return

            self._add_notes.setReadOnly(False)
            self._add_notes.setText(text)
            self._add_notes.setReadOnly(True)
        except Exception:
            pass

    # ---- Meaning resolver façade (preferred) ----
    def _meanings_for_hanzi(self, hanzi: str) -> list[str]:
        hz = (hanzi or "").strip()
        if not hz:
            return []

        facade = getattr(self, "_meaning_facade", None)
        if facade is None:
            return []

        try:
            _t_m = self._perf_start("MeaningFacade.meanings_for_display")
            out = facade.meanings_for_display(hz)
            try:
                logger.debug("MeaningFacade: hz=%r meanings_n=%d sample=%r", hz, len(list(out or [])), list(out or [])[:3])
            except Exception:
                pass
            self._perf_end("MeaningFacade.meanings_for_display", _t_m)
            return [str(x) for x in (out or []) if str(x).strip()]
        except Exception:
            self._perf_end("MeaningFacade.meanings_for_display", _t_m)
            return []

    def _build_category_profiles(self) -> None:
        """
        Build lightweight token-frequency profiles per category from existing vocab meanings.

        Populates self._cat_keywords as:
            {category_name: {token: weight, ...}, ...}

        These are used as a soft hint when ranking reverse-lookup candidates so items whose
        glosses look similar to other items in the active category get a small score boost.
        """
        try:
            token_re = re.compile(r"[a-z]+")
            self._cat_keywords = {}
            if not isinstance(self._cats, dict) or not isinstance(self._vocab, dict):
                return

            for cat, hanzi_list in (self._cats or {}).items():
                if not hanzi_list:
                    continue
                weights: dict[str, float] = {}
                total = 0.0
                for hz in (hanzi_list or []):
                    try:
                        v = self._vocab.get(hz)
                    except Exception:
                        v = None
                    if not v:
                        continue
                    meanings = v[0] if isinstance(v, (list, tuple)) and v else []
                    for g in (meanings or []):
                        text = str(g).lower()
                        for tok in token_re.findall(text):
                            weights[tok] = weights.get(tok, 0.0) + 1.0
                            total += 1.0
                if weights and total > 0.0:
                    # Normalise so that more common tokens within the category have higher weight
                    for t in list(weights.keys()):
                        try:
                            weights[t] = weights[t] / total
                        except Exception:
                            pass
                    self._cat_keywords[str(cat)] = weights
            try:
                logger.debug(f"Category profiles built for {len(self._cat_keywords)} categories")
            except Exception:
                pass
        except Exception:
            # Profiles are an optional hint; failures should not break the dialog
            try:
                self._cat_keywords = {}
            except Exception:
                pass

    def _meaning_preview_for_hz(self, hz: str, max_items: int = 1) -> str:
        """Return a short, UI-safe meaning preview for a Hanzi (comma-separated).

        Used only for compact candidate labels; does not change domain logic.
        """
        try:
            hz_s = (hz or "").strip()
        except Exception:
            hz_s = ""
        if not hz_s:
            return ""

        try:
            glosses = self._meanings_for_hanzi(hz_s) or []
        except Exception:
            glosses = []

        try:
            out = [str(g).strip() for g in glosses if str(g).strip()]
        except Exception:
            out = []

        if not out:
            return ""

        try:
            n = int(max_items or 1)
        except Exception:
            n = 1
        if n < 1:
            n = 1

        try:
            # Prefer semicolon separation; strip any excessive whitespace.
            return "; ".join([s.strip() for s in out[:n] if s.strip()])
        except Exception:
            try:
                return str(out[0])
            except Exception:
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
            self._last_candidates = list(cands or [])
        except Exception:
            self._last_candidates = []

        try:
            self._cand_combo.blockSignals(True)
            self._cand_combo.clear()
        except Exception:
            return

        if not cands:
            try:
                self._cand_combo.setVisible(False)
            except Exception:
                pass
            try:
                self._cand_combo.blockSignals(False)
            except Exception:
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
            except Exception:
                pass

            # Debug: confirm incoming candidate shape before we populate UI
            try:
                _sample_in = []
                for _i, (_hz, _src, _sc) in enumerate((cands or [])[:5], start=1):
                    _sample_in.append((_i, str(_hz), str(_src), int(round(float(_sc or 0.0)))))
                logger.debug("PopulateComboAudit: sample_in=%r", _sample_in)
            except Exception:
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
                            except Exception:
                                selected_meanings = []
                    except Exception:
                        label = ""
                        selected = None
                        selected_meanings = []


                if not label:
                    # Final fallback: Hanzi + friendly source label
                    try:
                        friendly = FRIENDLY_SOURCE_LABELS.get(src, abbr_for_source(src))
                    except Exception:
                        friendly = abbr_for_source(src)
                    label = "{} ({})".format(hz_s, friendly)
                    if preferred:
                        label = "✓ {}".format(label)

                # Ensure the combobox shows a brief meaning preview (historical behaviour).
                # Primary source: meanings returned by select_candidate().
                # Fallbacks (in order): pipeline.glosses_for_candidate(), then dialog meaning facade.
                preview = ""
                try:
                    meanings_src: list[str] = []
                    try:
                        logger.debug(
                            "ComboPreviewAudit: hz=%r src=%r preferred=%s selected_meanings_n=%d",
                            hz_s,
                            src,
                            preferred,
                            len(selected_meanings or []),
                        )
                    except Exception:
                        pass

                    if selected_meanings:
                        meanings_src = [str(g).strip() for g in selected_meanings if str(g).strip()]
                    else:
                        # Prefer pipeline-provided gloss resolution if available.
                        try:
                            pipeline = getattr(self, "_hanzi_pipeline", None)
                        except Exception:
                            pipeline = None

                        if pipeline is not None and hasattr(pipeline, "glosses_for_candidate"):
                            try:
                                meanings_src = [
                                    str(g).strip()
                                    for g in (pipeline.glosses_for_candidate(hz_s) or [])
                                    if str(g).strip()
                                ]
                            except Exception:
                                meanings_src = []

                        if not meanings_src:
                            # Last fallback: dialog helper (meaning facade)
                            try:
                                meanings_src = [
                                    str(g).strip()
                                    for g in (self._meanings_for_hanzi(hz_s) or [])
                                    if str(g).strip()
                                ]
                            except Exception:
                                meanings_src = []

                    try:
                        logger.debug(
                            "ComboPreviewAudit: hz=%r meanings_src_n=%d meanings_src_sample=%r",
                            hz_s,
                            len(meanings_src or []),
                            (meanings_src or [])[:4],
                        )
                    except Exception:
                        pass

                    # Preserve previous UI filtering: drop items containing '[' or '(' and then take up to 2.
                    clean = [g for g in meanings_src if "[" not in g and "(" not in g]
                    shown = clean[:2] if clean else meanings_src[:2]

                    try:
                        logger.debug(
                            "ComboPreviewAudit: hz=%r clean_n=%d shown=%r",
                            hz_s,
                            len(clean or []),
                            shown,
                        )
                    except Exception:
                        pass

                    if shown:
                        preview = ", ".join([s for s in shown if s])
                except Exception:
                    preview = ""

                # Hard cap preview length to prevent the combobox from becoming unreadable.
                try:
                    if isinstance(preview, str) and len(preview) > 80:
                        preview = preview[:77].rstrip() + "…"
                except Exception:
                    pass

                if preview:
                    # Avoid duplicating if the label already contains a preview separator.
                    try:
                        if " — " not in label:
                            # Insert the preview before the source tag, if a tag exists.
                            if label.endswith(")") and " (" in label:
                                i = label.rfind(" (")
                                if i > 0:
                                    label = "{} — {}{}".format(label[:i], preview, label[i:])
                                else:
                                    label = "{} — {}".format(label, preview)
                            else:
                                label = "{} — {}".format(label, preview)
                    except Exception:
                        pass

                # Store (hz, src) so selection handler has source context if needed later
                try:
                    logger.debug("ComboLabelAudit: hz=%r final_label=%r", hz_s, label)
                except Exception:
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
                except Exception:
                    pass

            self._cand_combo.setCurrentIndex(0)
            self._cand_combo.setVisible(True)
        except Exception:
            pass
        finally:
            try:
                self._cand_combo.blockSignals(False)
            except Exception:
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
        except Exception:
            pass

        try:
            logger.debug("AddItem: no candidates; showing custom Hanzi entry option")
        except Exception:
            pass

        try:
            if getattr(self, "_add_hz", None) is not None:
                self._add_hz.setReadOnly(False)
                try:
                    self._add_hz.setPlaceholderText("Type Hanzi (or paste)")
                except Exception:
                    pass
                self._add_hz.clear()
                self._add_hz.setFocus()
        except Exception:
            pass

        try:
            if getattr(self, "_cand_combo", None) is not None:
                self._cand_combo.setVisible(False)
        except Exception:
            pass

        try:
            if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                self._update_save_enabled()
        except Exception:
            pass

        return 0

    def _set_hanzi_top_candidate(self, cands: list[tuple[str, str, int]]) -> str | None:
        """Set Hanzi edit to the top candidate and return the preferred Hanzi."""
        preferred_hz = None
        preferred_src = ""
        try:
            if isinstance(cands, list) and cands:
                preferred_hz = cands[0][0]
                try:
                    preferred_src = str(cands[0][1] or "").strip()
                except Exception:
                    preferred_src = ""
        except Exception:
            preferred_hz = None
            preferred_src = ""

        if preferred_hz:
            try:
                if getattr(self, "_add_hz", None) is not None:
                    self._add_hz.setText(preferred_hz)
            except Exception:
                pass

            # If meanings are empty, try to auto-fill from the resolved Hanzi.
            try:
                mn_edit = getattr(self, "_add_mn", None)
            except Exception:
                mn_edit = None

            try:
                mn_existing = (mn_edit.text() or "").strip() if mn_edit is not None else ""
            except Exception:
                mn_existing = ""

            if mn_edit is not None and not mn_existing:
                meanings: list[str] = []
                try:
                    facade = getattr(self, "_meaning_facade", None)
                except Exception:
                    facade = None

                if facade is not None and hasattr(facade, "select_candidate"):
                    try:
                        selected = facade.select_candidate(preferred_hz, preferred_src, preferred=True, max_items=2)
                        meanings = [str(x) for x in (getattr(selected, "meanings", []) or []) if str(x).strip()]
                    except Exception:
                        meanings = []
                if not meanings:
                    try:
                        meanings = [str(x) for x in (self._meanings_for_hanzi(preferred_hz) or []) if str(x).strip()]
                    except Exception:
                        meanings = []

                try:
                    if meanings:
                        mn_edit.setText(", ".join(meanings))
                    else:
                        mn_edit.setPlaceholderText("Enter English meaning")
                except Exception:
                    pass

        return preferred_hz

    def _clear_candidate_view_highlight(self) -> None:
        try:
            v = self._cand_combo.view()
            if v is not None:
                v.setCurrentIndex(QModelIndex())
        except Exception:
            pass

    def _maybe_autofill_single_candidate_meanings(self, cands: list[tuple[str, str, int]]) -> None:
        """If there is exactly one candidate, populate meanings (best-effort) and focus meanings."""
        try:
            if not (isinstance(cands, list) and len(cands) == 1):
                return
        except Exception:
            return

        single_hz = None
        try:
            single_hz = cands[0][0]
        except Exception:
            single_hz = None

        if not single_hz:
            return

        try:
            if getattr(self, "_add_hz", None) is not None:
                self._add_hz.setText(single_hz)
        except Exception:
            pass

        # Meanings are resolved via the MeaningFacade (single source of truth)
        glosses_single = self._meanings_for_hanzi(single_hz)

        try:
            if getattr(self, "_add_mn", None) is not None:
                self._add_mn.setText(", ".join(glosses_single) if glosses_single else "")
        except Exception:
            pass

        try:
            if getattr(self, "_add_mn", None) is not None:
                self._add_mn.setFocus()
                self._add_mn.selectAll()
        except Exception:
            pass

        try:
            if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                self._update_save_enabled()
        except Exception:
            pass

        try:
            logger.debug("AddItem: auto-filled meanings for single candidate '%s' -> %r", single_hz,
                         (glosses_single[:3] if glosses_single else []))
        except Exception:
            pass

    def _apply_selected_candidate(self, index: int | None = None) -> None:
        """Apply the currently-selected candidate from the combobox.

        Orchestration only: set Hanzi field, then resolve meanings via the domain façade.
        """
        combo = getattr(self, "_cand_combo", None)
        if combo is None:
            return

        try:
            idx = combo.currentIndex() if index is None else int(index)
        except Exception:
            idx = combo.currentIndex()

        # 0 is placeholder
        if idx <= 0:
            return

        try:
            data = combo.itemData(idx)
        except Exception:
            data = None

        # Debug: what exactly did the combobox store?
        try:
            logger.debug(
                "CandidateSelectAudit: idx=%d text=%r itemData_type=%s itemData=%r",
                idx,
                combo.currentText(),
                type(data).__name__,
                data,
            )
        except Exception:
            pass

        hz = ""
        src = ""

        # Expected shape: (hanzi, source) stored as tuple (preferred) or list (legacy).
        if isinstance(data, (tuple, list)) and len(data) >= 2:
            try:
                hz = str(data[0] or "").strip()
            except Exception:
                hz = ""
            try:
                src = str(data[1] or "").strip()
            except Exception:
                src = ""

        # Back-compat: some older builds stored only a plain string Hanzi.
        elif isinstance(data, str):
            try:
                hz = str(data or "").strip()
            except Exception:
                hz = ""

        else:
            hz = ""
            src = ""

        if not hz:
            return

        # Selecting a candidate exits manual mode.
        try:
            self._manual_hanzi_mode = False
        except Exception:
            pass

        # Apply Hanzi selection to the UI
        try:
            hz_edit = getattr(self, "_add_hz", None)
        except Exception:
            hz_edit = None

        if hz_edit is not None:
            try:
                hz_edit.setReadOnly(True)
            except Exception:
                pass
            try:
                hz_edit.setText(hz)
            except Exception:
                pass

        # Domain owns meaning resolution + cleaning.
        meanings: list[str] = []
        try:
            facade = getattr(self, "_meaning_facade", None)
        except Exception:
            facade = None

        if facade is not None and hasattr(facade, "select_candidate"):
            try:
                selected = facade.select_candidate(hz, src, preferred=False, max_items=2)
                meanings = [str(x) for x in (getattr(selected, "meanings", []) or []) if str(x).strip()]
            except Exception:
                meanings = []
        else:
            # Back-compat fallback
            try:
                meanings = [str(x) for x in (self._meanings_for_hanzi(hz) or []) if str(x).strip()]
            except Exception:
                meanings = []

        # Apply meanings to UI (best-effort)
        try:
            mn_edit = getattr(self, "_add_mn", None)
        except Exception:
            mn_edit = None

        if mn_edit is not None:
            try:
                if meanings:
                    mn_edit.setText(", ".join(meanings))
                else:
                    mn_edit.setText("")
                    mn_edit.setPlaceholderText("Enter English meaning")
            except Exception:
                pass

            # Keep the existing interaction pattern: move focus to meanings after selection.
            try:
                mn_edit.setFocus()
                mn_edit.selectAll()
            except Exception:
                pass

        try:
            if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                self._update_save_enabled()
        except Exception:
            pass

    def _apply_ambiguity_notes(self, jy_n: str, n_syllables: int, cands: list[tuple[str, str, int]]) -> None:
        """Set notes based on domain ambiguity rules (UI-free logic lives in domain.category_rules)."""
        try:
            top_glosses: list[str] | None = None
            try:
                if isinstance(cands, list) and cands:
                    top_hz = cands[0][0]
                    if isinstance(top_hz, str) and top_hz.strip():
                        top_glosses = self._meanings_for_hanzi(top_hz)
            except Exception:
                top_glosses = None

            note = ambiguity_note(jy_n, n_syllables, cands, top_glosses)
            if note:
                self._set_notes(note, source="domain")
            else:
                self._set_notes("", source="domain")
        except Exception:
            # Notes are non-critical; never break the UI.
            try:
                self._set_notes("", source="domain")
            except Exception:
                pass

    def _update_hanzi_tooltip_preview(self, cands: list[tuple[str, str, int]]) -> None:
        """Tooltip preview on the Hanzi field for quick glance."""
        try:
            if not getattr(self, "_add_hz", None):
                return
        except Exception:
            return

        try:
            if cands:
                preview_parts = []
                for (hz, src, freq) in cands[:6]:
                    try:
                        ms = self._meanings_for_hanzi(hz)
                        if ms:
                            preview_parts.append(f"{hz} — {', '.join(ms[:2])}")
                        else:
                            preview_parts.append(hz)
                    except Exception:
                        preview_parts.append(hz)
                self._add_hz.setToolTip(", ".join(preview_parts))
            else:
                self._add_hz.setToolTip("No candidates found")
        except Exception:
            pass

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
                    except Exception:
                        _sample = []
                logger.debug(
                    "ReverseIndexAudit: jy=%r present=%s size=%s sample=%r",
                    jy_n,
                    _has_key,
                    _ri_sz,
                    _sample,
                )
            except Exception:
                pass

            # If the user has opted to type their own Hanzi, do not overwrite or re-suggest.
            if bool(getattr(self, "_manual_hanzi_mode", False)):
                try:
                    logger.debug("_fill_hanzi_candidates: manual Hanzi mode active; skipping auto-fill")
                except Exception:
                    pass
                return 0

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
                        except Exception:
                            sc_f = 0.0
                        src_s = (str(_src) or "").strip() or "reverse"
                        tier1.append((hz_s, src_s, sc_f))
            except Exception:
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
                except Exception as e:
                    try:
                        logger.warning("Hanzi pipeline failed for %r: %s", jy_n, e)
                    except Exception:
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
            except Exception:
                pass

            # Cap to a sane UI maximum
            try:
                max_n = int(getattr(self, "MAX_HANZI_CANDIDATES", 10) or 10)
            except Exception:
                max_n = 10
            if isinstance(cands, list) and max_n > 0:
                cands = cands[:max_n]

            # Extra debug: confirm Tier-1 presence and whether Tier-2 was suppressed.
            try:
                if tier1:
                    logger.debug("CandidateMergeAudit: jy=%r tier1_n=%d tier2_n=%d merged_n=%d top=%r", jy_n, len(tier1), len(tier2), len(cands), (cands[0] if cands else None))
            except Exception:
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
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception:
                pass

            # No candidates → manual Hanzi affordance
            if not cands:
                return self._handle_no_hanzi_candidates()

            # Set top candidate into Hanzi field
            preferred_hz = self._set_hanzi_top_candidate(cands)  # type: ignore[arg-type]
            try:
                if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                    self._update_save_enabled()
            except Exception:
                pass
            try:
                if preferred_hz:
                    logger.debug("TopCandidateAudit: preferred_hz=%r src=%r score=%r", cands[0][0], cands[0][1],
                                 cands[0][2])
            except Exception:
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
            except Exception:
                pass

            # Tooltip preview for quick glance
            self._update_hanzi_tooltip_preview(cands)  # type: ignore[arg-type]

            # Nudge UI to repaint immediately
            try:
                hz_widget = getattr(self, "_add_hz", None)
                if hz_widget is not None:
                    hz_widget.repaint()
                    hz_widget.update()
            except Exception:
                pass

            return len(cands)

        except Exception as e:
            # Defensive: keep UI consistent even on unexpected failure
            try:
                logger.exception("_fill_hanzi_candidates failed for %r: %s", jy_n or jy, e)
            except Exception:
                pass
            try:
                hz_widget = getattr(self, "_add_hz", None)
                if hz_widget is not None:
                    hz_widget.clear()
                    hz_widget.setToolTip("")
                combo = getattr(self, "_cand_combo", None)
                if combo is not None:
                    combo.setVisible(False)
            except Exception:
                pass
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
        except Exception:
            pass
        try:
            self._manual_hanzi_mode = True
        except Exception:
            pass
        # Track first entry into manual mode so repeated clicks don't wipe user input
        try:
            if not hasattr(self, "_manual_hanzi_started"):
                self._manual_hanzi_started = False
        except Exception:
            pass

        # Hide and clear the candidates combobox so we are no longer in
        # \"suggested candidates\" mode.
        try:
            cand_combo = getattr(self, "_cand_combo", None)
        except Exception:
            cand_combo = None
        if cand_combo is not None:
            try:
                cand_combo.blockSignals(True)
                try:
                    cand_combo.clear()
                    cand_combo.setVisible(False)
                finally:
                    cand_combo.blockSignals(False)
            except Exception:
                pass

        # Allow direct editing of the Hanzi field and move focus there.
        try:
            hz_edit = getattr(self, "_add_hz", None)
        except Exception:
            hz_edit = None
        if hz_edit is not None:
            try:
                hz_edit.setReadOnly(False)
            except Exception:
                pass
            try:
                hz_edit.setPlaceholderText("Type Hanzi (or paste)")
            except Exception:
                pass
            # Only clear Hanzi the first time we enter manual mode.
            if not getattr(self, "_manual_hanzi_started", False):
                try:
                    hz_edit.clear()
                except Exception:
                    pass
                self._manual_hanzi_started = True
            # Ensure we only connect these signals once; repeated connections cause repeated firing.
            try:
                if not getattr(self, "_manual_hanzi_signals_connected", False):
                    try:
                        hz_edit.textChanged.connect(self._update_save_enabled)
                    except Exception:
                        pass
                    try:
                        hz_edit.textChanged.connect(self._maybe_autofill_meanings_from_hz_manual)
                    except Exception:
                        pass
                    self._manual_hanzi_signals_connected = True
            except Exception:
                pass
            try:
                hz_edit.setFocus()
                hz_edit.selectAll()
            except Exception:
                pass

        # Finally, refresh Save enabled/disabled state so that once the
        # user types Hanzi and meanings, Save will light up.
        try:
            if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                self._update_save_enabled()
        except Exception:
            pass

    def _maybe_autofill_meanings_from_hz_manual(self):
        """
        When the user types Hanzi in manual mode, try once to populate meanings
        from available sources. If nothing is found, guide the user to enter
        meanings manually.
        """
        try:
            if not getattr(self, "_manual_hanzi_mode", False):
                return
        except Exception:
            return

        try:
            hz = (self._add_hz.text() or "").strip()
            mn_edit = getattr(self, "_add_mn", None)
        except Exception:
            return

        if not hz or mn_edit is None:
            return

        # Do not overwrite user-entered meanings
        try:
            if (mn_edit.text() or "").strip():
                return
        except Exception:
            pass

        # Attempt to derive meanings
        glosses = self._meanings_for_hanzi(hz)

        if glosses:
            try:
                mn_edit.setText(", ".join(glosses))
                mn_edit.selectAll()
            except Exception:
                pass
        else:
            # No glosses found: guide the user explicitly
            try:
                mn_edit.setPlaceholderText("Enter English meaning")
                mn_edit.setFocus()
            except Exception:
                pass

        try:
            if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                self._update_save_enabled()
        except Exception:
            pass

    def _is_duplicate_jy(self, jy: str) -> bool:
        """
        Consider it a duplicate if any existing vocab entry has the same normalized jyut string.
        """
        try:
            jy_n = self._normalize_jy(jy)
            for _hz, _val in (self._vocab or {}).items():
                try:
                    vjy = (_val[1] if isinstance(_val, (list, tuple)) and len(_val) > 1 else "")
                    if self._normalize_jy(vjy) == jy_n:
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _reset_add_panel(self):
        """Clear Add/Edit fields back to initial state and focus Jyutping."""
        try:
            self._manual_hanzi_mode = False
        except Exception:
            pass
        try:
            self._manual_hanzi_started = False
        except Exception:
            pass
        try:
            if getattr(self, "_cand_combo", None):
                self._cand_combo.blockSignals(True)
                try:
                    self._cand_combo.clear()
                    self._cand_combo.setVisible(False)
                finally:
                    self._cand_combo.blockSignals(False)
        except Exception:
            pass
        try:
            if getattr(self, "_add_hz", None):
                self._add_hz.clear()
                self._add_hz.setToolTip("")
        except Exception:
            pass
        try:
            if getattr(self, "_add_mn", None):
                self._add_mn.clear()
        except Exception:
            pass
        try:
            if getattr(self, "_add_cat", None):
                # No synthetic placeholder category: require the user to pick a real category.
                self._add_cat.setCurrentIndex(-1)
        except Exception:
            pass
        try:
            if getattr(self, "btn_save", None):
                self.btn_save.setEnabled(False)
                self.btn_save.setDefault(False)
                self.btn_save.setAutoDefault(False)
        except Exception:
            pass
        try:
            if getattr(self, "_add_jy", None):
                self._add_jy.setFocus()
        except Exception:
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
        self._category_committed = True
        self._refresh_add_state()
        if self._add_state != AddEditState.READY_TO_SAVE:
            return

        # Re-check that Save should be enabled (defensive)
        try:
            self._update_save_enabled()
        except Exception:
            pass

        cb = getattr(self, "_commit_callback", None)
        if not callable(cb):
            logger.warning(
                "Save clicked but no commit routine was found; please wire to your add/commit method."
            )
            return

        try:
            jy = (self._add_jy.text() or "").strip() if getattr(self, "_add_jy", None) is not None else ""
            hz = (self._add_hz.text() or "").strip() if getattr(self, "_add_hz", None) is not None else ""
            mn = (self._add_mn.text() or "").strip() if getattr(self, "_add_mn", None) is not None else ""
            cat = (self._add_cat.currentText() or "").strip() if getattr(self, "_add_cat", None) is not None else ""
        except Exception as e:
            logger.warning("Save aborted: unable to read Add fields (%s)", e)
            return

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
        except Exception:
            pass

    def _on_meanings_enter(self):
        """When user presses Enter in Meanings, move focus to Category."""
        try:
            if getattr(self, "_add_cat", None):
                if self._add_cat.isEditable() and self._add_cat.lineEdit():
                    self._add_cat.lineEdit().setFocus()
                    self._add_cat.lineEdit().selectAll()
                else:
                    self._add_cat.setFocus()
        except Exception:
            pass

    def _is_unassigned_category(self) -> bool:
        try:
            txt = (self._add_cat.currentText() or "").strip().lower()
            return txt == "unassigned"
        except Exception:
            return False

    def _on_jyut_enter(self):
        """
        Handler for Enter/Return in the Jyutping field.

        Behaviour:
          - Validate the Jyutping structurally (and via attestation if available).
          - If invalid, show a single warning and keep focus in the Jyutping field.
          - If valid, move focus to the Category control so the user can pick a context.
          - Do *not* trigger category commit logic or show category warnings here; those
            are only shown when the user explicitly commits a category or tries to
            progress without a real category.
        """
        jy_text = ""
        try:
            if getattr(self, "_add_jy", None) is not None:
                jy_text = (self._add_jy.text() or "").strip()
        except Exception:
            jy_text = ""

        if not jy_text:
            # Nothing to do; keep focus where it is.
            try:
                if getattr(self, "_add_jy", None) is not None:
                    self._add_jy.setFocus()
            except Exception:
                pass
            return

        # Validate Jyutping; if invalid, warn (with a specific reason when available)
        # and keep focus in Jyutping.
        try:
            from domain.attestation import is_attested_phrase as _is_attested_phrase
        except Exception:
            try:
                _is_attested_phrase = is_attested_phrase  # type: ignore[name-defined]
            except Exception:
                _is_attested_phrase = (lambda _s: False)

        try:
            ok = attested_or_structural_ok(
                jy_text,
                is_attested_phrase=_is_attested_phrase,
            )
        except Exception:
            ok = True

        if not ok:
            reason = None
            try:
                from domain.jyutping_validation import validate_jyut_syllables as _validate_jyut_syllables
                _ok_struct, reason = _validate_jyut_syllables(jy_text)
            except Exception:
                try:
                    _ok_struct, reason = validate_jyut_syllables(jy_text)  # type: ignore[name-defined]
                except Exception:
                    reason = None

            msg = (
                "The Jyutping you entered does not look valid.\n"
                "Please check the syllables and tone numbers."
            )
            if reason:
                msg = msg + "\n\n" + str(reason)

            try:
                QMessageBox.warning(
                    self,
                    "Jyutping",
                    msg,
                )
            except Exception:
                pass
            try:
                if getattr(self, "_add_jy", None) is not None:
                    self._add_jy.setFocus()
                    self._add_jy.selectAll()
            except Exception:
                pass
            return

        try:
            self._manual_hanzi_mode = False
        except Exception:
            pass

        # Jyutping is structurally OK: move focus to Category, but do not run category commit yet.
        try:
            cat = getattr(self, "_add_cat", None)
        except Exception:
            cat = None

        if cat is not None:
            try:
                if cat.isEditable() and cat.lineEdit():
                    le_cat = cat.lineEdit()
                    le_cat.setFocus()
                    le_cat.selectAll()
                else:
                    cat.setFocus()
            except Exception:
                pass

            # Make the focus change obvious by opening the dropdown (best-effort).
            try:
                cat.showPopup()
            except Exception:
                pass

        # Refresh Save state, but do not attempt reverse lookup or category warnings yet.
        try:
            if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                self._update_save_enabled()
        except Exception:
            pass

    def _validate_jyut_syllables(self, jy: str) -> tuple[bool, str | None]:
        """Back-compat helper for regression tests.

        This method must contain no validation heuristics; it delegates to the
        module-level `validate_jyut_syllables`, imported from
        `domain.jyutping_validation`.
        """
        return validate_jyut_syllables(jy)


    def _on_add_category_committed(self) -> None:
        """Commit the category from the editable Add-panel combobox.

        This is the handler for Enter/Return on the category line edit.
        It normalises/creates categories and then triggers candidate lookup
        if Jyutping is present and Hanzi is still empty.
        """
        text = (self._add_cat.currentText() or "").strip() if getattr(self, "_add_cat", None) is not None else ""

        # Require explicit category choice
        if not text:
            QMessageBox.warning(
                self,
                "Category required",
                "Please choose or type a category for this entry.\n"
                "If you really cannot decide, you can use ‘unassigned’."
            )
            try:
                if self._add_cat.isEditable() and self._add_cat.lineEdit():
                    le_cat = self._add_cat.lineEdit()
                    le_cat.setFocus()
                    le_cat.selectAll()
                else:
                    self._add_cat.setFocus()
            except Exception:
                pass
            return

        # Normalise / reuse / create
        try:
            if hasattr(self, "_canon_cat_name") and hasattr(self, "_find_existing_canonical"):
                canon = self._canon_cat_name(text)
                existing = self._find_existing_canonical(canon)
                if existing:
                    self._add_cat.blockSignals(True)
                    try:
                        idx = self._add_cat.findText(existing)
                        if idx >= 0:
                            self._add_cat.setCurrentIndex(idx)
                        else:
                            self._add_cat.setCurrentText(existing)
                    finally:
                        self._add_cat.blockSignals(False)
                else:
                    if hasattr(self, "_is_reserved_cat") and self._is_reserved_cat(canon):
                        QMessageBox.information(self, "Category", f"‘{canon}’ is a reserved name and cannot be used.")
                        return

                    resp = QMessageBox.question(
                        self,
                        "Add Category",
                        f"Add new category ‘{canon}’?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if resp != QMessageBox.StandardButton.Yes:
                        return

                    if hasattr(self, "_add_new_category"):
                        self._add_new_category(canon)
                    else:
                        # Inline creation fallback
                        if canon not in self._cats:
                            self._cats[canon] = []
                            self._all_cats = sorted(set(self._cats.keys()), key=lambda s: s.lower())
                            self._add_cat.blockSignals(True)
                            try:
                                self._add_cat.clear()
                                self._add_cat.addItems(self._all_cats)
                                idx = self._add_cat.findText(canon)
                                if idx >= 0:
                                    self._add_cat.setCurrentIndex(idx)
                            finally:
                                self._add_cat.blockSignals(False)
        except Exception:
            # Creation failures should never break the dialog
            pass

        # After commit, trigger lookup if needed
        try:
            jy_txt = (self._add_jy.text() or "").strip() if getattr(self, "_add_jy", None) is not None else ""
            hz_txt = (self._add_hz.text() or "").strip() if getattr(self, "_add_hz", None) is not None else ""
        except Exception:
            jy_txt = ""
            hz_txt = ""

        if jy_txt and not hz_txt:
            _CatTimer.singleShot(0, lambda: self._post_category_fill(jy_txt))
        else:
            try:
                if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                    self._update_save_enabled()
            except Exception:
                pass

    def _post_category_fill(self, jy_txt: str) -> None:
        """Run reverse lookup after a category has been committed."""
        try:
            n = self._fill_hanzi_candidates(self._normalize_jy(jy_txt))
        except Exception:
            n = 0

        cand_combo = getattr(self, "_cand_combo", None)
        has_candidates = bool(n and n > 0)

        try:
            if has_candidates and cand_combo is not None:
                try:
                    cand_combo.setVisible(True)
                    cand_combo.showPopup()
                    cand_combo.setFocus()
                except Exception:
                    pass
                try:
                    btn_custom = getattr(self, "_btn_custom_hz", None)
                    if btn_custom is not None:
                        btn_custom.setVisible(False)
                except Exception:
                    pass
            else:
                try:
                    if cand_combo is not None:
                        cand_combo.blockSignals(True)
                        try:
                            cand_combo.clear()
                            cand_combo.setVisible(False)
                        finally:
                            cand_combo.blockSignals(False)
                except Exception:
                    pass
                try:
                    btn_custom = getattr(self, "_btn_custom_hz", None)
                    if btn_custom is not None:
                        btn_custom.setVisible(True)
                except Exception:
                    pass
                try:
                    hz_edit = getattr(self, "_add_hz", None)
                    if hz_edit is not None:
                        hz_edit.setFocus()
                        hz_edit.selectAll()
                except Exception:
                    pass
        finally:
            try:
                if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                    self._update_save_enabled()
            except Exception:
                pass

    def _on_candidate_index_activated(self, index: int) -> None:
        try:
            self._apply_selected_candidate(index)
        except Exception:
            pass

    def _on_candidate_text_changed(self, _text: str) -> None:
        try:
            self._apply_selected_candidate(None)
        except Exception:
            pass

    def _clean_glosses_for_display_safe(self, glosses: object) -> list[str]:
        """Back-compat wrapper; prefer domain.meaning_sources.clean_glosses_for_display."""
        try:
            return list(clean_glosses_for_display(glosses) or [])
        except Exception:
            # Last-resort, minimal cleaning
            try:
                seq = glosses if isinstance(glosses, (list, tuple)) else []
                return [str(x).strip() for x in seq if str(x).strip()]
            except Exception:
                return []

    def _call_best_effort(self, fn, *args):
        """Call `fn` with the largest compatible prefix of args.

        This protects us from legacy utils callables whose signatures vary.
        """
        if fn is None or not callable(fn):
            return None

        try:
            import inspect
            sig = inspect.signature(fn)
            params = list(sig.parameters.values())

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
        except Exception:
            pass

        try:
            return fn(*args[:1])
        except Exception:
            return None

    def _get_compose_and_rank(self):
        """Return (compose_fn, shortlist_fn) for tier-2 Hanzi candidate generation.

        This dialog stays orchestration-only. Tier-2 composition/shortlisting is an
        infrastructure concern and lives in `infra.hanzi_composition`.
        """
        compose_fn = None
        shortlist_fn = None

        try:
            from infra.hanzi_composition import compose_candidates_from_chars as _compose
            compose_fn = _compose
        except Exception:
            compose_fn = None

        try:
            from infra.hanzi_composition import shortlist_candidates as _shortlist
            shortlist_fn = _shortlist
        except Exception:
            shortlist_fn = None

        return compose_fn, shortlist_fn

    def get_cccanto_glosses_for(self, hanzi: str):
        """UI shim: provide CC-Canto glosses for a Hanzi candidate (if available).

        Keep this file free of any static utils imports (architecture boundary).
        """
        hz = (hanzi or "").strip()
        if not hz:
            return []

        try:
            import importlib
            mod = importlib.import_module("utils.utils")

            # Best-effort initialisation if a loader exists
            try:
                init_fn = getattr(mod, "get_cccanto_reverse_map", None)
                if callable(init_fn):
                    self._call_best_effort(init_fn)
            except Exception:
                pass

            fn = getattr(mod, "get_cccanto_glosses_for", None)
            if callable(fn):
                out = self._call_best_effort(fn, hz)
                seq = list(out or [])
                return [str(x).strip() for x in seq if str(x).strip()]

        except Exception as e:
            try:
                logger.debug("CCCanto shim failed for %r: %s", hz, e)
            except Exception:
                pass

        return []

    def get_cedict_meanings_for(self, hanzi: str):
        """UI shim: provide CEDICT meanings for a Hanzi candidate (if available).

        Keep this file free of any static utils imports (architecture boundary).
        """
        hz = (hanzi or "").strip()
        if not hz:
            return []

        try:
            import importlib
            mod = importlib.import_module("utils.utils")

            # Best-effort initialisation if a loader exists (names vary historically)
            for init_name in ("load_cedict", "load_cedict_dict", "load_cedict_meanings", "get_cedict_dict"):
                try:
                    init_fn = getattr(mod, init_name, None)
                    if callable(init_fn):
                        self._call_best_effort(init_fn)
                        break
                except Exception:
                    continue

            fn = getattr(mod, "get_cedict_meanings_for", None)
            if callable(fn):
                out = self._call_best_effort(fn, hz)
                seq = list(out or [])
                return [str(x).strip() for x in seq if str(x).strip()]

        except Exception as e:
            try:
                logger.debug("CEDICT shim failed for %r: %s", hz, e)
            except Exception:
                pass

        return []

    def clean_glosses_for_display(self, glosses):
        try:
            from domain.meaning_sources import clean_glosses_for_display as _cleaner
            cleaned = _cleaner(list(glosses or []))
            return list(cleaned or [])
        except Exception:
            return list(glosses or [])