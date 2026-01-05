import logging
import os
import re
import shlex
import sys
import tempfile
import time
from typing import Any, cast

import yaml
from infra.paths import project_root, data_path, ui_path


logger = logging.getLogger(__name__)


def _perf_start(name: str) -> float:
    try:
        t0 = time.perf_counter()
        try:
            logger.debug("PERF start: %s", name)
        except Exception:
            pass
        return t0
    except Exception:
        return 0.0


def _perf_end(name: str, t0: float) -> None:
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


# ---- settings shim: provide load_one via load_all if not exported ----
def load_one(key, default=None):
    try:
        cfg = load_all()
        if isinstance(cfg, dict):
            return cfg.get(key, default)
    except Exception:
        pass
    return default


# === Unified vocab.yaml loader ===
def _load_vocab_from_unified_yaml():
    """Load vocab.yaml (unified categories + entries) and return (vocab, categories_map).

    vocab: {hanzi: [meanings_list, jyutping_str]}
    categories_map: {category: [hanzi, ...]}
    """
    path = data_path("vocab.yaml")
    if not os.path.exists(path):
        logger.warning("vocab.yaml not found at: %s", path)
        return {}, {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as e:
        logger.warning("Failed to load vocab.yaml: %s", e)
        return {}, {}

    if not isinstance(data, dict):
        logger.warning("vocab.yaml top-level is not a mapping; got %r", type(data))
        return {}, {}

    categories_block = data.get("categories") or {}
    entries_block = data.get("entries") or {}

    if not isinstance(categories_block, dict):
        categories_block = {}
    if not isinstance(entries_block, dict):
        entries_block = {}

    vocab = {}
    categories_map = {}

    # Start with empty lists for all defined categories
    for cat_key in categories_block.keys():
        categories_map[str(cat_key)] = []

    # Populate vocab and categories from entries
    for jy_key, entry in entries_block.items():
        if not isinstance(entry, dict):
            continue
        jyut = entry.get("jyutping") or jy_key
        senses = entry.get("senses") or []
        if not isinstance(senses, list):
            continue
        for sense in senses:
            if not isinstance(sense, dict):
                continue
            hanzi = sense.get("hanzi")
            gloss = sense.get("gloss")
            cats = sense.get("categories") or []
            if not hanzi or not gloss:
                continue

            # Build meanings list as a list of gloss strings; merge if Hanzi already present
            if hanzi in vocab:
                existing_meanings = vocab[hanzi][0]
                existing_jy = vocab[hanzi][1]
                if gloss not in existing_meanings:
                    existing_meanings.append(gloss)
                if not existing_jy and jyut:
                    vocab[hanzi][1] = jyut
            else:
                vocab[hanzi] = [[gloss], jyut]

            # Populate categories map
            for cat in cats:
                if not cat:
                    continue
                cat_str = str(cat)
                if cat_str not in categories_map:
                    categories_map[cat_str] = []
                if hanzi not in categories_map[cat_str]:
                    categories_map[cat_str].append(hanzi)

    # Ensure an 'unassigned' bucket exists even if empty
    if "unassigned" not in categories_map:
        categories_map["unassigned"] = []

    return vocab, categories_map


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
def _dump_layout_tree(widget: QWidget, indent=0):
    """Print the widget/layout hierarchy with size policies and geometries."""
    sp = widget.sizePolicy()
    try:
        geo = widget.geometry()
        geo_str = f"{geo.width()}x{geo.height()}@{geo.x()},{geo.y()}"
    except Exception:
        geo_str = "n/a"
    logger.debug("%s[%s] name=%r policy=%s/%s min=%sx%s max=%sx%s geo=%s",
                 "  " * indent,
                 widget.metaObject().className(),
                 widget.objectName(),
                 sp.horizontalPolicy(), sp.verticalPolicy(),
                 widget.minimumWidth(), widget.minimumHeight(),
                 widget.maximumWidth(), widget.maximumHeight(),
                 geo_str)
    lay = widget.layout()
    if isinstance(lay, QLayout):
        logger.debug("%s  <layout %s name=%r margin=%s spacing=%s>",
                     "  " * indent, type(lay).__name__, getattr(lay, "objectName", lambda: "")(),
                     lay.contentsMargins(), lay.spacing())
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item is None:
                continue
            if item.widget():
                _dump_layout_tree(item.widget(), indent + 2)
            elif item.layout():
                # make a tiny proxy widget to print layout info
                logger.debug("%s  <sublayout %s>", "  " * (indent + 1), type(item.layout()).__name__)
                # Dive into sublayout by iterating its items
                sub = item.layout()
                for j in range(sub.count()):
                    subitem = sub.itemAt(j)
                    if subitem and subitem.widget():
                        _dump_layout_tree(subitem.widget(), indent + 3)
    else:
        # PySide6: find-child options live under Qt.FindChildOption in many versions/stubs.
        # If unavailable, fall back to the default recursive behaviour by omitting `options=`.
        _opts = None
        try:
            from PySide6.QtCore import Qt as _Qt
            _opt = getattr(_Qt, "FindChildOption", None)
            if _opt is not None:
                _opts = getattr(_opt, "FindDirectChildrenOnly", None)
                if _opts is None:
                    _opts = getattr(_opt, "FindChildrenRecursively", None)
        except Exception:
            _opts = None

        if _opts is None:
            for ch in widget.findChildren(QWidget):
                _dump_layout_tree(ch, indent + 1)
        else:
            for ch in widget.findChildren(QWidget, options=_opts):
                _dump_layout_tree(ch, indent + 1)


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
                if (portrait_w is None or portrait_h is None) and "screen" in b and isinstance(b.get("screen"), (list, tuple)):
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
            # In tests/offscreen, skip heavy tree-dump introspection entirely.
            try:
                if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
                    return
                if os.environ.get("PYTEST_CURRENT_TEST"):
                    return
            except Exception:
                # If env access fails, proceed.
                pass

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
                        # If validity check fails, fall back to Qt checks below.
                        pass
            except Exception:
                return

            # Check visibility; if not visible or destroyed, return
            try:
                if not dlg.isVisible():
                    return
            except RuntimeError:
                return
            except Exception:
                # If isVisible fails for other reasons, proceed (fail open)
                pass

            try:
                logger.debug("=== add_item.ui TREE DUMP (after show) ===")
                _dump_layout_tree(dlg, 0)
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
        try:
            if os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen" and not os.environ.get("PYTEST_CURRENT_TEST"):
                QTimer.singleShot(50, _after_show)
        except Exception:
            # If env checks fail, schedule as before.
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


class MainController:
    """Lightweight controller wrapper that centralises high-level UI actions.

    This groups the 'big' behaviours like showing the current item, changing category,
    playing the sequence, and moving next/previous, so they can be exercised in tests
    without going through button click signals.
    """

    def __init__(self, window, label_hanzi=None, edit_jyut=None, text_meanings=None):
        self.window = window
        self.label_hanzi = label_hanzi
        self.edit_jyut = edit_jyut
        self.text_meanings = text_meanings

        # Button references (wired later from __main__)
        self.btn_play = None
        self.btn_next = None
        self.btn_prev = None

    def show_current(self):
        """Show the current vocab item in the UI."""
        window = self.window
        idx = getattr(window, "_vocab_index", -1)
        items = getattr(window, "_vocab_items", [])
        if idx < 0 or not items:
            return

        try:
            hanzi, val = items[idx]
        except Exception:
            return

        meanings = val[0] if isinstance(val, list) and len(val) > 0 else []
        jyut = val[1] if isinstance(val, list) and len(val) > 1 else ""
        # Inlined _ensure_jyut behaviour: only use supplied jyut
        jyut = jyut or ""

        logger.debug("Show index=%s hanzi='%s' jyut='%s' meanings=%s", idx, hanzi, jyut, meanings)

        label_hanzi = self.label_hanzi
        edit_jyut = self.edit_jyut
        text_meanings = self.text_meanings

        # Update Hanzi label + font fitting
        if label_hanzi is not None:
            try:
                label_hanzi.setText(hanzi)
                upd = getattr(window, "_update_hanzi_font_now", None)
                if callable(upd):
                    try:
                        upd()
                        QTimer.singleShot(0, upd)
                    except Exception:
                        pass
            except Exception:
                pass

        # Update Jyutping field
        if edit_jyut is not None:
            try:
                edit_jyut.setText(jyut)
            except AttributeError:
                # Fallback for QLabel vs QLineEdit differences
                try:
                    edit_jyut.setText(jyut)
                except Exception:
                    pass

        # Update meanings text
        from PySide6.QtWidgets import QTextEdit as _QTextEdit  # local alias to avoid circulars at import time
        if text_meanings is not None and isinstance(text_meanings, _QTextEdit):
            try:
                text_meanings.setPlainText(", ".join(meanings))
            except Exception:
                pass

    def apply_category_filter(self, cat_name: str):
        """Filter the vocabulary list by the given category name; 'All' shows everything."""
        window = self.window

        # Guard: ignore category changes during playback
        if getattr(window, "_is_playing", False):
            logger.debug("Category change requested during playback -> ignored")
            return

        # Use the module-level vocab/categories_map for now
        full_items = list(vocab.items())
        if cat_name and cat_name != "All" and cat_name in categories_map:
            hanzi_set = set(categories_map.get(cat_name, []))
            filtered = [item for item in full_items if item[0] in hanzi_set]
        else:
            filtered = full_items

        window._vocab_items = filtered
        window._vocab_index = 0 if filtered else -1
        logger.debug("Category set to %s -> %d items", cat_name, len(filtered))

        # Use the controller’s show_current
        self.show_current()

    def next_item(self):
        """Advance to the next vocab item and play it, respecting playback guards."""
        window = self.window

        # Ignore if playing; (buttons are disabled while playing anyway)
        if getattr(window, "_is_playing", False):
            return
        # If not armed yet, ignore (Next is disabled; this is just a guard)
        if not getattr(window, "_tts_armed", False):
            return

        items = getattr(window, "_vocab_items", [])
        if not items:
            return

        try:
            idx = int(getattr(window, "_vocab_index", 0))
        except Exception:
            idx = 0

        window._vocab_index = (idx + 1) % len(items)
        self.show_current()

        # Delegate to the controller-managed playback entry point
        self.play_sequence()

    def prev_item(self):
        """Move to the previous vocab item and play it, respecting playback guards."""
        window = self.window

        if getattr(window, "_is_playing", False):
            return
        if not getattr(window, "_tts_armed", False):
            return

        items = getattr(window, "_vocab_items", [])
        if not items:
            return

        try:
            idx = int(getattr(window, "_vocab_index", 0))
        except Exception:
            idx = 0

        window._vocab_index = (idx - 1) % len(items)
        self.show_current()

        self.play_sequence()

    def attach_buttons(self, btn_play=None, btn_next=None, btn_prev=None):
        """Attach navigation and play buttons so controller can manage their state."""
        self.btn_play = btn_play
        self.btn_next = btn_next
        self.btn_prev = btn_prev

    def update_buttons(self):
        """Enable/disable buttons based on playback, arming, and auto-mode state.

        Rules:
          - While _is_playing: everything disabled.
          - Until _tts_armed is True: Next/Prev disabled.
          - While _auto_mode is True: disable Play/Repeat, Next, Previous and the Category combobox.
        """
        window = self.window
        btn_play = getattr(self, "btn_play", None)
        btn_next = getattr(self, "btn_next", None)
        btn_prev = getattr(self, "btn_prev", None)

        auto_on = bool(getattr(window, "_auto_mode", False))
        if getattr(window, "_is_playing", False):
            play_enabled = False
            nav_enabled = False
        else:
            play_enabled = True
            nav_enabled = bool(getattr(window, "_tts_armed", False))

        if auto_on:
            play_enabled = False
            nav_enabled = False

        if btn_play is not None:
            btn_play.setEnabled(play_enabled)
        if btn_next is not None:
            btn_next.setEnabled(nav_enabled)
        if btn_prev is not None:
            btn_prev.setEnabled(nav_enabled)

        # Also manage the category combobox here so it stays disabled in auto mode
        try:
            combo = window.findChild(QComboBox, "comboCategory")
            if combo is not None:
                combo.setEnabled(not auto_on)
        except Exception:
            pass

    def on_play_clicked(self):
        """Handle Play/Repeat button clicks using the controller state."""
        window = self.window
        btn_play = getattr(self, "btn_play", None)

        # First time: arm and relabel
        if not getattr(window, "_tts_armed", False):
            window._tts_armed = True
            if btn_play is not None:
                try:
                    btn_play.setText("Repeat")
                except Exception:
                    pass
            # button enable/disable will be managed by playback sequence

        # Delegate to the controller-managed playback entry point
        self.play_sequence()

    def play_sequence(self, on_done=None):
        """Entry point for playing the current item sequence.

        This wraps the module-level _play_sequence so tests can call the
        controller directly without going through nested functions.
        """
        try:
            if on_done is not None:
                _play_sequence(on_done=on_done)
            else:
                _play_sequence()
        except TypeError:
            # Fallback for older signature without on_done
            try:
                _play_sequence()
            except Exception:
                pass
        except NameError:
            # No playback helper available yet
            pass

    def play_once(self, *args, **kwargs):
        """Thin wrapper around the module-level _play_once for tests.

        Uses *args/**kwargs to avoid coupling to the exact signature.
        """
        try:
            _play_once(*args, **kwargs)
        except NameError:
            # _play_once not defined in this build
            pass
        except Exception:
            # Do not crash the UI from test-only calls
            pass

    def set_auto_mode(self, on: bool):
        """Turn auto mode on or off and handle the first kick-off when turning on.

        When turning ON:
          - Mark auto mode flag on the window.
          - Ensure TTS is armed and Play label shows 'Repeat'.
          - Start a play sequence whose completion will trigger auto-advance.
        When turning OFF:
          - Just flip the flag; any in-progress playback will finish normally.
        """
        window = self.window
        btn_play = getattr(self, "btn_play", None)

        window._auto_mode = bool(on)
        logger.debug("Auto mode %s", "ON" if on else "OFF")

        # Recompute enabled states consistently
        self.update_buttons()

        if not on:
            # Nothing more to do; _play_sequence() will clear _is_playing when current run finishes.
            return

        # When turning auto mode ON, ensure TTS is armed and label shows Repeat
        try:
            if not getattr(window, "_tts_armed", False):
                window._tts_armed = True
                if btn_play is not None:
                    try:
                        btn_play.setText("Repeat")
                    except Exception:
                        pass
        except Exception:
            pass

        # Kick off a sequence; when it finishes, we auto-advance and schedule the next one.
        def _after_first():
            self.auto_advance_step()

        # Use the controller-managed playback entry point
        self.play_sequence(on_done=_after_first)

    def auto_advance_step(self):
        """In auto mode, advance to the next item and schedule its playback after the auto delay."""
        window = self.window

        # Abort if auto mode has been turned off meanwhile
        if not getattr(window, "_auto_mode", False):
            logger.debug("Auto advance skipped: auto mode OFF")
            return

        items = getattr(window, "_vocab_items", [])
        if not items:
            logger.debug("Auto advance skipped: no vocab items")
            return

        try:
            idx = int(getattr(window, "_vocab_index", 0))
        except Exception:
            idx = 0

        window._vocab_index = (idx + 1) % len(items)
        self.show_current()

        # Read auto delay (seconds) from the slider, if present
        try:
            delay_sec = int(slider_auto.value()) if slider_auto is not None else 0
        except NameError:
            delay_sec = 0
        except Exception:
            delay_sec = 0

        ms = max(0, delay_sec) * 1000

        def _kickoff_next():
            # Re-check auto mode at the moment of kicking off
            if not getattr(window, "_auto_mode", False):
                logger.debug("Auto advance kickoff aborted: auto mode OFF")
                return
            # Use the controller-managed playback entry point for the next cycle
            self.play_sequence(on_done=self.auto_advance_step)

        if ms:
            QTimer.singleShot(ms, _kickoff_next)
        else:
            _kickoff_next()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")
    app = QApplication(sys.argv)

    # Load the Qt Designer form. Use absolute or relative-to-absolute path conversion.
    try:
        window = cast(Any, load_ui("./ui/form.ui"))
        # Load bounds once so they are available to handlers like _on_tortoise_toggled
        b = bounds()

        # ---- Settings wiring ----
        # Find sliders and reset button by objectName from form.ui
        slider_wpm = window.findChild(QSlider, "sliderWpm")
        slider_repeats = window.findChild(QSlider, "sliderRepeats")
        slider_intro = window.findChild(QSlider, "sliderIntroDelay")
        slider_repeat = window.findChild(QSlider, "sliderRepeatDelay")
        slider_extro = window.findChild(QSlider, "sliderExtroDelay")
        slider_auto = window.findChild(QSlider, "sliderAutoDelay")
        btn_reset = window.findChild(QPushButton, "btnReset")

        # ---- Vocabulary loading & navigation (YAML only) ----
        # Widgets for display
        label_hanzi = window.findChild(QLabel, "labelHanzi")
        # --- Auto-size Hanzi font based on text length and label width/height ---
        # HANZI_SIDE_PADDING = 30  # px on each side

        # Ensure single-line, no wrapping, and apply padding
        if label_hanzi is not None:
            label_hanzi.setWordWrap(False)
            # Qt6 / PySide6: use AlignmentFlag (stubs may not expose legacy Qt.Align* names)
            label_hanzi.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            # zero margins (preferred)
            try:
                label_hanzi.setContentsMargins(0, 0, 0, 0)
            except Exception:
                # sanitize stylesheet if it had padding
                ss = label_hanzi.styleSheet() or ""
                if "padding-left" in ss or "padding-right" in ss:
                    ss = ss.replace("padding-left:", "/*padding-left:*/")
                    ss = ss.replace("padding-right:", "/*padding-right:*/")
                label_hanzi.setStyleSheet(ss)
            # Qt6 / PySide6: use QSizePolicy.Policy (stubs may not expose legacy QSizePolicy.* names)
            label_hanzi.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            logger.debug("labelHanzi sizePolicy set to Ignored/Preferred to avoid window width jump")
            # Capture base stylesheet so we can override font-size reliably (stylesheets override QFont)
            window._hanzi_base_stylesheet = label_hanzi.styleSheet() or ""

            # Capture a baseline available width after the first layout pass
            window._hanzi_avail_w0 = None


            def _capture_hanzi_baseline():
                # Log initial sizes when the app first opens (after first layout pass)
                try:
                    w_total = int(label_hanzi.width())
                except Exception:
                    w_total = -1
                try:
                    w_contents = int(label_hanzi.contentsRect().width())
                except Exception:
                    w_contents = w_total
                try:
                    win_w = int(window.width())
                except Exception:
                    win_w = -1
                logger.debug("Initial sizes: window_w=%d labelHanzi_w=%d contentsRect_w=%d", win_w, w_total, w_contents)

                w0 = max(0, w_contents if w_contents is not None else w_total)
                if w0 > 0 and window._hanzi_avail_w0 is None:
                    window._hanzi_avail_w0 = w0
                    logger.debug("Hanzi baseline avail_w0 set to %d", w0)


            QTimer.singleShot(0, _capture_hanzi_baseline)


        def _apply_hanzi_pt_stylesheet(w, pt):
            """Apply font-size via stylesheet, removing any prior font-size so QFontMetrics matches render."""
            try:
                # import re
                base = getattr(window, "_hanzi_base_stylesheet", w.styleSheet() or "")
                # remove all font-size decls
                cleaned = re.sub(r"font-size\s*:\s*\d+\s*pt\s*;?", "", base, flags=re.IGNORECASE)
                # ensure trailing semicolon before append if needed
                if cleaned and not cleaned.strip().endswith(";"):
                    cleaned = cleaned.strip() + ";"
                w.setStyleSheet(f"{cleaned} font-size: {int(pt)}pt;")
            except Exception:
                # fallback to QFont if stylesheet fails
                f = w.font()
                f.setPointSize(int(pt))
                w.setFont(f)


        def _parse_base_point_size_from_stylesheet(w):
            try:
                # import re
                ss = w.styleSheet() or ""
                m = re.search(r"font-size:\s*(\d+)pt", ss)
                if m:
                    return int(m.group(1))
            except Exception:
                pass
            return 96  # default if not found


        def _measure_text_px(font, text):
            fm = QFontMetrics(font)
            try:
                rect = fm.tightBoundingRect(text)
                w_px = rect.width()
                h_px = rect.height()
            except Exception:
                rect = fm.boundingRect(text)
                w_px = rect.width()
                h_px = rect.height()
            return w_px, h_px


        def _compute_avail_width(w):
            try:
                avail = max(0, w.contentsRect().width())
            except Exception:
                avail = max(0, w.width())
            # do not exceed baseline measured at startup (prevents right-edge jump/expand)
            b = getattr(window, "_hanzi_avail_w0", None)
            if isinstance(b, int) and b > 0:
                avail = min(avail, b)
            # safety margin to avoid glyph overhang clipping, scale for devicePixelRatio
            try:
                dpr = max(1.0, float(w.devicePixelRatioF()))
            except Exception:
                dpr = 1.0
            safety = int(12 * dpr)  # larger safety for HiDPI
            return max(0, avail - safety)


        def _norm_jy(jy: str) -> str:
            """Normalize jyutping: lowercase, collapse spaces."""
            return " ".join((jy or "").strip().lower().split())


        def _fit_hanzi_font_to_label(w, hanzi_text, jyut_text, base_pt):
            ht = hanzi_text or ""
            jt = jyut_text or ""
            # If BOTH <= 4 chars, honour stylesheet/base size
            if len(ht) <= 4 and len(jt) <= 4:
                _apply_hanzi_pt_stylesheet(w, base_pt)
                return

            avail_w = _compute_avail_width(w)
            max_h = w.maximumHeight() if w.maximumHeight() > 0 else 10_000
            if avail_w < 10:
                QTimer.singleShot(0, lambda: _fit_hanzi_font_to_label(w, ht, jt, base_pt))
                return

            # Choose the wider of Hanzi/Jyut for conservative fit
            display_txt = ht

            # Binary search for best point size
            f = w.font()
            lo, hi = 6, 200  # allow growth beyond prior stylesheet size
            best = lo
            while lo <= hi:
                mid = (lo + hi) // 2
                f.setPointSize(mid)
                w_px, h_px = _measure_text_px(f, display_txt)
                logger.debug("fit try: sz=%d text_px=%dx%d avail_w=%d max_h=%d", mid, w_px, h_px, avail_w, max_h)
                if w_px <= avail_w and h_px <= max_h:
                    best = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            final_pt = max(6, best - 2)
            _apply_hanzi_pt_stylesheet(w, final_pt)
            # measure using a QFont that matches stylesheet size
            f.setPointSize(final_pt)
            fw, fh = _measure_text_px(f, display_txt)
            logger.debug("fit final: applied_pt=%d (best=%d) text_px=%dx%d avail_w=%d", final_pt, best, fw, fh, avail_w)
            # Post-fit safeguard: if still too large, shrink further
            for _ in range(3):
                if fw <= avail_w and fh <= max_h:
                    break
                final_pt = max(6, final_pt - 2)
                _apply_hanzi_pt_stylesheet(w, final_pt)
                f.setPointSize(final_pt)
                fw, fh = _measure_text_px(f, display_txt)
            # Post-fit safeguard: if metrics still exceed the available rect (due to glyph overhangs, AA, or late layout changes),
            # iteratively step down until it fits. This guarantees no visual clipping.
            safety_px = 2  # extra pixels to keep clear of the edges
            max_iters = 16
            iters = 0
            while iters < max_iters:
                try:
                    curr_avail_w = _compute_avail_width(w)
                except Exception:
                    curr_avail_w = avail_w
                if fw <= max(0, curr_avail_w - safety_px) and fh <= max_h:
                    break
                final_pt = max(6, final_pt - 1)
                _apply_hanzi_pt_stylesheet(w, final_pt)
                f.setPointSize(final_pt)  # keep font in sync for measurement
                fw, fh = _measure_text_px(f, display_txt)
                iters += 1
                logger.debug("post-fit adjust: pt=%d text_px=%dx%d curr_avail_w=%d", final_pt, fw, fh, curr_avail_w)


        def _update_hanzi_font_now():
            if not label_hanzi:
                return
            hanzi_txt = label_hanzi.text()
            try:
                jyut_txt = edit_jyut.text() if edit_jyut is not None else ""
            except Exception:
                jyut_txt = ""
            base_pt = _parse_base_point_size_from_stylesheet(label_hanzi)
            _fit_hanzi_font_to_label(label_hanzi, hanzi_txt, jyut_txt, base_pt)


        # Update font when label is resized
        if label_hanzi is not None:
            # from PySide6.QtCore import QObject

            class _HanziSizer(QObject):
                def eventFilter(self, obj, event):
                    if obj is label_hanzi and event.type() == QEvent.Type.Resize:
                        # allow baseline to shrink but never grow
                        try:
                            cw = max(0, label_hanzi.contentsRect().width())
                        except Exception:
                            cw = max(0, label_hanzi.width())
                        if cw > 0 and isinstance(getattr(window, "_hanzi_avail_w0", None), int):
                            if window._hanzi_avail_w0 is None or cw < window._hanzi_avail_w0:
                                window._hanzi_avail_w0 = cw
                                logger.debug("Hanzi baseline reduced to %d due to shrink", cw)
                        _update_hanzi_font_now()
                    return False


            _sizer = _HanziSizer()
            label_hanzi.installEventFilter(_sizer)
            window._hanzi_sizer = _sizer  # keep ref

        edit_jyut = window.findChild(QLineEdit, "jyutping")  # or window.findChild(QLabel, "editJyutping")
        text_meanings = window.findChild(QTextEdit, "textMeanings")
        controller = MainController(window, label_hanzi, edit_jyut, text_meanings)


        # Find navigation buttons robustly by name or text
        def _find_button(candidates, text_candidates):
            for name in candidates:
                b = window.findChild(QPushButton, name)
                if b is not None:
                    return b
            # fallback by visible text
            for b in window.findChildren(QPushButton):
                try:
                    t = b.text().strip().lower()
                except Exception:
                    continue
                for txt in text_candidates:
                    if t == txt.lower():
                        return b
            return None


        btn_next = _find_button(["btnNext", "nextButton", "pushButtonNext"], ["Next", "→", "›"])
        btn_prev = _find_button(["btnPrevious", "btnPrev", "previousButton", "pushButtonPrev"],
                                ["Previous", "Prev", "←", "‹"])
        btn_play = _find_button(["btnPlay", "btnListen", "playButton", "listenButton", "pushButtonPlay"],
                                ["Play", "Listen", "▶", "►"])

        logger.debug("Buttons resolved -> play:%s next:%s prev:%s", bool(btn_play), bool(btn_next), bool(btn_prev))
        controller.attach_buttons(btn_play=btn_play, btn_next=btn_next, btn_prev=btn_prev)
        controller.update_buttons()  # at startup: Play enabled, Next/Prev disabled

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


        def _load_categories_map() -> dict:
            """Return the current categories_map (fallback to reloading from vocab.yaml if empty)."""
            try:
                if isinstance(categories_map, dict) and categories_map:
                    return categories_map
            except Exception:
                pass
            _v, cats = _load_vocab_from_unified_yaml()
            return cats or {}


        # --- Load categories map and resolve saved category ---
        # ensure these exist before category wiring
        saved_category = load_one("category") or "All"
        # Make categories available to other parts of the app (e.g., Add & Edit dialog)
        try:
            setattr(window, "_categories_map", categories_map)
            logger.debug("Attached _categories_map to window: %d categories", len(categories_map or {}))
        except Exception:
            pass


        # Optional: canto-explain fallback for missing jyutping

        def _ensure_jyut(hanzi, jyut):
            """Return provided jyut if present; otherwise leave empty (no 3rd-party fallback)."""
            return jyut or ""


        # Wire central Category combobox (above Jyutping)
        # Diagnostics: list all comboboxes present to ensure we find comboCategory
        try:
            all_combos = window.findChildren(QComboBox)
            logger.debug("Found %d QComboBox widgets: %s", len(all_combos), [c.objectName() for c in all_combos])
        except Exception as _diag_e:
            logger.debug("Could not enumerate QComboBox children: %s", _diag_e)

        combo_category = window.findChild(QComboBox, "comboCategory")
        if combo_category is not None:
            try:
                combo_category.blockSignals(True)
                combo_category.clear()
                combo_category.addItem("All")
                for k in sorted(categories_map.keys()):
                    combo_category.addItem(k)
                # set saved category if present in list
                idx = combo_category.findText(saved_category)
                if idx >= 0:
                    combo_category.setCurrentIndex(idx)
            finally:
                combo_category.blockSignals(False)


            def _on_category_changed(name):
                save_one("category", name)
                # Reset TTS arming: relabel to Play, mark unarmed, and update buttons
                try:
                    window._tts_armed = False
                    if btn_play is not None:
                        btn_play.setText("Play")
                except Exception:
                    pass
                controller.update_buttons()
                controller.apply_category_filter(name)


            combo_category.currentTextChanged.connect(_on_category_changed)
            logger.debug("comboCategory wired; initial selection='%s' (saved='%s')", combo_category.currentText(),
                         saved_category)
            # Apply filter using saved/current selection
            controller.apply_category_filter(combo_category.currentText())
        else:
            # Fallback: combobox not found — still honor saved category if present
            logger.debug("comboCategory not found; applying saved category '%s'", saved_category)
            controller.apply_category_filter(
                saved_category if saved_category in categories_map or saved_category == "All" else "All")

        # Connect buttons
        if btn_play is not None:
            logger.debug("Connecting Play button")
            btn_play.clicked.connect(controller.on_play_clicked)
        if btn_next is not None:
            btn_next.clicked.connect(controller.next_item)
        if btn_prev is not None:
            btn_prev.clicked.connect(controller.prev_item)
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


        # --- TTS wiring (canto-explain when available) ---

        def _detect_macos_voices():
            """Return a list of available voices from `say -v '?'` (name, locale, desc)."""
            try:
                proc = QProcess(window)
                proc.setProgram("/usr/bin/say")
                proc.setArguments(["-v", "?"])
                proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
                proc.start()
                proc.waitForFinished(3000)
                qba = proc.readAllStandardOutput()
                try:
                    out = qba.data().decode("utf-8", "ignore")
                except Exception:
                    out = bytes(qba).decode("utf-8", "ignore")
                voices = []
                for line in out.splitlines():
                    # Example line: "  Sin-ji              zh_HK    # Cantonese (Hong Kong)"
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        name = parts[0]
                        locale = parts[1] if parts[1].startswith("zh") else ""
                        voices.append((name, locale, line.strip()))
                return voices
            except Exception as e:
                logger.warning("Voice detection failed: %s", e)
                return []


        _available_voices = _detect_macos_voices()


        def _pick_cantonese_voice():
            prefs = ["Sin-ji", "Sinji", "Yuna", "Ting-Ting", "Mei-Jia"]
            # prefer zh_HK then zh_*
            zh_hk = [v for v in _available_voices if v[1] == "zh_HK"]
            if zh_hk:
                return zh_hk[0][0]
            zh_any = [v for v in _available_voices if v[1].startswith("zh")]
            if zh_any:
                return zh_any[0][0]
            for p in prefs:
                for v in _available_voices:
                    if v[0] == p:
                        return p
            return None


        _default_voice = _pick_cantonese_voice()
        logger.debug("Detected voices: %d, default=%s", len(_available_voices), _default_voice)

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
                logger.debug("CacheAudit: char_map source=%s size=%d", _cmap_src, len(getattr(window, "_char_map", {}) or {}))
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




        def _normalize_reverse_index(obj):
            """Normalize reverse-index payloads to the expected shape.

            Expected shape:
              {"jyutping": [("漢字", "src", 123), ...], ...}

            Some loaders may return a wrapper dict of size 1 (e.g., {"reverse": {...}})
            or a dict mapping jyutping -> ["漢字", ...]. We coerce these into the
            canonical form used by _reverse_candidates_for_jy().
            """
            # Unwrap common one-key wrapper dicts
            if isinstance(obj, dict) and len(obj) == 1:
                try:
                    only_val = next(iter(obj.values()))
                    if isinstance(only_val, dict):
                        obj = only_val
                except Exception:
                    pass

            if not isinstance(obj, dict) or not obj:
                return {}

            out = {}
            for k, v in obj.items():
                if not isinstance(k, str):
                    continue
                if not v:
                    continue

                # Already canonical: list of triples
                if isinstance(v, list) and v and isinstance(v[0], (tuple, list)):
                    triples = []
                    ok = True
                    for item in v:
                        try:
                            hz = str(item[0]).strip()
                            src = str(item[1]).strip() if len(item) > 1 else "tier1"
                            score = int(item[2]) if len(item) > 2 else 100
                        except Exception:
                            ok = False
                            break
                        if hz:
                            triples.append((hz, src or "tier1", score))
                    if ok and triples:
                        out[k] = triples
                        continue

                # Coerce: list of strings -> list of triples
                if isinstance(v, list) and v and isinstance(v[0], str):
                    triples = []
                    for hz in v:
                        hz_s = str(hz).strip()
                        if hz_s:
                            triples.append((hz_s, "tier1", 100))
                    if triples:
                        out[k] = triples
                        continue

                # Coerce: single string -> one triple
                if isinstance(v, str):
                    hz_s = v.strip()
                    if hz_s:
                        out[k] = [(hz_s, "tier1", 100)]
                    continue

            return out

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
                    logger.debug("CacheAudit: reverse_index source=%s size=%d", src, len(getattr(window, "_reverse_index", {}) or {}))
                    try:
                        _sz = len(getattr(window, "_reverse_index", {}) or {})
                        if src == "disk" and _sz <= 3:
                            # Common symptom: loader returned a wrapper dict; normalization should prevent this.
                            logger.debug("Reverse index looks unusually small (size=%d); check data file path and loader output shape", _sz)
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


        def _reverse_candidates_for_jy(jy: str) -> list[tuple[str, str, int]]:
            """Tiered reverse candidates for a Jyutping phrase.
            Order:
              1) reverse index (manual/cache)
              2) Tier 2: compose from Unihan + shortlist (if utils provide it)
            Returns a list of (hanzi, source, score_int).
            """
            try:
                jy_n = " ".join((jy or "").strip().lower().split())
            except Exception:
                jy_n = (jy or "").strip().lower()

            # Tier 1: prebuilt reverse index
            try:
                if isinstance(getattr(window, "_reverse_index", None), dict):
                    hits = window._reverse_index.get(jy_n)
                    if hits:
                        logger.debug("revlookup tier1: %d candidates for '%s'", len(hits), jy_n)
                        return list(hits)
            except Exception:
                pass

            # Tier 2: compose from Unihan and rank via utils
            compose_fn = None
            shortlist_fn = None
            try:
                compose_fn = compose_candidates_from_chars
            except NameError:
                compose_fn = None
            try:
                shortlist_fn = shortlist_candidates
            except NameError:
                shortlist_fn = None

            if callable(compose_fn) and callable(shortlist_fn):
                combos = []  # ensure defined for all paths
                try:
                    cmap = getattr(window, "_char_map", {}) or {}
                    if not isinstance(cmap, dict) or not cmap:
                        logger.debug("revlookup tier2: no char_map available for '%s'", jy_n)
                        return []

                    logger.debug("revlookup tier2: composing from Unihan for '%s'", jy_n)
                    combos = compose_fn(jy_n, cmap) or []

                    ranked_pairs = shortlist_fn(jyut=jy_n, combos=combos, top_n=10) or []
                    out = [(hz, "tier2-char-ranked", int(score)) for hz, score in ranked_pairs]
                    logger.debug("revlookup tier2: ranked shortlist size=%d for '%s'", len(out), jy_n)
                    return out

                except TypeError:
                    # Older shortlist signature
                    try:
                        ranked_pairs = shortlist_fn(jy_n, combos, 10) or []
                        out = [(hz, "tier2-char-ranked", int(score)) for hz, score in ranked_pairs]
                        logger.debug(
                            "revlookup tier2: ranked shortlist(size=%d) [fallback signature] for '%s'",
                            len(out), jy_n
                        )
                        return out
                    except Exception:
                        pass

            logger.debug("revlookup tier2: compose function or char_map unavailable for '%s'", jy_n)
            return []


        def _commit_vocab_entry_from_dialog(entry: dict, dialog=None):
            """
            Commit a new vocab entry coming from the CategoryManagerDialog.

            The `entry` dict is expected to have:
                - jyutping: str
                - hanzi: str
                - gloss: str
                - categories: list[str]
            """
            try:
                jy = " ".join((entry.get("jyutping") or "").strip().lower().split())
                hz = (entry.get("hanzi") or "").strip()
                gloss = (entry.get("gloss") or "").strip()
                cats_in = entry.get("categories") or []
                cats = [str(c).strip() for c in cats_in if str(c).strip()]
            except Exception as e:
                logger.warning("Commit aborted: malformed entry payload %r (%s)", entry, e)
                return

            if not jy or not hz or not gloss or not cats:
                logger.debug(
                    "Commit aborted: missing fields jy=%r hz=%r gloss=%r cats=%r",
                    jy, hz, gloss, cats,
                )
                return

            global vocab, categories_map

            # ---- Update in-memory vocab ----
            try:
                if hz in vocab:
                    meanings, jy_existing = vocab.get(hz, ([], ""))
                    if not isinstance(meanings, list):
                        meanings = []
                    if gloss not in meanings:
                        meanings.append(gloss)
                    if not jy_existing:
                        jy_existing = jy
                    vocab[hz] = [meanings, jy_existing]
                else:
                    vocab[hz] = [[gloss], jy]
            except Exception as e:
                logger.warning("Failed to update in-memory vocab for '%s' (%s)", hz, e)

            # ---- Mirror update back into the dialog (same-session duplicate detection) ----
            # The dialog keeps its own in-memory vocab snapshot for duplicate checks and previews.
            # Ensure it is updated immediately after Save, so the user can re-enter the same
            # Jyutping without restarting the app/dialog.
            try:
                dlg_vocab = getattr(dialog, "_vocab", None)
            except (TypeError, AttributeError, RuntimeError):
                dlg_vocab = None

            if isinstance(dlg_vocab, dict):
                try:
                    # Dialog expects the canonical internal shape used by its own logic.
                    # Prefer list-of-meanings + jyutping (matches the rest of the app).
                    dlg_vocab[hz] = [[gloss], jy]
                except (TypeError, AttributeError, RuntimeError):
                    pass

            # Optional: if the dialog exposes a test/legacy mirror dict, keep it in sync too.
            try:
                dlg_vocab_items = getattr(dialog, "vocab_items", None)
            except (TypeError, AttributeError, RuntimeError):
                dlg_vocab_items = None

            if isinstance(dlg_vocab_items, dict):
                try:
                    dlg_vocab_items[hz] = [[gloss], jy]
                except (TypeError, AttributeError, RuntimeError):
                    pass

            # ---- Update in-memory categories_map ----
            try:
                for cat in cats:
                    lst = categories_map.setdefault(cat, [])
                    if hz not in lst:
                        lst.append(hz)
            except Exception as e:
                logger.warning("Failed to update in-memory categories_map for '%s' (%s)", hz, e)

            # Reflect changes on the window's categories map
            try:
                wmap = getattr(window, "_categories_map", None)
                if isinstance(wmap, dict):
                    for cat in cats:
                        lst = wmap.setdefault(cat, [])
                        if hz not in lst:
                            lst.append(hz)
                    setattr(window, "_categories_map", wmap)
            except Exception as e:
                logger.debug("Could not mirror categories onto window._categories_map: %s", e)

            # ---- Persist changes back to vocab.yaml ----
            try:
                vocab_path = data_path("vocab.yaml")
                if not os.path.exists(vocab_path):
                    logger.warning("Cannot persist new entry: vocab.yaml not found at %s", vocab_path)
                    return

                with open(vocab_path, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                if not isinstance(data, dict):
                    data = {}

                categories_block = data.get("categories")
                if not isinstance(categories_block, dict):
                    categories_block = {}

                entries_block = data.get("entries")
                if not isinstance(entries_block, dict):
                    entries_block = {}

                # Ensure categories exist in the categories block
                for cat in cats:
                    categories_block.setdefault(cat, {})

                # Upsert the entry under its Jyutping key
                entry_obj = entries_block.get(jy)
                if not isinstance(entry_obj, dict):
                    entry_obj = {"jyutping": jy, "senses": []}
                else:
                    entry_obj.setdefault("jyutping", jy)
                    if not isinstance(entry_obj.get("senses"), list):
                        entry_obj["senses"] = []

                senses = entry_obj["senses"]

                # Try to merge with an existing sense that matches hanzi+gloss
                merged = False
                for s in senses:
                    if not isinstance(s, dict):
                        continue
                    if s.get("hanzi") == hz and s.get("gloss") == gloss:
                        existing_cats = s.get("categories") or []
                        merged_cats = sorted({*(str(c) for c in existing_cats), *cats})
                        s["categories"] = merged_cats
                        merged = True
                        break

                if not merged:
                    senses.append({"hanzi": hz, "gloss": gloss, "categories": cats})

                entry_obj["senses"] = senses
                entries_block[jy] = entry_obj

                data["categories"] = categories_block
                data["entries"] = entries_block

                with open(vocab_path, "w", encoding="utf-8") as fh:
                    yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=True)

                logger.debug(
                    "Committed new vocab entry to %s: jy=%r hanzi=%r cats=%r",
                    vocab_path, jy, hz, cats,
                )
            except Exception as e:
                logger.warning(
                    "Failed to persist vocab entry for jy=%r hanzi=%r: %s",
                    jy, hz, e,
                )


        # Expose helper on window for dialogs
        try:
            setattr(window, "_reverse_candidates_for_jy", _reverse_candidates_for_jy)
        except Exception:
            pass

        # Delays disclosure: flip label and show/hide panel
        btn_delays = window.findChild(QToolButton, "btnDelaysDisclosure")
        group_delays = window.findChild(QGroupBox, "groupDelays")
        if btn_delays is not None and group_delays is not None:
            def _sync_delays(checked: bool):
                group_delays.setVisible(checked)
                # swap the glyph and include a space before the word
                btn_delays.setText("▼ Delays" if checked else "▶ Delays (Advanced)")


            btn_delays.toggled.connect(_sync_delays)
            _sync_delays(btn_delays.isChecked())

        # About disclosure: flip label and show/hide panel
        btn_about = window.findChild(QToolButton, "btnAboutDisclosure")
        group_about = window.findChild(QGroupBox, "groupAbout")
        if btn_about is not None and group_about is not None:
            def _sync_about(checked: bool):
                group_about.setVisible(checked)
                btn_about.setText("▼ About" if checked else "▶ About")


            btn_about.toggled.connect(_sync_about)
            _sync_about(btn_about.isChecked())


        # -----------------------------
        # In-app Category Manager Dialog
        # -----------------------------

        def _open_category_manager(focus_add: bool = False):
            """Open the Add & Edit dialog, ensuring categories are available on the window.
            Falls back to reloading from disk if the attribute is missing.
            """
            # Use the already-loaded vocab from this scope
            vocab_dict = vocab if isinstance(vocab, dict) else {}

            # Ensure we have a categories map on the window
            try:
                cats = getattr(window, "_categories_map", None)
                if not isinstance(cats, dict) or not cats:
                    cats = _load_categories_map()
                    try:
                        setattr(window, "_categories_map", cats)
                    except Exception:
                        pass
            except Exception:
                cats = _load_categories_map()

            logger.debug("_open_category_manager: categories ready -> %d keys", len(cats or {}))

            _t_dlg = _perf_start("CategoryManagerDialog(create)")
            dlg = CategoryManagerDialog(window, vocab_dict, cats)
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

            # After the dialog closes, refresh the current category view so any new items appear.
            try:
                combo = window.findChild(QComboBox, "comboCategory")
                current_cat = combo.currentText() if combo is not None else "All"
            except Exception:
                current_cat = "All"
            controller.apply_category_filter(current_cat)


        # (MultiCategoryCombo class definition removed)

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


        # Tones & Radicals toggle: show/hide both groups together
        btn_tr = window.findChild(QToolButton, "btnTonesAndRadicalsToggle")
        if btn_tr is None:
            btn_tr = window.findChild(QPushButton, "btnTonesAndRadicalsToggle")
        group_tones = window.findChild(QGroupBox, "groupSoundToneMastery")
        group_rad = window.findChild(QGroupBox, "groupRadicals")
        if btn_tr is not None:
            try:
                btn_tr.setCheckable(True)
            except Exception:
                pass


            def _sync_tr(checked: bool):
                vis = bool(checked)
                if group_tones is not None:
                    group_tones.setVisible(vis)
                if group_rad is not None:
                    group_rad.setVisible(vis)


            btn_tr.toggled.connect(_sync_tr)
            _sync_tr(btn_tr.isChecked())

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

        # Wire Add button (in “Add and Edit”) — always available
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


        def _tts_call(text, rate=None):
            """Third-party TTS providers disabled; using system TTS only."""
            logger.debug("Third-party TTS disabled; skipping provider calls")
            return False


        # Fallback TTS helper using macOS 'say' and system sound
        def _fallback_say(text, rate=None):
            """macOS 'say' fallback: synthesize to temp .aiff and play with afplay. Keeps QProcess refs."""
            try:
                say_path = "/usr/bin/say"
                afplay = "/usr/bin/afplay"
                # choose voice: from combo if present, else detected default
                voice = None
                combo = window.findChild(QComboBox, "comboVoice")
                if combo is not None and combo.currentText().strip():
                    voice = combo.currentText().strip()
                if not voice:
                    voice = _default_voice
                # synthesize to a temp file
                tmp = tempfile.NamedTemporaryFile(prefix="learncanto_", suffix=".aiff", delete=False)
                tmp_path = tmp.name
                tmp.close()
                args = []
                if voice:
                    args += ["-v", voice]
                if isinstance(rate, int) and rate > 0:
                    args += ["-r", str(rate)]
                args += ["-o", tmp_path, "--", text]
                logger.debug("Synth via say -> %s %s", say_path, " ".join(shlex.quote(a) for a in args))
                proc_say = QProcess(window)
                proc_say.setProgram(say_path)
                proc_say.setArguments(args)
                proc_say.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
                proc_say.start()
                if not proc_say.waitForFinished(10000):
                    logger.warning("say did not finish in time")
                else:
                    logger.debug("say finished code=%s status=%s", proc_say.exitCode(), proc_say.exitStatus())
                # play it
                proc_play = QProcess(window)
                proc_play.setProgram(afplay)
                proc_play.setArguments([tmp_path])
                proc_play.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
                proc_play.start()
                logger.debug("Playing synthesized file: %s", tmp_path)
            except Exception as e:
                logger.warning("Synth+play fallback failed: %s", e)


        def _play_once(on_finished=None):
            """Synthesize current Hanzi to a temp AIFF and play via afplay; call on_finished() when done."""
            idx = window._vocab_index
            if idx < 0 or not window._vocab_items:
                if callable(on_finished):
                    QTimer.singleShot(0, on_finished)
                return
            hanzi, val = window._vocab_items[idx]
            text = hanzi
            rate = int(slider_wpm.value()) if slider_wpm is not None else None
            logger.debug("Play once (async): idx=%s hanzi='%s' rate=%s", idx, hanzi, rate)

            try:
                say_path = "/usr/bin/say"
                afplay = "/usr/bin/afplay"
                # choose voice: from combo if present, else detected default
                voice = None
                combo = window.findChild(QComboBox, "comboVoice")
                if combo is not None and combo.currentText().strip():
                    voice = combo.currentText().strip()
                if not voice:
                    voice = _default_voice
                # synthesize to a temp file
                tmp = tempfile.NamedTemporaryFile(prefix="learncanto_", suffix=".aiff", delete=False)
                tmp_path = tmp.name
                tmp.close()
                args = []
                if voice:
                    args += ["-v", voice]
                if isinstance(rate, int) and rate > 0:
                    args += ["-r", str(rate)]
                args += ["-o", tmp_path, "--", text]
                logger.debug("Synth via say -> %s %s", say_path, " ".join(shlex.quote(a) for a in args))

                proc_say = QProcess(window)
                proc_say.setProgram(say_path)
                proc_say.setArguments(args)
                proc_say.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

                def _after_synth(code, status):
                    logger.debug("say finished code=%s status=%s", code, status)
                    # Now play it
                    proc_play = QProcess(window)
                    proc_play.setProgram(afplay)
                    proc_play.setArguments([tmp_path])
                    proc_play.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

                    def _after_play(pcode, pstatus):
                        logger.debug("afplay finished code=%s status=%s (file=%s)", pcode, pstatus, tmp_path)
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
                        if callable(on_finished):
                            on_finished()

                    proc_play.finished.connect(_after_play)
                    proc_play.start()

                proc_say.finished.connect(_after_synth)
                proc_say.start()
            except Exception as e:
                logger.warning("Synth+play fallback failed: %s", e)
                if callable(on_finished):
                    QTimer.singleShot(0, on_finished)


        def _play_sequence(on_done=None):
            # Respect repeats and delays
            repeats = int(slider_repeats.value()) if slider_repeats is not None else 1
            intro = int(slider_intro.value()) if slider_intro is not None else 0
            gap = int(slider_repeat.value()) if slider_repeat is not None else 0
            extro = int(slider_extro.value()) if slider_extro is not None else 0

            logger.debug("Play sequence: repeats=%s intro=%s gap=%s extro=%s", repeats, intro, gap, extro)

            if window._is_playing:
                logger.debug("Play requested while already playing; ignoring")
                return

            window._is_playing = True
            controller.update_buttons()  # disable all buttons

            total = max(1, repeats)
            ms_intro = max(0, intro) * 1000
            ms_gap = max(0, gap) * 1000
            ms_extro = max(0, extro) * 1000

            state = {"i": 0}

            def _after_one():
                # Called after one audio playback has finished
                if state["i"] + 1 < total:
                    state["i"] += 1
                    if ms_gap:
                        QTimer.singleShot(ms_gap, lambda: _play_once(_after_one))
                    else:
                        _play_once(_after_one)
                else:
                    # Finished all repeats -> extro delay then done
                    def _done():
                        window._is_playing = False
                        # Now that a sequence has run at least once, Next/Prev may be enabled
                        controller.update_buttons()
                        if callable(on_done):
                            on_done()

                    if ms_extro:
                        QTimer.singleShot(ms_extro, _done)
                    else:
                        _done()

            # Kick off after intro
            if ms_intro:
                QTimer.singleShot(ms_intro, lambda: _play_once(_after_one))
            else:
                _play_once(_after_one)


        # Show the first entry on startup (after category filter applied)
        controller.show_current()


        # Helper to update label texts with ranges and current values
        def _set_delay_label(label_obj, base_text, current_val):
            if label_obj is not None:
                label_obj.setText("{} (0–10): {}".format(base_text, int(current_val)))


        def _update_all_labels():
            # WPM in group title: show range and current value
            group_wpm = window.findChild(QGroupBox, "groupWpm")
            if group_wpm is not None and slider_wpm is not None:
                group_wpm.setTitle("WPM (60–220): {}".format(int(slider_wpm.value())))
            # Delay labels
            lbl_intro = window.findChild(QLabel, "labelIntroDelay")
            lbl_repeat = window.findChild(QLabel, "labelRepeatDelay")
            lbl_extro = window.findChild(QLabel, "labelExtroDelay")
            lbl_auto = window.findChild(QLabel, "labelAutoDelay")
            if slider_intro is not None:
                _set_delay_label(lbl_intro, "Intro delay", slider_intro.value())
            if slider_repeat is not None:
                _set_delay_label(lbl_repeat, "Repeat delay", slider_repeat.value())
            if slider_extro is not None:
                _set_delay_label(lbl_extro, "Extro delay", slider_extro.value())
            if slider_auto is not None:
                _set_delay_label(lbl_auto, "Auto delay", slider_auto.value())
            # Repeats in group title: show range and current value
            group_repeats = window.findChild(QGroupBox, "groupRepeats")
            if group_repeats is not None and slider_repeats is not None:
                group_repeats.setTitle("Repeats (1–10): {}".format(int(slider_repeats.value())))


        if slider_wpm is not None:
            slider_wpm.setRange(b["wpm"][0], b["wpm"][1])
            slider_wpm.setSingleStep(b["wpm"][2])
        pairs = [
            ("intro_delay", slider_intro),
            ("repeat_delay", slider_repeat),
            ("extro_delay", slider_extro),
            ("auto_delay", slider_auto),
            ("repeats", slider_repeats),
        ]
        for name, slider in pairs:
            if slider is not None:
                slider.setRange(b[name][0], b[name][1])
                slider.setSingleStep(b[name][2])

        # Load persisted values (or defaults on first run)
        vals = load_all()
        if slider_wpm is not None:
            slider_wpm.setValue(int(vals["wpm"]))
        if slider_intro is not None:
            slider_intro.setValue(int(vals["intro_delay"]))
        if slider_repeat is not None:
            slider_repeat.setValue(int(vals["repeat_delay"]))
        if slider_extro is not None:
            slider_extro.setValue(int(vals["extro_delay"]))
        if slider_auto is not None:
            slider_auto.setValue(int(vals["auto_delay"]))
        if slider_repeats is not None:
            slider_repeats.setValue(int(vals["repeats"]))

        _update_all_labels()

        # Persist on change
        if slider_wpm is not None:
            slider_wpm.valueChanged.connect(lambda v: (save_one("wpm", int(v)), _update_all_labels()))
        if slider_intro is not None:
            slider_intro.valueChanged.connect(lambda v: (save_one("intro_delay", int(v)), _update_all_labels()))
        if slider_repeat is not None:
            slider_repeat.valueChanged.connect(lambda v: (save_one("repeat_delay", int(v)), _update_all_labels()))
        if slider_extro is not None:
            slider_extro.valueChanged.connect(lambda v: (save_one("extro_delay", int(v)), _update_all_labels()))
        if slider_auto is not None:
            slider_auto.valueChanged.connect(lambda v: (save_one("auto_delay", int(v)), _update_all_labels()))
        if slider_repeats is not None:
            slider_repeats.valueChanged.connect(
                lambda v: (save_one("repeats", int(v)), _update_all_labels())
            )


        # Reset category selection to 'All'

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
            _update_all_labels()
            # Reset category selection to 'All' (persist and apply)
            combo_category = window.findChild(QComboBox, "comboCategory")
            if combo_category is not None:
                idx = combo_category.findText("All")
                if idx >= 0:
                    combo_category.setCurrentIndex(idx)
                save_one("category", "All")
                controller.apply_category_filter("All")


        if btn_reset is not None:
            btn_reset.clicked.connect(_do_reset)
        # ---- end wiring ----

        # The initial size (720x1280) is set in form.ui geometry. Just show it.
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print("Error: {}".format(e))
