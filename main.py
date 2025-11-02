import logging
import os
import csv
import json
import shlex
import sys
import tempfile
from functools import partial

import yaml

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout, QLineEdit,
    QTextEdit, QComboBox, QToolButton, QSlider, QDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QSizePolicy,
    QListView, QLayout,
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, Qt, QTimer, QProcess, QEvent, Signal
from PySide6.QtGui import QFontMetrics, QStandardItemModel, QStandardItem


from settings import load_all, save_one, reset_all, bounds


# ---- settings shim: provide load_one via load_all if not exported ----
def load_one(key, default=None):
    try:
        cfg = load_all()
        if isinstance(cfg, dict):
            return cfg.get(key, default)
    except Exception:
        pass
    return default

# === Reverse lookup helpers (Tier 1 & 2) ===
try:
    # Tier 1: reverse index from andys_list.yaml + reverse_manual.yaml + frequencies
    # Tier 2: Unihan char map composition
    from utils import (
        load_andys_list_yaml,
        load_unihan_char_map,
        compose_candidates_from_chars,
        build_reverse_index,
        get_unihan_char_map,
        shortlist_candidates,
        get_cccanto_reverse_map, _norm_jy_key
    )
except Exception:  # keep app running even if utils missing
    load_andys_list_yaml = None
    load_unihan_char_map = None
    compose_candidates_from_chars = None
    build_reverse_index = None
    get_unihan_char_map = None
    shortlist_candidates = None




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
        # if no layout, list children widgets
        for ch in widget.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            _dump_layout_tree(ch, indent + 1)


def _load_add_item_ui(parent=None) -> QDialog | None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    ui_path = os.path.join(base_dir, "ui", "add_item.ui")
    file = QFile(ui_path)
    if not file.exists():
        logger.error("add_item.ui not found at %s", ui_path)
        return None
    if not file.open(QFile.ReadOnly):
        logger.error("Cannot open add_item.ui at %s", ui_path)
        return None
    try:
        dlg = QUiLoader().load(file, parent)
        if dlg is None:
            logger.error("QUiLoader returned None for add_item.ui")
            return None
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
            logger.debug("=== add_item.ui TREE DUMP (after show) ===")
            _dump_layout_tree(dlg, 0)
            ge = dlg.geometry()
            logger.debug("DIALOG size: %dx%d minimum:%dx%d", ge.width(), ge.height(),
                         dlg.minimumWidth(), dlg.minimumHeight())

        QTimer.singleShot(50, _after_show)
        return dlg
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
    if not ui_file.open(QIODevice.ReadOnly):
        raise FileNotFoundError("Cannot open UI file: {}".format(abs_path))
    try:
        loader = QUiLoader()
        window = loader.load(ui_file)
    finally:
        ui_file.close()
    if window is None:
        raise RuntimeError("Failed to load UI from: {}".format(abs_path))
    return window


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Load the Qt Designer form. Use absolute or relative-to-absolute path conversion.
    try:
        window = load_ui("./ui/form.ui")
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
            # Center text horizontally and vertically to avoid apparent edge clipping
            label_hanzi.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
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
            # Let the label expand within its layout, but we'll cap *measured* width
            label_hanzi.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
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
                import re
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
                import re
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
            from PySide6.QtCore import QObject


            class _HanziSizer(QObject):
                def eventFilter(self, obj, event):
                    if obj is label_hanzi and event.type() == QEvent.Resize:
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

        # --- Playback/TTS arming & button state (defined early so it exists before first call) ---
        window._is_playing = False
        window._tts_armed = False


        def _update_buttons():
            """
            Enable/disable buttons based on:
              - _is_playing: everything disabled while speaking
              - _tts_armed : Next/Prev disabled until Play is clicked once
              - _auto_mode : while ON, disable Play/Repeat, Next, Previous and the Category combobox
            """
            auto_on = bool(getattr(window, "_auto_mode", False))
            if window._is_playing:
                play_enabled = False
                nav_enabled = False
            else:
                play_enabled = True
                nav_enabled = window._tts_armed

            # Auto mode overrides and disables all controls
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

        _update_buttons()  # at startup: Play enabled, Next/Prev disabled

        # Load vocabulary from YAML, preserving order
        try:
            vocab = load_andys_list_yaml()
        except Exception as _e:
            vocab = {}
        logger.debug("Loaded vocab items: %d", len(vocab))

        def _load_categories_map() -> dict:
            """Load categories from data/categories.yaml and return {category: [hanzi,...]}.
            Accepts flat or wrapped files. Logs a short preview for debugging.
            """
            base_dir = os.path.dirname(os.path.abspath(__file__))
            cat_path = os.path.join(base_dir, "categories.yaml")
            m: dict[str, list[str]] = {}

            try:
                with open(cat_path, "r", encoding="utf-8") as fh:
                    raw_text = fh.read()
                # Log a short preview of the file contents for debugging
                try:
                    lines = [ln for ln in raw_text.splitlines() if ln.strip()][:8]
                    logger.debug("categories.yaml preview (first non-empty lines): %s", lines)
                except Exception:
                    pass

                raw = yaml.safe_load(raw_text) or {}

                # Log top-level type and keys before unwrap
                try:
                    if isinstance(raw, dict):
                        logger.debug("categories.yaml top-level keys BEFORE unwrap: %s", list(raw.keys()))
                    else:
                        logger.debug("categories.yaml is a %s, not a dict", type(raw).__name__)
                except Exception:
                    pass

                # Unwrap if the file is nested one level (e.g. {"categories": {...}} or any {"something": {...}})
                if isinstance(raw, dict):
                    # If exactly one key and the value is a dict, unwrap it
                    if len(raw) == 1:
                        only_key = next(iter(raw))
                        if isinstance(raw[only_key], dict):
                            raw = raw[only_key]

                    # Accept wrapped under a known "categories" key too
                    elif "categories" in raw and isinstance(raw["categories"], dict):
                        raw = raw["categories"]

                # Log top-level keys after unwrap
                try:
                    if isinstance(raw, dict):
                        logger.debug("categories.yaml keys AFTER unwrap: %s", list(raw.keys()))
                except Exception:
                    pass

                if isinstance(raw, dict):
                    for k, v in raw.items():
                        key = str(k).strip() if k is not None else ""
                        if not key:
                            continue
                        lst: list[str] = []
                        if isinstance(v, (list, tuple, set)):
                            for item in v:
                                s = str(item).strip() if item is not None else ""
                                if s:
                                    lst.append(s)
                        m[key] = lst
            except FileNotFoundError:
                logger.debug("categories.yaml not found; starting with empty map")
            except Exception as e:
                logger.warning("Failed to load categories.yaml: %s", e)

            # Ensure an 'unassigned' bucket exists
            if "unassigned" not in {k.lower() for k in m.keys()}:
                m.setdefault("unassigned", [])

            logger.debug("categories.yaml path resolved: %s", cat_path)
            logger.debug("categories.yaml keys (n=%d): %s", len(m), sorted(m.keys()))
            return m

        # --- Load categories map and resolve saved category ---
        # ensure these exist before category wiring
        saved_category = load_one("category") or "All"
        categories_map = _load_categories_map()
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


        def _on_play_clicked():
            # First time: arm and relabel
            if not window._tts_armed:
                window._tts_armed = True
                if btn_play is not None:
                    btn_play.setText("Repeat")
                # buttons will be managed by _play_sequence()
            _play_sequence()


        def _show_current():
            idx = window._vocab_index
            if idx < 0 or not window._vocab_items:
                return
            hanzi, val = window._vocab_items[idx]
            meanings = val[0] if isinstance(val, list) and len(val) > 0 else []
            jyut = val[1] if isinstance(val, list) and len(val) > 1 else ""
            jyut = _ensure_jyut(hanzi, jyut)

            logger.debug("Show index=%s hanzi='%s' jyut='%s' meanings=%s", idx, hanzi, jyut, meanings)

            if label_hanzi is not None:
                label_hanzi.setText(hanzi)
                _update_hanzi_font_now()
                QTimer.singleShot(0, _update_hanzi_font_now)
            if edit_jyut is not None:
                # QLineEdit or QLabel fallback
                try:
                    edit_jyut.setText(jyut)
                except AttributeError:
                    edit_jyut.setText(jyut)
            if text_meanings is not None and isinstance(text_meanings, QTextEdit):
                text_meanings.setPlainText(", ".join(meanings))


        def _apply_category_filter(cat_name):
            if getattr(window, "_is_playing", False):
                logger.debug("Category change requested during playback -> ignored")
                return
            """Filter the vocabulary list by the given category name; 'All' shows everything."""
            full_items = list(vocab.items())
            if cat_name and cat_name != "All" and cat_name in categories_map:
                hanzi_set = set(categories_map.get(cat_name, []))
                filtered = [item for item in full_items if item[0] in hanzi_set]
            else:
                filtered = full_items
            window._vocab_items = filtered
            window._vocab_index = 0 if filtered else -1
            logger.debug("Category set to %s -> %d items", cat_name, len(filtered))
            _show_current()


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
                _update_buttons()
                _apply_category_filter(name)


            combo_category.currentTextChanged.connect(_on_category_changed)
            logger.debug("comboCategory wired; initial selection='%s' (saved='%s')", combo_category.currentText(),
                         saved_category)
            # Apply filter using saved/current selection
            _apply_category_filter(combo_category.currentText())
        else:
            # Fallback: combobox not found — still honor saved category if present
            logger.debug("comboCategory not found; applying saved category '%s'", saved_category)
            _apply_category_filter(
                saved_category if saved_category in categories_map or saved_category == "All" else "All")


        def _next_item():
            # Ignore if playing; (buttons are disabled while playing anyway)
            if window._is_playing:
                return
            # If not armed yet, ignore (Next is disabled; this is just a guard)
            if not window._tts_armed:
                return
            if not window._vocab_items:
                return
            window._vocab_index = (window._vocab_index + 1) % len(window._vocab_items)
            _show_current()
            _play_sequence()  # will honour intro, repeats, extro


        def _prev_item():
            if window._is_playing:
                return
            if not window._tts_armed:
                return
            if not window._vocab_items:
                return
            window._vocab_index = (window._vocab_index - 1) % len(window._vocab_items)
            _show_current()
            _play_sequence()


        # Connect buttons
        if btn_play is not None:
            logger.debug("Connecting Play button")
            btn_play.clicked.connect(_on_play_clicked)
        if btn_next is not None:
            btn_next.clicked.connect(_next_item)
        if btn_prev is not None:
            btn_prev.clicked.connect(_prev_item)
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


        def _set_auto_mode(on: bool):
            window._auto_mode = bool(on)
            logger.debug("Auto mode %s", "ON" if on else "OFF")
            # Recompute enabled states consistently
            _update_buttons()
            if on and not window._auto_pending:
                window._auto_pending = True
                QTimer.singleShot(0, _auto_advance_step)
            if not on:
                window._auto_pending = False


        def _auto_advance_step():
            window._auto_pending = False
            if not window._auto_mode:
                return

            def _after_play():
                if not window._auto_mode:
                    return
                # wait autoDelay then advance to next and start again
                ms_auto = int(slider_auto.value()) * 1000 if slider_auto is not None else 0

                def _advance_and_next():
                    if not window._auto_mode or not window._vocab_items:
                        return
                    window._vocab_index = (window._vocab_index + 1) % len(window._vocab_items)
                    _show_current()
                    QTimer.singleShot(0, _auto_advance_step)

                if ms_auto > 0:
                    QTimer.singleShot(ms_auto, _advance_and_next)
                else:
                    _advance_and_next()

            # Play current item (honours intro/repeat/extro)
            _play_sequence(on_done=_after_play)


        # Connect toggles if present
        if btn_tortoise is not None:
            try:
                btn_tortoise.setCheckable(True)  # already set in .ui, but harmless
            except Exception:
                pass
            btn_tortoise.toggled.connect(_on_tortoise_toggled)

        if btn_auto is not None:
            try:
                btn_auto.setCheckable(True)  # already set in .ui, but harmless
            except Exception:
                pass
            btn_auto.toggled.connect(_set_auto_mode)


        # --- TTS wiring (canto-explain when available) ---

        def _detect_macos_voices():
            """Return a list of available voices from `say -v '?'` (name, locale, desc)."""
            try:
                proc = QProcess(window)
                proc.setProgram("/usr/bin/say")
                proc.setArguments(["-v", "?"])
                proc.setProcessChannelMode(QProcess.MergedChannels)
                proc.start()
                proc.waitForFinished(3000)
                out = bytes(proc.readAllStandardOutput()).decode("utf-8", "ignore")
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

        # Ensure a shared Unihan char map is available as a dict (not a callable)
        try:
            _get_map_fn = get_unihan_char_map  # may be None if utils import failed
        except NameError:
            _get_map_fn = None
        try:
            cmap = {}
            # Prefer a previously cached dict if present
            prev = getattr(window, "_char_map", None)
            if isinstance(prev, dict) and prev:
                cmap = prev
            else:
                if callable(_get_map_fn):
                    try:
                        cmap = _get_map_fn()
                    except Exception:
                        cmap = {}
                # If still empty, try a direct JSON load as a fallback
                if not isinstance(cmap, dict) or not cmap:
                    # import os, json

                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    json_path = os.path.join(base_dir, "data", "Unihan", "unihan_cantonese_chars.json")
                    if os.path.exists(json_path):
                        try:
                            with open(json_path, "r", encoding="utf-8") as fh:
                                raw = json.load(fh)
                            norm = {}
                            if isinstance(raw, dict):
                                for ch, vals in raw.items():
                                    if ch and isinstance(ch, str) and len(ch) == 1:
                                        if isinstance(vals, str):
                                            norm[ch] = [vals]
                                        elif isinstance(vals, (list, tuple, set)):
                                            norm[ch] = [str(v) for v in vals if v is not None]
                                        else:
                                            norm[ch] = [str(vals)]
                            cmap = norm
                        except Exception:
                            cmap = {}
            setattr(window, "_char_map", cmap if isinstance(cmap, dict) else {})
            logger.debug("Unihan char_map ready: %d entries (shared)", len(getattr(window, "_char_map", {}) or {}))

        except Exception as _e:
            setattr(window, "_char_map", {})
            logger.debug("Unihan shared map not available: %r", _e)


        # -----------------------------
        # Reverse index (Tier 1) loader + Tier 2 fallback
        # -----------------------------
        def _load_reverse_index_files() -> dict:
            """Load auto-generated reverse indices.
            Accepts two optional files:
              - data/reverse_manual.yaml (authoritative, multi-candidate per jyut)
              - data/reverse_cache.yaml  (memoized fallback from previous runs)
            Returns {jyut -> [(hanzi, source, score_int), ...]}
            """
            base_dir = os.path.dirname(os.path.abspath(__file__))
            out: dict[str, list[tuple[str, str, int]]] = {}

            def _merge_from_yaml(path: str, tag: str):
                if not os.path.exists(path):
                    return
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        raw = yaml.safe_load(fh) or {}
                except Exception as e:
                    logger.debug("reverse index load failed for %s: %s", path, e)
                    return
                if not isinstance(raw, dict):
                    return
                added, keys = 0, 0
                for jy, items in raw.items():
                    keys += 1
                    try:
                        jy_n = " ".join(str(jy).strip().lower().split())
                        if not jy_n:
                            continue
                        lst = out.setdefault(jy_n, [])
                        if isinstance(items, list):
                            for it in items:
                                if isinstance(it, dict):
                                    hz = str(it.get("hanzi", "")).strip()
                                    if not hz:
                                        continue
                                    src = str(it.get("source", tag)).strip() or tag
                                    sc = it.get("score", 0)
                                    try:
                                        sc_i = int(round(float(sc)))
                                    except Exception:
                                        sc_i = 0
                                    tup = (hz, src, sc_i)
                                    if tup not in lst:
                                        lst.append(tup)
                                        added += 1
                        # Also accept simple list[str] form
                        elif isinstance(items, (tuple, set)):
                            for hz in items:
                                s = str(hz).strip()
                                if s and (s, tag, 0) not in lst:
                                    lst.append((s, tag, 0))
                                    added += 1
                    except Exception:
                        continue
                logger.debug("reverse index loaded from %s: %d keys, %d candidates", path, keys, added)

            # Prefer project-relative data files
            _merge_from_yaml(os.path.join(base_dir, "data", "reverse_manual.yaml"), tag="reverse_manual")
            _merge_from_yaml(os.path.join(base_dir, "data", "reverse_cache.yaml"), tag="reverse_cache")
            # Also accept root-level files if present
            _merge_from_yaml(os.path.join(base_dir, "reverse_manual.yaml"), tag="reverse_manual")
            _merge_from_yaml(os.path.join(base_dir, "reverse_cache.yaml"), tag="reverse_cache")

            logger.debug("reverse index total keys: %d", len(out))
            return out

        # Attach a reverse index onto the main window
        try:
            window._reverse_index = _load_reverse_index_files()
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
            try:
                _ccc_rev = get_cccanto_reverse_map()
                window._ccc_rev = _ccc_rev
                logger.debug("reverse index (CC-Canto) size: %d jy-keys", len(_ccc_rev))
            except:
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
                try:
                    cmap = getattr(window, "_char_map", {}) or {}
                    if not isinstance(cmap, dict) or not cmap:
                        logger.debug("revlookup tier2: no char_map available for '%s'", jy_n)
                        return []
                    logger.debug("revlookup tier2: composing from Unihan for '%s'", jy_n)
                    combos = compose_fn(jy_n, cmap) or []
                    # shortlist expects (jyut, combos, top_n)
                    ranked_pairs = shortlist_fn(jyut=jy_n, combos=combos, top_n=10) or []
                    out = []
                    for hz, score in ranked_pairs:
                        out.append((hz, "tier2-char-ranked", int(score)))
                    logger.debug("revlookup tier2: ranked shortlist size=%d for '%s'", len(out), jy_n)
                    return out
                except TypeError:
                    # Older shortlist signature
                    try:
                        ranked_pairs = shortlist_fn(jy_n, combos, 10) or []
                        out = []
                        for hz, score in ranked_pairs:
                            out.append((hz, "tier2-char-ranked", int(score)))
                        logger.debug("revlookup tier2: ranked shortlist(size=%d) [fallback signature] for '%s'", len(out), jy_n)
                        return out
                    except Exception:
                        pass
                except Exception:
                    pass

            logger.debug("revlookup tier2: compose function or char_map unavailable for '%s'", jy_n)
            return []

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

            dlg = CategoryManagerDialog(window, vocab_dict, cats)

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

            dlg.exec()

        class MultiCategoryCombo(QComboBox):
            """A QComboBox that lets users check multiple categories via a checkable list view."""
            editingStarted = Signal()
            editingFinished = Signal()

            def __init__(self, categories, parent=None, initial_selected=None):
                super().__init__(parent)
                # Use the line edit for display text so we don't default to model row 0
                self.setEditable(True)
                try:
                    le = self.lineEdit()
                    if le is not None:
                        le.setReadOnly(True)
                        le.setPlaceholderText("(none)")
                except Exception:
                    pass
                # No actual model index selected; text comes from _update_display
                self.setCurrentIndex(-1)
                self._cats = list(categories or [])
                self.setView(QListView(self))
                model = QStandardItemModel(self)
                self.setModel(model)
                for cat in self._cats:
                    it = QStandardItem(cat)
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                    it.setData(Qt.Unchecked, Qt.CheckStateRole)
                    model.appendRow(it)
                # apply initial selection
                if initial_selected:
                    sel = set(initial_selected)
                    for i, cat in enumerate(self._cats):
                        if cat in sel:
                            model.item(i).setCheckState(Qt.Checked)
                # show current selection summary
                model.dataChanged.connect(self._update_display)
                self._update_display()
                # (Optional safety) After applying initial_selected, call _update_display() again
                self._update_display()

            def showPopup(self):
                try:
                    self.editingStarted.emit()
                except Exception:
                    pass
                super().showPopup()

            def hidePopup(self):
                try:
                    self.editingFinished.emit()
                except Exception:
                    pass
                super().hidePopup()

            def _update_display(self, *args):
                selected = []
                m = self.model()
                # Collect checked items
                for i in range(m.rowCount()):
                    it = m.item(i)
                    if it is not None and it.checkState() == Qt.Checked:
                        try:
                            selected.append(self._cats[i])
                        except Exception:
                            pass
                # Rule: once any non-'unassigned' category is checked, auto-uncheck 'unassigned'
                try:
                    lower_sel = [s.lower() for s in selected]
                    if any(s != 'unassigned' for s in lower_sel) and 'unassigned' in lower_sel:
                        m = self.model()
                        # find index of 'unassigned' in the model
                        un_idx = None
                        for i, cat_name in enumerate(self._cats):
                            if str(cat_name).lower() == 'unassigned':
                                un_idx = i
                                break
                        if un_idx is not None:
                            try:
                                m.blockSignals(True)
                                it_un = m.item(un_idx)
                                if it_un is not None:
                                    it_un.setCheckState(Qt.Unchecked)
                            finally:
                                m.blockSignals(False)
                            # recompute selected without 'unassigned'
                            selected = [self._cats[i] for i in range(m.rowCount()) if
                                        m.item(i) and m.item(i).checkState() == Qt.Checked]
                except Exception:
                    pass
                if selected:
                    # Case-insensitive sort; show the first
                    selected_sorted = sorted(selected, key=lambda s: s.lower())
                    display = selected_sorted[0]
                    tooltip = ", ".join(selected_sorted)
                else:
                    display = "(none)"
                    tooltip = ""
                try:
                    if self.isEditable() and self.lineEdit() is not None:
                        self.lineEdit().setText(display)
                    else:
                        # keep no actual index selected so Qt doesn't display row 0 (e.g., 'animals')
                        self.setCurrentIndex(-1)
                        self.setCurrentText(display)
                except Exception:
                    pass
                try:
                    self.setToolTip(tooltip)
                except Exception:
                    pass

            def selected(self):
                out = []
                m = self.model()
                for i in range(m.rowCount()):
                    if m.item(i).checkState() == Qt.Checked:
                        out.append(self._cats[i])
                return out

            def setCategories(self, categories):
                # rebuild model when category set changes
                self._cats = list(categories or [])
                model = QStandardItemModel(self)
                self.setModel(model)
                for cat in self._cats:
                    it = QStandardItem(cat)
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                    it.setData(Qt.Unchecked, Qt.CheckStateRole)
                    model.appendRow(it)
                try:
                    self.setCurrentIndex(-1)
                except Exception:
                    pass
                self._update_display()


            # --- Lazy import helpers for reverse lookup composition/ranking ---
            def _get_compose_and_rank(self):
                """Return (compose_candidates_from_chars, shortlist_candidates) from utils if available.
                Avoid hard import errors by resolving dynamically when first needed.
                """
                compose_fn = None
                shortlist_fn = None
                try:
                    compose_fn = compose_candidates_from_chars  # may be defined at module scope
                except NameError:
                    compose_fn = None
                try:
                    shortlist_fn = shortlist_candidates
                except NameError:
                    shortlist_fn = None
                if compose_fn is None or shortlist_fn is None:
                    try:
                        import utils as _u
                        if compose_fn is None:
                            compose_fn = getattr(_u, "compose_candidates_from_chars", None)
                        if shortlist_fn is None:
                            shortlist_fn = getattr(_u, "shortlist_candidates", None)
                    except Exception:
                        pass
                return compose_fn, shortlist_fn

        class CategoryManagerDialog(QDialog):
            # ---- Add & Edit: Jyutping validation + reverse lookup wiring ----
            def _normalize_jy(self, s: str) -> str:
                try:
                    return " ".join((s or "").strip().lower().split())
                except Exception:
                    return (s or "").strip().lower()

            # --- Lazy import helpers for reverse lookup composition/ranking (dialog-local) ---
            def _get_compose_and_rank(self):
                """Return (compose_candidates_from_chars, shortlist_candidates) from utils if available.
                This dialog-local copy avoids unresolved reference errors when the resolver exists only
                on other classes.
                """
                compose_fn = None
                shortlist_fn = None
                try:
                    compose_fn = compose_candidates_from_chars  # may be defined at module scope
                except NameError:
                    compose_fn = None
                try:
                    shortlist_fn = shortlist_candidates
                except NameError:
                    shortlist_fn = None
                if compose_fn is None or shortlist_fn is None:
                    try:
                        import utils as _u
                        if compose_fn is None:
                            compose_fn = getattr(_u, "compose_candidates_from_chars", None)
                        if shortlist_fn is None:
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
                Prefer attestation if an attested cache exists; otherwise fall back to structural OK.
                """
                try:
                    # If the dialog or parent provides an attestation helper, prefer it
                    if hasattr(self, "_is_attested_phrase") and callable(self._is_attested_phrase):
                        return bool(self._is_attested_phrase(self._normalize_jy(jy)))
                except Exception:
                    pass
                return self._validate_jyut_syllables(jy)

            # ---- Meanings / gloss helpers (lazy-loaded), with diagnostics ----
            # def _load_cedict_index(self):
            #     """
            #     Populate self._cedict as {hanzi: [gloss1, gloss2, ...]} using a lightweight parser.
            #     Safe if file is missing.
            #     """
            #     if hasattr(self, "_cedict") and isinstance(self._cedict, dict) and self._cedict:
            #         return self._cedict
            #     self._cedict = {}
            #     try:
            #         # import os, re
            #         base_dir = os.path.dirname(os.path.abspath(__file__))
            #         candidates = [
            #             os.path.join(base_dir, "data", "cedict", "cedict_ts.u8"),
            #             os.path.join(base_dir, "data", "CC-CEDICT", "cedict_ts.u8"),
            #             os.path.join(base_dir, "data", "cedict_ts.u8"),
            #         ]
            #         cedict_path = next((p for p in candidates if os.path.exists(p)), None)
            #         if not cedict_path:
            #             logger.debug("CEDICT not found in expected paths; glosses will be limited to andys_list.yaml")
            #             return self._cedict
            #         gloss_re = re.compile(r"^([^\s\[]+)\s+[^\[]+\s+\[(?:[^\]]*)\]\s+/(.+)/$")
            #         added = 0
            #         with open(cedict_path, "r", encoding="utf-8") as fh:
            #             for line in fh:
            #                 if not line or line.startswith("#"):
            #                     continue
            #                 m = gloss_re.match(line.strip())
            #                 if not m:
            #                     continue
            #                 hz = m.group(1)
            #                 glosses = [g.strip() for g in m.group(2).split("/") if g.strip()]
            #                 if hz and glosses:
            #                     self._cedict.setdefault(hz, glosses[:3])
            #                     added += 1
            #         logger.debug("CEDICT index loaded: %d Hanzi entries from %s", added, cedict_path)
            #     except Exception as e:
            #         logger.debug("CEDICT parse failed: %s", e)
            #     return self._cedict

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
                  2) CC-Canto (if present)
                  3) builtin fallback (optional)
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
                    # 2) CC-Canto
                    if not out_local:
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
                return []

            def _rerank_candidates_with_meanings(self, cands: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
                """Prefer candidates that:
                   1) yield glosses (from vocab or CEDICT),
                   2) use colloquial forms (阿… over 亚/亞…),
                   3) come from stronger sources (andys_list > csv > pycantonese > tier2),
                   4) have higher frequency if available.
                """

                def source_score(src: str) -> int:
                    order = ["andys_list", "builtin", "hkcancor", "subtitles", "cccanto", "pycantonese",
                             "tier2-char-ranked", "tier2"]
                    try:
                        return len(order) - order.index(src)
                    except Exception:
                        return 0

                scored = []
                for (hz, src, freq) in cands:
                    glosses = self._get_meanings_for_hanzi(hz)
                    has_gloss = 1 if glosses else 0
                    # Prefer 阿… over 亚/亞… in first position
                    first = hz[0] if hz else ""
                    colloquial_bonus = 1 if first == "阿" else 0
                    # Score tuple sorted descending
                    scored.append(((has_gloss, colloquial_bonus, source_score(src), int(freq or 0)), (hz, src, freq)))
                scored.sort(reverse=True)
                return [item for _score, item in scored]



            def _fill_hanzi_candidates(self, jy: str):
                try:
                    jy_n = self._normalize_jy(jy)
                    # Call the tiered reverse lookup to get candidates as (hanzi, source, freq)
                    cands = []
                    try:
                        if hasattr(self, "_reverse_candidates_for_jy") and callable(self._reverse_candidates_for_jy):
                            cands = self._reverse_candidates_for_jy(jy_n) or []
                    except Exception:
                        cands = []

                    # Re-rank to prefer items with glosses and colloquial forms
                    try:
                        cands = self._rerank_candidates_with_meanings(cands)
                    except Exception:
                        pass

                    # Update the Hanzi field with the top candidate (after re-ranking)
                    top_text = cands[0][0] if cands else ""
                    try:
                        self._add_hz.setText(top_text)
                    except Exception:
                        pass

                    # Populate candidates combobox with inline meanings when possible
                    try:
                        self._cand_combo.blockSignals(True)
                        self._cand_combo.clear()

                        if cands:
                            for (hz, src, freq) in cands:
                                # 1) Curated meanings first
                                glosses = []
                                try:
                                    if hasattr(self, "_get_meanings_for_hanzi") and callable(
                                            self._get_meanings_for_hanzi):
                                        glosses = self._get_meanings_for_hanzi(hz) or []
                                except Exception:
                                    glosses = []

                                # 2) Enrich with CC-Canto meanings if source is CC-Canto OR still empty
                                extra = []
                                extra_src = None
                                if (src == "cccanto") or (not glosses):
                                    try:
                                        from utils import get_cccanto_meanings_map  # lazy import
                                        _mn = get_cccanto_meanings_map() or {}

                                        # Debug: report key presence for common variants
                                        try:
                                            has_exact = hz in _mn
                                            hz_norm = self._normalize_hz_variant(hz) if hasattr(self, "_normalize_hz_variant") and callable(self._normalize_hz_variant) else hz
                                            has_norm = hz_norm in _mn
                                            # brute-force first-char swap
                                            swaps = []
                                            if hz:
                                                first, rest = hz[0], hz[1:]
                                                for alt in ("阿", "亞", "亚"):
                                                    if alt == first:
                                                        continue
                                                    cand = alt + rest
                                                    swaps.append((cand, cand in _mn))
                                            logger.debug("CCCanto meanings map: exact=%s norm(%s)=%s swaps=%s", has_exact, hz_norm, has_norm, swaps)
                                        except Exception:
                                            pass

                                        # a) exact match
                                        if hz in _mn:
                                            extra = list(_mn.get(hz, []))
                                            if extra:
                                                extra_src = "exact"
                                        # b) normalised variant (e.g., 亞/亚 -> 阿…)
                                        if (not extra) and hasattr(self, "_normalize_hz_variant") and callable(self._normalize_hz_variant):
                                            hz_norm = self._normalize_hz_variant(hz)
                                            if hz_norm and hz_norm != hz:
                                                extra = list(_mn.get(hz_norm, []))
                                                if extra:
                                                    extra_src = f"norm:{hz_norm}"
                                        # c) final fallback: brute-force swap first char among 阿/亞/亚
                                        if (not extra) and hz:
                                            first, rest = hz[0], hz[1:]
                                            for alt in ("阿", "亞", "亚"):
                                                if alt == first:
                                                    continue
                                                cand = alt + rest
                                                tmp = _mn.get(cand, [])
                                                if tmp:
                                                    extra = list(tmp)
                                                    extra_src = f"swap:{cand}"
                                                    break
                                    except Exception:
                                        logger.debug("CCCanto meanings: cache enrich failed for '%s'", hz)
                                        extra = []

                                    # d) last resort: scan the CC-Canto file directly
                                    if (not extra):
                                        try:
                                            from utils import get_cccanto_glosses_for
                                            extra = get_cccanto_glosses_for(hz) or []
                                            if extra:
                                                extra_src = "scan"
                                        except Exception:
                                            extra = []

                                    # Merge extras if any and log the outcome
                                    if extra:
                                        seen_m = set(glosses)
                                        for g in extra:
                                            if g not in seen_m:
                                                glosses.append(g)
                                                seen_m.add(g)
                                        logger.debug("CCCanto meanings: merged %d from %s for '%s' -> glosses=%r", len(extra), extra_src, hz, glosses[:3])
                                    else:
                                        logger.debug("CCCanto meanings: none found for '%s' (src=%s)", hz, src)

                                # 3) Build label: up to 2 meanings inline; else show source tag
                                if glosses:
                                    label = f"{hz} — {', '.join(glosses[:2])}"
                                else:
                                    label = f"{hz} — [{src}]" if src else hz

                                try:
                                    logger.debug("AddItem: candidate='%s' src=%s glosses=%d", hz, src, len(glosses))
                                except Exception:
                                    pass
                                # Second diagnostic: show first few glosses used in label
                                try:
                                    if glosses:
                                        logger.debug("AddItem: using glosses=%r for '%s'", glosses[:3], hz)
                                except Exception:
                                    pass

                                self._cand_combo.addItem(label, userData=hz)
                                try:
                                    self._cand_combo.setVisible(True)
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    # If exactly one candidate, auto-copy its glosses into Meanings and focus there
                    try:
                        if isinstance(cands, list) and len(cands) == 1:
                            single_hz = cands[0][0]
                            # Re-derive glosses using the same sources used for labels
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
                                    if (not glosses_single) and hasattr(self, "_normalize_hz_variant") and callable(
                                            self._normalize_hz_variant):
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
                                self._add_mn.setText(", ".join(glosses_single) if glosses_single else "")
                            except Exception:
                                pass
                            try:
                                if self._add_mn is not None:
                                    self._add_mn.setFocus()
                                    self._add_mn.selectAll()
                            except Exception:
                                pass
                            try:
                                logger.debug("AddItem: auto-filled meanings for single candidate '%s' -> %r",
                                             single_hz, (glosses_single[:3] if glosses_single else []))
                            except Exception:
                                pass
                    except Exception:
                        pass

                    # Tooltip preview on the Hanzi field for quick glance
                    try:
                        if cands:
                            preview_parts = []
                            for (hz, src, freq) in cands[:6]:
                                try:
                                    ms = []
                                    if hasattr(self, "_get_meanings_for_hanzi") and callable(self._get_meanings_for_hanzi):
                                        ms = self._get_meanings_for_hanzi(hz) or []
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

                    # Nudge UI to update immediately
                    try:
                        self._add_hz.repaint(); self._add_hz.update()
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

            def _on_jyut_enter(self):
                """
                Handle Enter/Return on the Jyutping line:
                  1) Duplicate check -> warn + focus Jyutping
                  2) Structural/attestation check -> warn + focus Jyutping
                  3) Reverse lookup -> fill Hanzi (best), reveal candidates dropdown and open it
                """
                try:
                    raw = self._add_jy.text() if self._add_jy is not None else ""
                except Exception:
                    raw = ""
                jy = self._normalize_jy(raw)

                # 1) duplicate?
                if self._is_duplicate_jy(jy):
                    QMessageBox.warning(self, "Duplicate Jyutping",
                                        "This Jyutping already exists. Please enter a different Jyutping.")
                    try:
                        self._add_jy.setFocus();
                        self._add_jy.selectAll()
                    except Exception:
                        pass
                    return

                # 2) validity / attestation
                if not self._attested_or_structural_ok(jy):
                    QMessageBox.information(self, "Invalid Jyutping",
                                            "Please enter valid Jyutping with tone digits (e.g., nei5 hou2).\n"
                                            "Special cases like m4 / ng5 are allowed.")
                    try:
                        self._add_jy.setFocus();
                        self._add_jy.selectAll()
                    except Exception:
                        pass
                    return

                # 3) reverse lookup & UI reveal; defer with singleShot to avoid blocking key event
                from PySide6.QtCore import QTimer
                def _do_fill():
                    n = self._fill_hanzi_candidates(jy)
                    # Ensure dropdown is visible and opened if we have candidates
                    try:
                        self._cand_combo.setVisible(n > 0)
                        if n > 0:
                            try:
                                # Make popup wide enough for “HZ — meaning, meaning”
                                self._cand_combo.view().setMinimumWidth(max(280, self._cand_combo.width()))
                            except Exception:
                                pass
                            QTimer.singleShot(0, self._cand_combo.showPopup)
                    except Exception:
                        pass
                    # Focus meanings next regardless; user can pick Hanzi from popup
                    try:
                        if self._add_mn is not None:
                            self._add_mn.setFocus()
                    except Exception:
                        pass
                    logger.debug("AddItem: Jyut validated; %d candidate(s) shown", n)

                QTimer.singleShot(0, _do_fill)

            def __init__(self, parent, vocab_items: dict, categories_map: dict):
                super().__init__(parent)
                self._parent = parent
                self._save_pending = False
                self._saving_now = False
                # Ensure optional dictionaries exist before any loader touches them
                self._rev_manual = {}
                self._cedict = {}

                self.setWindowTitle("Add & Edit Items")
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
                    logger.debug("AddItem: _cats keys (n=%d): %s", len(self._cats), sorted(self._cats.keys()))
                    logger.debug("AddItem: _all_cats (n=%d): %s", len(self._all_cats), self._all_cats)
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
                                    logger.debug("AddItem: categories reloaded from %s -> %d keys", cat_path, len(self._all_cats))
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
                header.addWidget(btn_close, 0, Qt.AlignTop | Qt.AlignRight)
                self._root.addLayout(header)
                btn_close.clicked.connect(self.accept)

                # Row: [ Entry (left) | Hanzi (right) ]
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(12)
                row.setStretch(0, 4)
                row.setStretch(1, 2)

                # --- Left: Entry group ---
                groupEntry = QGroupBox("Entry", self)
                formEntry = QFormLayout(groupEntry)
                formEntry.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
                formEntry.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
                formEntry.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
                formEntry.setRowWrapPolicy(QFormLayout.DontWrapRows)

                self._add_jy = QLineEdit(groupEntry)
                self._add_jy.setPlaceholderText("e.g. nei5 hou2")
                self._add_jy.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                try:
                    self._add_jy.setClearButtonEnabled(True)
                except Exception:
                    pass

                self._add_mn = QLineEdit(groupEntry)
                self._add_mn.setPlaceholderText("comma-separated meanings, e.g. hello, hi")
                self._add_mn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                try:
                    self._add_mn.setClearButtonEnabled(True)
                except Exception:
                    pass

                formEntry.addRow("Jyutping:", self._add_jy)
                formEntry.addRow("Meanings:", self._add_mn)

                # Category (editable combobox; defaults to 'unassigned')
                self._add_cat = QComboBox(groupEntry)
                self._add_cat.setObjectName("comboAddCategories")
                self._add_cat.setEditable(True)  # editable ONLY in Add panel
                self._add_cat.setInsertPolicy(QComboBox.NoInsert)
                self._add_cat.clear()
                self._add_cat.addItems(self._all_cats)
                try:
                    logger.debug("AddItem: category list populated (n=%d): %s",
                                 self._add_cat.count(),
                                 [self._add_cat.itemText(i) for i in range(self._add_cat.count())])
                except Exception:
                    pass

                # --- enforce sensible popup width and default hidden ---
                try:
                    # Wide enough to show “漢字 — meaning, meaning”
                    if hasattr(self._cand_combo, "view") and self._cand_combo.view() is not None:
                        self._cand_combo.view().setMinimumWidth(320)
                    # Keep hidden until candidates exist
                    self._cand_combo.setVisible(False)
                except Exception:
                    pass

                # default to 'unassigned'
                try:
                    idx_un = -1
                    for i in range(self._add_cat.count()):
                        if self._add_cat.itemText(i).strip().lower() == "unassigned":
                            idx_un = i
                            break
                    if idx_un >= 0:
                        self._add_cat.setCurrentIndex(idx_un)
                    else:
                        self._add_cat.setCurrentIndex(-1)
                except Exception:
                    pass
                self._add_cat.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                try:
                    le = self._add_cat.lineEdit()
                    if le:
                        le.setPlaceholderText("Type or choose a category…")
                        le.setClearButtonEnabled(True)
                        le.setToolTip("Select an existing category or type a new one; press Enter to add.")

                        # Hook: add-on-enter (if supporting helpers exist)
                        def _on_add_cat_text_committed():
                            text = (self._add_cat.currentText() or "").strip()
                            if not text:
                                return
                            # If helpers exist, use them; otherwise add directly if unique
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
                                        return
                                    # Reserved?
                                    if hasattr(self, "_is_reserved_cat") and self._is_reserved_cat(canon):
                                        QMessageBox.information(self, "Category",
                                                                f"‘{canon}’ is a reserved name and cannot be used.")
                                        return
                                    # Confirm creation
                                    if QMessageBox.question(self, "Add Category",
                                                            f"Add new category ‘{canon}’?",
                                                            QMessageBox.Yes | QMessageBox.No,
                                                            QMessageBox.Yes) != QMessageBox.Yes:
                                        return
                                    # Create via helper if present, else inline
                                    if hasattr(self, "_add_new_category"):
                                        self._add_new_category(canon)
                                    else:
                                        # Inline creation
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
                                pass

                        if le:
                            le.returnPressed.connect(_on_add_cat_text_committed)
                            le.editingFinished.connect(_on_add_cat_text_committed)
                except Exception:
                    pass

                formEntry.addRow("Category:", self._add_cat)

                # --- Robust wiring for Enter/Return on Add-Item fields ---
                # try:
                #     from PySide6.QtGui import QShortcut, QKeySequence
                # except Exception:
                #     QShortcut = None
                #     QKeySequence = None

                def _wire_enter(_le, _func):
                    if _le is None or not callable(_func):
                        return
                    try:
                        _le.returnPressed.connect(_func)
                    except Exception:
                        pass
                    # Avoid connecting editingFinished to the same handler to prevent double-fires while focus changes

                # Hook Jyutping handler (prefer class method if present)
                _jy_handler = getattr(self, "_on_jyut_enter", None)
                if not callable(_jy_handler):
                    def _jy_handler():
                        try:
                            logger.debug("AddItem: Enter pressed on Jyutping (fallback handler fired)")
                            if hasattr(self, "_add_mn") and self._add_mn is not None:
                                self._add_mn.setFocus()
                        except Exception:
                            pass

                logger.debug("AddItem: wiring Enter/Return for Jyutping line (post-build)")
                _wire_enter(self._add_jy, _jy_handler)

                # Wire Meanings and editable Category to the add-item commit handler if present
                _add_handler = getattr(self, "_on_add_item_enter", None)
                if callable(_add_handler):
                    logger.debug("AddItem: wiring Enter/Return for Meanings/Category (post-build)")
                    _wire_enter(self._add_mn, _add_handler)
                    try:
                        _le_cat = self._add_cat.lineEdit() if self._add_cat and self._add_cat.isEditable() else None
                        if _le_cat is not None:
                            _wire_enter(_le_cat, _add_handler)
                    except Exception:
                        pass

                # --- Right: Hanzi group (read-only) ---
                groupHanzi = QGroupBox("Hanzi", self)
                formHanzi = QFormLayout(groupHanzi)
                formHanzi.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

                self._add_hz = QLineEdit(groupHanzi)
                self._add_hz.setReadOnly(True)
                self._add_hz.setPlaceholderText("auto after Jyutping (reverse lookup)")
                self._add_hz.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
                self._add_hz.setMaximumWidth(260)
                try:
                    formHanzi.addRow(self._add_hz)  # span field column (no label)
                except TypeError:
                    formHanzi.addRow(QLabel("", groupHanzi), self._add_hz)

                # Candidate dropdown for reverse lookup
                self._cand_combo = QComboBox(groupHanzi)
                self._cand_combo.setObjectName("comboHanziCandidates")
                self._cand_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
                self._cand_combo.setVisible(False)
                # Keep the dropdown reasonably wide but allow it to shrink
                self._cand_combo.setMinimumWidth(240)
                self._cand_combo.setMaximumWidth(320)
                try:
                    formHanzi.addRow("Candidates:", self._cand_combo)
                except TypeError:
                    formHanzi.addRow(QLabel("Candidates:", groupHanzi), self._cand_combo)

                # Selecting a candidate fills the read-only Hanzi field
                def _on_candidate_chosen(text: str):
                    try:
                        self._add_hz.setText(text or "")
                    except Exception:
                        pass

                def _on_candidate_index(i: int):
                    try:
                        # Prefer stored userData (raw Hanzi), else fall back to the displayed text
                        hz = self._cand_combo.itemData(i)
                        if not hz:
                            hz = self._cand_combo.itemText(i)
                        self._add_hz.setText(hz or "")

                        # Derive glosses for this selection
                        glosses = []
                        try:
                            if hasattr(self, "_get_meanings_for_hanzi") and callable(self._get_meanings_for_hanzi):
                                glosses = self._get_meanings_for_hanzi(hz) or []
                        except Exception:
                            glosses = []
                        if not glosses:
                            try:
                                from utils import get_cccanto_glosses_for
                                glosses = get_cccanto_glosses_for(hz) or []
                            except Exception:
                                glosses = []

                        # Copy into Meanings and focus
                        try:
                            self._add_mn.setText(", ".join(glosses) if glosses else "")
                        except Exception:
                            pass
                        try:
                            if self._add_mn is not None:
                                self._add_mn.setFocus()
                                self._add_mn.selectAll()
                        except Exception:
                            pass
                    except Exception:
                        pass

                # Connect signals in a way that works across PySide6 variants
                connected = False
                try:
                    self._cand_combo.activated[int].connect(_on_candidate_index)
                    connected = True
                except Exception:
                    pass
                try:
                    # Some versions expose a generic .activated without overload helpers
                    if not connected:
                        self._cand_combo.activated.connect(_on_candidate_index)  # type: ignore
                        connected = True
                except Exception:
                    pass
                try:
                    # Also keep text-based updates in sync
                    self._cand_combo.currentTextChanged.connect(_on_candidate_chosen)
                except Exception:
                    pass

                # Apply size policies to prevent vertical stacking
                groupEntry.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
                groupEntry.setMinimumWidth(360)
                groupHanzi.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
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
                self._table.setSelectionBehavior(QTableWidget.SelectRows)
                self._table.setEditTriggers(QTableWidget.NoEditTriggers)
                self._table.setSortingEnabled(True)
                self._root.addWidget(self._table, 1)  # stretch to fill

                # If you already have a model-builder, call it; otherwise show empty table safely
                try:
                    if hasattr(self, "_rebuild_items_model"):
                        self._rebuild_items_model()  # fills self._table
                except Exception:
                    pass

                # --- Wiring: Enter on Jyutping / Meanings / Category to add item ---
                # Ensure a single, robust connection for Enter on Jyutping
                try:
                    self._add_jy.returnPressed.disconnect()
                except Exception:
                    pass
                if hasattr(self, "_on_jyut_enter") and callable(self._on_jyut_enter):
                    self._add_jy.returnPressed.connect(self._on_jyut_enter)
                try:
                    if hasattr(self, "_on_add_item_enter"):
                        self._add_mn.returnPressed.connect(self._on_add_item_enter)
                        if self._add_cat.isEditable() and self._add_cat.lineEdit():
                            self._add_cat.lineEdit().returnPressed.connect(self._on_add_item_enter)
                except Exception:
                    pass

                # Done: dialog is fully constructed and safe even if some helpers are missing
                logger.debug("CategoryManagerDialog: init complete")


            def _reverse_candidates_for_jy(self, jy: str):
                """Return a list of candidate Hanzi for a normalized jyut string.
                Sources (in priority order):
                  1) In-memory vocab (andys_list.yaml)
                  2) data/frequency/*.csv (if present), trying to infer columns
                  3) pycantonese reverse lookup (if available)
                Each item is a (hanzi, source_label, freq_int) tuple.
                """
                jy_n = " ".join((jy or "").strip().lower().split())
                out = []
                seen = set()

                # 1) In-memory vocab
                try:
                    for h, v in (self._vocab or {}).items():
                        try:
                            vjy = (v[1] if isinstance(v, list) and len(v) > 1 else "")
                            if " ".join((vjy or "").strip().lower().split()) == jy_n:
                                if h not in seen:
                                    out.append((h, "andys_list", 0))
                                    seen.add(h)
                        except Exception:
                            continue
                except Exception:
                    pass

                # 1b) Curated built-in reverse map (automated safety net)
                #    This helps when corpora are empty and pycantonese doesn’t expose a reverse API.
                BUILTIN_REVERSE = {
                    # greetings / basics
                    "nei5 hou2": ["你好"],
                    # common kinship / titles
                    "sin1 saang1": ["先生"],  # mister / sir / husband (contextual)
                    "taa3 taai2": ["太太"],  # Mrs.; note: jyut may vary; keep as minimal seed
                    # money / shopping examples often used in your dataset
                    "cin2": ["錢"],
                    "ping4 di1": ["平啲"],
                    "jau5 mou5 zit3 aa3": ["有冇折呀"],
                    "ni1 bun2 syu1 gei2 cin2 aa3": ["呢本書幾錢呀"],
                }
                try:
                    for hz in BUILTIN_REVERSE.get(jy_n, []) or []:
                        if hz and hz not in seen:
                            out.append((hz, "builtin", 0))
                            seen.add(hz)
                    if any(t[1] == "builtin" for t in out):
                        logger.debug("revlookup builtin: %d match(es) for '%s'",
                                     sum(1 for t in out if t[1] == "builtin"), jy_n)
                except Exception:
                    pass

                # 2) CSV frequency files (optional)
                def _try_csv(path, label):
                    try:
                        if not os.path.exists(path):
                            logger.debug("revlookup CSV skip: %s (missing)", path)
                            return
                        added = 0
                        with open(path, "r", encoding="utf-8") as fh:
                            r = csv.DictReader(fh)
                            fns = [fn.lower() for fn in (r.fieldnames or [])]
                            # Heuristics for column names
                            jy_col = next(
                                (n for n in ("jyut", "jyutping", "jyutping_str", "jyutping_text") if n in fns), None)
                            hanzi_col = next((n for n in ("hanzi", "word", "token", "char", "chars") if n in fns), None)
                            freq_col = next((n for n in ("freq", "frequency", "count", "token_count") if n in fns),
                                            None)
                            for row in r:
                                jyv = row.get(jy_col, "") if jy_col else ""
                                if " ".join((jyv or "").strip().lower().split()) != jy_n:
                                    continue
                                hzv = row.get(hanzi_col, "") if hanzi_col else (list(row.values())[0] if row else "")
                                if not hzv:
                                    continue
                                if hzv in seen:
                                    continue
                                try:
                                    fv = int(row.get(freq_col, 0)) if freq_col else 0
                                except Exception:
                                    fv = 0
                                out.append((hzv, label, fv))
                                seen.add(hzv)
                                added += 1
                        logger.debug("revlookup CSV hit: %s -> %d matches", label, added)
                    except Exception:
                        logger.debug("revlookup CSV error: %s", path)
                        pass

                _try_csv("data/frequency/hkcancor_words.csv", "hkcancor")
                _try_csv("data/frequency/subtitles_words.csv", "subtitles")
                _try_csv("data/frequency/cccanto_words.csv", "cccanto")

                # Tier-1: CC-Canto reverse (direct phrase hits)
                try:
                    # lazy-import to avoid hard dependency
                    try:
                        from utils import get_cccanto_reverse_map  # type: ignore
                    except Exception:
                        get_cccanto_reverse_map = None  # type: ignore

                    # cache the reverse map on the top-level window if available; else on this dialog
                    cache_host = getattr(self, "_parent", self)
                    ccc = getattr(cache_host, "_ccc_rev", None)
                    if not isinstance(ccc, dict) or not ccc:
                        if callable(get_cccanto_reverse_map):
                            ccc = get_cccanto_reverse_map() or {}
                        else:
                            ccc = {}
                        try:
                            setattr(cache_host, "_ccc_rev", ccc)
                        except Exception:
                            pass

                    # accept either {jy -> [hanzi,...]} or {jy -> [{"hanzi":...}, ...]}
                    hits_raw = (ccc.get(jy_n) or []) if isinstance(ccc, dict) else []
                    # normalise to list[str]
                    if hits_raw and isinstance(hits_raw, list):
                        hz_list = []
                        for item in hits_raw:
                            if isinstance(item, str):
                                h = item.strip()
                                if h:
                                    hz_list.append(h)
                            elif isinstance(item, dict):
                                h = str(item.get("hanzi", "")).strip()
                                if h:
                                    hz_list.append(h)

                        # append uniquely
                        added = 0
                        for hz in hz_list:
                            if hz not in seen:
                                out.append((hz, "cccanto", 0))
                                seen.add(hz)
                                added += 1
                        if added:
                            logger.debug("revlookup cccanto: %d candidates for '%s'", added, jy_n)
                except Exception:
                    logger.debug("revlookup cccanto: error", exc_info=True)

                # 3) pycantonese reverse lookup (optional)
                try:
                    import pycantonese as pc  # type: ignore
                except Exception:
                    pc = None
                if pc is not None:
                    # Try several likely function names/APIs to maximize compatibility across versions
                    def _unique_add(hz_val: str, src_label: str):
                        if hz_val and hz_val not in seen:
                            out.append((hz_val, src_label, 0))
                            seen.add(hz_val)

                    tried = False
                    # a) Direct function (if exists): jyutping_to_hanzi / jyutping_to_characters
                    for fn_name in ("jyutping_to_hanzi", "jyutping_to_characters", "characters_for_jyutping"):
                        try:
                            fn = getattr(pc, fn_name, None)
                            if callable(fn):
                                tried = True
                                res = fn(jy_n)
                                # Accept common return shapes: list[str], set[str], list[tuple]
                                if isinstance(res, (list, set, tuple)):
                                    for item in res:
                                        if isinstance(item, (list, tuple)) and item:
                                            _unique_add(str(item[0]), "pycantonese")
                                        elif isinstance(item, str):
                                            _unique_add(item, "pycantonese")
                                elif isinstance(res, str):
                                    _unique_add(res, "pycantonese")
                                logger.debug("revlookup pycantonese API '%s' -> %d total pyc candidates", fn_name,
                                             len([t for t in out if t[1] == 'pycantonese']))
                        except Exception:
                            pass

                    # b) If no direct function, try scanning a small built-in lexicon if exposed
                    if not tried:
                        # Some versions expose a mapping of characters to jyutping; attempt a lightweight reverse
                        for attr in ("lexicon", "chars_to_jyutping", "character_to_jyutping", "char_to_jyutping"):
                            try:
                                mapping = getattr(pc, attr, None)
                            except Exception:
                                mapping = None
                            if isinstance(mapping, dict) and mapping:
                                tried = True
                                # Heuristic: check exact phrase matches in keys
                                for hz_key, jy_val in list(mapping.items())[:50000]:  # cap to avoid heavy scanning
                                    try:
                                        jnorm = " ".join((str(jy_val) or "").strip().lower().split())
                                        if jnorm == jy_n:
                                            _unique_add(str(hz_key), "pycantonese")
                                    except Exception:
                                        continue
                                logger.debug("revlookup pycantonese map '%s' -> %d total pyc candidates", attr,
                                             len([t for t in out if t[1] == 'pycantonese']))
                                break


                    # c) As a final attempt, if HKCanCor is available via pycantonese, try frequent tokens
                    if not out:
                        try:
                            # Avoid loading full utterances; some versions expose token frequency helpers
                            get_freq = getattr(pc, "word_frequency", None)
                            if callable(get_freq):
                                # If a frequency API exists, we’d need a list of candidate words; skip without candidates
                                pass
                        except Exception:
                            pass

                # If pycantonese available but yielded nothing new, log it
                try:
                    _pyc_count = len([t for t in out if t[1] == 'pycantonese'])
                    if pc is not None and _pyc_count == 0:
                        logger.debug("revlookup pycantonese: no candidates for '%s'", jy_n)
                except Exception:
                    pass

                # ---- Report how many tier-1 candidates we gathered and, if none, try tier-2 ----
                try:
                    logger.debug("revlookup tier1: %d candidates for '%s'", len(out), jy_n)
                except Exception:
                    pass

                if len(out) == 0:
                    logger.debug("revlookup tier2: composing from Unihan for '%s'", jy_n)
                    try:
                        char_map = getattr(self, "_char_map", None)
                        compose_fn, shortlist_fn = (self.
                                                    _get_compose_and_rank())
                        if callable(compose_fn) and isinstance(char_map, dict) and char_map:
                            # 1) build raw combos from per-char readings (tone-sensitive)
                            raw = compose_fn(
                                jy_n, char_map, cap_per_syl=60, cap_combos=500
                            ) or []
                            logger.debug(
                                "revlookup tier2: composed %d raw combos for '%s' (preview: %s)",
                                len(raw), jy_n, ", ".join(raw[:10])
                            )

                            # 2) Try to rank/shortlist if helper is available
                            ranked_pairs = []
                            try:
                                if callable(shortlist_fn) and raw:
                                    base_dir = os.path.dirname(os.path.abspath(__file__))
                                    ranked_pairs = shortlist_fn(
                                        jy_n,  # <- positional 'jy'
                                        raw,  # <- positional 'cands'
                                        vocab=self._vocab,
                                        reverse_manual_path=os.path.join(base_dir, "data", "reverse_manual.yaml"),
                                        freq_csvs=[
                                            os.path.join(base_dir, "data", "frequency", "hkcancor_words.csv"),
                                            os.path.join(base_dir, "data", "frequency", "subtitles_words.csv"),
                                            os.path.join(base_dir, "data", "frequency", "cccanto_words.csv"),
                                        ],
                                        top_n=10,
                                    ) or []
                                    logger.debug(
                                        "revlookup tier2: ranked shortlist size=%d for '%s'",
                                        len(ranked_pairs), jy_n
                                    )
                            except Exception as _rank_err:
                                logger.debug("revlookup tier2: ranking error for '%s': %s", jy_n, _rank_err, exc_info=True)
                                ranked_pairs = []

                            # 3) Choose final list (ranked if present, otherwise raw fallback)
                            if ranked_pairs:
                                candidates_final = [hz for (hz, _score) in ranked_pairs]
                                src_label = ""
                            else:
                                candidates_final = raw[:10]
                                src_label = "tier2-char"
                                logger.debug("revlookup tier2: fallback using raw (n=%d) for '%s'",
                                             len(candidates_final), jy_n)

                            # 4) Append to output, avoid duplicates
                            added = 0
                            for hz in candidates_final:
                                if hz and (hz not in seen):
                                    out.append((hz, src_label, 0))
                                    seen.add(hz)
                                    added += 1
                            logger.debug("revlookup tier2: appended %d candidates for '%s'", added, jy_n)
                        else:
                            # Extra diagnostics to explain why Tier-2 was skipped
                            logger.debug(
                                "revlookup tier2: compose unavailable (compose_fn=%r, char_map_size=%s) for '%s'",
                                bool(callable(compose_fn)), len(char_map or {}) if isinstance(char_map, dict) else None, jy_n
                            )
                    except Exception:
                        logger.debug("revlookup tier2: exception while composing for '%s'", jy_n, exc_info=True)

                # 3b) Fallback: compose by per-character readings if a mapping is exposed
                try:
                    if pc is not None and len(out) == 0:
                        # Try to locate a mapping of single character -> readings
                        char_map = None
                        map_attr_used = None
                        for attr in ("character_to_jyutping", "char_to_jyutping", "chars_to_jyutping", "lexicon"):
                            try:
                                m = getattr(pc, attr, None)
                            except Exception:
                                m = None
                            if isinstance(m, dict) and m:
                                char_map = m
                                map_attr_used = attr
                                break
                        if isinstance(char_map, dict) and char_map:
                            parts = jy_n.split()
                            # Build candidate lists per syllable (cap each list to avoid explosion)
                            per_syl_chars = []
                            CAP_PER_SYL = 30
                            scanned = 0
                            for syl in parts:
                                cand_chars = []
                                # Iterate a capped slice of mapping items to avoid heavy scans
                                for ch, jyv in list(char_map.items())[:60000]:
                                    scanned += 1
                                    try:
                                        # Normalize mapping readings into a set of strings
                                        vals = []
                                        if isinstance(jyv, str):
                                            vals = [jyv]
                                        elif isinstance(jyv, (list, tuple, set)):
                                            vals = list(jyv)
                                        elif jyv is not None:
                                            vals = [str(jyv)]
                                        matched = False
                                        for v in vals:
                                            vnorm = " ".join((v or "").strip().lower().split())
                                            # Accept exact syllable match within space-separated readings
                                            if vnorm == syl or syl in vnorm.split():
                                                matched = True
                                                break
                                        if matched and isinstance(ch, str) and len(ch) == 1:
                                            cand_chars.append(ch)
                                            if len(cand_chars) >= CAP_PER_SYL:
                                                break
                                    except Exception:
                                        continue
                                if not cand_chars:
                                    per_syl_chars = []
                                    break  # cannot compose phrase if any syllable has no candidates
                                per_syl_chars.append(cand_chars)
                            if per_syl_chars:
                                from itertools import product
                                CAP_COMBOS = 100
                                combos_added = 0
                                for tup in product(*per_syl_chars):
                                    hz = "".join(tup)
                                    if hz and hz not in seen:
                                        out.append((hz, f"pycantonese-char:{map_attr_used}", 0))
                                        seen.add(hz)
                                        combos_added += 1
                                    if combos_added >= CAP_COMBOS:
                                        break
                                logger.debug("revlookup pycantonese-char '%s': built %d combos from %d scanned items",
                                             map_attr_used, combos_added, scanned)
                        else:
                            logger.debug("revlookup pycantonese-char: no character mapping exposed on pycantonese")
                except Exception:
                    logger.debug("revlookup pycantonese-char: fallback error", exc_info=True)

                # Sort by (higher freq first), then source label, then hanzi
                out.sort(key=lambda t: (-int(t[2]) if isinstance(t[2], int) else 0, t[1], t[0]))
                return out



            def _load_reverse_manual(self):
                """Lazy-load data/reverse_manual.yaml into a {hanzi: [meanings]} dict."""
                if hasattr(self, "_rev_manual") and isinstance(self._rev_manual, dict) and self._rev_manual:
                    return self._rev_manual
                try:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    path = os.path.join(base_dir, "data", "reverse_manual.yaml")
                    if not os.path.exists(path):
                        self._rev_manual = {}
                        return self._rev_manual
                    with open(path, "r", encoding="utf-8") as fh:
                        raw = yaml.safe_load(fh) or {}
                    out = {}
                    # Accept two shapes:
                    #  A) { "爸": ["dad","father"], "父": ["father"] }
                    #  B) { "entries": [ {"hanzi":"爸","meanings":["father"]}, ... ] }
                    if isinstance(raw, dict):
                        if "entries" in raw and isinstance(raw["entries"], list):
                            for item in raw["entries"]:
                                try:
                                    hz = str(item.get("hanzi","")).strip()
                                    m  = item.get("meanings", [])
                                    if hz:
                                        if isinstance(m, str):
                                            out.setdefault(hz, []).append(m)
                                        elif isinstance(m, (list, tuple, set)):
                                            out.setdefault(hz, []).extend([str(x) for x in m if x])
                                except Exception:
                                    continue
                        else:
                            for k, v in raw.items():
                                try:
                                    hz = str(k).strip()
                                    if not hz:
                                        continue
                                    if isinstance(v, str):
                                        out.setdefault(hz, []).append(v)
                                    elif isinstance(v, (list, tuple, set)):
                                        out.setdefault(hz, []).extend([str(x) for x in v if x])
                                except Exception:
                                    continue
                    self._rev_manual = {k: [s for s in v if s] for k, v in out.items()}
                except Exception:
                    self._rev_manual = {}
                return self._rev_manual

            class CategoryManagerDialog(QDialog):
                # ---- Meanings / gloss helpers (lazy-loaded), with diagnostics ----

                def _load_cccanto_index(self):
                    """
                    Load CC-Canto export as {hanzi: [glosses]}.
                    Each line: HANZI HANZI [jyut1 jyut2 ...] /meaning1/meaning2/
                    """
                    if hasattr(self, "_cccanto") and isinstance(self._cccanto, dict) and self._cccanto:
                        return self._cccanto
                    self._cccanto = {}
                    try:
                        base_dir = os.path.dirname(os.path.abspath(__file__))
                        path = os.path.join(base_dir, "data", "cccanto.txt")
                        if not os.path.exists(path):
                            logger.debug("CC-Canto not found at %s", path)
                            return self._cccanto
                        import re
                        line_re = re.compile(r"^(\S+)\s+\S+\s+\[[^\]]+\]\s+/(.+)/$")
                        added = 0
                        with open(path, "r", encoding="utf-8") as fh:
                            for line in fh:
                                if not line or line.startswith("#"):
                                    continue
                                m = line_re.match(line.strip())
                                if not m:
                                    continue
                                hz = m.group(1)
                                glosses = [g.strip() for g in m.group(2).split("/") if g.strip()]
                                if hz and glosses:
                                    self._cccanto.setdefault(hz, glosses[:3])
                                    added += 1
                        logger.debug("CC-Canto index loaded: %d Hanzi entries", added)
                    except Exception as e:
                        logger.debug("CC-Canto parse failed: %s", e)
                    return self._cccanto

                def _load_cccanto_index(self):
                    """
                    Load CC-Canto into {hanzi: [glosses…]}.
                    Tries these paths (first hit wins):
                      data/CC-CANTO/cccanto.txt
                      data/CC-Canto/cccanto.txt
                      data/cccanto.txt
                      data/cccanto.csv
                    Safe if file missing; returns {}.
                    """
                    if hasattr(self, "_cccanto") and isinstance(self._cccanto, dict) and self._cccanto:
                        return self._cccanto
                    self._cccanto = {}
                    # import os, csv
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    candidates = [
                        os.path.join(base_dir, "data", "CC-CANTO", "cccanto.txt"),
                        os.path.join(base_dir, "data", "CC-Canto", "cccanto.txt"),
                        os.path.join(base_dir, "data", "cccanto.txt"),
                        os.path.join(base_dir, "data", "cccanto.csv"),
                    ]
                    path = next((p for p in candidates if os.path.exists(p)), None)
                    if not path:
                        logger.debug("CC-Canto not found in expected paths; meanings will use andys_list / CEDICT only")
                        return self._cccanto

                    delim = "\t" if path.endswith(".tsv") else ","
                    added = 0
                    try:
                        with open(path, "r", encoding="utf-8") as fh:
                            # tolerate odd delimiters
                            try:
                                sample = fh.read(4096);
                                fh.seek(0)
                                dialect = csv.Sniffer().sniff(sample)
                                reader = csv.reader(fh, dialect)
                            except Exception:
                                reader = csv.reader(fh, delimiter=delim)
                            for row in reader:
                                if not row or len(row) < 3:
                                    continue
                                hz = str(row[0]).strip()
                                gloss = str(row[2]).strip()
                                if hz and gloss:
                                    self._cccanto.setdefault(hz, [])
                                    if gloss not in self._cccanto[hz]:
                                        self._cccanto[hz].append(gloss)
                                        added += 1
                        logger.debug("CC-Canto index loaded: %d gloss entries from %s", added, path)
                    except Exception as e:
                        logger.debug("CC-Canto parse failed: %s", e)
                    return self._cccanto



            # def _get_meanings_for_hanzi(self, hz: str):
            #     """Return a short list of English meanings for a Hanzi candidate, probing multiple sources."""
            #     out = []
            #     # 1) Current in-memory vocab (andys_list.yaml already loaded)
            #     try:
            #         if hz in (self._vocab or {}):
            #             val = self._vocab.get(hz)
            #             if isinstance(val, (list, tuple)) and len(val) > 0:
            #                 ms = val[0] if isinstance(val[0], list) else [str(val[0])]
            #                 out.extend([m for m in ms if m])
            #     except Exception:
            #         pass
            #     # 2) reverse_manual.yaml
            #     try:
            #         rm = self._load_reverse_manual()
            #         if hz in rm:
            #             out.extend([m for m in rm.get(hz, []) if m])
            #     except Exception:
            #         pass
            #
            #     # Dedup and limit
            #     return list(dict.fromkeys(out))[:3]



            def _is_valid_jyut(self, jy: str) -> bool:
                """Validate a space-separated Jyutping string.
                Rules:
                  - Each syllable must end with a tone digit 1-6
                  - Allows standalone 'm'/'ng' syllables (e.g., m4, ng5)
                  - Otherwise requires (optional initial)(final) + tone
                Tries pycantonese if available; falls back to regex.
                """
                s = (jy or "").strip().lower()
                if not s:
                    logger.debug("Jy validate: EMPTY input -> invalid")
                    return False

                # Collapse multiple spaces so "nei5   hou2" is handled
                parts = " ".join(s.split()).split(" ")

                import re
                initials = (
                    "b|p|m|f|d|t|n|l|g|k|ng|h|z|c|s|gw|kw|w|j"
                )
                # NOTE: 'ou' added (needed for hou2)
                finals = (
                    "aa|aai|aau|aam|aan|aang|aap|aat|aak|"
                    "ai|au|am|an|ang|ap|at|ak|"
                    "e|ei|eng|ek|"
                    "i|iu|im|in|ing|ip|it|ik|"
                    "o|oi|on|ong|ot|ok|"
                    "ou|"  # <— added
                    "u|ui|un|ung|ut|uk|"
                    "eo|eoi|eon|eot|eok|"
                    "oe|oeng|oek|"
                    "yu|yun|yut"
                )

                syl_re = re.compile(rf"^(?:((?:{initials})?)((?:{finals}))|((?:m|ng)))([1-6])$")

                for syl in parts:
                    if not syl_re.match(syl):
                        logger.debug("Jy validate: syllable FAIL -> '%s' (from '%s')", syl, " ".join(parts))
                        return False

                logger.debug("Jy validate: OK -> '%s'", " ".join(parts))
                return True

            def _load_attested_sources(self):
                """Populate two caches:
                   _attested_phrases: set[str] of full jyut strings (space-separated)
                   _attested_syllables: set[str] of individual syllables with tone
                Sources: in-memory vocab (andys_list.yaml) + optional CSVs under data/frequency/.
                """

                def _norm_phrase(s: str) -> str:
                    return " ".join((s or "").strip().lower().split())

                phrases, sylls = set(), set()

                # In-memory vocab (from andys_list.yaml already loaded into self._vocab)
                try:
                    for _, v in (self._vocab or {}).items():
                        jy = _norm_phrase(v[1] if isinstance(v, list) and len(v) > 1 else "")
                        if jy:
                            phrases.add(jy)
                            for syl in jy.split():
                                if syl:
                                    sylls.add(syl)
                except Exception:
                    pass

                # import os, csv
                def _load_csv(path: str):
                    try:
                        if not os.path.exists(path):
                            return
                        with open(path, "r", encoding="utf-8") as fh:
                            r = csv.DictReader(fh)
                            cols = [c.lower() for c in (r.fieldnames or [])] if r.fieldnames else []
                            jy_col = next(
                                (n for n in ("jyut", "jyutping", "jyutping_str", "jyutping_text") if n in cols), None)
                            for row in r:
                                val = row.get(jy_col, "") if jy_col else (list(row.values())[0] if row else "")
                                j = _norm_phrase(val)
                                if j:
                                    phrases.add(j)
                                    for syl in j.split():
                                        if syl:
                                            sylls.add(syl)
                    except Exception:
                        pass

                _load_csv("data/frequency/hkcancor_words.csv")
                _load_csv("data/frequency/subtitles_words.csv")
                _load_csv("data/frequency/cccanto_words.csv")

                self._attested_phrases = phrases
                self._attested_syllables = sylls

            def _ensure_attested_cache(self):
                if not hasattr(self, "_attested_phrases") or self._attested_phrases is None \
                        or not hasattr(self, "_attested_syllables") or self._attested_syllables is None:
                    self._load_attested_sources()

            def _is_attested_jyut(self, jy: str) -> bool:
                """True if the *phrase* is attested, or every syllable is attested.
                Falls back to structure-only if caches are empty or missing syllables."""
                self._ensure_attested_cache()

                # --- Ensure seed syllables are present (union into cache) ---
                base_sylls = [
                    "a", "aa", "ai", "au", "am", "an", "ang", "ap", "at", "ak",
                    "e", "ei", "eng", "ek",
                    "i", "iu", "im", "in", "ing", "ip", "it", "ik",
                    "o", "oi", "on", "ong", "ot", "ok",
                    "ou", "u", "ui", "un", "ung", "ut", "uk",
                    "eo", "eoi", "eon", "eot", "eok",
                    "oe", "oeng", "oek",
                    "yu", "yun", "yut",
                    # syllabic and frequent bases used in day-to-day phrases
                    "m", "ng", "nei", "hou", "sin", "saang", "pin", "fuk", "baa"
                ]
                seed_set = {b + str(t) for b in base_sylls for t in range(1, 7)}
                if not hasattr(self, "_attested_syllables") or self._attested_syllables is None:
                    self._attested_syllables = set()
                # Union (so we keep any already-loaded syllables from CSVs/vocab)
                missing_before = len(seed_set - self._attested_syllables)
                self._attested_syllables |= seed_set
                if not hasattr(self, "_attested_phrases") or self._attested_phrases is None:
                    self._attested_phrases = set()
                logger.debug(
                    "Seed syllables merged: now=%d (added %d)",
                    len(self._attested_syllables),
                    missing_before,
                )

                # --- Fallback if caches are empty ---
                if not self._attested_phrases and not self._attested_syllables:
                    logger.debug("Attest check: caches empty -> fallback to structural validity")
                    return self._is_valid_jyut(jy)

                s = " ".join((jy or "").strip().lower().split())
                logger.debug("Attest check: '%s'", s)

                # Fetch caches up front so they're available for any logging below
                phrases = getattr(self, "_attested_phrases", None)
                sylls = getattr(self, "_attested_syllables", None)

                if not s:
                    logger.debug("Attest check: empty input -> False")
                    return False

                # Replacement logic: log missing syllables, fallback to structure if phrase not attested and some sylls missing
                if phrases is not None and sylls is not None:
                    parts = s.split()
                    if s in phrases:
                        logger.debug("Attest check: phrase FOUND '%s'", s)
                        return True
                    if parts:
                        missing = [p for p in parts if p not in sylls]
                        ok_all = (len(missing) == 0)
                        if ok_all:
                            logger.debug("Attest check: all syllables known for '%s'", s)
                            return True
                        # Generalized fallback: accept structurally valid phrases even if not in caches yet
                        if self._is_valid_jyut(s):
                            logger.debug("Attest check: fallback STRUCTURAL PASS for '%s'; missing syllables: %s", s,
                                         missing)
                            return True
                        logger.debug("Attest check: FAIL for '%s'; missing syllables: %s", s, missing)
                        return False
                    # No parts -> invalid
                    return False
                # no corpora loaded -> accept based on structural validity only
                return self._is_valid_jyut(s)

            def _canon_cat_name(self, s: str) -> str:
                # normalize: trim outer spaces, collapse inner multiple spaces to a single space
                if s is None:
                    return ""
                s2 = " ".join(s.strip().split())
                # optional: constrain length
                if not s2 or len(s2) > 48:
                    return ""
                return s2

            def _is_reserved_cat(self, name: str) -> bool:
                if not name:
                    return True
                low = name.lower()
                reserved = {"all", "unassigned"}
                return low in reserved

            def _find_existing_canonical(self, name: str) -> str | None:
                # case-insensitive match against current category set; return the stored canonical form if found
                low = name.lower()
                for c in self._all_cats:
                    if str(c).lower() == low:
                        return c
                return None

            def _add_new_category(self, canon: str):
                # Insert into in-memory lists/maps
                if canon not in self._all_cats:
                    self._all_cats.append(canon)
                    self._all_cats.sort(key=lambda s: s.lower())
                self._cats.setdefault(canon, [])

                # Update the Add-Item combobox model without losing selection
                cur = canon
                self._add_cat.blockSignals(True)
                try:
                    self._add_cat.clear()
                    self._add_cat.addItems(sorted(self._all_cats, key=lambda s: s.lower()))
                    idx = self._add_cat.findText(cur)
                    if idx >= 0:
                        self._add_cat.setCurrentIndex(idx)
                    else:
                        self._add_cat.setCurrentText(cur)
                finally:
                    self._add_cat.blockSignals(False)

                # Persist immediately to categories.yaml and refresh main window’s combobox (without changing selection)
                cats = self._aggregate_categories()  # live table selections
                # also ensure the new empty category exists in persisted structure
                cats.setdefault(canon, [])
                self._write_categories(cats)

                # Refresh all row combos to include the new category
                self._rebuild_category_widgets_column()

            def _save_table_viewport(self):
                try:
                    vs = self._table.verticalScrollBar().value()
                except Exception:
                    vs = 0
                try:
                    cur = self._table.currentRow()
                except Exception:
                    cur = -1
                anchor = self._anchor_hanzi
                return (vs, cur, anchor)

            def _restore_table_viewport(self, state):
                try:
                    vs, cur, anchor = state
                except Exception:
                    return
                try:
                    self._table.verticalScrollBar().setValue(int(vs))
                except Exception:
                    pass
                # Prefer identity-based restore (robust if rows reorder)
                try:
                    if anchor:
                        target_row = None
                        for r in range(self._table.rowCount()):
                            it = self._table.item(r, 0)
                            if it and it.text() == anchor:
                                target_row = r
                                break
                        if target_row is not None:
                            self._table.setCurrentCell(target_row, 0)
                            self._table.selectRow(target_row)
                            return
                except Exception:
                    pass
                # Fallback: row index
                try:
                    if 0 <= cur < self._table.rowCount():
                        self._table.setCurrentCell(cur, 0)
                        self._table.selectRow(cur)
                except Exception:
                    pass

            def _aggregate_categories(self) -> dict:
                out = {c: [] for c in self._all_cats}
                for roww in self._row_widgets:
                    h = roww["hanzi"]
                    sel = roww["combo"].selected() if roww.get("combo") else []
                    for cat in sel:
                        out[cat].append(h)
                # sort & dedupe
                out = {c: sorted(set(v)) for c, v in out.items()}
                # clean: remove from 'unassigned' if present in any other category
                try:
                    others = set()
                    for cat, items in out.items():
                        if cat != 'unassigned':
                            others.update(items)
                    if 'unassigned' in out:
                        out['unassigned'] = [h for h in out['unassigned'] if h not in others]
                except Exception:
                    pass
                return out

            def _normalize_meanings(self, text: str) -> list[str]:
                parts = [p.strip() for p in (text or "").split(",")]
                return [p for p in parts if p]

            def _write_andys_list(self):
                """Persist current vocab (self._vocab) back to andys_list.yaml in the expected format.
                Uses only built-in serializable types and writes atomically to avoid file truncation.
                """
                try:
                    import tempfile, os

                    # 1) Build a plain-`dict` with string keys and [list[str], str] values
                    data = {}
                    for k, v in (self._vocab or {}).items():
                        try:
                            key = str(k)
                            if isinstance(v, list) and len(v) >= 2:
                                meanings = v[0]
                                jy = v[1]
                            elif isinstance(v, tuple) and len(v) >= 2:
                                meanings = v[0]
                                jy = v[1]
                            else:
                                # Skip malformed entries quietly
                                continue
                            # Coerce to serializable shapes
                            if not isinstance(meanings, list):
                                meanings = [str(meanings)] if meanings is not None else []
                            else:
                                meanings = [str(m) for m in meanings if m is not None]
                            jy = " ".join((str(jy) or "").strip().split())
                            data[key] = [meanings, jy]
                        except Exception:
                            continue

                    # 2) Sort by Hanzi key for stable output (regular dict preserves insertion order in Py3.7+)
                    ordered_pairs = sorted(data.items(), key=lambda kv: kv[0])
                    ordered_dict = {k: v for k, v in ordered_pairs}

                    # 3) Atomic write: to tmp file then replace
                    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "andys_list.yaml")
                    tmp_fd, tmp_path = tempfile.mkstemp(prefix="andys_list_", suffix=".yaml",
                                                        dir=os.path.dirname(target))
                    try:
                        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                            yaml.safe_dump(
                                ordered_dict,
                                fh,
                                allow_unicode=True,
                                sort_keys=False,
                                default_flow_style=False,
                            )
                            fh.flush()
                            os.fsync(fh.fileno())
                        os.replace(tmp_path, target)
                    finally:
                        # In case of exception before replace
                        try:
                            if os.path.exists(tmp_path):
                                os.remove(tmp_path)
                        except Exception:
                            pass

                    logger.debug("andys_list.yaml saved (%d entries) [atomic]", len(ordered_dict))
                except Exception as e:
                    logger.warning("Failed to save andys_list.yaml: %s", e)

            def _ensure_category_exists_or_confirm(self, name: str) -> str | None:
                """Ensure category exists; if not, confirm add (blocking). Returns canonical name or None if cancelled."""
                canon = self._canon_cat_name(name)
                if not canon:
                    return None
                existing = self._find_existing_canonical(canon)
                if existing:
                    return existing
                if self._is_reserved_cat(canon):
                    QMessageBox.information(self, "Category", f"‘{canon}’ is a reserved name and cannot be used.")
                    return None
                if QMessageBox.question(self, "Add Category", f"Add new category ‘{canon}’?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
                    return None
                self._add_new_category(canon)
                return canon

            def _find_hanzi_by_jyut(self, jy: str) -> str | None:
                """Return the Hanzi key for an existing item whose Jyutping matches `jy` (case-insensitive),
                or None if not found."""
                jn = (jy or "").strip().lower()
                if not jn:
                    return None
                for h, v in (self._vocab or {}).items():
                    try:
                        vjy = (v[1] if isinstance(v, list) and len(v) > 1 else "")
                        if (vjy or "").strip().lower() == jn:
                            return h
                    except Exception:
                        continue
                return None

            def _on_add_item_enter(self):
                """Triggered when user presses Enter in Add Item fields. Save only if Jyutping, Meanings and Category are valid.
                If meanings are missing, warn and focus Meanings."""
                try:
                    jy_raw = (self._add_jy.text() or "")
                    jy = " ".join(jy_raw.strip().lower().split())
                    logger.debug("Add Item: raw_jy='%s' norm='%s'", jy_raw, jy)
                except Exception:
                    jy = ""
                try:
                    mn_text = (self._add_mn.text() or "").strip()
                except Exception:
                    mn_text = ""
                try:
                    cat_text = (self._add_cat.currentText() or "").strip()
                except Exception:
                    cat_text = ""

                # Duplicate Jyutping check FIRST
                existing_hz = self._find_hanzi_by_jyut(jy)
                if existing_hz is not None:
                    try:
                        hz_peek = (self._add_hz.text() or "").strip()
                    except Exception:
                        hz_peek = ""
                    # If we are adding a brand-new item or the target differs, block and clear
                    if not hz_peek or existing_hz != hz_peek:
                        QMessageBox.warning(
                            self,
                            "Duplicate Jyutping",
                            (
                                "The Jyutping ‘{0}’ is already used by the entry ‘{1}’.\n"
                                "Please use a unique Jyutping or edit the existing item instead."
                            ).format(jy, existing_hz),
                        )
                        try:
                            self._add_jy.clear()
                            self._add_jy.setFocus()
                        except Exception:
                            pass
                        return

                # Validate Jyutping structure first
                if not self._is_valid_jyut(jy):
                    QMessageBox.warning(self, "Add Item",
                                        "The Jyutping is invalid. Please enter a valid Jyutping with tone digits (e.g., nei5, hou2, m4, ng5).")
                    try:
                        self._add_jy.setFocus()
                        self._add_jy.selectAll()
                    except Exception:
                        pass
                    return

                if not self._is_attested_jyut(jy):
                    QMessageBox.warning(self, "Add Item",
                                        "This Jyutping isn’t in your dictionaries/corpora "
                                        "(HKCANCOR/Subtitles/CC-Canto/andys_list).\n"
                                        "Please confirm it’s correct or adjust it.")
                    try:
                        self._add_jy.setFocus();
                        self._add_jy.selectAll()
                    except Exception:
                        pass
                    return

                # Require meanings
                if not mn_text:
                    QMessageBox.warning(self, "Add Item", "Please add at least one meaning before saving.")
                    try:
                        self._add_mn.setFocus()
                        self._add_mn.selectAll()
                    except Exception:
                        pass
                    return

                # Resolve category (confirm create if needed)
                cat_canon = self._ensure_category_exists_or_confirm(cat_text)
                if not cat_canon:
                    try:
                        self._add_cat.setFocus()
                    except Exception:
                        pass
                    return

                # Hanzi must be resolved (readonly field populated elsewhere)
                try:
                    hz = (self._add_hz.text() or "").strip()
                except Exception:
                    hz = ""
                if not hz:
                    QMessageBox.warning(self, "Add Item",
                                        "No Hanzi found for this Jyutping yet. Please enter Jyutping that maps to a Hanzi first.")
                    try:
                        self._add_jy.setFocus()
                        self._add_jy.selectAll()
                    except Exception:
                        pass
                    return

                # Build/update vocab entry
                meanings = self._normalize_meanings(mn_text)
                if not meanings:
                    QMessageBox.warning(self, "Add Item", "Please add at least one meaning before saving.")
                    try:
                        self._add_mn.setFocus()
                        self._add_mn.selectAll()
                    except Exception:
                        pass
                    return

                # Update in-memory vocab
                self._vocab[hz] = [meanings, jy]

                # Update category assignment: ensure present in chosen category, and not left in 'unassigned'
                self._cats.setdefault(cat_canon, [])
                if hz not in self._cats[cat_canon]:
                    self._cats[cat_canon].append(hz)
                    self._cats[cat_canon] = sorted(set(self._cats[cat_canon]))
                if 'unassigned' in self._cats:
                    try:
                        self._cats['unassigned'] = [h for h in self._cats['unassigned'] if h != hz]
                    except Exception:
                        pass

                # Persist both files
                self._write_andys_list()
                self._write_categories(self._cats)

                # Refresh table rows to reflect new/updated item
                self._populate_rows()

                # Clear inputs for faster next entry, keep category
                try:
                    self._add_jy.clear()
                    self._add_mn.clear()
                    self._add_hz.clear()
                    self._add_jy.setFocus()
                except Exception:
                    pass

            def _write_categories(self, cats: dict):
                # persist to YAML
                try:
                    with open("categories.yaml", "w", encoding="utf-8") as fh:
                        yaml.safe_dump(cats, fh, allow_unicode=True, sort_keys=True)
                    logger.debug("categories.yaml saved (%d categories) [autosave]", len(cats))
                except Exception as e:
                    logger.warning("Failed to save categories.yaml: %s", e)
                # update parent UI combobox without changing selection
                try:
                    self._cats = cats
                    if hasattr(self._parent, "findChild"):
                        combo = self._parent.findChild(QComboBox, "comboCategory")
                        if combo is not None:
                            current = combo.currentText()
                            combo.blockSignals(True)
                            combo.clear()
                            combo.addItem("All")
                            for k in sorted(cats.keys()):
                                combo.addItem(k)
                            idx = combo.findText(current)
                            combo.setCurrentIndex(idx if idx >= 0 else 0)
                            combo.blockSignals(False)
                except Exception as e:
                    logger.debug("UI update after autosave failed: %s", e)

            def _do_autosave(self):
                if self._saving_now:
                    return
                self._save_pending = False
                self._saving_now = True
                try:
                    cats = self._aggregate_categories()
                    self._write_categories(cats)
                finally:
                    self._saving_now = False

            def _do_live_resort(self):
                """Run the deferred live re-sort safely (debounced)."""
                if self._resort_in_progress:
                    return
                self._resort_pending = False
                self._resort_in_progress = True
                try:
                    saved = self._save_table_viewport()
                    self._resort_rows_live(saved_state=saved)
                    pending = self._pending_select_next_unassigned_after
                    self._pending_select_next_unassigned_after = None
                    if pending:
                        QTimer.singleShot(0, lambda p=pending: self._select_next_unassigned_from(p))
                finally:
                    self._resort_in_progress = False

            def _get_combo_by_hanzi(self, hanzi_key):
                for idx, roww in enumerate(getattr(self, "_row_widgets", []) or []):
                    if roww.get("hanzi") == hanzi_key:
                        return roww.get("combo"), idx
                return None, -1

            def _is_combo_unassigned(self, combo):
                try:
                    sel = combo.selected() if combo else []
                except Exception:
                    sel = []
                if not sel:
                    return True
                if len(sel) == 1 and str(sel[0]).lower() == "unassigned":
                    return True
                return False

            def _on_edit_started(self, row, hanzi_key, combo):
                # Focus/anchor current row and record if it was unassigned at the start of edit
                try:
                    self._anchor_hanzi = hanzi_key
                    self._table.setCurrentCell(row, 0)
                    self._table.selectRow(row)
                    it = self._table.item(row, 0)
                    if it is not None:
                        from PySide6.QtWidgets import QAbstractItemView
                        self._table.scrollToItem(it, QAbstractItemView.PositionAtCenter)
                except Exception:
                    pass
                try:
                    self._row_was_unassigned[hanzi_key] = self._is_combo_unassigned(combo)
                except Exception:
                    self._row_was_unassigned[hanzi_key] = False

            def _select_next_unassigned_from(self, hanzi_key):
                # Find current row index of hanzi_key
                _, start_idx = self._get_combo_by_hanzi(hanzi_key)
                if start_idx < 0:
                    return
                n = self._table.rowCount()
                if n <= 1:
                    return
                # Search forward, wrapping, for the next unassigned row
                for offs in range(1, n + 1):
                    r = (start_idx + offs) % n
                    combo = self._table.cellWidget(r, 3)
                    if self._is_combo_unassigned(combo):
                        try:
                            self._anchor_hanzi = self._table.item(r, 0).text()
                            self._table.setCurrentCell(r, 0)
                            self._table.selectRow(r)
                            from PySide6.QtWidgets import QAbstractItemView
                            self._table.scrollToItem(self._table.item(r, 0), QAbstractItemView.PositionAtCenter)
                        except Exception:
                            pass
                        return

            def _build_live_cat_index(self):
                """Build a hanzi -> set(categories) from the current combo selections."""
                idx = {}
                for roww in getattr(self, "_row_widgets", []) or []:
                    h = roww.get("hanzi")
                    combo = roww.get("combo")
                    if not h or combo is None:
                        continue
                    for c in combo.selected():
                        idx.setdefault(h, set()).add(c)
                return idx

            def _resort_rows_live(self, saved_state=None):
                """Resort table using live combo selections; keep selection and scroll."""
                table = self._table
                # Freeze UI and block signals during rebuild
                try:
                    table.setUpdatesEnabled(False)
                    table.blockSignals(True)
                except Exception:
                    pass
                try:
                    if saved_state is None:
                        saved_state = self._save_table_viewport()

                    live_index = self._build_live_cat_index()

                    # Build sortable list from current vocab + live assigned cats
                    sortable = []
                    for hanzi, val in self._vocab.items():
                        meanings = val[0] if isinstance(val, list) and len(val) > 0 else []
                        jyut = val[1] if isinstance(val, list) and len(val) > 1 else ""
                        assigned = sorted(list(live_index.get(hanzi, set())))
                        first_cat = (assigned[0] if assigned else "unassigned")
                        meaning_key = "; ".join(meanings)
                        sortable.append(
                            ((first_cat.lower(), meaning_key.lower(), hanzi), hanzi, meanings, jyut, assigned))
                    sortable.sort(key=lambda t: t[0])

                    # Rebuild table rows
                    self._table.setRowCount(len(sortable))
                    new_rows = []
                    for row, (_key, hanzi, meanings, jyut, assigned) in enumerate(sortable):
                        it_h = QTableWidgetItem(hanzi)
                        it_j = QTableWidgetItem(jyut)
                        it_j.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        it_j.setToolTip(jyut)
                        it_m = QTableWidgetItem("; ".join(meanings))
                        it_h.setFlags(it_h.flags() & ~Qt.ItemIsEditable)
                        it_j.setFlags(it_j.flags() & ~Qt.ItemIsEditable)
                        it_m.setFlags(it_m.flags() & ~Qt.ItemIsEditable)
                        self._table.setItem(row, 0, it_h)
                        self._table.setItem(row, 1, it_j)
                        self._table.setItem(row, 2, it_m)

                        combo = MultiCategoryCombo(self._all_cats, self._table, initial_selected=set(assigned))
                        self._table.setCellWidget(row, 3, combo)

                        combo.editingStarted.connect(partial(self._on_edit_started, row, hanzi, combo))
                        try:
                            combo.model().dataChanged.connect(
                                lambda *args, row=row, hanzi=hanzi: self._on_combo_changed(row, hanzi))
                            combo.editingFinished.connect(partial(self._on_combo_changed, row, hanzi))
                        except Exception:
                            pass

                        new_rows.append({
                            "hanzi": hanzi,
                            "combo": combo,
                            "jyut": jyut,
                            "meanings": meanings,
                        })

                    self._row_widgets = new_rows
                    try:
                        self._table.resizeRowsToContents()
                    except Exception:
                        pass
                finally:
                    # Unfreeze UI and restore signals
                    try:
                        table.blockSignals(False)
                        table.setUpdatesEnabled(True)
                    except Exception:
                        pass
                self._restore_table_viewport(saved_state)

            def _on_combo_changed(self, row, hanzi_key, *args, **kwargs):
                """After a row’s categories change, keep that row selected and re-sort live (debounced).
                If the row was previously unassigned and now assigned, queue selecting the next unassigned row."""
                self._anchor_hanzi = hanzi_key
                try:
                    was_unassigned = bool(self._row_was_unassigned.get(hanzi_key, False))
                    combo, _ = self._get_combo_by_hanzi(hanzi_key)
                    now_unassigned = self._is_combo_unassigned(combo)
                    if was_unassigned and not now_unassigned:
                        # after resort completes, jump to next unassigned row
                        self._pending_select_next_unassigned_after = hanzi_key
                except Exception:
                    pass
                if self._resort_in_progress:
                    return
                if not self._resort_pending:
                    self._resort_pending = True
                    QTimer.singleShot(60, self._do_live_resort)
                # Debounced autosave
                if not self._save_pending:
                    self._save_pending = True
                    QTimer.singleShot(120, self._do_autosave)

            def _populate_rows(self):
                # Build current category index first
                cat_index = self._build_current_cat_index()

                # Build sortable list: first category name (alphabetical; 'unassigned' if none), then meaning text, then Hanzi
                sortable = []
                for hanzi, val in self._vocab.items():
                    meanings = val[0] if isinstance(val, list) and len(val) > 0 else []
                    jyut = val[1] if isinstance(val, list) and len(val) > 1 else ""
                    assigned = sorted(list(cat_index.get(hanzi, [])))
                    first_cat = (assigned[0] if assigned else "unassigned")
                    meaning_key = "; ".join(meanings)
                    sortable.append(((first_cat.lower(), meaning_key.lower(), hanzi), hanzi, meanings, jyut, assigned))

                # Sort alphabetically by (category, meaning, hanzi)
                sortable.sort(key=lambda t: t[0])

                self._table.setRowCount(len(sortable))
                self._row_widgets = []  # list of dicts per row: {"hanzi":..., "combo":MultiCategoryCombo}
                for row, (_key, hanzi, meanings, jyut, assigned) in enumerate(sortable):
                    it_h = QTableWidgetItem(hanzi)
                    it_j = QTableWidgetItem(jyut)
                    it_j.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    it_j.setToolTip(jyut)
                    it_m = QTableWidgetItem("; ".join(meanings))
                    # read-only text items
                    it_h.setFlags(it_h.flags() & ~Qt.ItemIsEditable)
                    it_j.setFlags(it_j.flags() & ~Qt.ItemIsEditable)
                    it_m.setFlags(it_m.flags() & ~Qt.ItemIsEditable)
                    self._table.setItem(row, 0, it_h)
                    self._table.setItem(row, 1, it_j)
                    self._table.setItem(row, 2, it_m)

                    combo = MultiCategoryCombo(self._all_cats, self._table, initial_selected=set(assigned))
                    self._table.setCellWidget(row, 3, combo)

                    combo.editingStarted.connect(partial(self._on_edit_started, row, hanzi, combo))
                    try:
                        combo.model().dataChanged.connect(
                            lambda *args, row=row, hanzi=hanzi: self._on_combo_changed(row, hanzi))
                        combo.editingFinished.connect(partial(self._on_combo_changed, row, hanzi))
                    except Exception:
                        pass

                    self._row_widgets.append({
                        "hanzi": hanzi,
                        "combo": combo,
                        "jyut": jyut,
                        "meanings": meanings,
                    })
                try:
                    self._table.resizeRowsToContents()
                except Exception:
                    pass

            def _build_current_cat_index(self):
                idx = {}
                for cat, items in (self._cats or {}).items():
                    for h in items or []:
                        idx.setdefault(h, set()).add(cat)
                return idx

            def _apply_filter(self, text: str):
                t = (text or "").strip().lower()
                for row, roww in enumerate(self._row_widgets):
                    h = roww["hanzi"].lower()
                    j = (roww.get("jyut") or "").lower()
                    m = "; ".join(roww.get("meanings") or []).lower()
                    show = (t in h) or (t in j) or (t in m)
                    if t:
                        self._table.setRowHidden(row, not show)
                    else:
                        self._table.setRowHidden(row, False)

            def _rebuild_category_widgets_column(self):
                saved = self._save_table_viewport()
                table = self._table
                try:
                    table.setUpdatesEnabled(False)
                    table.blockSignals(True)
                except Exception:
                    pass
                cat_index = self._build_current_cat_index()
                for row, roww in enumerate(self._row_widgets):
                    assigned = set(cat_index.get(roww["hanzi"], []))
                    combo = MultiCategoryCombo(self._all_cats, self._table, initial_selected=assigned)
                    self._table.setCellWidget(row, 3, combo)
                    roww["combo"] = combo

                    combo.editingStarted.connect(partial(self._on_edit_started, row, roww["hanzi"], combo))
                    try:
                        combo.model().dataChanged.connect(
                            lambda *args, row=row, h=roww["hanzi"]: self._on_combo_changed(row, h))
                        combo.editingFinished.connect(partial(self._on_combo_changed, row, roww["hanzi"]))
                    except Exception:
                        pass
                try:
                    table.blockSignals(False)
                    table.setUpdatesEnabled(True)
                except Exception:
                    pass
                self._restore_table_viewport(saved)

            def _on_save(self):
                cats = self._aggregate_categories()
                self._write_categories(cats)
                self._cats = cats
                self.accept()

            def result_categories(self) -> dict:
                return self._cats


        def _load_add_item_dialog(parent):
            # Resolve absolute path relative to this file, not the working directory
            base_dir = os.path.dirname(os.path.abspath(__file__))
            ui_path = os.path.join(base_dir, "ui", "add_item.ui")

            if not os.path.exists(ui_path):
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(parent, "Add Item", "UI not found at:\n{}".format(ui_path))
                return None

            file = QFile(ui_path)
            if not file.open(QFile.ReadOnly):
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(parent, "Add Item", "Unable to open UI file:\n{}".format(ui_path))
                return None

            try:
                loader = QUiLoader()
                dlg = loader.load(file, parent)
                return dlg
            finally:
                file.close()


        def _open_category_manager(focus_add=False):
            vocab_dict = {h: v for (h, v) in window._vocab_items} if getattr(window, "_vocab_items", None) else dict(
                vocab)
            dlg = CategoryManagerDialog(window, vocab_dict, window._categories_map)
            if focus_add:
                try:
                    dlg._add_jy.setFocus()
                except Exception:
                    pass
            if dlg.exec() == QDialog.Accepted:
                new_cats = dlg.result_categories()
                # write to categories.yaml
                try:
                    with open("categories.yaml", "w", encoding="utf-8") as fh:
                        yaml.safe_dump(new_cats, fh, allow_unicode=True, sort_keys=True)
                    logger.debug("categories.yaml saved (%d categories)", len(new_cats))
                except Exception as e:
                    logger.warning("Failed to save categories.yaml: %s", e)
                    return
                # update runtime state and UI combobox
                window._categories_map = new_cats
                combo = window.findChild(QComboBox, "comboCategory")
                if combo is not None:
                    try:
                        current = combo.currentText()
                        combo.blockSignals(True)
                        combo.clear()
                        combo.addItem("All")
                        for k in sorted(new_cats.keys()):
                            combo.addItem(k)
                        # try to restore previous selection if still present
                        idx = combo.findText(current)
                        combo.setCurrentIndex(idx if idx >= 0 else 0)
                    finally:
                        combo.blockSignals(False)
                # re-apply filter to reflect any changes
                sel = combo.currentText() if combo is not None else "All"
                _apply_category_filter(sel)


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

        if btn_add is not None:
            try:
                btn_add.clicked.disconnect()
            except Exception:
                pass
            if DEBUG_ADD_ITEM_UI:
                btn_add.clicked.connect(debug_open_add_item_dialog)
                QTimer.singleShot(300, debug_open_add_item_dialog)  # was for tree dump; remove when False
            else:
                btn_add.clicked.connect(lambda: _open_category_manager(focus_add=True))


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
                proc_say.setProcessChannelMode(QProcess.MergedChannels)
                proc_say.start()
                if not proc_say.waitForFinished(10000):
                    logger.warning("say did not finish in time")
                else:
                    logger.debug("say finished code=%s status=%s", proc_say.exitCode(), proc_say.exitStatus())
                # play it
                proc_play = QProcess(window)
                proc_play.setProgram(afplay)
                proc_play.setArguments([tmp_path])
                proc_play.setProcessChannelMode(QProcess.MergedChannels)
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
                proc_say.setProcessChannelMode(QProcess.MergedChannels)

                def _after_synth(code, status):
                    logger.debug("say finished code=%s status=%s", code, status)
                    # Now play it
                    proc_play = QProcess(window)
                    proc_play.setProgram(afplay)
                    proc_play.setArguments([tmp_path])
                    proc_play.setProcessChannelMode(QProcess.MergedChannels)

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
            _update_buttons()  # disable all buttons

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
                        _update_buttons()
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
        _show_current()


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


        # Apply bounds (min, max, step) from a single source of truth
        b = bounds()
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
                _apply_category_filter("All")


        if btn_reset is not None:
            btn_reset.clicked.connect(_do_reset)
        # ---- end wiring ----
        # The initial size (720x1280) is set in form.ui geometry. Just show it.
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print("Error: {}".format(e))

        # --- UI-loaded CategoryManagerDialog version ---
        # If you have a UI-loaded CategoryManagerDialog elsewhere (not shown in this code),
        # you would do similar selection behavior and row focus logic:
        # After self._table.setSortingEnabled(False), add:
        # from PySide6.QtWidgets import QAbstractItemView
        # self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        # self._table.setStyleSheet(self._table.styleSheet() + "\nQTableView::item:selected{background: palette(highlight); color: palette(highlighted-text);} ")
        # In _populate_rows, after setting the combo as cell widget, add:
        #   def _focus_row():
        #       try:
        #           self._table.setCurrentCell(row, 0)
        #           self._table.selectRow(row)
        #           it = self._table.item(row, 0)
        #           if it is not None:
        #               from PySide6.QtWidgets import QAbstractItemView
        #               self._table.scrollToItem(it, QAbstractItemView.PositionAtCenter)
        #       except Exception:
        #           pass
        #   combo.editingStarted.connect(_focus_row)
        #   try:
        #       combo.model().dataChanged.connect(lambda *_: _focus_row())
        #   except Exception:
        #       pass
