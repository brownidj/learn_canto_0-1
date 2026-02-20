from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QGroupBox, QWidget, QVBoxLayout, QRadioButton, QButtonGroup, QComboBox

def setup_tortoise_and_auto(window_adapter, controller, slider_wpm, btn_tortoise, btn_auto, bounds_data, save_one):
    window_adapter.set("_tortoise_prev_wpm", None)

    def _on_tortoise_toggled(checked: bool):
        if slider_wpm is None:
            return
        wpm_min, _wpm_max, _ = bounds_data["wpm"] if isinstance(bounds_data, dict) and "wpm" in bounds_data else (60, 220, 1)
        if checked:
            try:
                window_adapter.set("_tortoise_prev_wpm", int(slider_wpm.value()))
            except Exception:
                window_adapter.set("_tortoise_prev_wpm", None)
            slider_wpm.setValue(int(wpm_min))
            if callable(save_one):
                save_one("wpm", int(wpm_min))
        else:
            prev = window_adapter.get("_tortoise_prev_wpm")
            if isinstance(prev, int) and prev > 0:
                slider_wpm.setValue(prev)
                if callable(save_one):
                    save_one("wpm", prev)

    window_adapter.set("_auto_mode", False)
    window_adapter.set("_auto_pending", False)

    if btn_tortoise is not None:
        try:
            btn_tortoise.setCheckable(True)
        except Exception:
            pass
        btn_tortoise.toggled.connect(_on_tortoise_toggled)

    if btn_auto is not None:
        btn_auto.toggled.connect(controller.set_auto_mode)


def setup_labels_and_reset(window_adapter, ui_setup, controller, save_one, reset_all, update_labels_fn):
    slider_wpm = ui_setup.slider_wpm
    slider_repeats = ui_setup.slider_repeats
    slider_intro = ui_setup.slider_intro
    slider_repeat = ui_setup.slider_repeat
    slider_extro = ui_setup.slider_extro
    slider_auto = ui_setup.slider_auto

    def _update_labels_wrapper():
        update_labels_fn(
            window_adapter.window,
            slider_wpm,
            slider_repeats,
            slider_intro,
            slider_repeat,
            slider_extro,
            slider_auto,
        )

    _update_labels_wrapper()
    ui_setup.wire_slider_changes(_update_labels_wrapper)

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
        from PySide6.QtWidgets import QComboBox
        combo_category = window_adapter.widget(QComboBox, "comboCategory")
        if combo_category is not None:
            idx = combo_category.findText("All")
            if idx >= 0:
                combo_category.setCurrentIndex(idx)
            save_one("category", "All")
            controller.apply_category_filter("All")

    ui_setup.wire_reset_button(_do_reset)


def setup_audio_test(about_disclosure, tts_service, slider_wpm):
    if about_disclosure is None:
        return

    parent = about_disclosure.parentWidget()
    if parent is None:
        return
    layout = parent.layout()
    if layout is None:
        return

    existing = parent.findChild(QPushButton, "btnAudioTest")
    if existing is not None:
        return

    container = QWidget(parent)
    container.setObjectName("audioTestContainer")
    container_layout = QVBoxLayout(container)
    container_layout.setContentsMargins(0, 0, 0, 0)
    container_layout.setSpacing(6)

    row_w = QGroupBox()
    row_w.setFlat(True)
    row_w.setTitle("")
    from PySide6.QtWidgets import QVBoxLayout as _VBox
    row_w.setLayout(_VBox())

    rb_macos = QRadioButton("macOS (Sinji)")
    rb_macos.setObjectName("radioMacVoice")
    rb_google = QRadioButton("Google (Cantonese)")
    rb_google.setObjectName("radioGoogleVoice")
    group = QButtonGroup(row_w)
    group.addButton(rb_google)
    group.addButton(rb_macos)
    row_w.layout().addWidget(rb_macos)
    row_w.layout().addWidget(rb_google)
    combo_google = QComboBox()
    combo_google.setObjectName("comboGoogleVoice")
    combo_google.setEnabled(False)
    row_w.layout().addWidget(combo_google)
    container_layout.addWidget(row_w)
    btn_audio_test = QPushButton("Audio Test (🔊 你好)")
    btn_audio_test.setObjectName("btnAudioTest")
    container_layout.addWidget(btn_audio_test)

    try:
        insert_at = layout.indexOf(about_disclosure)
    except Exception:
        insert_at = -1
    if insert_at < 0:
        layout.addWidget(container)
    else:
        layout.insertWidget(insert_at, container)

    def _list_google_voices():
        win = about_disclosure.window()
        tts_google = getattr(win, "_tts_google", None)
        voices = []
        if tts_google is not None:
            for name, locale, label in getattr(tts_google, "available_voices", []) or []:
                if locale.startswith("yue"):
                    voices.append((name, label))
        return voices

    def _populate_google_voices():
        voices = _list_google_voices()
        combo_google.blockSignals(True)
        combo_google.clear()
        if voices:
            for name, label in voices:
                combo_google.addItem(label, name)
            combo_google.setEnabled(True)
        else:
            combo_google.addItem("No Cantonese voices found", "")
            combo_google.setEnabled(False)
        combo_google.blockSignals(False)

    def _sync_google_voice_selection():
        win = about_disclosure.window()
        voice = getattr(win, "_google_voice", None)
        if voice:
            idx = combo_google.findData(voice)
            if idx >= 0:
                combo_google.setCurrentIndex(idx)

    def _select_engine():
        win = about_disclosure.window()
        if (getattr(win, "_tts_engine", "google") == "google"
                and getattr(win, "_tts_google", None) is not None
                and _list_google_voices()):
            rb_google.setChecked(True)
        else:
            rb_macos.setChecked(True)

    def _apply_engine():
        win = about_disclosure.window()
        google_ok = rb_google.isChecked() and getattr(win, "_tts_google", None) is not None and _list_google_voices()
        if rb_google.isChecked() and not google_ok:
            rb_macos.setChecked(True)
        if google_ok:
            win._tts_engine = "google"
            win._tts_active = win._tts_google
            if combo_google.currentData():
                win._google_voice = combo_google.currentData()
            else:
                win._google_voice = None
        else:
            win._tts_engine = "macos"
            win._tts_active = win._tts_macos or tts_service
            win._macos_voice = "Sinji"
        combo_google.setEnabled(bool(google_ok))
        try:
            import logging
            logging.getLogger(__name__).debug("TTS engine=%s voice=%s",
                                             win._tts_engine,
                                             win._google_voice if win._tts_engine == "google" else win._macos_voice)
        except Exception:
            pass

    _populate_google_voices()
    _select_engine()
    _sync_google_voice_selection()
    _apply_engine()
    rb_google.toggled.connect(lambda _=None: _apply_engine())
    rb_macos.toggled.connect(lambda _=None: _apply_engine())
    combo_google.currentIndexChanged.connect(lambda _=None: _apply_engine())

    def _tts_call(text, rate=None):
        win = about_disclosure.window()
        active = getattr(win, "_tts_active", tts_service)
        engine = getattr(win, "_tts_engine", "google")
        voice = getattr(win, "_google_voice", None) if engine == "google" else getattr(win, "_macos_voice", "Sinji")
        active.play_once(text, voice=voice, rate=rate)
        return True

    def _fallback_say(text, rate=None):
        _tts_call(text, rate)

    def _audio_test():
        sample = "你好"
        r = int(slider_wpm.value()) if slider_wpm is not None else None
        played = _tts_call(sample, rate=r)
        if not played:
            _fallback_say(sample, r)

    btn_audio_test.clicked.connect(_audio_test)
