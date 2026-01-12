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
        # we must not overwrite it with any later autofill.
        self._manual_hanzi_mode = False
        self._cat_combo_ctrl = None
        # One-time Add/Edit signal wiring guard (prevents duplicate connects on some Qt builds)
        self._add_edit_wired = False

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
        # --- Persist vocab input under stable attribute names (tests + UI rely on these) ---
        # Keep a legacy alias to the caller-provided vocab map, but do not use it as the
        # authoritative internal store.
        try:
            if isinstance(vocab_items, dict):
                self.vocab_items = vocab_items  # legacy / tests only
        except (AttributeError, TypeError, ValueError, RuntimeError):
            pass

        # In-memory vocab (shallow copy to avoid mutating callers)
        self._vocab = {
            k: (
                list(v[0]) if isinstance(v, (list, tuple)) and v else [],
                v[1] if isinstance(v, (list, tuple)) and len(v) > 1 else "",
            )
            for k, v in (vocab_items or {}).items()
        }

        # In-memory categories (authoritative). Start as a defensive copy.
        self._cats = {
            str(k).strip(): list(v or [])
            for k, v in (categories_map or {}).items()
            if str(k).strip()
        }

        # Single source of truth: `_cats` is authoritative in this dialog.
        # `_categories_map` is a legacy alias/view; it must not be consulted as an authority.
        self._categories_map = self._cats

        # Repo + commit service wiring (UI-free). These modules own invariants and persistence.
        # IMPORTANT: CategoryRepo currently maintains its own internal dict; therefore, after
        # constructing it, we must re-point `self._cats` at the repo's internal map so that
        # UI tests asserting against `dlg._cats` observe the authoritative store.
        self._cat_repo = None
        self._cat_commit_svc = None

        try:
            from category_repo import CategoryRepo
            from category_commit import CategoryCommitService

            canon_fn = getattr(self, "_canon_cat_name", None)

            # Persistence: repo expects persist(cats_map). Most existing persistence fns are
            # zero-arg; adapt them rather than changing their signatures.
            # Persistence: write categories.yaml directly.
            # Domain repo/service own mutation; the dialog owns the file-write boundary.

            persist_cb = None
            try:
                def persist_cb(_cats_map: dict) -> None:
                    try:
                        persist_categories_yaml(_cats_map)
                    except ():
                        return
            except (AttributeError, TypeError, RuntimeError):
                persist_cb = None

            repo = CategoryRepo(
                self._cats,
                canon=canon_fn if callable(canon_fn) else None,
                persist=persist_cb,
            )

            # Re-point dialog-authoritative map to the repo's internal store.
            # This keeps the invariant: after successful add-category flow, `self._cats[cat]` exists.
            try:
                repo_map = getattr(repo, "_cats", None)
            except (TypeError, AttributeError, RuntimeError):
                repo_map = None

            if isinstance(repo_map, dict):
                self._cats = repo_map
                self._categories_map = self._cats

            # Keep any other legacy map coherent if present (best-effort only).
            try:
                legacy_map = getattr(self, "_categories_map", None)
            except (TypeError, AttributeError, RuntimeError):
                legacy_map = None

            try:
                if legacy_map is not None and hasattr(repo, "sync_to"):
                    repo.sync_to(legacy_map)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

            self._cat_repo = repo
            self._cat_commit_svc = CategoryCommitService(repo)

        except (ImportError, ModuleNotFoundError):
            self._cat_repo = None
            self._cat_commit_svc = None

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
        try:
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
        except (TypeError, ValueError):
            # Logging must never break dialog creation.
            pass

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

        try:
            combo.blockSignals(True)
        except (TypeError, AttributeError, RuntimeError):
            pass

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

        # Always provide a minimal pipeline, so call sites never need to guard against None.
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

        # ---- Typography ----
        self._apply_add_edit_typography(
            group_entry=group_entry,
            form_entry=form_entry,
            group_hanzi=group_hanzi,
            form_hanzi=form_hanzi,
        )

        # ---- Vocab table scroll panel (preferred) ----
        self._table_panel_ctrl = None
        self._table_panel = None

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

                    # Populate panel data.
                    # IMPORTANT: legacy `_rebuild_items_model()` targets a QTableWidget.
                    # The new panel may expose QTableView/QAbstractItemView, so prefer the
                    # controller's explicit population API when available.
                    try:
                        populated = False

                        # 1) Preferred: controller population hooks (single source of truth)
                        # Try a small, explicit set of method names (no broad guessing ladders).
                        for meth in (
                            "set_vocab_and_categories",
                            "set_data",
                            "set_maps",
                            "populate_from_maps",
                            "populate",
                            "refresh",
                        ):
                            fn = getattr(self._table_panel_ctrl, meth, None)
                            if not callable(fn):
                                continue
                            try:
                                # Most likely signature: (vocab, cats)
                                fn(getattr(self, "_vocab", {}), getattr(self, "_cats", {}))
                                populated = True
                                break
                            except TypeError:
                                try:
                                    # Alternate: accept just vocab
                                    fn(getattr(self, "_vocab", {}))
                                    populated = True
                                    break
                                except TypeError:
                                    try:
                                        # Alternate: zero-arg refresh
                                        fn()
                                        populated = True
                                        break
                                    except (TypeError, AttributeError, RuntimeError):
                                        pass
                            except ():
                                # Best-effort: keep trying other hooks.
                                pass

                        # 2) Fallback: if the panel actually contains a QTableWidget, reuse legacy rebuild.
                        if not populated:
                            tbl = getattr(self, "_table", None)
                            if isinstance(tbl, QTableWidget):
                                fn_rebuild = getattr(self, "_rebuild_items_model", None)
                                if callable(fn_rebuild):
                                    fn_rebuild()
                                    populated = True

                        # Diagnostics: log what we ended up with (must never raise)
                        try:
                            tbl = getattr(self, "_table", None)
                            if tbl is not None:
                                cls = type(tbl).__name__
                                rows = None
                                try:
                                    # QTableWidget
                                    if hasattr(tbl, "rowCount"):
                                        rows = int(tbl.rowCount())
                                except (TypeError, AttributeError, RuntimeError):
                                    rows = None
                                if rows is None:
                                    try:
                                        # QTableView-like
                                        m = tbl.model() if hasattr(tbl, "model") else None
                                        rows = int(m.rowCount()) if m is not None and hasattr(m, "rowCount") else None
                                    except (TypeError, AttributeError, RuntimeError):
                                        rows = None
                                logger.debug(
                                    "Table panel populated=%s table=%s rows=%s",
                                    bool(populated),
                                    cls,
                                    rows if rows is not None else "?",
                                )
                        except (TypeError, AttributeError, RuntimeError):
                            pass

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

            # Populate rows immediately.
            # Prefer the newer row-population path when present; fall back to the legacy rebuild.
            fn_populate = getattr(self, "_populate_rows", None)
            if callable(fn_populate):
                try:
                    fn_populate()
                except (TypeError, AttributeError, RuntimeError):
                    # If the newer path fails for any reason, fall back to the legacy rebuild.
                    fn_populate = None

            if fn_populate is None:
                fn_rebuild = getattr(self, "_rebuild_items_model", None)
                if callable(fn_rebuild):
                    fn_rebuild()

            try:
                rows = "?"
                if self._table is not None and hasattr(self._table, "rowCount"):
                    try:
                        rows = str(int(self._table.rowCount()))
                    except (TypeError, AttributeError, RuntimeError):
                        rows = "?"
                logger.debug(
                    "Legacy table ready: type=%s rows=%s",
                    type(self._table).__name__ if self._table is not None else "None",
                    rows,
                )
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

    def _apply_add_edit_typography(
            self,
            *,
            group_entry: QGroupBox,
            form_entry: QFormLayout,
            group_hanzi: QGroupBox,
            form_hanzi: QFormLayout,
    ) -> None:
        """Apply the Add/Edit panel typography in one place.

        - Labels: +_LABEL_FONT_DELTA_PT
        - Input fields (Jyutping, Meanings, Hanzi): +_INPUT_FONT_DELTA_PT
        - Form vertical spacing: _FORM_VERTICAL_SPACING_PX

        Best-effort only: this must never break dialog construction.
        """
        # Spacing first (Qt may raise TypeError on some bindings)

        try:
            from PySide6.QtCore import Qt
        except (ImportError, ModuleNotFoundError):
            Qt = None
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
        input_hanzi.setPointSize(int(self._HANZI_TEXT_DELTA_PT))

        # Apply label fonts via the QFormLayout label column
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
            # Ensure the Hanzi display field is tall enough for the glyphs, but not excessively padded.
            try:
                m = QFontMetrics(input_hanzi)
                target_h = int(m.height() * 1.25) + 12
                hz.setMinimumHeight(target_h)
                # Light, commensurate padding for large Hanzi.
                try:
                    hz.setTextMargins(10, 6, 10, 6)
                except (TypeError, AttributeError, RuntimeError):
                    pass
                if Qt is not None:
                    hz.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

        # Hanzi candidate combobox: leave platform defaults (no font/stylesheet overrides).
        # This avoids macOS popup/focus-ring quirks caused by manual sizing.
        combo = getattr(self, "_cand_combo", None)
        if combo is not None:
            try:
                combo.setStyleSheet("")
            except (RuntimeError, TypeError, AttributeError):
                pass
        try:
            self._debug_hanzi_panel_geometry("after _apply_add_edit_typography")
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

    def _debug_hanzi_panel_geometry(self, reason: str = "") -> None:
        """Debug geometry/fonts for the Hanzi panel.

        Temporary diagnostic for clipping / sizing issues:
          - Hanzi display QLineEdit (`_add_hz`)
          - Candidate combobox (`_cand_combo`) and its popup view
          - Custom Hanzi button

        Must never raise.
        """
        try:
            hz = getattr(self, "_add_hz", None)
            combo = getattr(self, "_cand_combo", None)
            btn = getattr(self, "_btn_custom_hz", None)

            grp = None
            try:
                if hz is not None:
                    grp = hz.parent()
            except (TypeError, AttributeError, RuntimeError):
                grp = None

            def _g(w):
                if w is None:
                    return "None"
                try:
                    g = w.geometry()
                    return "x={0} y={1} w={2} h={3}".format(
                        int(g.x()), int(g.y()), int(g.width()), int(g.height())
                    )
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    return "?"

            def _cr(w):
                if w is None:
                    return "None"
                try:
                    r = w.contentsRect()
                    return "x={0} y={1} w={2} h={3}".format(
                        int(r.x()), int(r.y()), int(r.width()), int(r.height())
                    )
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    return "?"

            def _font(w):
                if w is None:
                    return "None"
                try:
                    f = w.font()
                    return "family={0} pt={1} px={2}".format(
                        str(f.family()), int(f.pointSize()), int(f.pixelSize())
                    )
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    return "?"

            def _sh(w):
                if w is None:
                    return "None"
                try:
                    s = w.sizeHint()
                    return "w={0} h={1}".format(int(s.width()), int(s.height()))
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    return "?"

            def _minmax(w):
                if w is None:
                    return "None"
                try:
                    return "min={0}x{1} max={2}x{3}".format(
                        int(w.minimumWidth()),
                        int(w.minimumHeight()),
                        int(w.maximumWidth()),
                        int(w.maximumHeight()),
                    )
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    return "?"

            view = None
            try:
                view = combo.view() if combo is not None else None
            except (TypeError, AttributeError, RuntimeError):
                view = None

            logger.debug("HANZI-GEO %s", str(reason or "").strip())
            logger.debug("  grp:   geo=%s cr=%s sh=%s %s font=%s", _g(grp), _cr(grp), _sh(grp), _minmax(grp), _font(grp))
            logger.debug(
                "  hz:    geo=%s cr=%s sh=%s %s ro=%s align=%s font=%s",
                _g(hz),
                _cr(hz),
                _sh(hz),
                _minmax(hz),
                bool(getattr(hz, "isReadOnly", lambda: False)()),
                str(getattr(hz, "alignment", lambda: "?")()),
                _font(hz),
            )
            logger.debug(
                "  combo: geo=%s cr=%s sh=%s %s vis=%s font=%s",
                _g(combo),
                _cr(combo),
                _sh(combo),
                _minmax(combo),
                bool(getattr(combo, "isVisible", lambda: False)()),
                _font(combo),
            )

            try:
                ss = combo.styleSheet() if combo is not None else ""
            except (TypeError, AttributeError, RuntimeError):
                ss = ""
            if ss:
                logger.debug("  combo stylesheet: %s", ss)

            logger.debug(
                "  view:  geo=%s cr=%s sh=%s %s vis=%s font=%s",
                _g(view),
                _cr(view),
                _sh(view),
                _minmax(view),
                bool(getattr(view, "isVisible", lambda: False)()),
                _font(view),
            )

            logger.debug(
                "  btn:   geo=%s cr=%s sh=%s %s text=%r font=%s",
                _g(btn),
                _cr(btn),
                _sh(btn),
                _minmax(btn),
                str(getattr(btn, "text", lambda: "")()),
                _font(btn),
            )

            # Font metrics (height/ascent/descent) for Hanzi widgets
            try:
                if hz is not None:
                    fm = QFontMetrics(hz.font())
                    logger.debug(
                        "  hz metrics: h=%d asc=%d desc=%d lead=%d",
                        int(fm.height()),
                        int(fm.ascent()),
                        int(fm.descent()),
                        int(fm.leading()),
                    )
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

            try:
                if combo is not None:
                    fm2 = QFontMetrics(combo.font())
                    logger.debug(
                        "  combo metrics: h=%d asc=%d desc=%d lead=%d",
                        int(fm2.height()),
                        int(fm2.ascent()),
                        int(fm2.descent()),
                        int(fm2.leading()),
                    )
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass



        except (TypeError, AttributeError, RuntimeError, ValueError):
            return

    def _ensure_combo_closed_height(self, combo) -> None:
        """Ensure the *closed* combobox height is compact.

        Important: this implementation intentionally avoids any calls that rely on
        QStyleOption / QComboBox.initStyleOption / style subControlRect. Those paths
        have been triggering macOS headless (offscreen/minimal) segfaults.
        """
        try:
            if combo is None:
                return

            # Use font metrics only (safe in headless) to derive a reasonable closed height.
            fm = combo.fontMetrics()
            text_h = 0
            try:
                text_h = int(fm.lineSpacing())
            except (TypeError, AttributeError, RuntimeError, ValueError):
                try:
                    text_h = int(fm.height())
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    text_h = 0

            # Empirical padding for macOS/Aqua: text + margins + arrow + focus ring.
            target = max(34, text_h + 14)

            try:
                combo.setMinimumHeight(target)
                combo.setMaximumHeight(target)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                # Fallback for older bindings/styles.
                try:
                    combo.setFixedHeight(target)
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    pass

            try:
                combo.updateGeometry()
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

        except Exception as e:
            try:
                logger.debug("_ensure_combo_closed_height skipped (%s)", e)
            except (TypeError, AttributeError, RuntimeError, ValueError):
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
            This method must never be recursed. It only dispatches to the concrete
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
        """Defer focus movement to the next event-loop tick (best-effort).

        This prevents QComboBox signal churn (activated/currentTextChanged/editingFinished)
        from overriding our intended focus move.

        target: 'cand' | 'hz' | 'mn' | 'jy' | 'cat'
        """
        try:
            from PySide6.QtCore import QTimer
        except (ImportError, TypeError):
            QTimer = None

        def _apply() -> None:
            # --- DEBUG LOGGING: focus state at start ---
            try:
                from PySide6.QtWidgets import QApplication
                fw = QApplication.focusWidget()
                fw_name = None
                try:
                    fw_name = str(fw.objectName() or "") if fw is not None else ""
                except (TypeError, AttributeError, RuntimeError):
                    fw_name = ""
                logger.debug(
                    "DEFER_FOCUS start: target=%r current_focus=%r name=%r",
                    target,
                    type(fw).__name__ if fw else None,
                    fw_name,
                )
            except (TypeError, AttributeError, RuntimeError):
                pass
            try:
                if target == "cand":
                    combo = getattr(self, "_cand_combo", None)
                    if combo is not None:
                        try:
                            combo.setVisible(True)
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                        try:
                            combo.setFocus()
                            # --- DEBUG LOGGING: focus state at end ---
                            try:
                                from PySide6.QtWidgets import QApplication
                                fw2 = QApplication.focusWidget()
                                fw2_name = None
                                try:
                                    fw2_name = str(fw2.objectName() or "") if fw2 is not None else ""
                                except (TypeError, AttributeError, RuntimeError):
                                    fw2_name = ""
                                logger.debug("DEFER_FOCUS end: target=%r final_focus=%r name=%r", target, type(fw2).__name__ if fw2 else None, fw2_name)
                            except (TypeError, AttributeError, RuntimeError):
                                pass
                            return
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                    # fall back
                    target2 = "hz"
                else:
                    target2 = target

                if target2 == "hz":
                    # Prefer the Hanzi field, but if it is read-only (common in candidate-driven flow),
                    # do not dead-end the user: move focus to the manual Hanzi button instead.
                    self._focus_hanzi(select_all=True)

                    try:
                        hz = getattr(self, "_add_hz", None)
                    except (TypeError, AttributeError, RuntimeError):
                        hz = None

                    hz_ro = False
                    try:
                        if hz is not None and callable(getattr(hz, "isReadOnly", None)):
                            hz_ro = bool(hz.isReadOnly())
                    except (TypeError, AttributeError, RuntimeError):
                        hz_ro = False

                    if hz_ro:
                        # If the Hanzi field is read-only and we have no candidate list,
                        # auto-enter manual Hanzi mode rather than focusing a button (dead-end).
                        did_manual = False

                        # We have a single canonical entrypoint for manual Hanzi mode.
                        try:
                            self._on_btn_custom_hz_clicked()
                            did_manual = True
                        except Exception:
                            did_manual = False

                        # Fallback: click the existing button if present.
                        if not did_manual:
                            try:
                                btn = getattr(self, "_btn_custom_hz", None)
                            except (TypeError, AttributeError, RuntimeError):
                                btn = None
                            try:
                                if btn is not None and bool(btn.isEnabled()) and bool(btn.isVisible()):
                                    try:
                                        btn.click()
                                    except Exception:
                                        try:
                                            # Some bindings prefer animateClick
                                            btn.animateClick(0)
                                        except Exception:
                                            pass
                                    did_manual = True
                            except (TypeError, AttributeError, RuntimeError):
                                did_manual = False

                        # After entering manual mode, try to focus Hanzi again so typing can begin.
                        try:
                            self._focus_hanzi(select_all=True)
                        except (TypeError, AttributeError, RuntimeError):
                            pass

                    # --- DEBUG LOGGING: focus state at end ---
                    try:
                        from PySide6.QtWidgets import QApplication
                        fw2 = QApplication.focusWidget()
                        fw2_name = None
                        try:
                            fw2_name = str(fw2.objectName() or "") if fw2 is not None else ""
                        except (TypeError, AttributeError, RuntimeError):
                            fw2_name = ""
                        logger.debug(
                            "DEFER_FOCUS end: target=%r final_focus=%r name=%r",
                            target,
                            type(fw2).__name__ if fw2 else None,
                            fw2_name,
                        )
                    except (TypeError, AttributeError, RuntimeError):
                        pass
                    return
                if target2 == "mn":
                    self._focus_meanings(select_all=True)
                    # --- DEBUG LOGGING: focus state at end ---
                    try:
                        from PySide6.QtWidgets import QApplication
                        fw2 = QApplication.focusWidget()
                        fw2_name = None
                        try:
                            fw2_name = str(fw2.objectName() or "") if fw2 is not None else ""
                        except (TypeError, AttributeError, RuntimeError):
                            fw2_name = ""
                        logger.debug("DEFER_FOCUS end: target=%r final_focus=%r name=%r", target, type(fw2).__name__ if fw2 else None, fw2_name)
                    except (TypeError, AttributeError, RuntimeError):
                        pass
                    return
                if target2 == "jy":
                    self._focus_jyutping(select_all=True)
                    # --- DEBUG LOGGING: focus state at end ---
                    try:
                        from PySide6.QtWidgets import QApplication
                        fw2 = QApplication.focusWidget()
                        fw2_name = None
                        try:
                            fw2_name = str(fw2.objectName() or "") if fw2 is not None else ""
                        except (TypeError, AttributeError, RuntimeError):
                            fw2_name = ""
                        logger.debug("DEFER_FOCUS end: target=%r final_focus=%r name=%r", target, type(fw2).__name__ if fw2 else None, fw2_name)
                    except (TypeError, AttributeError, RuntimeError):
                        pass
                    return
                if target2 == "cat":
                    self._focus_category(select_all=True, show_popup=True)
                    # --- DEBUG LOGGING: focus state at end ---
                    try:
                        from PySide6.QtWidgets import QApplication
                        fw2 = QApplication.focusWidget()
                        fw2_name = None
                        try:
                            fw2_name = str(fw2.objectName() or "") if fw2 is not None else ""
                        except (TypeError, AttributeError, RuntimeError):
                            fw2_name = ""
                        logger.debug("DEFER_FOCUS end: target=%r final_focus=%r name=%r", target, type(fw2).__name__ if fw2 else None, fw2_name)
                    except (TypeError, AttributeError, RuntimeError):
                        pass
                    return
            except (TypeError, AttributeError, RuntimeError):
                # --- DEBUG LOGGING: focus state at end (exceptional) ---
                try:
                    from PySide6.QtWidgets import QApplication
                    fw2 = QApplication.focusWidget()
                    fw2_name = None
                    try:
                        fw2_name = str(fw2.objectName() or "") if fw2 is not None else ""
                    except (TypeError, AttributeError, RuntimeError):
                        fw2_name = ""
                    logger.debug("DEFER_FOCUS end: target=%r final_focus=%r name=%r", target, type(fw2).__name__ if fw2 else None, fw2_name)
                except (TypeError, AttributeError, RuntimeError):
                    pass
                return
            # --- DEBUG LOGGING: focus state at end (normal fallthrough) ---
            try:
                from PySide6.QtWidgets import QApplication
                fw2 = QApplication.focusWidget()
                fw2_name = None
                try:
                    fw2_name = str(fw2.objectName() or "") if fw2 is not None else ""
                except Exception:
                    fw2_name = ""
                logger.debug("DEFER_FOCUS end: target=%r final_focus=%r name=%r", target, type(fw2).__name__ if fw2 else None, fw2_name)
            except Exception:
                pass

        if QTimer is not None and hasattr(QTimer, "singleShot"):
            try:
                QTimer.singleShot(0, _apply)
                return
            except Exception:
                pass

        # Fallback: apply immediately.
        _apply()

    def _on_btn_custom_hz_clicked(self) -> None:
        """Enter manual Hanzi mode (user types their own Hanzi).

        Must not add UI elements; best-effort and never raise.
        """
        try:
            logger.debug("ManualHanzi: button clicked")
        except Exception:
            pass

        # Prefer extracted controller if you created one.
        try:
            ctrl = getattr(self, "_manual_hanzi_controller", None)
        except (TypeError, AttributeError, RuntimeError):
            ctrl = None

        if ctrl is not None:
            try:
                enter = getattr(ctrl, "enter_manual_mode", None)
            except (TypeError, AttributeError, RuntimeError):
                enter = None

            if callable(enter):
                try:
                    enter()
                    return
                except Exception:
                    pass

        # Local best-effort behaviour.
        try:
            self._manual_hanzi_mode = True
        except Exception:
            pass

        # Clear any existing auto-selected Hanzi so Save gating requires an explicit manual entry.
        try:
            self._mark_hanzi_committed(False)
        except Exception:
            pass

        try:
            ctx = getattr(self, "_add_edit_ctx", None)
        except (TypeError, AttributeError, RuntimeError):
            ctx = None

        if ctx is not None:
            try:
                ctx.manual_hanzi = True
            except Exception:
                pass
            try:
                ctx.hanzi = ""
            except Exception:
                pass
            try:
                ctx.hz_ok = False
            except Exception:
                pass

        try:
            hz = getattr(self, "_add_hz", None)
        except (TypeError, AttributeError, RuntimeError):
            hz = None

        if hz is not None:
            try:
                hz.setReadOnly(False)
            except Exception:
                pass
            try:
                hz.clear()
            except Exception:
                pass
            try:
                hz.setPlaceholderText("Type Hanzi…")
            except (TypeError, AttributeError, RuntimeError):
                pass

        try:
            combo = getattr(self, "_cand_combo", None)
        except (TypeError, AttributeError, RuntimeError):
            combo = None

        if combo is not None:
            try:
                combo.setVisible(False)
            except (TypeError, AttributeError, RuntimeError):
                pass
            try:
                combo.setCurrentIndex(-1)
            except ():
                pass

        # Focus Hanzi for typing.
        try:
            self._focus_hanzi(select_all=True)
        except (TypeError, AttributeError, RuntimeError):
            try:
                if hz is not None and hasattr(hz, "setFocus"):
                    hz.setFocus()
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Refresh Save gating.
        try:
            fn_gate = getattr(self, "_update_save_enabled", None)
        except (TypeError, AttributeError, RuntimeError):
            fn_gate = None

        if callable(fn_gate):
            try:
                fn_gate()
            except Exception:
                pass

    def _on_save_clicked(self) -> None:
        """Legacy inline Save button handler.

        This remains the manual-save pathway when the user chooses 'Edit'
        from the Meaning-Enter confirmation flow.

        Best-effort only: never raise from UI callbacks.
        """
        # Prefer the historical handler name if present.
        try:
            fn = getattr(self, "_on_add_item_enter", None)
            if callable(fn):
                fn()
                return
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Fall back to other known save entry points.
        try:
            fn = getattr(self, "_save_add_item", None)
            if callable(fn):
                fn()
                return
        except (TypeError, AttributeError, RuntimeError):
            pass

        try:
            fn = getattr(self, "_do_save", None)
            if callable(fn):
                fn()
                return
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Absolute last resort: do nothing.
        return

    def _ensure_category_services(self):
        """Ensure CategoryRepo + CategoryCommitService are available (UI-free, best-effort).

        Returns:
            (repo, svc) or (None, None) if unavailable.
        """
        try:
            repo = getattr(self, "_cat_repo", None)
        except (TypeError, AttributeError, RuntimeError):
            repo = None

        try:
            svc = getattr(self, "_cat_commit_svc", None)
        except (TypeError, AttributeError, RuntimeError):
            svc = None

        if repo is not None and svc is not None:
            return repo, svc

        # Lazy import so domain modules remain optional in some test modes.
        try:
            from category_repo import CategoryRepo
            from category_commit import CategoryCommitService
        except (ImportError, ModuleNotFoundError):
            return None, None

        # Canonicaliser is optional.
        try:
            canon_fn = getattr(self, "_canon_cat_name", None)
            canon_cb = canon_fn if callable(canon_fn) else None
        except (TypeError, AttributeError, RuntimeError):
            canon_cb = None

        # Persist callback: write categories.yaml directly.
        # The repo/service layer owns mutation; the dialog owns the file write boundary.
        def _persist_cb(_cats_map: dict) -> None:
            try:
                persist_categories_yaml(_cats_map)
            except Exception:
                return

        # Authoritative map is always self._cats.
        try:
            cats_map = getattr(self, "_cats", None)
        except (TypeError, AttributeError, RuntimeError):
            cats_map = None

        if not isinstance(cats_map, dict):
            cats_map = {}
            try:
                setattr(self, "_cats", cats_map)
            except (TypeError, AttributeError, RuntimeError):
                pass

        try:
            repo = CategoryRepo(cats_map, canon=canon_cb, persist=_persist_cb)
            svc = CategoryCommitService(repo)
        except Exception:
            return None, None

        try:
            self._cat_repo = repo
            self._cat_commit_svc = svc
        except (TypeError, AttributeError, RuntimeError):
            pass

        return repo, svc

    def _add_new_category(self, cat: str) -> bool:
        """Add a new category via the authoritative CategoryRepo (best-effort, never raise)."""
        try:
            cat_s = str(cat or "").strip()
        except Exception:
            cat_s = ""

        if not cat_s:
            return False

        # Prefer repo-based mutation (single source of truth: self._cats).
        repo = getattr(self, "_cat_repo", None)
        if repo is not None and hasattr(repo, "add"):
            try:
                try:
                    logger.debug("_add_new_category: repo.add(%r) starting", str(cat_s or ""))
                except Exception:
                    pass

                ok = bool(repo.add(cat_s))

                try:
                    logger.debug("_add_new_category: repo.add(%r) -> ok=%s", str(cat_s or ""), bool(ok))
                except Exception:
                    pass
            except Exception as e:
                ok = False
                try:
                    logger.debug("_add_new_category: repo.add(%r) raised: %s", str(cat_s or ""), e)
                except Exception:
                    pass

            # Ensure the UI dropdown contains it (UI-only effect; repo is the authority).
            if ok:
                try:
                    w_cat = getattr(self, "_add_cat", None)
                except Exception:
                    w_cat = None

                if w_cat is not None:
                    try:
                        if hasattr(w_cat, "findText") and hasattr(w_cat, "addItem"):
                            if int(w_cat.findText(repo.canon(cat_s))) < 0:
                                w_cat.addItem(repo.canon(cat_s))
                    except Exception:
                        pass

            return ok

        # Fallback (should be rare): minimal in-memory add to self._cats.
        try:
            cats_map = getattr(self, "_cats", None)
        except Exception:
            cats_map = None

        if not isinstance(cats_map, dict):
            return False

        try:
            canon = getattr(self, "_canon_cat_name", None)
            cat_key = str(canon(cat_s) if callable(canon) else cat_s).strip()
        except Exception:
            cat_key = cat_s

        if not cat_key:
            return False

        if cat_key not in cats_map:
            cats_map[cat_key] = []
        return True

    def _on_add_category_committed(self, *args, user_action: bool = False, **kwargs) -> None:
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

            try:
                exists_now = bool(canon) and bool(repo.exists(canon))
            except (TypeError, AttributeError, RuntimeError, ValueError):
                exists_now = False

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

            # 5) Core commit (pure decision + repo mutation)
            try:
                logger.debug(
                    "Add/Edit category commit: calling svc.commit(requested=%r has_jy=%s confirmed_add=%s)",
                    str(cat_raw or ""),
                    bool(has_jy),
                    bool(user_confirmed_add),
                )
            except Exception:
                pass
            try:
                res = svc.commit(
                    requested=str(cat_raw or ""),
                    has_jyutping=bool(has_jy),
                    user_confirmed_add=bool(user_confirmed_add),
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

            # Candidate fill is non-optional when service requests it.
            try:
                should_fill = bool(getattr(res, "should_fill_candidates", False))
            except (TypeError, AttributeError, RuntimeError):
                should_fill = False

            if has_jy and should_fill:
                try:
                    fn_fill = getattr(self, "_fill_hanzi_candidates", None)
                    if callable(fn_fill):
                        try:
                            fn_fill(jy, category=cat)
                        except TypeError:
                            fn_fill(jy)
                except (TypeError, AttributeError, RuntimeError, ValueError):
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
        """Build a stable preview payload for the pending add/edit entry (no mutation)."""
        try:
            preview_obj = AddEntryPreviewBuilder.build(self)
            return preview_obj.to_payload()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return {}

    def _confirm_add_entry(self, preview: dict) -> str:
        """Confirmation dialog for a pending add/edit entry.

        Returns: 'save' | 'edit' | 'cancel'
        """
        # try:
        #     from PySide6.QtWidgets import QMessageBox
        # except (ImportError, ModuleNotFoundError, AttributeError, TypeError, RuntimeError):
        #     # If Qt is not available, preserve legacy behavior.
        #     return "edit"

        jy = str((preview.get("jyutping") or "")).strip()
        hz = str((preview.get("hanzi") or "")).strip()
        mn = str((preview.get("meaning") or "")).strip()
        cat = str((preview.get("category") or "")).strip()

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("Confirm entry")
        msg.setText("Save this entry?")
        msg.setInformativeText(
            "Jyutping: {0}\nHanzi: {1}\nMeaning: {2}\nCategory: {3}".format(jy, hz, mn, cat)
        )

        btn_save = msg.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        btn_edit = msg.addButton("Edit", QMessageBox.ButtonRole.ActionRole)
        # btn_cancel = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

        try:
            msg.setDefaultButton(btn_save)
        except (TypeError, AttributeError, RuntimeError):
            pass

        try:
            msg.exec()
        except (TypeError, AttributeError, RuntimeError):
            return "edit"

        try:
            clicked = msg.clickedButton()
        except (TypeError, AttributeError, RuntimeError):
            clicked = None

        if clicked is btn_save:
            return "save"
        if clicked is btn_edit:
            return "edit"
        return "cancel"

    def _set_save_button_visible(self, visible: bool) -> None:
        """Show/hide the legacy inline Save button.

        Rule:
          - Hidden by default
          - Shown only when the user chooses 'Edit' from the confirmation dialog
        """
        # Canonical: current implementation uses `self.btn_save`
        btn = _save_button(self)

        # Qt-boundary fallback: objectName lookup
        if btn is None:
            try:
                btn = self.findChild(QPushButton, "btn_save")
            except (TypeError, AttributeError, RuntimeError):
                btn = None

        if btn is None:
            try:
                btn = self.findChild(QPushButton, "btnSave")
            except (TypeError, AttributeError, RuntimeError):
                btn = None

        if btn is None:
            return

        try:
            btn.setVisible(bool(visible))
        except (TypeError, AttributeError, RuntimeError):
            try:
                (btn.show() if visible else btn.hide())
            except (TypeError, AttributeError, RuntimeError):
                pass

    def _clear_add_entry_fields(self) -> None:
        """Clear Add/Edit fields best-effort."""
        try:
            if getattr(self, "_add_jy", None) is not None:
                self._add_jy.clear()
        except (TypeError, AttributeError, RuntimeError):
            pass
        try:
            if getattr(self, "_add_hz", None) is not None:
                self._add_hz.clear()
        except (TypeError, AttributeError, RuntimeError):
            pass
        try:
            if getattr(self, "_add_mn", None) is not None:
                self._add_mn.clear()
        except (TypeError, AttributeError, RuntimeError):
            pass

        try:
            self._set_notes("", source="auto-default")
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Also clear category selection
        try:
            if getattr(self, "_add_cat", None) is not None:
                try:
                    self._add_cat.setCurrentIndex(-1)
                except (TypeError, AttributeError, RuntimeError):
                    # Some builds may not like -1; fall back to first item.
                    try:
                        self._add_cat.setCurrentIndex(0)
                    except (TypeError, AttributeError, RuntimeError):
                        pass
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Reset manual-Hanzi state so candidates behave normally for the next entry.
        try:
            self._mark_manual_hanzi_mode(False)
        except Exception:
            try:
                self._manual_hanzi_mode = False
            except Exception:
                pass

        try:
            ctx = getattr(self, "_add_edit_ctx", None)
        except (TypeError, AttributeError, RuntimeError):
            ctx = None

        if ctx is not None:
            try:
                ctx.manual_hanzi = False
            except Exception:
                pass
            try:
                ctx.hanzi = ""
            except Exception:
                pass
            try:
                ctx.hz_ok = False
            except Exception:
                pass

        try:
            hz = getattr(self, "_add_hz", None)
        except (TypeError, AttributeError, RuntimeError):
            hz = None

        if hz is not None:
            try:
                hz.setReadOnly(True)
            except Exception:
                pass
            try:
                hz.setPlaceholderText("Auto, after reverse lookup")
            except Exception:
                pass

        try:
            combo = getattr(self, "_cand_combo", None)
        except (TypeError, AttributeError, RuntimeError):
            combo = None

        if combo is not None:
            # Do not force visibility here; the next category commit will decide.
            try:
                combo.setCurrentIndex(-1)
            except Exception:
                pass

        try:
            if callable(getattr(self, "_update_save_enabled", None)):
                try:
                    fn_gate = getattr(self, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _reset_add_panel_pre_validation(self) -> None:
        """Return Add/Edit panel to pre-validation state (placeholders only)."""
        # Clear dependent fields
        try:
            if getattr(self, "_add_mn", None) is not None:
                self._add_mn.clear()
        except (TypeError, AttributeError, RuntimeError):
            pass

        try:
            if getattr(self, "_add_hz", None) is not None:
                self._add_hz.clear()
        except (TypeError, AttributeError, RuntimeError):
            pass

        try:
            self._set_notes("", source="auto-default")
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Reset category selection to placeholder
        try:
            if getattr(self, "_add_cat", None) is not None:
                try:
                    self._add_cat.setCurrentIndex(-1)
                except (TypeError, AttributeError, RuntimeError):
                    pass
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Hide and clear candidate combobox
        try:
            combo = getattr(self, "_cand_combo", None)
            if combo is not None:
                try:
                    combo.blockSignals(True)
                except (TypeError, AttributeError, RuntimeError):
                    pass
                try:
                    combo.clear()
                except (TypeError, AttributeError, RuntimeError):
                    pass
                try:
                    combo.setVisible(False)
                except (TypeError, AttributeError, RuntimeError):
                    pass
                try:
                    combo.blockSignals(False)
                except (TypeError, AttributeError, RuntimeError):
                    pass
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Reset intent flags
        try:
            self._mark_hanzi_committed(False)
        except (TypeError, AttributeError, RuntimeError):
            try:
                self._hanzi_committed = False
            except (TypeError, AttributeError, RuntimeError):
                pass

        try:
            self._mark_manual_hanzi_mode(False)
        except (TypeError, AttributeError, RuntimeError):
            try:
                self._manual_hanzi_mode = False
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Reset SM context best-effort
        ctx = None
        try:
            ctx = getattr(self, "_add_edit_ctx", None)
        except (TypeError, AttributeError, RuntimeError):
            ctx = None

        if ctx is not None:
            for _k, _v in (
                    ("jy_ok", False),
                    ("duplicate", None),
                    ("hanzi", ""),
                    ("hz_ok", False),
                    ("manual_hanzi", False),
                    ("meaning", ""),
                    ("mn_ok", False),
                    ("category", ""),
                    ("cat_ok", False),
            ):
                try:
                    setattr(ctx, _k, _v)
                except (TypeError, AttributeError, RuntimeError):
                    pass

        try:
            if callable(getattr(self, "_update_save_enabled", None)):
                try:
                    fn_gate = getattr(self, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
        except (TypeError, AttributeError, RuntimeError):
            pass

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
        # ---- gather inputs ----
        try:
            preview = self._build_add_entry_preview()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            preview = {}

        try:
            jy, hz, mn, cat = self._read_add_fields()
        except (TypeError, AttributeError, RuntimeError):
            jy = hz = mn = cat = ""

        inp = AddEditInputs(
            jyutping=str(jy or "").strip(),
            hanzi=str(hz or "").strip(),
            meaning=str(mn or "").strip(),
            category=str(cat or "").strip(),
            saving=bool(getattr(self, "_saving_now", False)),
            validate_jy=getattr(self, "_validate_jyut_syllables", None),
            valid_categories=set(getattr(self, "_categories_map", {}).keys())
            if hasattr(self, "_categories_map")
            else None,
        )

        # ---- user decision (still Qt) ----
        try:
            decision = self._confirm_add_entry(preview)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            decision = "edit"

        decision = str(decision or "").strip().lower()

        # ---- controller ----
        result = AddEditController.on_meaning_enter(
            preview=preview,
            decision=decision,
            inp=inp,
        )

        # Controller returns a dict contract; older code paths may return an object.
        try:
            is_dict = isinstance(result, dict)
        except (TypeError, AttributeError, RuntimeError):
            is_dict = False

        def _rget(key: str, default=None):
            if is_dict:
                try:
                    return result.get(key, default)
                except (TypeError, AttributeError, RuntimeError):
                    return default
            try:
                return getattr(result, key, default)
            except (TypeError, AttributeError, RuntimeError):
                return default

        show_save = bool(_rget("show_save", False))
        clear_fields = bool(_rget("clear_fields", False))
        focus_target = _rget("focus_target", None)
        commit = bool(_rget("commit", False))
        commit_payload = _rget("commit_payload", None)
        preview_payload = _rget("preview_payload", None)

        # Back-compat: if controller didn’t provide these, fall back to the preview we already built.
        if preview_payload is None:
            preview_payload = preview
        if commit_payload is None:
            commit_payload = preview_payload

        # ---- apply result ----
        if show_save:
            self._set_save_button_visible(True)
            try:
                fn_gate = getattr(self, "_update_save_enabled", None)
                if callable(fn_gate):
                    fn_gate()
            except (TypeError, AttributeError, RuntimeError):
                pass
            return

        if clear_fields:
            self._clear_add_entry_fields()
            self._set_save_button_visible(False)

        if commit:
            cb = getattr(self, "_commit_callback", None)
            if callable(cb):
                cb(commit_payload)
            else:
                self._on_save_clicked()
            # Clear Hanzi field on successful Save
            try:
                if getattr(self, "_add_hz", None) is not None:
                    self._add_hz.clear()
            except (TypeError, AttributeError, RuntimeError):
                pass

        if focus_target == "jy":
            self._focus_jyutping(select_all=True)

    # ---- Add & Edit: Jyutping validation + reverse lookup wiring ----

    @staticmethod
    def _normalize_jy(s: str) -> str:
        text = (s or "").strip().lower()
        # Collapse runs of whitespace to single spaces.
        return " ".join(text.split())

    def _warn_duplicate_jy_and_reset(self, jy: str) -> None:
        """Warn that Jyutping already exists, keep the text, and focus/select Jyutping."""
        try:
            QMessageBox.warning(
                self,
                "Duplicate Jyutping",
                "The Jyutping \u201c{}\u201d already exists in your vocabulary.\n\nPlease edit the Jyutping and try again.".format(jy),
            )
        except (TypeError, AttributeError, RuntimeError):
            # If the message box cannot be shown (headless / shutdown), continue with field reset.
            pass

        # Central focus helper already handles best-effort fallbacks.
        self._focus_jyutping(select_all=True)

    def _read_add_fields(self) -> tuple[str, str, str, str]:
        """Read Add/Edit panel fields safely (legacy compatibility)."""
        try:
            w_jy = getattr(self, "_add_jy", None)
            w_hz = getattr(self, "_add_hz", None)
            w_mn = getattr(self, "_add_mn", None)
            w_cat = getattr(self, "_add_cat", None)

            jy = (w_jy.text() or "").strip() if w_jy is not None else ""
            hz = (w_hz.text() or "").strip() if w_hz is not None else ""
            mn = (w_mn.text() or "").strip() if w_mn is not None else ""
            cat = ""
            if w_cat is not None:
                try:
                    cat = (w_cat.currentText() or "").strip()
                except (TypeError, AttributeError, RuntimeError):
                    cat = ""
                if not cat:
                    # Some Qt builds return "" from currentText() when index is -1,
                    # even though the editable lineEdit has text.
                    try:
                        le = w_cat.lineEdit() if hasattr(w_cat, "lineEdit") else None
                        if le is not None and hasattr(le, "text"):
                            cat = (le.text() or "").strip()
                    except (TypeError, AttributeError, RuntimeError):
                        cat = cat or ""
            return jy, hz, mn, cat
        except (TypeError, AttributeError, RuntimeError):
            return "", "", "", ""

    def _ensure_category_combo_editable(self) -> None:
        """Ensure the Add/Edit category combobox is editable (best-effort)."""
        try:
            w_cat = getattr(self, "_add_cat", None)
            if w_cat is not None and hasattr(w_cat, "setEditable"):
                w_cat.setEditable(True)
        except (TypeError, AttributeError, RuntimeError):
            return

    def _fill_hanzi_candidates(self, jy: str, category: str | None = None) -> None:
        jy_s = str(jy or "").strip()
        if not jy_s:
            return
        try:
            logger.debug(
                "_fill_hanzi_candidates: start jy=%r category=%r",
                str(jy_s or ""),
                str(category or ""),
            )
        except (TypeError, AttributeError, RuntimeError):
            pass

        # ---- gather Tier-1 candidates (order must remain deterministic) ----
        try:
            cands = self._reverse_candidates_for_jy(jy_s)
        except (TypeError, AttributeError, RuntimeError):
            cands = []

        try:
            cands_list = list(cands or [])
        except (TypeError, AttributeError, RuntimeError):
            cands_list = []

        try:
            logger.debug(
                "_fill_hanzi_candidates: raw candidates n=%d (jy=%r)",
                int(len(cands_list or [])),
                str(jy_s or ""),
            )
        except Exception:
            pass

        # ---- find preferred Hanzi within category (if provided) ----
        preferred_hz = ""
        try:
            cat_s = str(category or "").strip()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            cat_s = ""

        if cat_s:
            members = None
            try:
                cats_map = getattr(self, "_cats", None)
                members = cats_map.get(cat_s) if isinstance(cats_map, dict) else None
            except (TypeError, AttributeError, RuntimeError):
                members = None

            if isinstance(members, (list, tuple, set)) and cands_list:
                try:
                    member_set = set([str(x).strip() for x in list(members) if str(x).strip()])
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    member_set = set()

                if member_set:
                    for row in cands_list:
                        try:
                            hz0 = str((row[0] if isinstance(row, (list, tuple)) and len(row) >= 1 else row) or "").strip()
                        except (TypeError, AttributeError, RuntimeError, ValueError):
                            hz0 = ""
                        if hz0 and hz0 in member_set:
                            preferred_hz = hz0
                            break

        # ---- widgets / controller ----
        try:
            combo = getattr(self, "_cand_combo", None)
        except (TypeError, AttributeError, RuntimeError):
            combo = None

        # Ensure controller exists when combo exists (populate helper)
        try:
            if combo is not None:
                self._cand_combo_ctrl = CandidateComboController(combo)
            else:
                self._cand_combo_ctrl = None
        except (TypeError, AttributeError, RuntimeError, ImportError):
            self._cand_combo_ctrl = None

        # ---- ctx helpers ----
        try:
            ctx = getattr(self, "_add_edit_ctx", None)
        except (TypeError, AttributeError, RuntimeError):
            ctx = None

        def _ctx_set(name: str, value) -> None:
            if ctx is None:
                return
            try:
                setattr(ctx, name, value)
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Block signals while we repopulate to prevent accidental double-firing.
        if combo is not None:
            try:
                combo.blockSignals(True)
            except (TypeError, AttributeError, RuntimeError):
                pass

        try:
            # Populate combo via controller
            ctrl = getattr(self, "_cand_combo_ctrl", None)
            if ctrl is not None:
                try:
                    ctrl.clear()
                except (TypeError, AttributeError, RuntimeError):
                    pass
                try:
                    ctrl.populate(cands_list)
                except (TypeError, AttributeError, RuntimeError):
                    pass

            try:
                if combo is not None:
                    try:
                        _n = int(combo.count())
                    except Exception:
                        _n = -1
                    try:
                        _vis = bool(combo.isVisible())
                    except Exception:
                        _vis = False
                    logger.debug(
                        "_fill_hanzi_candidates: after populate combo.count=%s visible=%s preferred_hz=%r",
                        _n,
                        bool(_vis),
                        str(preferred_hz or ""),
                    )
            except (TypeError, AttributeError, RuntimeError):
                pass

            # Empty: hide combo and clear dependent fields
            if not cands_list:
                try:
                    if combo is not None:
                        try:
                            logger.debug(
                                "_fill_hanzi_candidates: no candidates -> hiding cand combo (had_combo=%s)",
                                bool(combo is not None),
                            )
                        except Exception:
                            pass
                        combo.setVisible(False)
                except (TypeError, AttributeError, RuntimeError):
                    pass

                try:
                    w_hz = getattr(self, "_add_hz", None)
                    if w_hz is not None:
                        w_hz.clear()
                except (TypeError, AttributeError, RuntimeError):
                    pass

                try:
                    w_mn = getattr(self, "_add_mn", None)
                    if w_mn is not None:
                        w_mn.clear()
                except (TypeError, AttributeError, RuntimeError):
                    pass

                _ctx_set("hanzi", "")
                _ctx_set("hz_ok", False)
                _ctx_set("meaning", "")
                _ctx_set("mn_ok", False)

                try:
                    self._mark_hanzi_committed(False)
                except (TypeError, AttributeError, RuntimeError):
                    try:
                        self._hanzi_committed = False
                    except (TypeError, AttributeError, RuntimeError):
                        pass
                return

            # Non-empty: show combo
            try:
                if combo is not None:
                    combo.setVisible(True)
            except (TypeError, AttributeError, RuntimeError):
                pass

            # Choose selection index (preferred or first)
            sel_idx = 0
            if preferred_hz and combo is not None:
                try:
                    i = int(combo.findText(str(preferred_hz).strip()))
                    if i >= 0:
                        sel_idx = i
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    sel_idx = 0

            # Apply selection (signals blocked)
            try:
                if combo is not None:
                    combo.setCurrentIndex(int(sel_idx))
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

            # Resolve selected_hz and src aligned to candidate list order
            selected_hz = ""
            selected_src = ""
            try:
                row = cands_list[int(sel_idx)] if int(sel_idx) < len(cands_list) else None
            except (TypeError, AttributeError, RuntimeError, ValueError, IndexError):
                row = None

            if row is not None:
                try:
                    selected_hz = str((row[0] if isinstance(row, (list, tuple)) and len(row) >= 1 else row) or "").strip()
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    selected_hz = ""
                try:
                    if isinstance(row, (list, tuple)) and len(row) > 1:
                        selected_src = str(row[1] or "").strip()
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    selected_src = ""

            if not selected_hz and combo is not None:
                try:
                    selected_hz = str(combo.currentText() or "").strip()
                except (TypeError, AttributeError, RuntimeError):
                    selected_hz = ""

            # Set Hanzi field
            try:
                w_hz2 = getattr(self, "_add_hz", None)
                if w_hz2 is not None:
                    if selected_hz:
                        w_hz2.setText(selected_hz)
                    else:
                        w_hz2.clear()
            except (TypeError, AttributeError, RuntimeError):
                pass

            _ctx_set("hanzi", selected_hz)
            _ctx_set("hz_ok", bool(selected_hz))

            # Meaning autofill policy (test + UX compatible):
            #   - Always prefer vocab-backed meanings (via _resolve_meanings_for_candidate),
            #     even when there are multiple candidates.
            #   - If there is exactly one candidate, allow a secondary fallback
            #     (_meanings_for_hanzi) if the resolver returns nothing.
            #   - If there are multiple candidates and the resolver returns nothing,
            #     leave Meaning blank until the user explicitly selects a candidate.
            joined = ""
            if selected_hz:
                try:
                    ms = self._resolve_meanings_for_candidate(selected_hz, selected_src)
                    joined = ", ".join([str(x).strip() for x in (ms or []) if str(x).strip()])
                except (TypeError, AttributeError, RuntimeError):
                    joined = ""

            if (not str(joined or "").strip()) and (len(cands_list) == 1) and selected_hz:
                try:
                    ms2 = self._meanings_for_hanzi(selected_hz)
                    joined = ", ".join([str(x).strip() for x in (ms2 or []) if str(x).strip()])
                except (TypeError, AttributeError, RuntimeError):
                    joined = ""

            # Only set the meaning field when we have something concrete to show.
            # For multi-candidate lists with no resolver meaning, keep it blank.
            try:
                w_mn2 = getattr(self, "_add_mn", None)
                if w_mn2 is not None:
                    if str(joined or "").strip():
                        w_mn2.setText(joined)
                    else:
                        w_mn2.clear()
            except (TypeError, AttributeError, RuntimeError):
                pass

            _ctx_set("meaning", joined)
            _ctx_set("mn_ok", bool(str(joined or "").strip()))

            # Mark committed only when there is exactly one candidate
            if len(cands_list) == 1 and bool(selected_hz):
                try:
                    self._mark_hanzi_committed(True)
                except (TypeError, AttributeError, RuntimeError):
                    try:
                        self._hanzi_committed = True
                    except (TypeError, AttributeError, RuntimeError):
                        pass
            else:
                try:
                    self._mark_hanzi_committed(False)
                except (TypeError, AttributeError, RuntimeError):
                    try:
                        self._hanzi_committed = False
                    except (TypeError, AttributeError, RuntimeError):
                        pass

        finally:
            if combo is not None:
                try:
                    combo.blockSignals(False)
                except (TypeError, AttributeError, RuntimeError):
                    pass

        # Refresh Save gating
        try:
            fn_gate = getattr(self, "_update_save_enabled", None)
            if callable(fn_gate):
                _gate = fn_gate  # type-narrow for linters
                _gate()
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Focus behaviour:
        #   - single candidate -> proceed to Meaning
        #   - multiple candidates -> focus candidate combo (never steal to Meaning)
        try:
            if len(cands_list) == 1:
                w_mn3 = getattr(self, "_add_mn", None)
                if w_mn3 is not None:
                    w_mn3.setFocus()
            else:
                if combo is not None and hasattr(combo, "setFocus"):
                    combo.setFocus()
        except (TypeError, AttributeError, RuntimeError):
            pass


    def _save_add_item(self) -> None:
        """Legacy save entry point shim."""
        try:
            fn = getattr(self, "_on_add_item_enter", None)
            if callable(fn):
                fn()
        except (TypeError, AttributeError, RuntimeError):
            pass

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
        """Return Tier-1 reverse candidates for a Jyutping (deterministic, test-friendly)."""
        jy_s = str(jy or "").strip()
        if not jy_s:
            return []

        # Locate reverse index (multiple historical attribute names)
        rev = None
        for attr in ("_reverse_index", "_rev_index", "_reverse_jyut_index"):
            try:
                v = getattr(self, attr, None)
            except (TypeError, AttributeError, RuntimeError):
                v = None
            if isinstance(v, dict):
                rev = v
                break

        items = []
        if isinstance(rev, dict):
            try:
                items = rev.get(jy_s) or []
            except (TypeError, AttributeError, RuntimeError):
                items = []

        out: list[tuple[str, str, int]] = []
        try:
            for row in list(items):
                # Expected shapes: (hz, src, score) or (hz, src)
                if isinstance(row, (list, tuple)) and len(row) >= 3:
                    hz, src, score = row[0], row[1], row[2]
                elif isinstance(row, (list, tuple)) and len(row) == 2:
                    hz, src, score = row[0], row[1], 0
                else:
                    hz, src, score = row, "", 0

                hz_s2 = str(hz or "").strip()
                if not hz_s2:
                    continue
                src_s = str(src or "").strip()

                try:
                    score_i = int(score)
                except (TypeError, ValueError):
                    try:
                        score_i = int(float(score))
                    except (TypeError, ValueError):
                        score_i = 0

                out.append((hz_s2, src_s, score_i))
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return []

        return out

    def _on_jyut_enter(self) -> None:
        """Commit Jyutping entry into the Add/Edit SM context and advance to Category."""
        try:
            jy = ""
            w = getattr(self, "_add_jy", None)
            if w is not None:
                jy = str((w.text() or "")).strip()
        except (TypeError, AttributeError, RuntimeError):
            jy = ""

        jy_s = self._normalize_jy(jy)
        # Ensure Add/Edit SM context exists (some builds initialise lazily; tests expect it).
        ctx = getattr(self, "_add_edit_ctx", None)
        if ctx is None:
            try:
                from domain.add_edit_sm import AddEditContext
                ctx = AddEditContext()
                self._add_edit_ctx = ctx
            except (TypeError, AttributeError, RuntimeError, ImportError):
                ctx = None

        # Some builds may use an immutable (frozen) context object; support both by
        # falling back to dataclasses.replace() when attribute assignment fails.
        def _ctx_replace(**kwargs) -> None:
            nonlocal ctx
            if ctx is None:
                return
            try:
                import dataclasses
            except (ImportError, TypeError, AttributeError, RuntimeError):
                return
            try:
                ctx = dataclasses.replace(ctx, **kwargs)
                self._add_edit_ctx = ctx
            except (TypeError, AttributeError, RuntimeError, ValueError):
                return

        # Write normalized Jyutping back to the widget to keep UI and SM context aligned
        try:
            w = getattr(self, "_add_jy", None)
            if w is not None and hasattr(w, "setText"):
                w.setText(jy_s)
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Update SM context
        if ctx is not None:
            try:
                ctx.jy = jy_s
            except (TypeError, AttributeError, RuntimeError):
                _ctx_replace(jy=jy_s)

        # Empty -> not valid
        if not jy_s:
            if ctx is not None:
                try:
                    ctx.jy_ok = False
                except (TypeError, AttributeError, RuntimeError):
                    _ctx_replace(jy_ok=False)
            try:
                try:
                    fn_gate = getattr(self, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
            except (TypeError, AttributeError, RuntimeError):
                pass
            return

        # Validate syllables if validator exists
        try:
            vfn = getattr(self, "_validate_jyut_syllables", None)
            jy_ok = bool(vfn(jy_s)) if callable(vfn) else True
        except (TypeError, AttributeError, RuntimeError):
            jy_ok = True

        if ctx is not None:
            try:
                ctx.jy_ok = bool(jy_ok)
            except (TypeError, AttributeError, RuntimeError):
                _ctx_replace(jy_ok=bool(jy_ok))

        if not jy_ok:
            try:
                try:
                    fn_gate = getattr(self, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
            except (TypeError, AttributeError, RuntimeError):
                pass
            return

        # Duplicate detection by scanning vocab
        dup = False
        try:
            v = getattr(self, "_vocab", None)
            if isinstance(v, dict):
                for _hz, row in v.items():
                    if isinstance(row, (list, tuple)) and len(row) >= 2:
                        try:
                            j = str(row[1] or "").strip()
                        except (TypeError, AttributeError, RuntimeError):
                            j = ""
                        if j and self._normalize_jy(j) == jy_s:
                            dup = True
                            break
        except (TypeError, AttributeError, RuntimeError):
            dup = False

        if ctx is not None:
            try:
                ctx.duplicate = jy_s if dup else None
            except (TypeError, AttributeError, RuntimeError):
                _ctx_replace(duplicate=jy_s if dup else None)

        if dup:
            # Must warn and keep focus on Jyutping (test asserts QMessageBox.warning called)
            try:
                self._warn_duplicate_jy_and_reset(jy_s)
            except ():
                pass
            try:
                try:
                    fn_gate = getattr(self, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
            except (TypeError, AttributeError, RuntimeError):
                pass
            return

        try:
            ctrl = getattr(self, "_cat_combo_ctrl", None)
            if ctrl is not None and hasattr(ctrl, "focus"):
                ctrl.focus()
        except (TypeError, AttributeError, RuntimeError):
            pass

        try:
            try:
                fn_gate = getattr(self, "_update_save_enabled", None)
                if callable(fn_gate):
                    fn_gate()
            except (TypeError, AttributeError, RuntimeError):
                pass
        except (TypeError, AttributeError, RuntimeError):
            pass
        return

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
        """Handler for when a Hanzi candidate is selected from the combo.

        This slot must tolerate both overloaded signal forms (int/str) and must be
        deterministic in offscreen tests.

        Contract:
          - We treat the combo's visible text as the selected Hanzi.
          - If CandidateComboController populated itemData, we also use that to
            retrieve the candidate 'src' for meaning resolution.

        This must never raise.
        """
        # --- resolve combo + index + selected hanzi ---
        combo = None
        idx = -1
        selected_hz = ""
        try:
            combo = getattr(self, "_cand_combo", None)
            if combo is None:
                return

            idx = None
            if args:
                a0 = args[0]
                if isinstance(a0, int):
                    idx = a0
                elif isinstance(a0, str):
                    try:
                        idx = int(combo.findText(a0))
                    except (TypeError, AttributeError, RuntimeError, ValueError):
                        idx = None

            if idx is None:
                try:
                    idx = int(combo.currentIndex())
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    idx = -1

            if idx < 0:
                return

            # Prefer itemText(idx) because currentText() can lag behind in some
            # signal-ordering cases (especially offscreen tests).
            selected_hz = ""
            try:
                if hasattr(combo, "itemText"):
                    selected_hz = str(combo.itemText(idx) or "").strip()
            except (TypeError, AttributeError, RuntimeError):
                selected_hz = ""

            if not selected_hz:
                try:
                    selected_hz = str(combo.currentText() or "").strip()
                except (TypeError, AttributeError, RuntimeError):
                    selected_hz = ""

            if not selected_hz:
                return

        except (TypeError, AttributeError, RuntimeError):
            pass

        # Guard: if resolution failed, bail out before continuing.
        if combo is None or idx < 0 or (not selected_hz):
            return

        # --- pull src from itemData (CandidateComboController) ---
        src = ""
        try:
            data = None
            # QComboBox stores userData under Qt.UserRole; itemData() without role
            # often returns that, but be explicit when possible.
            try:
                data = combo.itemData(idx)
            except (TypeError, AttributeError, RuntimeError):
                data = None

            if (data is None) and (_Qt is not None):
                try:
                    data = combo.itemData(idx, _Qt.ItemDataRole.UserRole)
                except (TypeError, AttributeError, RuntimeError):
                    data = None

            # Accept a few tolerant shapes.
            if isinstance(data, dict):
                try:
                    src = str(data.get("src", "") or "").strip()
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    src = ""
            elif isinstance(data, (list, tuple)):
                # Expected: (hz, src, score?)
                try:
                    if len(data) >= 2:
                        src2 = str(data[1] or "").strip()
                        if src2:
                            src = src2
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    pass
            else:
                # If controller didn't store anything useful, src remains empty.
                src = src or ""
        except (TypeError, AttributeError, RuntimeError):
            src = ""

        # --- apply selection to UI ---
        try:
            w_hz = getattr(self, "_add_hz", None)
            if w_hz is not None and hasattr(w_hz, "setText"):
                w_hz.setText(selected_hz)
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Meanings for this candidate
        try:
            ms = self._resolve_meanings_for_candidate(selected_hz, src)
            joined = ", ".join([str(x).strip() for x in (ms or []) if str(x).strip()])
            w_mn = getattr(self, "_add_mn", None)
            if w_mn is not None and hasattr(w_mn, "setText"):
                w_mn.setText(joined)
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Update SM ctx hanzi best-effort
        try:
            ctx = getattr(self, "_add_edit_ctx", None)
        except (TypeError, AttributeError, RuntimeError):
            ctx = None

        if ctx is not None:
            try:
                ctx.hanzi = selected_hz
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Refresh Save gating
        try:
            fn_gate = getattr(self, "_update_save_enabled", None)
            if callable(fn_gate):
                fn_gate()
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Keep focus moving forward (prevents category from stealing focus after
        # candidate selection). Use a 0ms singleShot to avoid focus races when the
        # popup closes.
        try:
            w_mn = getattr(self, "_add_mn", None)
            if w_mn is not None and hasattr(w_mn, "setFocus"):
                try:
                    QTimer.singleShot(0, w_mn.setFocus)
                except (TypeError, AttributeError, RuntimeError):
                    try:
                        w_mn.setFocus()
                    except (TypeError, AttributeError, RuntimeError):
                        pass
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _on_candidate_text_changed(self, text: str) -> None:
        """Delegate to index-activated handler for consistent candidate selection logic."""
        try:
            combo = getattr(self, "_cand_combo", None)
            if combo is None:
                return
            idx = int(combo.currentIndex())
            if idx < 0:
                return
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return

        try:
            self._on_candidate_index_activated(idx)
        except (TypeError, AttributeError, RuntimeError):
            return