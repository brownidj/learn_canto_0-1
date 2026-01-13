import logging
import os
import re
import shlex
import sys
import tempfile
import time
from typing import Any, cast, Optional

from infra.paths import project_root, ui_path
from persistence.categories_store import load_categories as _load_categories

logger = logging.getLogger(__name__)


from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGroupBox, QLineEdit,
    QTextEdit, QComboBox, QToolButton, QSlider, QDialog, QMessageBox,
    QSizePolicy,
    QLayout,
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, Qt, QTimer, QProcess, QEvent, QObject
from PySide6.QtGui import QFontMetrics

from settings import load_all, save_one, reset_all, bounds
from category_manager import CategoryManagerDialog


# ---- Test helper: construct the Add/Edit dialog deterministically ----
# Several UI integration tests expect `main._load_add_dialog()` to exist.
# This must be safe to call when `main` is imported as a module (i.e., without
# executing the `__main__` block).

def _load_add_dialog(parent: Optional[QWidget] = None) -> CategoryManagerDialog:
    """Create and return the Add/Edit dialog (CategoryManagerDialog).

    This helper is intended for tests. It avoids reliance on globals initialised
    in the `__main__` block.

    Args:
        parent: Optional Qt parent widget.

    Returns:
        A constructed CategoryManagerDialog instance.
    """
    # Ensure a QApplication exists (tests sometimes construct dialogs directly).
    try:
        app = QApplication.instance()
    except Exception:
        app = None

    if app is None:
        # Best-effort: create a local application for the dialog.
        # Use an empty argv to avoid consuming pytest args.
        try:
            QApplication([])
        except Exception:
            # If we cannot create an application, allow the constructor to raise
            # in the calling test.
            pass

    # Load a vocab snapshot (used for duplicate checks / preview behaviour).
    try:
        vocab_dict, vocab_categories_map = _load_vocab_from_unified_yaml()
    except Exception:
        vocab_dict, vocab_categories_map = {}, {}

    # Load authoritative categories from categories.yaml when available.
    cats_map = None
    try:
        cats_map = _load_categories()
    except Exception:
        cats_map = None

    if not isinstance(cats_map, dict) or not cats_map:
        cats_map = vocab_categories_map if isinstance(vocab_categories_map, dict) else {}

    # Construct the dialog.
    return CategoryManagerDialog(parent, vocab_dict if isinstance(vocab_dict, dict) else {}, cats_map)


# ---- settings shim: provide load_one via load_all if not exported ----
def load_one(key, default=None):
    try:
        cfg = load_all()
        if isinstance(cfg, dict):
            return cfg.get(key, default)
    except Exception:
        pass
    return default


# Import extracted helper functions
from main_helpers import (
    normalize_reverse_index as _normalize_reverse_index,
    parse_base_point_size_from_stylesheet,
    perf_start as _perf_start,
    perf_end as _perf_end,
)

# Import extracted service functions
from services.vocab_loader import (
    load_vocab_from_unified_yaml as _load_vocab_from_unified_yaml,
    load_categories_from_disk as _load_categories_from_disk,
    load_categories_map as _load_categories_map,
    commit_vocab_entry,
)
from services.tts_service import TTSService
from services.reverse_lookup_service import ReverseLookupService
from ui.main_window_setup import MainWindowSetup
from ui.hanzi_font_controller import HanziFontController
from ui.disclosure_handlers import setup_delays_disclosure, setup_about_disclosure, setup_tones_radicals_toggle
from ui.label_helpers import update_all_labels
from controllers.main_controller import MainController
from utils.debug_ui import dump_layout_tree, should_skip_debug_introspection

# === Reverse lookup helpers (Tier 1 & 2) ===
try:
    from infra.hanzi_composition import (
        compose_candidates_from_chars,
        shortlist_candidates,
    )
except Exception:
    compose_candidates_from_chars = None
    shortlist_candidates = None

# Tier 1 reverse index files + Unihan JSON loading are infrastructure concerns.
try:
    from infra.reverse_index import load_reverse_index_files
except Exception:
    load_reverse_index_files = None

try:
    from infra.unihan import load_unihan_char_map
except Exception:
    load_unihan_char_map = None


# ===== DEBUG: add_item.ui layout introspection =====
def _load_add_item_ui(parent=None) -> QDialog | None:
    path = ui_path("add_item.ui")
    file = QFile(path)
    if not file.exists():
        logger.error("add_item.ui not found at %s", path)
        return None
    if not file.open(QIODevice.OpenModeFlag.ReadOnly):
        logger.error("Cannot open add_item.ui at %s", path)
        return None
    try:
        dlg = QUiLoader().load(file, parent)
        # QUiLoader.load() is typed as QWidget; enforce that this UI is actually a QDialog.
        if not isinstance(dlg, QDialog):
            logger.error("add_item.ui root is not a QDialog; got %r", type(dlg))
            return None
        if dlg is None:
            logger.error("QUiLoader returned None for add_item.ui")
            return None

        # --- Geometry contract: portrait screen dimensions, but in landscape ---
        # Prefer settings.bounds() if it provides a canonical portrait size; otherwise fall back to parent/suggested sizes.
        portrait_w = None
        portrait_h = None
        try:
            b = bounds()
        except Exception:
            b = None

        # Common patterns: bounds()["window"] or bounds()["screen"] as (w, h, step) or (w, h)
        try:
            if isinstance(b, dict):
                if "window" in b and isinstance(b.get("window"), (list, tuple)):
                    tup = b.get("window")
                    if len(tup) >= 2:
                        portrait_w = int(tup[0])
                        portrait_h = int(tup[1])
                if (portrait_w is None or portrait_h is None) and "screen" in b and isinstance(b.get("screen"),
                                                                                               (list, tuple)):
                    tup = b.get("screen")
                    if len(tup) >= 2:
                        portrait_w = int(tup[0])
                        portrait_h = int(tup[1])
        except Exception:
            portrait_w = None
            portrait_h = None

        # Fallback: use parent geometry if supplied
        if portrait_w is None or portrait_h is None:
            try:
                if parent is not None:
                    portrait_w = int(parent.width())
                    portrait_h = int(parent.height())
            except Exception:
                portrait_w = None
                portrait_h = None

        # Final fallback: use the dialog's size hint
        if portrait_w is None or portrait_h is None:
            try:
                sh = dlg.sizeHint()
                portrait_w = int(sh.width())
                portrait_h = int(sh.height())
            except Exception:
                portrait_w = 600
                portrait_h = 900

        # Swap portrait dims to get a landscape dialog.
        # Force landscape regardless of what bounds()/sizeHint returned.
        try:
            # Hard contract: Add/Edit dialog is the portrait baseline (720x1280) swapped into landscape.
            # Do not derive from bounds() or sizeHint() here; offscreen/test sizing and Qt sizeHints can be misleading.
            land_w = 1280
            land_h = 720
        except Exception:
            land_w = 900
            land_h = 600

        # Enforce a fixed dialog size so UI is consistent regardless of layout tweaks.
        # Enforce a fixed dialog size so UI is consistent regardless of layout tweaks.
        def _apply_fixed_add_item_size():
            try:
                # setFixedSize is the strongest contract; keep min/max in sync for safety.
                dlg.setFixedSize(land_w, land_h)
                dlg.setMinimumSize(land_w, land_h)
                dlg.setMaximumSize(land_w, land_h)
                dlg.resize(land_w, land_h)
                try:
                    dlg.updateGeometry()
                except Exception:
                    pass
                logger.debug(
                    "add_item dialog fixed size -> %dx%d (from portrait %dx%d)",
                    land_w,
                    land_h,
                    int(portrait_w),
                    int(portrait_h),
                )
            except Exception as _e:
                logger.debug("add_item dialog sizing failed: %r", _e)

        # Apply immediately, then re-apply after the first layout pass.
        _apply_fixed_add_item_size()
        QTimer.singleShot(0, _apply_fixed_add_item_size)
        QTimer.singleShot(50, _apply_fixed_add_item_size)

        # Attach resize logger
        _orig_resize = dlg.resizeEvent

        def _dbg_resize(ev):
            logger.debug("RESIZE: dlg %dx%d | entry=%s %dx%d | hanzi=%s %dx%d",
                         dlg.width(), dlg.height(),
                         getattr(dlg.findChild(QGroupBox, "groupEntry"), "objectName", lambda: "groupEntry")(),
                         dlg.findChild(QGroupBox, "groupEntry").width() if dlg.findChild(QGroupBox,
                                                                                         "groupEntry") else -1,
                         dlg.findChild(QGroupBox, "groupEntry").height() if dlg.findChild(QGroupBox,
                                                                                          "groupEntry") else -1,
                         getattr(dlg.findChild(QGroupBox, "groupHanzi"), "objectName", lambda: "groupHanzi")(),
                         dlg.findChild(QGroupBox, "groupHanzi").width() if dlg.findChild(QGroupBox,
                                                                                         "groupHanzi") else -1,
                         dlg.findChild(QGroupBox, "groupHanzi").height() if dlg.findChild(QGroupBox,
                                                                                          "groupHanzi") else -1)
            return _orig_resize(ev)

        dlg.resizeEvent = _dbg_resize

        # Log once after show, to dump full tree with actual sizes
        def _after_show():
            if should_skip_debug_introspection():
                return

            # Guard: dlg may have been deleted; use shiboken6 validity where available.
            try:
                import shiboken6  # type: ignore
            except Exception:
                shiboken6 = None

            try:
                if dlg is None:
                    return
                if shiboken6 is not None and hasattr(shiboken6, "isValid"):
                    try:
                        if not shiboken6.isValid(dlg):
                            return
                    except Exception:
                        pass
            except Exception:
                return

            # Check visibility
            try:
                if not dlg.isVisible():
                    return
            except RuntimeError:
                return
            except Exception:
                pass

            try:
                logger.debug("=== add_item.ui TREE DUMP (after show) ===")
                dump_layout_tree(dlg, 0)
                ge = dlg.geometry()
                logger.debug(
                    "DIALOG size: %dx%d minimum:%dx%d",
                    ge.width(),
                    ge.height(),
                    dlg.minimumWidth(),
                    dlg.minimumHeight(),
                )
            except RuntimeError:
                return

        # Avoid scheduling post-show debug work during tests/offscreen runs.
        if not should_skip_debug_introspection():
            QTimer.singleShot(50, _after_show)
        return dlg  # type: ignore[return-value]
    finally:
        file.close()


def debug_open_add_item_dialog():
    dlg = _load_add_item_ui(window)  # use main window as parent if available
    if dlg is None:
        return
    dlg.show()


# ===== END DEBUG =====


def load_ui(path: str):
    # Convert relative path to absolute path
    abs_path = os.path.abspath(path)
    ui_file = QFile(abs_path)
    if not ui_file.open(QIODevice.OpenModeFlag.ReadOnly):
        raise FileNotFoundError("Cannot open UI file: {}".format(abs_path))
    try:
        loader = QUiLoader()
        window = loader.load(ui_file)
    finally:
        ui_file.close()
    if window is None:
        raise RuntimeError("Failed to load UI from: {}".format(abs_path))
    return window


# MainController is imported from controllers.main_controller

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")
    app = QApplication(sys.argv)

    # Load the Qt Designer form. Use absolute or relative-to-absolute path conversion.
    try:
        window = cast(Any, load_ui("./ui/form.ui"))
        # Load bounds once so they are available to handlers like _on_tortoise_toggled
        b = bounds()

        # ---- UI Setup using MainWindowSetup ----
        # Create controller first (needed by setup)
        label_hanzi = window.findChild(QLabel, "labelHanzi")

        # Configure Hanzi label appearance
        if label_hanzi is not None:
            label_hanzi.setWordWrap(False)
            label_hanzi.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

            try:
                label_hanzi.setContentsMargins(0, 0, 0, 0)
            except Exception:
                # Sanitize stylesheet if it had padding
                ss = label_hanzi.styleSheet() or ""
                if "padding-left" in ss or "padding-right" in ss:
                    ss = ss.replace("padding-left:", "/*padding-left:*/")
                    ss = ss.replace("padding-right:", "/*padding-right:*/")
                label_hanzi.setStyleSheet(ss)

            label_hanzi.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            logger.debug("labelHanzi sizePolicy set to Ignored/Preferred to avoid window width jump")

            # Initialize font controller
            hanzi_font_ctrl = HanziFontController(label_hanzi, window)
            QTimer.singleShot(0, hanzi_font_ctrl.capture_baseline)

            # Expose update method for MainController
            window._update_hanzi_font_now = lambda: hanzi_font_ctrl.update_font_now(
                jyut_text=edit_jyut.text() if edit_jyut is not None else ""
            )

        edit_jyut = window.findChild(QLineEdit, "jyutping")
        text_meanings = window.findChild(QTextEdit, "textMeanings")
        controller = MainController(window, label_hanzi, edit_jyut, text_meanings)

        # Initialize UI setup handler
        ui_setup = MainWindowSetup(window, controller)

        # --- Playback/TTS arming & button state (defined early so it exists before first call) ---
        window._is_playing = False
        window._tts_armed = False

        # Load vocabulary and categories from unified vocab.yaml
        _t_vocab = _perf_start("load vocab.yaml")
        vocab, categories_map = _load_vocab_from_unified_yaml()
        _perf_end("load vocab.yaml", _t_vocab)
        logger.debug(
            "Loaded unified vocab.yaml: %d hanzi entries, %d categories",
            len(vocab),
            len(categories_map),
        )

        # Prefer authoritative categories.yaml for category list; fall back to vocab-derived.
        try:
            cats_disk = _load_categories_from_disk()
        except Exception:
            cats_disk = {}

        if isinstance(cats_disk, dict) and cats_disk:
            categories_map = cats_disk
            try:
                logger.debug(
                    "Loaded categories.yaml: %d categories (authoritative)",
                    len(categories_map),
                )
            except Exception:
                pass

        # Store vocab and categories on window for controller access
        window._vocab = vocab
        window._categories_map = categories_map

        # --- Load categories map and resolve saved category ---
        saved_category = load_one("category") or "All"

        # Run main UI setup
        ui_setup.setup_all(b, categories_map, saved_category)

        # Get slider references for use in code below
        slider_wpm = ui_setup.slider_wpm
        slider_repeats = ui_setup.slider_repeats
        slider_intro = ui_setup.slider_intro
        slider_repeat = ui_setup.slider_repeat
        slider_extro = ui_setup.slider_extro
        slider_auto = ui_setup.slider_auto
        btn_reset = ui_setup.btn_reset

        # Update controller buttons state after setup
        controller.update_buttons()
        # Make categories available to other parts of the app (e.g., Add & Edit dialog)
        try:
            cats_best = _load_categories_map()
        except Exception:
            cats_best = categories_map

        if isinstance(cats_best, dict) and cats_best:
            categories_map = cats_best

        try:
            setattr(window, "_categories_map", categories_map)
            logger.debug("Attached _categories_map to window: %d categories", len(categories_map or {}))
        except Exception:
            pass

        # Wire category combo change handler
        def _on_category_changed(name):
            save_one("category", name)
            # Reset TTS arming: relabel to Play, mark unarmed, and update buttons
            try:
                window._tts_armed = False
                if ui_setup.btn_play is not None:
                    ui_setup.btn_play.setText("Play")
            except Exception:
                pass
            controller.update_buttons()
            controller.apply_category_filter(name)

        ui_setup.wire_category_change(_on_category_changed)

        # Apply initial category filter
        if ui_setup.combo_category is not None:
            controller.apply_category_filter(ui_setup.combo_category.currentText())
        else:
            logger.debug("comboCategory not found; applying saved category '%s'", saved_category)
            controller.apply_category_filter(saved_category if saved_category in categories_map or saved_category == "All" else "All")
        # --- Tortoise (slow mode) & Auto mode wiring ---
        btn_tortoise = window.findChild(QPushButton, "btnTortoise")
        btn_auto = window.findChild(QPushButton, "btnAuto")

        # Remember last non-tortoise WPM so we can restore it
        window._tortoise_prev_wpm = None


        def _on_tortoise_toggled(checked: bool):
            if slider_wpm is None:
                return
            wpm_min, wpm_max, _ = b["wpm"] if isinstance(b, dict) and "wpm" in b else (60, 220, 1)
            if checked:
                # store current WPM and force to min (60)
                try:
                    window._tortoise_prev_wpm = int(slider_wpm.value())
                except Exception:
                    window._tortoise_prev_wpm = None
                slider_wpm.setValue(int(wpm_min))
                save_one("wpm", int(wpm_min))
                logger.debug("Tortoise ON: set WPM -> %d (stored prev=%r)", int(wpm_min), window._tortoise_prev_wpm)
            else:
                # restore previous WPM if available
                prev = window._tortoise_prev_wpm
                if isinstance(prev, int) and prev > 0:
                    slider_wpm.setValue(prev)
                    save_one("wpm", prev)
                    logger.debug("Tortoise OFF: restored WPM -> %d", prev)
                else:
                    logger.debug("Tortoise OFF: no previous WPM to restore")


        # Auto mode
        window._auto_mode = False
        window._auto_pending = False  # guard to avoid double starts

        # Connect toggles if present
        if btn_tortoise is not None:
            try:
                btn_tortoise.setCheckable(True)  # already set in .ui, but harmless
            except Exception:
                pass
            btn_tortoise.toggled.connect(_on_tortoise_toggled)

        if btn_auto is not None:
            btn_auto.toggled.connect(controller.set_auto_mode)


        # --- TTS wiring: Initialize service ---
        tts_service = TTSService(window)
        _available_voices = tts_service.available_voices
        _default_voice = tts_service.default_voice

        # Ensure a shared Unihan char map is available as a dict.
        _t_cmap = 0.0
        try:
            cmap = {}
            prev = getattr(window, "_char_map", None)
            _t_cmap = _perf_start("load_unihan_char_map")
            _cmap_src = "empty"
            if isinstance(prev, dict) and prev:
                cmap = prev
                _cmap_src = "cache"
            else:
                _cmap_src = "disk" if callable(load_unihan_char_map) else "unavailable"
                if callable(load_unihan_char_map):
                    cmap = load_unihan_char_map(project_root()) or {}
                else:
                    cmap = {}

            setattr(window, "_char_map", cmap if isinstance(cmap, dict) else {})
            _perf_end("load_unihan_char_map", _t_cmap)
            try:
                logger.debug("CacheAudit: char_map source=%s size=%d", _cmap_src,
                             len(getattr(window, "_char_map", {}) or {}))
            except Exception:
                pass
            logger.debug(
                "Unihan char_map ready: %d entries (shared)",
                len(getattr(window, "_char_map", {}) or {}),
            )
        except Exception as _e:
            _perf_end("load_unihan_char_map", _t_cmap)
            setattr(window, "_char_map", {})
            logger.debug("Unihan shared map not available: %r", _e)

        # Attach a reverse index onto the main window
        try:
            prev_idx = getattr(window, "_reverse_index", None)
        except Exception:
            prev_idx = None

        try:
            if isinstance(prev_idx, dict) and prev_idx:
                window._reverse_index = _normalize_reverse_index(prev_idx)
                try:
                    logger.debug(
                        "CacheAudit: reverse_index source=cache size=%d",
                        len(getattr(window, "_reverse_index", {}) or {}),
                    )
                except Exception:
                    pass
            else:
                _t_rev = _perf_start("load_reverse_index_files")
                try:
                    if callable(load_reverse_index_files):
                        window._reverse_index = _normalize_reverse_index(load_reverse_index_files(project_root()))
                        src = "disk"
                    else:
                        window._reverse_index = {}
                        src = "unavailable"
                except Exception:
                    window._reverse_index = {}
                    src = "error"
                _perf_end("load_reverse_index_files", _t_rev)
                try:
                    logger.debug("CacheAudit: reverse_index source=%s size=%d", src,
                                 len(getattr(window, "_reverse_index", {}) or {}))
                    try:
                        _sz = len(getattr(window, "_reverse_index", {}) or {})
                        if src == "disk" and _sz <= 3:
                            # Common symptom: loader returned a wrapper dict; normalization should prevent this.
                            logger.debug(
                                "Reverse index looks unusually small (size=%d); check data file path and loader output shape",
                                _sz)
                            try:
                                _keys = list((getattr(window, "_reverse_index", {}) or {}).keys())
                                logger.debug("Reverse index sample keys (up to 8): %r", _keys[:8])
                            except Exception:
                                pass
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            window._reverse_index = {}

        # Initialize reverse lookup service
        reverse_lookup = ReverseLookupService(
            reverse_index=getattr(window, "_reverse_index", {}),
            char_map=getattr(window, "_char_map", {}),
            compose_fn=compose_candidates_from_chars,
            shortlist_fn=shortlist_candidates
        )

        def _reverse_candidates_for_jy(jy: str) -> list[tuple[str, str, int]]:
            """Wrapper for reverse lookup service."""
            return reverse_lookup.candidates_for_jyutping(jy)

        def _commit_vocab_entry_from_dialog(entry: dict, dialog=None):
            """Wrapper to maintain signature compatibility with existing code."""
            global vocab, categories_map
            commit_vocab_entry(entry, vocab, categories_map, window, dialog)


        # Expose helper on window for dialogs
        try:
            setattr(window, "_reverse_candidates_for_jy", _reverse_candidates_for_jy)
        except Exception:
            pass

        # Setup UI disclosure handlers
        setup_delays_disclosure(
            window.findChild(QToolButton, "btnDelaysDisclosure"),
            window.findChild(QGroupBox, "groupDelays")
        )

        setup_about_disclosure(
            window.findChild(QToolButton, "btnAboutDisclosure"),
            window.findChild(QGroupBox, "groupAbout")
        )

        # Get group_about for audio test setup below
        group_about = window.findChild(QGroupBox, "groupAbout")

        # -----------------------------
        # In-app Category Manager Dialog
        # -----------------------------

        def _open_category_manager(focus_add: bool = False):
            """Open the Add & Edit dialog, ensuring categories are available on the window.
            Falls back to reloading from disk if the attribute is missing.
            """
            # Use the already-loaded vocab from this scope
            vocab_dict = vocab if isinstance(vocab, dict) else {}

            # Always reload categories from disk before opening the dialog.
            # This prevents reopening from a stale vocab-derived map.
            try:
                cats = _load_categories_map()
            except (TypeError, AttributeError, RuntimeError):
                cats = {}

            if isinstance(cats, dict) and cats:
                try:
                    setattr(window, "_categories_map", cats)
                except (TypeError, AttributeError, RuntimeError):
                    pass
                try:
                    # Keep module-level cache coherent for apply_category_filter() and dropdown rebuilds
                    global categories_map
                    categories_map = cats
                except (TypeError, AttributeError, RuntimeError):
                    # If global fails for any reason, ignore (best-effort)
                    pass
            else:
                try:
                    cats = getattr(window, "_categories_map", None)
                except (TypeError, AttributeError, RuntimeError):
                    cats = None
                if not isinstance(cats, dict):
                    cats = {}

            logger.debug("_open_category_manager: categories ready -> %d keys", len(cats or {}))

            _t_dlg = _perf_start("CategoryManagerDialog(create)")
            dlg = CategoryManagerDialog(window, vocab_dict, cats)
            try:
                edits = dlg.findChildren(QLineEdit)
                logger.debug("LIVE dlg QLineEdits: %r", [e.objectName() for e in edits])
            except Exception as e:
                logger.debug("Probe failed: %r", e)
            _perf_end("CategoryManagerDialog(create)", _t_dlg)

            # --- DEBUG: log actual Add/Edit dialog sizing ---
            try:
                geo = dlg.geometry()
                logger.debug(
                    "Add/Edit dlg initial: size=%dx%d min=%dx%d max=%dx%d geo=%dx%d@%d,%d hint=%dx%d",
                    int(dlg.width()),
                    int(dlg.height()),
                    int(dlg.minimumWidth()),
                    int(dlg.minimumHeight()),
                    int(dlg.maximumWidth()),
                    int(dlg.maximumHeight()),
                    int(geo.width()),
                    int(geo.height()),
                    int(geo.x()),
                    int(geo.y()),
                    int(dlg.sizeHint().width()),
                    int(dlg.sizeHint().height()),
                )
            except Exception as _e:
                logger.debug("Add/Edit dlg initial sizing log failed: %r", _e)

            def _log_dlg_after_exec():
                try:
                    geo2 = dlg.geometry()
                    logger.debug(
                        "Add/Edit dlg after-exec: size=%dx%d min=%dx%d max=%dx%d geo=%dx%d@%d,%d",
                        int(dlg.width()),
                        int(dlg.height()),
                        int(dlg.minimumWidth()),
                        int(dlg.minimumHeight()),
                        int(dlg.maximumWidth()),
                        int(dlg.maximumHeight()),
                        int(geo2.width()),
                        int(geo2.height()),
                        int(geo2.x()),
                        int(geo2.y()),
                    )
                except Exception as _e2:
                    logger.debug("Add/Edit dlg after-exec sizing log failed: %r", _e2)

            QTimer.singleShot(0, _log_dlg_after_exec)
            QTimer.singleShot(50, _log_dlg_after_exec)

            # Provide a commit callback so Save in the dialog can update vocab and persist to YAML
            try:
                def _commit_with_dialog(entry: dict):
                    return _commit_vocab_entry_from_dialog(entry, dialog=dlg)

                dlg._commit_callback = _commit_with_dialog
            except Exception:
                logger.debug("Could not attach commit callback to CategoryManagerDialog")

            # Provide reverse candidates and shared char map to the dialog
            try:
                if hasattr(window, "_reverse_candidates_for_jy"):
                    dlg._reverse_candidates_for_jy = window._reverse_candidates_for_jy
            except Exception:
                pass
            try:
                if isinstance(getattr(window, "_char_map", None), dict):
                    dlg._char_map = window._char_map
            except Exception:
                pass

            # Optional: place focus straight into the Jyutping field when requested
            if focus_add:
                try:
                    if hasattr(dlg, "_add_jy") and dlg._add_jy is not None:
                        dlg._add_jy.setFocus()
                except Exception:
                    pass

            _t_exec = _perf_start("CategoryManagerDialog.exec")
            dlg.exec()
            _perf_end("CategoryManagerDialog.exec", _t_exec)

            # After dialog closes: reload authoritative categories.yaml and refresh the main category dropdown.
            try:
                cats_after = _load_categories_map()
            except Exception:
                cats_after = {}

            if isinstance(cats_after, dict) and cats_after:
                try:
                    setattr(window, "_categories_map", cats_after)
                except Exception:
                    pass
                try:
                    categories_map = cats_after
                except Exception:
                    pass

                try:
                    combo_main = window.findChild(QComboBox, "comboCategory")
                except Exception:
                    combo_main = None

                if combo_main is not None:
                    try:
                        sel = combo_main.currentText() or "All"
                    except Exception:
                        sel = "All"

                    try:
                        combo_main.blockSignals(True)
                        combo_main.clear()
                        combo_main.addItem("All")
                        for k in sorted((categories_map or {}).keys()):
                            combo_main.addItem(k)
                        idx = combo_main.findText(sel)
                        if idx >= 0:
                            combo_main.setCurrentIndex(idx)
                        else:
                            # If the previous selection disappeared, fall back to All.
                            idx_all = combo_main.findText("All")
                            if idx_all >= 0:
                                combo_main.setCurrentIndex(idx_all)
                    except Exception:
                        pass
                    finally:
                        try:
                            combo_main.blockSignals(False)
                        except Exception:
                            pass

            # After the dialog closes, refresh the current category view so any new items appear.
            try:
                combo = window.findChild(QComboBox, "comboCategory")
                current_cat = combo.currentText() if combo is not None else "All"
            except Exception:
                current_cat = "All"
            controller.apply_category_filter(current_cat)


        def _load_add_item_dialog(parent):
            # Resolve absolute path using ui_path helper
            path = ui_path("add_item.ui")

            if not os.path.exists(path):
                QMessageBox.warning(parent, "Add Item", "UI not found at:\n{}".format(path))
                return None

            file = QFile(path)
            if not file.open(QIODevice.OpenModeFlag.ReadOnly):
                QMessageBox.warning(parent, "Add Item", "Unable to open UI file:\n{}".format(path))
                return None

            try:
                loader = QUiLoader()
                dlg = loader.load(file, parent)
                return dlg
            finally:
                file.close()

        # Setup tones & radicals toggle
        btn_tr = window.findChild(QToolButton, "btnTonesAndRadicalsToggle")
        if btn_tr is None:
            btn_tr = window.findChild(QPushButton, "btnTonesAndRadicalsToggle")

        setup_tones_radicals_toggle(
            btn_tr,
            window.findChild(QGroupBox, "groupSoundToneMastery"),
            window.findChild(QGroupBox, "groupRadicals")
        )

        # Add an Audio Test button inside the About group for quick diagnostics
        if group_about is not None:
            layout = group_about.layout()
            if layout is None:
                layout = QVBoxLayout(group_about)
                group_about.setLayout(layout)
            # Voice selector row
            row = QHBoxLayout()
            lbl_voice = QLabel("macOS voice:")
            combo_voice = QComboBox()
            combo_voice.setObjectName("comboVoice")
            # populate voices (show name and locale)
            for name, locale, desc in _available_voices:
                combo_voice.addItem(name)
            if _default_voice:
                idx = combo_voice.findText(_default_voice)
                if idx >= 0:
                    combo_voice.setCurrentIndex(idx)
            row.addWidget(lbl_voice)
            row.addWidget(combo_voice)
            # create a container widget for the row
            row_w = QGroupBox()
            row_w.setFlat(True)
            row_w.setTitle("")
            row_w.setLayout(QHBoxLayout())
            # transfer items from row into row_w layout
            row_w.layout().addWidget(lbl_voice)
            row_w.layout().addWidget(combo_voice)
            layout.addWidget(row_w)
            btn_audio_test = QPushButton("Audio Test (🔊 你好)")
            btn_audio_test.setObjectName("btnAudioTest")
            layout.addWidget(btn_audio_test)


            def _audio_test():
                sample = "你好"
                r = int(slider_wpm.value()) if slider_wpm is not None else None
                logger.debug("Audio test: speaking '%s' rate=%s", sample, r)
                played = _tts_call(sample, rate=r)
                if not played:
                    _fallback_say(sample, r)


            btn_audio_test.clicked.connect(_audio_test)

        # Wire Add button (in "Add and Edit") — always available
        btn_add = window.findChild(QPushButton, "btnAdd")
        if btn_add is None:
            for _b in window.findChildren(QPushButton):
                try:
                    if _b.text().strip().lower() == "add":
                        btn_add = _b
                        break
                except Exception:
                    pass

        DEBUG_ADD_ITEM_UI = False  # restore normal behaviour

        if btn_add is not None and not getattr(btn_add, "_lc_add_wired", False):
            if DEBUG_ADD_ITEM_UI:
                btn_add.clicked.connect(debug_open_add_item_dialog)
                QTimer.singleShot(300, debug_open_add_item_dialog)  # was for tree dump; remove when False
            else:
                btn_add.clicked.connect(lambda: _open_category_manager(focus_add=True))
            # Mark as wired so we don't double-connect or need disconnects
            btn_add._lc_add_wired = True


        def _get_current_voice():
            """Get the currently selected voice from the combo, or default."""
            combo = window.findChild(QComboBox, "comboVoice")
            if combo is not None and combo.currentText().strip():
                return combo.currentText().strip()
            return tts_service.default_voice


        def _tts_call(text, rate=None):
            """Compatibility shim for audio test button."""
            voice = _get_current_voice()
            tts_service.play_once(text, voice=voice, rate=rate)
            return True


        def _fallback_say(text, rate=None):
            """Compatibility shim (redirects to TTS service)."""
            _tts_call(text, rate)


        def _play_once(on_finished=None):
            """Play current vocab item once using TTS service."""
            idx = window._vocab_index
            if idx < 0 or not window._vocab_items:
                if callable(on_finished):
                    QTimer.singleShot(0, on_finished)
                return

            hanzi, val = window._vocab_items[idx]
            text = hanzi
            rate = int(slider_wpm.value()) if slider_wpm is not None else None
            voice = _get_current_voice()

            logger.debug("Play once (async): idx=%s hanzi='%s' rate=%s", idx, hanzi, rate)
            tts_service.play_once(text, voice=voice, rate=rate, on_finished=on_finished)


        def _play_sequence(on_done=None):
            """Play current vocab item with repeats and delays using TTS service."""
            # Respect repeats and delays
            repeats = int(slider_repeats.value()) if slider_repeats is not None else 1
            intro = int(slider_intro.value()) if slider_intro is not None else 0
            gap = int(slider_repeat.value()) if slider_repeat is not None else 0
            extro = int(slider_extro.value()) if slider_extro is not None else 0

            if window._is_playing:
                logger.debug("Play requested while already playing; ignoring")
                return

            idx = window._vocab_index
            if idx < 0 or not window._vocab_items:
                if callable(on_done):
                    QTimer.singleShot(0, on_done)
                return

            hanzi, val = window._vocab_items[idx]
            text = hanzi
            rate = int(slider_wpm.value()) if slider_wpm is not None else None
            voice = _get_current_voice()

            window._is_playing = True
            controller.update_buttons()  # disable all buttons

            def _sequence_done():
                window._is_playing = False
                controller.update_buttons()
                if callable(on_done):
                    on_done()

            tts_service.play_sequence(
                text=text,
                voice=voice,
                rate=rate,
                repeats=repeats,
                intro_delay=intro,
                repeat_delay=gap,
                extro_delay=extro,
                on_done=_sequence_done
            )


        # Show the first entry on startup (after category filter applied)
        controller.show_current()

        # Update all labels with ranges and current values
        def _update_labels_wrapper():
            update_all_labels(
                window,
                slider_wpm,
                slider_repeats,
                slider_intro,
                slider_repeat,
                slider_extro,
                slider_auto,
            )

        # Sliders already configured by setup_all()
        _update_labels_wrapper()

        # Wire slider changes to persist and update labels
        ui_setup.wire_slider_changes(_update_labels_wrapper)


        # Reset handler
        def _do_reset():
            new_vals = reset_all()
            if slider_wpm is not None:
                slider_wpm.setValue(int(new_vals["wpm"]))
            if slider_intro is not None:
                slider_intro.setValue(int(new_vals["intro_delay"]))
            if slider_repeat is not None:
                slider_repeat.setValue(int(new_vals["repeat_delay"]))
            if slider_extro is not None:
                slider_extro.setValue(int(new_vals["extro_delay"]))
            if slider_auto is not None:
                slider_auto.setValue(int(new_vals["auto_delay"]))
            if slider_repeats is not None:
                slider_repeats.setValue(int(new_vals["repeats"]))
            _update_labels_wrapper()
            # Reset category selection to 'All' (persist and apply)
            combo_category = window.findChild(QComboBox, "comboCategory")
            if combo_category is not None:
                idx = combo_category.findText("All")
                if idx >= 0:
                    combo_category.setCurrentIndex(idx)
                save_one("category", "All")
                controller.apply_category_filter("All")


        ui_setup.wire_reset_button(_do_reset)
        # ---- end wiring ----

        # The initial size (720x1280) is set in form.ui geometry. Just show it.
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        logger.exception("Fatal error in main:")
        sys.exit(1)
