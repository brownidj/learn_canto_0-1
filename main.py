import sys
import os
import tempfile
import shlex
import yaml


import logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

from PySide6.QtWidgets import (QApplication,
                               QSlider,
                               QPushButton,
                               QLabel, QGroupBox,
                               QToolButton,
                               QTextEdit,
                               QLineEdit,
                               QVBoxLayout,
                               QComboBox,
                               QHBoxLayout,
                               QSizePolicy)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, Qt, QTimer, QProcess, QEvent
from PySide6.QtGui import QFontMetrics

from settings import load_all, save_one, reset_all, bounds
from utils import load_andys_list_yaml


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

        # ---- Vocabulary loading & navigation (YAML + canto-explain fallback) ----
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




        edit_jyut = window.findChild(QLineEdit, "jyutping")   # or window.findChild(QLabel, "editJyutping")
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
        btn_prev = _find_button(["btnPrevious", "btnPrev", "previousButton", "pushButtonPrev"], ["Previous", "Prev", "←", "‹"])
        btn_play = _find_button(["btnPlay", "btnListen", "playButton", "listenButton", "pushButtonPlay"], ["Play", "Listen", "▶", "►"])

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
        ordered_items = list(vocab.items())  # [(hanzi, [[eng...], jyut]), ...]
        # Load categories from categories.yaml (optional)
        try:
            with open("categories.yaml", "r") as _cfh:
                categories_map = yaml.safe_load(_cfh) or {}
        except Exception as e:
            logger.warning("Could not load categories.yaml: %s", e)
            categories_map = {}
        window._categories_map = categories_map
        # Read persisted category (default to 'All' if missing)
        try:
            _saved = load_all()
            saved_category = _saved.get("category", "All")
        except Exception:
            saved_category = "All"

        # Optional: canto-explain fallback for missing jyutping
        def _ensure_jyut(hanzi, jyut):
            if jyut:
                return jyut
            logger.debug("No jyutping in YAML for '%s'; trying canto_explain.jyutping.to_jyutping", hanzi)
            try:
                # Lazy import to avoid hard dependency if wheel not present
                from canto_explain.jyutping import to_jyutping
                # Assume to_jyutping returns a space-separated jyutping string for the phrase
                return to_jyutping(hanzi)
            except Exception as e:
                logger.warning("canto_explain to_jyutping failed for '%s': %s", hanzi, e)
                return jyut  # return as-is (possibly empty)

        # State stored on window so other parts could access if needed
        window._vocab_items = ordered_items
        window._tts_armed = False         # flips True after first Play click

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
            logger.debug("comboCategory wired; initial selection='%s' (saved='%s')", combo_category.currentText(), saved_category)
            # Apply filter using saved/current selection
            _apply_category_filter(combo_category.currentText())
        else:
            # Fallback: combobox not found — still honor saved category if present
            logger.debug("comboCategory not found; applying saved category '%s'", saved_category)
            _apply_category_filter(saved_category if saved_category in categories_map or saved_category == "All" else "All")

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
                btn_auto.setCheckable(True)      # already set in .ui, but harmless
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

        def _tts_call(text, rate=None):
            """Temporarily disable canto-explain TTS; always use system TTS fallback."""
            logger.debug("canto_explain TTS is temporarily disabled; skipping provider calls")
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
            intro   = int(slider_intro.value())   if slider_intro   is not None else 0
            gap     = int(slider_repeat.value())  if slider_repeat  is not None else 0
            extro   = int(slider_extro.value())   if slider_extro   is not None else 0

            logger.debug("Play sequence: repeats=%s intro=%s gap=%s extro=%s", repeats, intro, gap, extro)

            if window._is_playing:
                logger.debug("Play requested while already playing; ignoring")
                return

            window._is_playing = True
            _update_buttons()  # disable all buttons

            total   = max(1, repeats)
            ms_intro = max(0, intro) * 1000
            ms_gap   = max(0, gap)   * 1000
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
