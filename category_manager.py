# ----------------------------------------
# Standard library imports
# ----------------------------------------
import logging
import os

# ----------------------------------------
# Third-party imports
# ----------------------------------------
import yaml

# ----------------------------------------
# PySide6 imports
# ----------------------------------------
from PySide6.QtCore import QTimer as _CatTimer
from PySide6.QtCore import Qt
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

# ----------------------------------------
# Domain imports
# ----------------------------------------
from domain.category_rules import (
    CATEGORY_PLACEHOLDER_TEXT,
    is_category_placeholder,
    save_enabled_gate,
    should_show_custom_hanzi_button,
    prefer_meanings,
    ambiguity_note,
    HanziStyleIndex,
    CandidateCurator,
    abbr_for_source,
)


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

class CategoryManagerDialog(QDialog):
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

    def __init__(self, parent, vocab_items: dict, categories_map: dict):
        super().__init__(parent)
        self._parent = parent
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

        self.setWindowTitle("Add & Edit Items")
        # UI-free helpers
        try:
            _project_dir = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            _project_dir = os.getcwd()
        self._style_index = HanziStyleIndex(_project_dir)
        self._candidate_curator = CandidateCurator(self._style_index, self.MAX_HANZI_CANDIDATES)
        logger.debug("CategoryManagerDialog: init start (building UI and wiring)")

        # Wide enough to keep Entry/Hanzi side-by-side
        self.resize(720, 540)

        # ---------- Data / caches ----------
        # In-memory vocab & categories (make shallow copies to avoid mutating callers)
        self._vocab = {k: (list(v[0]) if isinstance(v, (list, tuple)) and v else [],
                           (v[1] if isinstance(v, (list, tuple)) and len(v) > 1 else ""))
                       for k, v in (vocab_items or {}).items()}
        self._cats = {str(k): list(v) for k, v in (categories_map or {}).items()}
        # Normalize category keys and drop sentinel 'All' if present
        try:
            self._cats = {str(k).strip(): list(v or []) for k, v in self._cats.items() if str(k).strip()}
            if len(self._cats) <= 1 and any(k.lower() == "all" for k in self._cats):
                self._cats.pop(next(k for k in list(self._cats) if k.lower() == "all"), None)
        except Exception:
            pass

        # Ensure a stable categories list (include 'unassigned')
        # Stable categories list: exclude 'All', ensure 'unassigned' exists
        self._all_cats = sorted(
            {k for k in self._cats if str(k).strip() and k.lower() != "all"},
            key=lambda s: s.lower()
        )
        # Diagnostics for category population
        try:
            logger.debug(f"AddItem: _cats keys (n={len(self._cats)}): {sorted(self._cats.keys())}")
            logger.debug(f"AddItem: _all_cats (n={len(self._all_cats)}): {self._all_cats}")
        except Exception:
            pass

        # If only 'unassigned' is available, attempt a one-time reload from disk
        try:
            if len(self._all_cats) <= 1:
                # import os, yaml
                base_dir = os.path.dirname(os.path.abspath(__file__))
                candidates = [
                    os.path.join(base_dir, "categories.yaml"),
                    os.path.join(base_dir, "data", "categories.yaml"),
                ]
                cat_path = next((p for p in candidates if os.path.exists(p)), None)
                if cat_path:
                    with open(cat_path, "r", encoding="utf-8") as fh:
                        raw = yaml.safe_load(fh) or {}
                    if isinstance(raw, dict):
                        keys = [str(k) for k in raw.keys() if str(k).strip() and str(k).lower() != "all"]
                        if keys:
                            self._all_cats = sorted(set(keys + ["unassigned"]), key=lambda s: s.lower())
                            logger.debug(f"AddItem: categories reloaded from {cat_path} -> {len(self._all_cats)} keys")
        except Exception:
            pass

        if "unassigned" not in (c.lower() for c in self._all_cats):
            self._all_cats.append("unassigned")
            self._all_cats = sorted(set(self._all_cats), key=lambda s: s.lower())

        # Attestation cache (if your class implements it)
        try:
            self._attested_jyut = None
            if hasattr(self, "_ensure_attested_cache"):
                self._ensure_attested_cache()
        except Exception:
            pass

        # Reverse lookup caches (Tier 1: reverse index; Tier 2: Unihan char map)
        # Reuse any prebuilt caches from the main window when present
        try:
            self._reverse_index = getattr(self._parent, "_reverse_index", None)
            if not isinstance(self._reverse_index, dict):
                self._reverse_index = {}
        except Exception:
            self._reverse_index = {}

        # Shared Unihan char map (dict[char] -> [readings...])
        try:
            # Prefer the one the main window already attached
            self._char_map = getattr(self._parent, "_char_map", None)
            if not isinstance(self._char_map, dict) or not self._char_map:
                # Try utils.get_unihan_char_map if available
                try:
                    from utils import get_unihan_char_map  # noqa: F401
                    self._char_map = get_unihan_char_map() or {}
                except Exception:
                    self._char_map = {}
            # Reattach to parent so other dialogs share it
            try:
                setattr(self._parent, "_char_map", self._char_map if isinstance(self._char_map, dict) else {})
            except Exception:
                pass
        except Exception:
            self._char_map = {}

        # Build category semantic profiles (category -> token weight) from existing vocab
        try:
            if not hasattr(self, "_cat_keywords"):
                self._cat_keywords = {}
            if isinstance(self._vocab, dict) and isinstance(self._cats, dict):
                self._build_category_profiles()
        except Exception:
            # Profiles are an optional hint; failures should not break the dialog
            self._cat_keywords = {}

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
        row.setStretch(0, 4)
        row.setStretch(1, 2)

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
        self._add_hz.setMaximumWidth(260)
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
        groupEntry.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
        groupEntry.setMinimumWidth(360)
        groupHanzi.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        groupHanzi.setMinimumWidth(300)
        groupHanzi.setMaximumWidth(360)

        # Assemble the side-by-side row
        row.addWidget(groupEntry)
        row.addWidget(groupHanzi)
        self._root.addLayout(row)
        try:
            # Favor the entry group, keep Hanzi reasonably narrow
            row.setStretch(0, 3)
            row.setStretch(1, 2)
            # Ensure enough horizontal space so the two groups don’t stack
            self.setMinimumWidth(700)
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

        def _on_jy_text_changed(val: str):
            try:
                if not (val or "").strip():
                    self._reset_add_panel()
                    return
                if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                    self._update_save_enabled()
            except Exception:
                pass

        try:
            self._add_jy.textChanged.connect(_on_jy_text_changed)
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

        # Sticky manual-entry mode: when the user chooses to type their own Hanzi,
        # we must not overwrite it with any later auto-fill.
        self._manual_hanzi_mode = False

        # Done: dialog is fully constructed and safe even if some helpers are missing
        logger.debug("CategoryManagerDialog: init complete")
    def _load_reverse_jyut_map(self):
        """Lazy-load the phrase reverse index (Jyutping -> [Hanzi...]) from data/reverse_jyut.yaml."""
        try:
            if hasattr(self, "_reverse_jyut_map") and isinstance(self._reverse_jyut_map, dict) and self._reverse_jyut_map:
                return self._reverse_jyut_map
        except Exception:
            pass

        self._reverse_jyut_map = {}
        try:
            import os
            import yaml

            base_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(base_dir, "data", "reverse_jyut.yaml")
            if not os.path.exists(path):
                return self._reverse_jyut_map

            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            if isinstance(data, dict):
                # Normalise keys to the same normaliser used elsewhere
                normed = {}
                for k, v in data.items():
                    try:
                        kk = self._normalize_jy(str(k))
                        if not kk:
                            continue
                        if isinstance(v, list):
                            vals = [str(x) for x in v if x]
                        elif isinstance(v, str):
                            vals = [v]
                        else:
                            vals = []
                        if vals:
                            normed[kk] = vals
                    except Exception:
                        continue
                self._reverse_jyut_map = normed
        except Exception:
            self._reverse_jyut_map = {}
        return self._reverse_jyut_map

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

    # --- Lazy import helpers for reverse lookup composition/ranking (dialog-local) ---
    def _get_compose_and_rank(self):
        """Return (compose_candidates_from_chars, shortlist_candidates) from utils if available.
        This avoids hard dependencies on those helpers when they are not present.
        """
        compose_fn = None
        shortlist_fn = None
        try:
            import utils as _u
            compose_fn = getattr(_u, "compose_candidates_from_chars", None)
            shortlist_fn = getattr(_u, "shortlist_candidates", None)
        except Exception:
            pass
        return compose_fn, shortlist_fn

    def _validate_jyut_syllables(self, jy: str) -> bool:
        """
        Structural validator: each syllable must end with a tone digit 1–6.
        Accepts 'm' and 'ng' as whole-syllable nuclei (with tone), e.g., m4, ng5.
        """
        import re
        jy_n = self._normalize_jy(jy)
        if not jy_n:
            return False
        # split by spaces; reject empty parts
        parts = [p for p in jy_n.split(" ") if p]
        if not parts:
            return False
        # pattern: (m|ng|letters) followed by tone digit 1-6
        syl_pat = re.compile(r"^(?:m|ng|[a-z]+)[1-6]$")
        for syl in parts:
            if not syl_pat.match(syl):
                return False
        return True

    def _attested_or_structural_ok(self, jy: str) -> bool:
        """
        Prefer attestation if an attested cache exists, but do not *block* structurally
        well‑formed new phrases. We treat attestation as a positive hint:
          - if attested -> True
          - if not attested or helper missing -> fall back to structural validation.
        """
        jy_n = self._normalize_jy(jy)
        if not jy_n:
            return False

        # 1) Try attested cache, if available
        try:
            if hasattr(self, "_is_attested_phrase") and callable(self._is_attested_phrase):
                try:
                    if self._is_attested_phrase(jy_n):
                        return True
                except Exception:
                    # If the attestation helper itself fails, fall back to structural
                    pass
        except Exception:
            # If any attribute/lookup issue, fall back to structural
            pass

        # 2) Fallback: structural OK (allows completely new, but well‑formed Jyutping)
        return self._validate_jyut_syllables(jy_n)

    def _update_save_enabled(self):
        """
        Enable the Save button when the Add panel has a structurally valid Jyutping,
        a resolved Hanzi, at least one meaning, and a non-empty category.

        This is intentionally permissive for *new* but well-formed phrases: we only
        require structural Jyutping validity via _attested_or_structural_ok, not that
        the phrase already appears in any corpus.
        """
        try:
            jy = (self._add_jy.text() or "").strip() if getattr(self, "_add_jy", None) is not None else ""
            hz = (self._add_hz.text() or "").strip() if getattr(self, "_add_hz", None) is not None else ""
            mn = (self._add_mn.text() or "").strip() if getattr(self, "_add_mn", None) is not None else ""
            cat = (self._add_cat.currentText() or "").strip() if getattr(self, "_add_cat", None) is not None else ""
        except Exception:
            # If we cannot even read the fields safely, keep Save disabled.
            try:
                if getattr(self, "btn_save", None) is not None:
                    self.btn_save.setEnabled(False)
            except Exception:
                pass
            return

        # Basic field checks
        jy_ok = bool(jy) and self._attested_or_structural_ok(jy)
        hz_ok = bool(hz)
        mn_ok = bool(mn)
        cat_l = cat.lower()
        cat_ok = bool(cat) and cat_l not in ("all",)

        # Do not allow Save while a save is in progress
        saving = False
        try:
            saving = bool(getattr(self, "_saving_now", False))
        except Exception:
            saving = False

        enable = jy_ok and hz_ok and mn_ok and cat_ok and (not saving)

        try:
            if getattr(self, "btn_save", None) is not None:
                self.btn_save.setEnabled(enable)
                # Optional: lightweight debug for why Save is off
                logger.debug(
                    f"SaveEnabled? {enable} (jy_ok={jy_ok}, hz_ok={hz_ok}, mn_ok={mn_ok}, "
                    f"cat_ok={cat_ok}, saving={saving}, jy='{jy}', hz='{hz}', cat='{cat}')"
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

    # ---- Meanings / gloss helpers (lazy-loaded), with diagnostics ----
    def _load_cedict_index(self):
        """
        Populate self._cedict as {hanzi: [gloss1, gloss2, ...]} using a lightweight parser.
        Safe if file is missing.
        """
        if hasattr(self, "_cedict") and isinstance(self._cedict, dict) and self._cedict:
            return self._cedict
        self._cedict = {}
        try:
            import os, re
            base_dir = os.path.dirname(os.path.abspath(__file__))
            candidates = [
                os.path.join(base_dir, "data", "cedict", "cedict_ts.u8"),
                os.path.join(base_dir, "data", "CC-CEDICT", "cedict_ts.u8"),
                os.path.join(base_dir, "data", "cedict_ts.u8"),
            ]
            cedict_path = next((p for p in candidates if os.path.exists(p)), None)
            if not cedict_path:
                logger.debug("CEDICT not found in expected paths; glosses limited to curated/CC‑Canto")
                return self._cedict
            gloss_re = re.compile(r"^([^\s\[]+)\s+[^\[]+\s+\[[^]]*]\s+/(.+)/$")
            added = 0
            with open(cedict_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    if not line or line.startswith("#"):
                        continue
                    m = gloss_re.match(line.strip())
                    if not m:
                        continue
                    hz = m.group(1)
                    glosses = [g.strip() for g in m.group(2).split("/") if g.strip()]
                    if hz and glosses:
                        self._cedict.setdefault(hz, glosses[:3])
                        added += 1
            logger.debug(f"CEDICT index loaded: {added} Hanzi entries from {cedict_path}")
        except Exception as e:
            logger.debug(f"CEDICT parse failed: {e}")
        return self._cedict

    def _normalize_hz_variant(self, hz: str) -> str:
        """Return a more colloquial variant for glossing if applicable.
        Minimal, conservative rules for Cantonese:
          - Prefer 阿 over 亚/亞 as a vocative prefix for aa3.
        """
        if not hz:
            return hz
        # Only touch first char; leave rest intact
        first = hz[0]
        # Map both Simplified/Traditional 'ya/ya' -> '阿'
        if first in ("亚", "亞"):
            return "阿" + hz[1:]
        return hz

    def _get_meanings_for_hanzi(self, hz: str):
        """
        Meanings priority:
          1) andys_list.yaml (self._vocab)
          2) CC-Canto (prefer Cantonese/colloquial when available)
          3) CEDICT phrase-level (fallback)
          4) builtin fallback (optional)
        Tries a normalized variant (e.g., 亚/亞 -> 阿…) if raw form has no gloss.
        """

        def _lookup(h: str):
            out_local = []
            # 1) from curated vocab
            try:
                if isinstance(self._vocab, dict) and h in self._vocab:
                    v = self._vocab.get(h)
                    if isinstance(v, (list, tuple)) and v:
                        mv = v[0]
                        if isinstance(mv, (list, tuple, list)):
                            out_local.extend([str(x) for x in mv if x])
            except Exception:
                pass
            # Decide whether to prefer CC-Canto (Cantonese/colloquial) over CEDICT.
            prefer_cccanto = False
            try:
                if isinstance(h, str) and len(h) == 1:
                    prefer_cccanto = True
                elif hasattr(self, "_is_colloquial_hanzi") and callable(self._is_colloquial_hanzi):
                    prefer_cccanto = bool(self._is_colloquial_hanzi(h))
            except Exception:
                prefer_cccanto = False

            # 2) CC-Canto (prefer when available)
            if not out_local and prefer_cccanto:
                try:
                    idx_canto = self._load_cccanto_index()
                    if isinstance(idx_canto, dict):
                        out_local.extend(idx_canto.get(h, []) or [])
                except Exception:
                    pass

            # 3) CEDICT phrase-level (fallback)
            if not out_local:
                try:
                    idx_ce = self._load_cedict_index()
                    if isinstance(idx_ce, dict):
                        g_ce = idx_ce.get(h, []) or []
                        if g_ce:
                            out_local.extend(g_ce)
                except Exception:
                    pass

            # If we didn't prefer CC-Canto initially (e.g., multi-character words),
            # still try it as a fallback before giving up.
            if not out_local and (not prefer_cccanto):
                try:
                    idx_canto = self._load_cccanto_index()
                    if isinstance(idx_canto, dict):
                        out_local.extend(idx_canto.get(h, []) or [])
                except Exception:
                    pass
            # de-duplicate and trim
            seen, cleaned = set(), []
            for g in out_local:
                if g not in seen:
                    cleaned.append(g)
                    seen.add(g)
            return cleaned[:3]

        glosses = _lookup(hz)
        if glosses:
            return glosses
        hz_norm = self._normalize_hz_variant(hz)
        if hz_norm != hz:
            glosses = _lookup(hz_norm)
            if glosses:
                return glosses
        # Fallback: infer from second character when the first looks like a vocative/prefix
        try:
            if (not glosses) and isinstance(hz, str) and len(hz) == 2 and hz:
                prefix_first = hz[0]
                # Common Cantonese vocative/prefixal first chars
                PREFIXES = {"阿", "亞", "亚", "吖", "呀", "叭"}
                if prefix_first in PREFIXES:
                    tail = hz[1]
                    inferred = []
                    # a) CEDICT single-character gloss
                    try:
                        idx_ce = self._load_cedict_index()
                        if isinstance(idx_ce, dict):
                            inferred.extend(idx_ce.get(tail, []) or [])
                    except Exception:
                        pass
                    # b) CC‑Canto single-character gloss (if available in cache)
                    try:
                        from utils import get_cccanto_meanings_map
                        _mn = get_cccanto_meanings_map() or {}
                        if not inferred and tail in _mn:
                            inferred.extend(_mn.get(tail, []) or [])
                    except Exception:
                        pass
                    # De‑dup, cap, and tag as character-level inference
                    if inferred:
                        seen, cleaned = set(), []
                        for g in inferred:
                            if g not in seen:
                                cleaned.append(g)
                                seen.add(g)
                        return [f"{g} [char]" for g in cleaned[:3]]
        except Exception:
            pass
        return []

    def _load_cccanto_index(self):
        """Populate self._cccanto_index as {hanzi: [gloss1, gloss2, ...]} using a shared CC-Canto map.
        Safe if the helper or data are missing.
        """
        try:
            if hasattr(self, "_cccanto_index") and isinstance(self._cccanto_index, dict) and self._cccanto_index:
                return self._cccanto_index
        except Exception:
            pass

        self._cccanto_index = {}
        try:
            from utils import get_cccanto_meanings_map  # lazy import
            data = get_cccanto_meanings_map() or {}
            if isinstance(data, dict):
                # shallow copy with list values to avoid mutating shared cache
                self._cccanto_index = {str(k): list(v or []) for k, v in data.items()}
        except Exception:
            self._cccanto_index = {}
        return self._cccanto_index

    def _clean_meanings_tags(self, glosses):
        """
        Remove square-bracket tags like “[char]”, “[dialect]” from meanings for the Meanings field.
        Parenthetical notes remain. Returns up to the original number of items with empties removed.
        """
        import re
        cleaned = []
        for g in (glosses or []):
            s = re.sub(r"\[[^]]*]", "", str(g)).strip()
            if s:
                cleaned.append(s)
        return cleaned

    def _build_category_profiles(self) -> None:
        """
        Build lightweight token-frequency profiles per category from existing vocab meanings.

        Populates self._cat_keywords as:
            {category_name: {token: weight, ...}, ...}

        These are used as a soft hint when ranking reverse-lookup candidates so items whose
        glosses look similar to other items in the active category get a small score boost.
        """
        try:
            import re
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

    def _rerank_candidates_with_meanings(self, cands: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
        """Prefer candidates that:
           0) prefer Cantonese / colloquial (`yue`) register first, then neutral/both, then literary-only;
           1) have clean phrase-level glosses;
           2) have any phrase-level gloss;
           3) for 2-char forms, both characters have independent glosses;
           4) else at least one character has an independent gloss;
           5) use colloquial forms (阿… over 亚/亞… etc.);
           6) have higher frequency;
           7) come from stronger sources.
        """
        # Active category hint from the Add panel; used to gently nudge candidates whose glosses
        # look similar (in English) to existing items in that category.
        try:
            active_cat = ""
            if hasattr(self, "_add_cat") and getattr(self, "_add_cat", None) is not None:
                active_cat = (self._add_cat.currentText() or "").strip()
        except Exception:
            active_cat = ""

        def category_score_for_glosses(glosses: list[str], active_cat_name: str) -> float:
            """
            Data-driven category hint score.

            Uses self._cat_keywords, which is a bag-of-words profile built from existing
            vocab + category assignments. We tokenise the candidate glosses and sum the
            weights of any tokens that appear in the active category profile.

            Returns a small float; higher means "more like other items in this category".
            """
            if not active_cat_name:
                return 0.0

            try:
                profiles = getattr(self, "_cat_keywords", {}) or {}
                kw = profiles.get(active_cat_name) or profiles.get(str(active_cat_name).lower())
            except Exception:
                kw = None
            if not kw:
                return 0.0

            import re
            token_re = re.compile(r"[a-z]+")
            seen_tokens: set[str] = set()
            score = 0.0

            for g in (glosses or []):
                text = str(g).lower()
                for tok in token_re.findall(text):
                    if tok in seen_tokens:
                        continue
                    seen_tokens.add(tok)
                    try:
                        score += float(kw.get(tok, 0.0))
                    except Exception:
                        continue
            # Debug log for category scoring
            try:
                logger.debug(
                    "CategoryHint: active_cat='%s', gloss_tokens=%r, score=%.4f",
                    active_cat_name,
                    list(seen_tokens),
                    score,
                )
            except Exception:
                pass
            return score

        # Prepare lightweight indices for character-level checks
        try:
            idx_ce = self._load_cedict_index()  # {hanzi: [gloss,...]}
        except Exception:
            idx_ce = {}
        try:
            from utils import get_cccanto_meanings_map  # char-level backup
            idx_canto = get_cccanto_meanings_map() or {}
        except Exception:
            idx_canto = {}

        def source_score(src: str) -> int:
            order = [
                "andys_list", "builtin", "hkcancor", "subtitles", "cccanto", "pycantonese",
                "tier2-char-ranked", "tier2"
            ]
            try:
                return len(order) - order.index(src)
            except Exception:
                return 0

        def char_has_gloss(ch: str) -> bool:
            if not ch:
                return False
            try:
                if ch in idx_ce and idx_ce[ch]:
                    return True
            except Exception:
                pass
            try:
                if ch in idx_canto and idx_canto[ch]:
                    return True
            except Exception:
                pass
            return False

        def split_clean(glosses: list[str]) -> tuple[list[str], list[str]]:
            """Return (clean, tagged) where clean has no square-bracket tags or parentheses.
            We treat any '[' or ']' or parenthetical as a tag indicator (e.g., "[char]", "[dialect]", "(variant)").
            """
            clean, tagged = [], []
            for g in (glosses or []):
                s = str(g)
                if ("[" in s and "]" in s) or ("(" in s and ")" in s):
                    tagged.append(s)
                else:
                    clean.append(s)
            return clean, tagged

        def register_score_for_glosses(glosses: list[str]) -> int:
            """
            Heuristic register scoring from gloss tags/content:
              2 -> explicitly Cantonese / colloquial (yue)
              1 -> neutral/unspecified (both / general)
              0 -> explicitly literary/written-only
            """
            if not glosses:
                return 1  # neutral by default

            text = " ".join(str(g) for g in glosses).lower()

            # Heuristic markers for Cantonese / colloquial
            yue_markers = ["[yue]", "[粵]", "[粵語]", " cantonese ", "(cantonese)", "(colloquial)"]
            is_yue = any(m in text for m in yue_markers)

            # Heuristic markers for literary / written registers
            lit_markers = ["[lit]", " literary ", "(literary)", "(written)"]
            is_lit = any(m in text for m in lit_markers)

            if is_yue and not is_lit:
                return 2
            if is_yue and is_lit:
                return 2  # treat as usable in spoken as well
            if not is_yue and is_lit:
                return 0
            return 1

        scored: list[tuple[tuple[float, int, int, int, int, int, int, int, int], tuple[str, str, int]]] = []
        for (hz, src, freq) in (cands or []):
            # Gather glosses using existing resolver
            try:
                glosses = self._get_meanings_for_hanzi(hz) or []
            except Exception:
                glosses = []

            reg_score = register_score_for_glosses(glosses)
            cat_score = category_score_for_glosses(glosses, active_cat)

            clean, tagged = split_clean(glosses)
            has_clean_phrase = 1 if clean else 0
            has_any_phrase = 1 if glosses and any("[char]" not in g for g in glosses) else 0

            # Character-coverage
            both_chars_gloss = 0
            one_char_gloss = 0
            if isinstance(hz, str) and len(hz) == 2:
                c1, c2 = hz[0], hz[1]
                g1 = char_has_gloss(c1)
                g2 = char_has_gloss(c2)
                if g1 and g2:
                    both_chars_gloss = 1
                elif g1 or g2:
                    one_char_gloss = 1

            # Colloquial bonus: prefer 阿…
            first = hz[0] if hz else ""
            colloquial_bonus = 1 if first == "阿" else 0

            # Frequency (already an int-like score from upstream ranking), default 0
            try:
                freq_i = int(freq or 0)
            except Exception:
                freq_i = 0

            scored.append((
                (
                    float(reg_score),  # 0) register score: yue > neutral > literary
                    int(cat_score > 0.0),  # 1) category hint present (coarse flag)
                    has_clean_phrase,  # 2) clean phrase-level glosses
                    has_any_phrase,  # 3) any phrase-level gloss (non-[char])
                    both_chars_gloss,  # 4) both chars have glosses
                    one_char_gloss,  # 5) at least one char has gloss
                    colloquial_bonus,  # 6) 阿… preferred
                    freq_i,  # 7) higher frequency
                    source_score(src)  # 8) stronger source
                ),
                (hz, src, freq)
            ))

        # Descending order by the composite tuple; the sort is stable for ties
        scored.sort(reverse=True)
        return [item for _score, item in scored]

    def _get_reverse_candidates(self, jy_n: str) -> list[tuple[str, str, int]]:
        """Tier-1 reverse lookup: ask the dialog's reverse-candidate provider if present."""
        cands: list[tuple[str, str, int]] = []
        try:
            if hasattr(self, "_reverse_candidates_for_jy") and callable(self._reverse_candidates_for_jy):
                cands = self._reverse_candidates_for_jy(jy_n) or []
        except Exception:
            cands = []
        return cands

    def _maybe_tier2_fallback_single_syllable(
        self,
        jy_n: str,
        n_syllables: int,
        cands: list[tuple[str, str, int]],
    ) -> list[tuple[str, str, int]]:
        """Tier-2 fallback for single-syllable Jyutping only.

        For multi-syllable phrases we intentionally avoid char-map heuristics.
        """
        if cands:
            return cands
        if n_syllables != 1:
            return cands

        try:
            compose_fn = None
            shortlist_fn = None
            if hasattr(self, "_get_compose_and_rank") and callable(self._get_compose_and_rank):
                try:
                    compose_fn, shortlist_fn = self._get_compose_and_rank()
                except Exception:
                    compose_fn, shortlist_fn = None, None

            # Prefer a proper composer if available
            if callable(compose_fn) and isinstance(getattr(self, "_char_map", None), dict) and self._char_map:
                try:
                    # noinspection PyTypeChecker
                    tier2 = compose_fn(jy_n, self._char_map) or []
                except Exception:
                    tier2 = []

                try:
                    if callable(shortlist_fn) and tier2:
                        # noinspection PyTypeChecker
                        tier2 = shortlist_fn(tier2) or tier2
                except Exception:
                    pass

                # Expect tier2 as iterable of (hanzi, score) or (hanzi, score, src);
                # normalise to (hanzi, "tier2", freq_like)
                cands_tier2: list[tuple[str, str, int]] = []
                for item in (tier2 or []):
                    try:
                        if not item:
                            continue
                        if len(item) >= 2:
                            hz = item[0]
                            score = item[1]
                        else:
                            continue
                        freq_like = int(score) if isinstance(score, (int, float)) else 0
                        cands_tier2.append((hz, "tier2", freq_like))
                    except Exception:
                        continue

                if cands_tier2:
                    cands = cands_tier2
                    try:
                        logger.debug(
                            "revlookup tier2: composed %d candidates for '%s' via Unihan",
                            len(cands),
                            jy_n,
                        )
                    except Exception:
                        pass

            # Minimal fallback: if no composer, try single-character matches from the char map.
            if (not cands) and isinstance(getattr(self, "_char_map", None), dict) and self._char_map:
                matches: list[tuple[str, str, int]] = []
                try:
                    for ch, readings in self._char_map.items():
                        try:
                            for r in (readings or []):
                                if self._normalize_jy(r) == jy_n:
                                    matches.append((ch, "tier2-char", 1))
                                    break
                        except Exception:
                            continue
                except Exception:
                    matches = []

                if matches:
                    cands = matches
                    try:
                        logger.debug(
                            "revlookup tier2-char: %d single-character matches for '%s'",
                            len(cands),
                            jy_n,
                        )
                    except Exception:
                        pass
        except Exception:
            # Any failure in tier-2 fallback should be silent from the user's perspective.
            pass

        return cands

    def _maybe_reverse_jyut_phrase_fallback(
        self,
        jy_n: str,
        n_syllables: int,
        cands: list[tuple[str, str, int]],
    ) -> list[tuple[str, str, int]]:
        """Phrase fallback via reverse_jyut.yaml for 2+ syllables when no candidates exist."""
        if cands:
            return cands
        if n_syllables < 2:
            return cands

        try:
            rev = self._load_reverse_jyut_map() if hasattr(self, "_load_reverse_jyut_map") else {}
            hits = (rev.get(jy_n) or []) if isinstance(rev, dict) else []
            if hits:
                # Give earlier hits a slightly higher pseudo-frequency
                cands = [(hz, "reverse_jyut", max(1, len(hits) - i)) for i, hz in enumerate(hits)]
                try:
                    logger.debug("revlookup reverse_jyut: %d candidate(s) for '%s'", len(cands), jy_n)
                except Exception:
                    pass
        except Exception:
            pass

        return cands

    def _postprocess_candidates(
        self,
        cands: list[tuple[str, str, int]],
        n_syllables: int,
    ) -> list[tuple[str, str, int]]:
        """Rerank, curate, phrase-filter, and dedupe candidates without UI side-effects."""
        # Re-rank to prefer items with glosses and colloquial forms
        try:
            cands = self._rerank_candidates_with_meanings(cands)
        except Exception:
            pass

        # Optional: debug after ranking
        try:
            logger.debug("rank: clean-first order -> %s", [c[0] for c in cands])
        except Exception:
            pass

        # Restrict to top N, preferring colloquial entries when available
        try:
            ranked_hz = self._curate_top_hanzi_candidates([hz for (hz, _, _) in cands])
            cands = [c for c in cands if c[0] in ranked_hz]
        except Exception:
            cands = cands[: self.MAX_HANZI_CANDIDATES]

        # In phrase mode (multi-syllable Jyutping), drop single-character candidates
        try:
            if isinstance(cands, list) and cands and n_syllables >= 2:
                filtered: list[tuple[str, str, int]] = []
                for hz, src, freq in cands:
                    try:
                        if isinstance(hz, str) and len(hz) == 1:
                            continue
                    except Exception:
                        pass
                    filtered.append((hz, src, freq))
                if filtered:
                    cands = filtered
        except Exception:
            pass

        # Deduplicate candidates by Hanzi after ranking so the combobox does not show repeats
        try:
            if isinstance(cands, list) and len(cands) > 1:
                seen_hz: set[str] = set()
                deduped: list[tuple[str, str, int]] = []
                for hz, src, freq in cands:
                    if hz in seen_hz:
                        continue
                    seen_hz.add(hz)
                    deduped.append((hz, src, freq))
                cands = deduped
        except Exception:
            pass

        return cands

    def _get_all_hanzi_candidates(self, jy_n: str, n_syllables: int) -> list[tuple[str, str, int]]:
        """Acquire raw Hanzi candidates via tiered reverse lookup (no UI side-effects)."""
        cands = self._get_reverse_candidates(jy_n)
        cands = self._maybe_tier2_fallback_single_syllable(jy_n, n_syllables, cands)
        cands = self._maybe_reverse_jyut_phrase_fallback(jy_n, n_syllables, cands)
        return cands

    def _prefill_candidate_gloss_cache(self, cands: list[tuple[str, str, int]]) -> None:
        """Preload a small CC‑Canto gloss cache for current candidates (best-effort)."""
        try:
            from utils import get_cccanto_meanings_map
            meanings_map = get_cccanto_meanings_map() or {}
        except Exception:
            meanings_map = {}

        if not hasattr(self, "_cand_gloss_cache") or not isinstance(self._cand_gloss_cache, dict):
            self._cand_gloss_cache = {}

        def _hz_variants(hz: str) -> list[str]:
            out = []
            if not hz:
                return out
            out.append(hz)
            try:
                if hasattr(self, "_normalize_hz_variant") and callable(self._normalize_hz_variant):
                    hz_norm = self._normalize_hz_variant(hz)
                    if hz_norm and hz_norm not in out:
                        out.append(hz_norm)
            except Exception:
                pass
            try:
                first, rest = hz[0], hz[1:]
                for alt in ("阿", "亞", "亚", "吖", "呀"):
                    if alt != first:
                        out.append(alt + rest)
            except Exception:
                pass
            return out

        prefilled = 0
        for hz, _src, _freq in cands:
            if not hz or hz in self._cand_gloss_cache:
                continue
            for v in _hz_variants(hz):
                try:
                    glosses = meanings_map.get(v)
                    if glosses:
                        self._cand_gloss_cache[hz] = list(glosses)[:3]
                        prefilled += 1
                        break
                except Exception:
                    continue

        if prefilled:
            try:
                logger.debug("prefill: cached glosses for %d/%d candidates via CC‑Canto", prefilled, len(cands))
            except Exception:
                pass

    def _populate_candidate_combobox(
        self,
        cands: list[tuple[str, str, int]],
        preferred_hz: str | None,
    ) -> None:
        """Populate the Hanzi candidates combobox with labels and meanings."""
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
            return

        items: list[tuple[str, str]] = []

        for hz, src, freq in cands:
            glosses = []
            tag_hint = None

            try:
                glosses = self._cand_gloss_cache.get(hz, [])
                if glosses:
                    tag_hint = "CC"
            except Exception:
                pass

            if not glosses:
                try:
                    glosses = self._get_meanings_for_hanzi(hz) or []
                except Exception:
                    glosses = []

            if not glosses:
                continue

            try:
                from utils import clean_glosses_for_display
                glosses = clean_glosses_for_display(glosses)
            except Exception:
                pass

            clean = [g for g in glosses if "[" not in g and "(" not in g]
            shown = clean[:2] if clean else glosses[:2]

            tag = tag_hint
            if not tag:
                try:
                    tag = abbr_for_source(src)
                except Exception:
                    tag = "UNK"

            label = f"{hz} — {', '.join(shown)} ({tag})"
            if hz == preferred_hz:
                label = f"✓ {label}"

            items.append((label, hz))

        try:
            self._cand_combo.clear()
            placeholder = "— choose a Hanzi —"
            self._cand_combo.addItem(placeholder)
            try:
                m = self._cand_combo.model()
                if m is not None:
                    from PySide6.QtCore import Qt as _Qt_
                    m.setData(m.index(0, 0), 0, int(_Qt_.ItemDataRole.UserRole) - 1)
            except Exception:
                pass

            for text, data in items:
                self._cand_combo.addItem(text, userData=data)

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
        try:
            preferred_hz = cands[0][0] if isinstance(cands, list) and cands else None
        except Exception:
            preferred_hz = None

        if preferred_hz:
            try:
                if getattr(self, "_add_hz", None) is not None:
                    self._add_hz.setText(preferred_hz)
            except Exception:
                pass

        return preferred_hz

    def _clear_candidate_view_highlight(self) -> None:
        try:
            v = self._cand_combo.view()
            if v is not None:
                from PySide6.QtCore import QModelIndex
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

        glosses_single = []
        try:
            if hasattr(self, "_get_meanings_for_hanzi") and callable(self._get_meanings_for_hanzi):
                glosses_single = self._get_meanings_for_hanzi(single_hz) or []
        except Exception:
            glosses_single = []

        if not glosses_single:
            try:
                from utils import get_cccanto_meanings_map
                _mn_single = get_cccanto_meanings_map() or {}
                glosses_single = list(_mn_single.get(single_hz, []))
                if (not glosses_single) and hasattr(self, "_normalize_hz_variant") and callable(self._normalize_hz_variant):
                    hz_norm = self._normalize_hz_variant(single_hz)
                    if hz_norm and hz_norm != single_hz:
                        glosses_single = list(_mn_single.get(hz_norm, []))
            except Exception:
                pass

        if not glosses_single:
            try:
                from utils import get_cccanto_glosses_for
                glosses_single = get_cccanto_glosses_for(single_hz) or []
            except Exception:
                glosses_single = []

        try:
            if getattr(self, "_add_mn", None) is not None:
                clean = self._clean_meanings_tags(glosses_single) if hasattr(self, "_clean_meanings_tags") else list(glosses_single or [])
                self._add_mn.setText(", ".join(clean) if clean else "")
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
            logger.debug("AddItem: auto-filled meanings for single candidate '%s' -> %r", single_hz, (glosses_single[:3] if glosses_single else []))
        except Exception:
            pass

    def _apply_ambiguity_notes(self, jy_n: str, n_syllables: int, cands: list[tuple[str, str, int]]) -> None:
        """Set notes based on domain ambiguity rules (UI-free logic lives in domain.category_rules)."""
        try:
            top_glosses = None
            try:
                if isinstance(cands, list) and cands:
                    top_hz = cands[0][0]
                    if top_hz and hasattr(self, "_get_meanings_for_hanzi") and callable(self._get_meanings_for_hanzi):
                        top_glosses = self._get_meanings_for_hanzi(top_hz) or []
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
                        ms = []
                        if hasattr(self, "_get_meanings_for_hanzi") and callable(self._get_meanings_for_hanzi):
                            ms = self._get_meanings_for_hanzi(hz) or []
                        try:
                            from utils import clean_glosses_for_display
                            ms = clean_glosses_for_display(ms)
                        except Exception:
                            pass
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

    def _fill_hanzi_candidates(self, jy: str):
        try:
            jy_n = self._normalize_jy(jy)
            # If the user has opted to type their own Hanzi, do not overwrite or re-suggest.
            try:
                if bool(getattr(self, "_manual_hanzi_mode", False)):
                    logger.debug("_fill_hanzi_candidates: manual Hanzi mode active; skipping auto-fill")
                    return 0
            except Exception:
                pass
            # Split normalised Jyutping into syllables so we can distinguish single-syllable vs phrase cases.
            syllables = jy_n.split()
            n_syllables = len(syllables) if syllables else 0

            # Use helper to get all candidates (tiered lookup)
            cands = self._get_all_hanzi_candidates(jy_n, n_syllables)
            # Post-process: rerank, curate, phrase-filter, and dedupe
            cands = self._postprocess_candidates(cands, n_syllables)

            # If still no candidates, switch to "manual Hanzi" affordance: show the button (if present)
            # and put focus into the Hanzi field so the user can type/paste.
            if not cands:
                return self._handle_no_hanzi_candidates()

            # Set the Hanzi field to the top candidate and get the preferred Hanzi
            preferred_hz = self._set_hanzi_top_candidate(cands)

            # Preload a small cache of glosses for current candidates using CC‑Canto + variant swaps
            self._prefill_candidate_gloss_cache(cands)

            # Populate candidates combobox with inline meanings when possible
            self._populate_candidate_combobox(cands, preferred_hz)

            # Clear any pre-highlight in combobox view
            self._clear_candidate_view_highlight()

            # If exactly one candidate, auto-copy its glosses into Meanings and focus there
            self._maybe_autofill_single_candidate_meanings(cands)

            # Ambiguity → notes (deterministic; do not persist for auto-default)
            self._apply_ambiguity_notes(jy_n, n_syllables, cands)

            # Tooltip preview on the Hanzi field for quick glance
            self._update_hanzi_tooltip_preview(cands)

            # Nudge UI to update immediately
            try:
                self._add_hz.repaint()
                self._add_hz.update()
            except Exception:
                pass
            return len(cands)
        except Exception:
            # Keep UI consistent even if an unexpected error occurs
            try:
                self._add_hz.clear()
                self._add_hz.setToolTip("")
                self._cand_combo.setVisible(False)
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
        glosses = []
        try:
            if hasattr(self, "_get_meanings_for_hanzi") and callable(self._get_meanings_for_hanzi):
                glosses = self._get_meanings_for_hanzi(hz) or []
        except Exception:
            glosses = []

        if glosses:
            try:
                clean = self._clean_meanings_tags(glosses) if hasattr(self, "_clean_meanings_tags") else glosses
                mn_edit.setText(", ".join(clean))
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

    def _is_placeholder_category(self) -> bool:
        """Return True if the current category is the UI-only placeholder 'Not yet assigned'."""
        try:
            txt = (self._add_cat.currentText() or "").strip().lower()
            return txt == "not yet assigned"
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

        # Validate Jyutping; if invalid, warn and keep focus in Jyutping.
        try:
            ok = self._attested_or_structural_ok(jy_text) if hasattr(self, "_attested_or_structural_ok") else True
        except Exception:
            ok = True

        if not ok:
            try:
                QMessageBox.warning(
                    self,
                    "Jyutping",
                    "The Jyutping you entered does not look valid.\n"
                    "Please check the syllables and tone numbers.",
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

            # Visually hint that Category now needs attention: style the placeholder and open the dropdown.
        try:
            if cat is not None:
                # Drop down the category list so the focus change is obvious.
                try:
                    cat.showPopup()
                except Exception:
                    pass
        except Exception:
            pass

            # Refresh Save state, but do not attempt reverse lookup or category warnings yet.
        try:
            if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                self._update_save_enabled()
        except Exception:
            pass

    def _has_valid_inputs(self) -> bool:
        """
        Validation gate for enabling the Save button in the Add/Edit panel.

        New workflow alignment
        ----------------------
        We treat the Add panel as valid (Save enabled) if:

          1) Jyutping:
             - Non-empty, and
             - Structurally valid / attested according to our Jyutping validator.

          2) Category:
             - Non-empty after stripping whitespace.
             - 'unassigned' is allowed; we still expect the rest of the entry to be complete.

          3) Hanzi:
             - The read-only Hanzi field has some non-empty text.
               (i.e., the user has either accepted the top candidate or chosen from the dropdown.)

          4) Meanings:
             - At least one non-empty meaning token after splitting on commas,
               or a single non-empty string.
               This ensures we don’t commit entries with completely blank glosses.

        If any of these conditions fail, Save is disabled. This keeps the UI responsive while
        still enforcing that an entry is "complete enough" for learner-facing vocab.
        """
        # Prefer new Add-Item widgets; fall back to legacy attributes if present
        jy_le = getattr(self, "_add_jy", getattr(self, "editJyut", None))
        mn_le = getattr(self, "_add_mn", getattr(self, "editMeanings", None))
        hz_le = getattr(self, "_add_hz", None)
        cat_cb = getattr(self, "_add_cat", getattr(self, "comboCategory", None))

        # 1) Jyutping: must be present and structurally/attested OK
        jy = (jy_le.text() if jy_le is not None else "").strip()
        if not jy:
            try:
                logger.debug("_has_valid_inputs: invalid -> empty Jyutping")
            except Exception:
                pass
            return False

        # Prefer the dialog's attestation-aware check if present
        try:
            if hasattr(self, "_attested_or_structural_ok") and callable(self._attested_or_structural_ok):
                jy_ok = bool(self._attested_or_structural_ok(jy))
            elif hasattr(self, "_validate_jyut_syllables") and callable(self._validate_jyut_syllables):
                jy_ok = bool(self._validate_jyut_syllables(jy))
            elif hasattr(self, "_validate_jyut") and callable(self._validate_jyut):
                jy_ok = bool(self._validate_jyut(jy))
            else:
                jy_ok = True  # last-resort fallback if no validator is wired
        except Exception:
            jy_ok = True

        if not jy_ok:
            try:
                logger.debug("_has_valid_inputs: invalid -> Jyutping failed validation: %r", jy)
            except Exception:
                pass
            return False

        # 2) Category: must be non-empty after stripping; 'unassigned' is allowed
        cat_txt = ""
        try:
            if cat_cb is not None:
                # Editable combobox: prefer its lineEdit if present
                if hasattr(cat_cb, "isEditable") and cat_cb.isEditable() and cat_cb.lineEdit() is not None:
                    cat_txt = (cat_cb.lineEdit().text() or "").strip()
                else:
                    cat_txt = (cat_cb.currentText() or "").strip()
        except Exception:
            cat_txt = ""

        # Category must be explicitly chosen/entered.
        if not cat_txt:
            try:
                logger.debug("_has_valid_inputs: invalid -> empty category")
            except Exception:
                pass
            return False

        # 3) Hanzi: the resolved Hanzi must be present
        hz_txt = ""
        try:
            if hz_le is not None:
                hz_txt = (hz_le.text() or "").strip()
        except Exception:
            hz_txt = ""

        if not hz_txt:
            try:
                logger.debug("_has_valid_inputs: invalid -> empty Hanzi field")
            except Exception:
                pass
            return False

        # 4) Meanings: require at least one non-empty token
        mn_txt = ""
        try:
            if mn_le is not None:
                mn_txt = (mn_le.text() or "").strip()
        except Exception:
            mn_txt = ""

        if not mn_txt:
            try:
                logger.debug("_has_valid_inputs: invalid -> empty meanings field")
            except Exception:
                pass
            return False

        # Split on commas and check that at least one token survives stripping
        try:
            tokens = [t.strip() for t in mn_txt.split(",")] if "," in mn_txt else [mn_txt.strip()]
            has_meaning = any(t for t in tokens)
        except Exception:
            has_meaning = bool(mn_txt)

        if not has_meaning:
            try:
                logger.debug("_has_valid_inputs: invalid -> no non-empty meaning tokens in %r", mn_txt)
            except Exception:
                pass
            return False

        try:
            logger.debug(
                "_has_valid_inputs: OK (jy=%r, cat=%r, hz=%r, meanings=%r)",
                jy, cat_txt, hz_txt, mn_txt,
            )
        except Exception:
            pass
        return True


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

    def _on_candidate_text_changed(self, text: str) -> None:
        """Keep the read-only Hanzi field in sync with the candidate combobox text."""
        try:
            if getattr(self, "_add_hz", None) is not None:
                self._add_hz.setText(text or "")
        except Exception:
            pass

    def _on_candidate_index_activated(self, i: int) -> None:
        """Apply the chosen candidate (index) into Hanzi + meanings + notes."""
        try:
            hz = None
            try:
                hz = self._cand_combo.itemData(i) if getattr(self, "_cand_combo", None) is not None else None
            except Exception:
                hz = None
            if not hz and getattr(self, "_cand_combo", None) is not None:
                hz = self._cand_combo.itemText(i)

            if not hz:
                return

            # Skip placeholder-ish entries
            try:
                if getattr(self, "_cand_combo", None) is not None:
                    label = (self._cand_combo.itemText(i) or "").strip()
                    if label.startswith("— choose"):
                        return
            except Exception:
                pass

            hz = (str(hz) or "").strip()
            if not hz:
                return

            try:
                self._add_hz.setText(hz)
            except Exception:
                pass

            # Prefer CC-Canto glosses for display; avoid overwriting with fallback meanings.
            glosses: list[str] = []
            try:
                if hasattr(self, "_get_meanings_for_hanzi") and callable(self._get_meanings_for_hanzi):
                    glosses = self._get_meanings_for_hanzi(hz) or []
            except Exception:
                glosses = []

            try:
                from utils import clean_glosses_for_display
                glosses = clean_glosses_for_display(glosses)
            except Exception:
                pass

            # Only fall back if we truly have no glosses
            if not glosses:
                try:
                    from utils import get_cccanto_glosses_for
                    glosses = get_cccanto_glosses_for(hz) or []
                except Exception:
                    glosses = []

            # Notes only when ambiguous (multi-sense)
            try:
                if glosses and len(glosses) > 1:
                    self._set_notes(
                        "Selected Hanzi has multiple senses in this context.",
                        source="chatgpt-style",
                    )
                else:
                    self._set_notes("", source="auto-default")
            except Exception:
                pass

            # Clean bracketed tags before inserting into Meanings
            try:
                if hasattr(self, "_clean_meanings_tags"):
                    clean = self._clean_meanings_tags(glosses or [])
                else:
                    import re as _re
                    _tag = _re.compile(r"\s*[(\[].*?[)\]]\s*")
                    clean = [_tag.sub("", str(g)).strip() for g in (glosses or []) if str(g).strip()]
                self._add_mn.setText(", ".join(clean) if clean else "")
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
        except Exception:
            # Never allow candidate selection to crash the dialog
            try:
                if hasattr(self, "_update_save_enabled") and callable(self._update_save_enabled):
                    self._update_save_enabled()
            except Exception:
                pass