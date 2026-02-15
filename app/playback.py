"""Playback helpers for main window."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox


def build_playback(window, controller, tts_service, sliders):
    slider_wpm = sliders.get("wpm")
    slider_repeats = sliders.get("repeats")
    slider_intro = sliders.get("intro")
    slider_repeat = sliders.get("repeat")
    slider_extro = sliders.get("extro")

    def _get_current_voice():
        combo = window.findChild(QComboBox, "comboVoice")
        if combo is not None and combo.currentText().strip():
            return combo.currentText().strip()
        return tts_service.default_voice

    def _play_once(on_finished=None):
        idx = window._vocab_index
        if idx < 0 or not window._vocab_items:
            if callable(on_finished):
                QTimer.singleShot(0, on_finished)
            return
        hanzi, _val = window._vocab_items[idx]
        text = hanzi
        rate = int(slider_wpm.value()) if slider_wpm is not None else None
        voice = _get_current_voice()
        tts_service.play_once(text, voice=voice, rate=rate, on_finished=on_finished)

    def _play_sequence(on_done=None):
        repeats = int(slider_repeats.value()) if slider_repeats is not None else 1
        intro = int(slider_intro.value()) if slider_intro is not None else 0
        gap = int(slider_repeat.value()) if slider_repeat is not None else 0
        extro = int(slider_extro.value()) if slider_extro is not None else 0

        if window._is_playing:
            return
        idx = window._vocab_index
        if idx < 0 or not window._vocab_items:
            if callable(on_done):
                QTimer.singleShot(0, on_done)
            return
        hanzi, _val = window._vocab_items[idx]
        text = hanzi
        rate = int(slider_wpm.value()) if slider_wpm is not None else None
        voice = _get_current_voice()

        window._is_playing = True
        controller.update_buttons()

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
            on_done=_sequence_done,
        )

    return _play_once, _play_sequence
