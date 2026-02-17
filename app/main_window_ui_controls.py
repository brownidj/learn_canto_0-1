from __future__ import annotations

from PySide6.QtWidgets import QLabel, QComboBox, QPushButton, QGroupBox, QWidget, QVBoxLayout

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

    lbl_voice = QLabel("macOS voice:")
    combo_voice = QComboBox()
    combo_voice.setObjectName("comboVoice")
    for name, locale, desc in tts_service.available_voices:
        combo_voice.addItem(name)
    if tts_service.default_voice:
        idx = combo_voice.findText(tts_service.default_voice)
        if idx >= 0:
            combo_voice.setCurrentIndex(idx)
    row_w = QGroupBox()
    row_w.setFlat(True)
    row_w.setTitle("")
    from PySide6.QtWidgets import QHBoxLayout
    row_w.setLayout(QHBoxLayout())
    row_w.layout().addWidget(lbl_voice)
    row_w.layout().addWidget(combo_voice)
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

    def _get_current_voice():
        combo = container.findChild(QComboBox, "comboVoice")
        if combo is not None and combo.currentText().strip():
            return combo.currentText().strip()
        return tts_service.default_voice

    def _tts_call(text, rate=None):
        voice = _get_current_voice()
        tts_service.play_once(text, voice=voice, rate=rate)
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
