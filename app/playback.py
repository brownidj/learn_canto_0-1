"""Playback helpers for main window."""

from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel


def build_playback(window, controller, tts_service, sliders):
    slider_wpm = sliders.get("wpm")
    slider_repeats = sliders.get("repeats")
    slider_intro = sliders.get("intro")
    slider_repeat = sliders.get("repeat")
    slider_extro = sliders.get("extro")

    def _get_current_voice(engine):
        if engine == "google":
            return getattr(window, "_google_voice", None) or getattr(tts_service, "default_voice", None)
        return "Sinji"

    def _play_once(on_finished=None):
        idx = window._vocab_index
        if idx < 0 or not window._vocab_items:
            if callable(on_finished):
                QTimer.singleShot(0, on_finished)
            return
        hanzi, _val = window._vocab_items[idx]
        text = hanzi
        rate = int(slider_wpm.value()) if slider_wpm is not None else None
        engine = getattr(window, "_tts_engine", "google")
        active = getattr(window, "_tts_active", tts_service)
        voice = _get_current_voice(engine)
        active.play_once(text, voice=voice, rate=rate, on_finished=on_finished)

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
        jyut = _val[1] if isinstance(_val, list) and len(_val) > 1 else ""
        text = hanzi
        rate = int(slider_wpm.value()) if slider_wpm is not None else None
        engine = getattr(window, "_tts_engine", "google")
        active = getattr(window, "_tts_active", tts_service)
        voice = _get_current_voice(engine)

        window._is_playing = True
        controller.update_buttons()

        def _sequence_done():
            window._is_playing = False
            controller.update_buttons()
            if callable(on_done):
                on_done()

        def _escape_html(s: str) -> str:
            return (
                s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

        def _set_hanzi_highlight(index: int | None):
            label = window.findChild(QLabel, "labelHanzi")
            if label is None:
                return
            base = getattr(window, "_hanzi_text", "") or hanzi
            chars = [c for c in str(base)]
            if index is None or index < 0 or index >= len(chars):
                label.setText(base)
                return
            parts = []
            for i, ch in enumerate(chars):
                if i == index:
                    parts.append(f"<span style='color:#C53030;'>{_escape_html(ch)}</span>")
                else:
                    parts.append(_escape_html(ch))
            label.setText("".join(parts))

        # clear any prior highlight timers
        for t in getattr(window, "_hanzi_highlight_timers", []):
            try:
                t.stop()
            except Exception:
                pass
        window._hanzi_highlight_timers = []

        chars = [c for c in str(getattr(window, "_hanzi_text", "") or hanzi)]

        def _play_with_timepoints(on_done):
            ssml_parts = ["<speak>"]
            for i, ch in enumerate(chars):
                ssml_parts.append(f"<mark name='s{i}'/>{_escape_html(ch)}")
            ssml_parts.append("</speak>")
            ssml = "".join(ssml_parts)

            audio_bytes, timepoints = active.synthesize_ssml_with_timepoints(
                ssml=ssml, voice=voice, rate=rate
            )
            if not audio_bytes:
                active.play_sequence(
                    text=text,
                    voice=voice,
                    rate=rate,
                    repeats=repeats,
                    intro_delay=intro,
                    repeat_delay=gap,
                    extro_delay=extro,
                    on_done=on_done,
                )
                return

            def _play_once_with_marks(done_cb):
                tmp = tempfile.NamedTemporaryFile(prefix="learncanto_", suffix=".mp3", delete=False)
                tmp_path = tmp.name
                tmp.write(audio_bytes)
                tmp.close()

                for tp_name, tp_time in timepoints:
                    if not tp_name.startswith("s"):
                        continue
                    try:
                        idx = int(tp_name[1:])
                    except Exception:
                        continue
                    timer_on = QTimer(window)
                    timer_on.setSingleShot(True)
                    timer_on.timeout.connect(lambda i=idx: _set_hanzi_highlight(i))
                    timer_on.start(int(tp_time * 1000))
                    window._hanzi_highlight_timers.append(timer_on)

                def _finish():
                    _set_hanzi_highlight(None)
                    if callable(done_cb):
                        done_cb()
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

                active.play_file(tmp_path, on_finished=_finish)

            def _repeat(rep_idx):
                if rep_idx + 1 > repeats:
                    if extro and callable(on_done):
                        QTimer.singleShot(extro * 1000, on_done)
                    elif callable(on_done):
                        on_done()
                    return

                def _after_one():
                    if rep_idx + 1 < repeats:
                        if gap:
                            QTimer.singleShot(gap * 1000, lambda: _repeat(rep_idx + 1))
                        else:
                            _repeat(rep_idx + 1)
                    else:
                        if extro and callable(on_done):
                            QTimer.singleShot(extro * 1000, on_done)
                        elif callable(on_done):
                            on_done()

                _play_once_with_marks(_after_one)

            if intro:
                QTimer.singleShot(intro * 1000, lambda: _repeat(0))
            else:
                _repeat(0)

        if hasattr(active, "synthesize_ssml_with_timepoints"):
            _play_with_timepoints(_sequence_done)
        else:
            active.play_sequence(
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
