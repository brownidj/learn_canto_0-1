"""Main window wiring and application run loop."""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, cast

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QGroupBox, QLineEdit, QTextEdit
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice

from app.bootstrap import load_one
from app.debug_ui import debug_open_add_item_dialog
from app.main_window_services import (
    load_vocab_and_categories,
    refresh_categories_map,
    ensure_char_map,
    ensure_reverse_index,
    build_reverse_lookup,
    attach_candidate_provider,
    create_tts_service,
)
from app.main_window_dialogs import open_category_manager
from app.main_window_ui import (
    setup_label_hanzi,
    wire_category_change,
    apply_initial_category,
    setup_tortoise_and_auto,
    setup_disclosures,
    setup_tones_radicals,
    setup_audio_test,
    setup_add_button,
    setup_labels_and_reset,
)
from app.playback import build_playback
from settings import save_one, reset_all, bounds
from ui.main_window_setup import MainWindowSetup
from controllers.main_controller import MainController

logger = logging.getLogger(__name__)


def load_ui(path: str):
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


def run() -> int:
    app = QApplication(sys.argv)

    try:
        window = cast(Any, load_ui("./ui/form.ui"))
        b = bounds()

        label_hanzi = window.findChild(QLabel, "labelHanzi")
        edit_jyut = window.findChild(QLineEdit, "jyutping")
        text_meanings = window.findChild(QTextEdit, "textMeanings")
        setup_label_hanzi(window, label_hanzi, edit_jyut)
        controller = MainController(window, label_hanzi, edit_jyut, text_meanings)

        ui_setup = MainWindowSetup(window, controller)

        window._is_playing = False
        window._tts_armed = False

        vocab, categories_map = load_vocab_and_categories()

        window._vocab = vocab
        window._categories_map = categories_map

        saved_category = load_one("category") or "All"
        ui_setup.setup_all(b, categories_map, saved_category)

        slider_wpm = ui_setup.slider_wpm
        slider_repeats = ui_setup.slider_repeats
        slider_intro = ui_setup.slider_intro
        slider_repeat = ui_setup.slider_repeat
        slider_extro = ui_setup.slider_extro
        slider_auto = ui_setup.slider_auto
        btn_reset = ui_setup.btn_reset

        controller.update_buttons()

        categories_map = refresh_categories_map(window, categories_map)
        wire_category_change(ui_setup, window, controller, save_one)
        apply_initial_category(ui_setup, controller, categories_map, saved_category)

        btn_tortoise = window.findChild(QPushButton, "btnTortoise")
        btn_auto = window.findChild(QPushButton, "btnAuto")

        setup_tortoise_and_auto(window, controller, slider_wpm, btn_tortoise, btn_auto, b, save_one)
        tts_service = create_tts_service(window)
        ensure_char_map(window)
        ensure_reverse_index(window)
        reverse_lookup = build_reverse_lookup(window)
        attach_candidate_provider(window, reverse_lookup)
        setup_disclosures(window)
        group_about = window.findChild(QGroupBox, "groupAbout")
        setup_tones_radicals(window)

        def _open_category_manager(focus_add: bool = False):
            nonlocal categories_map
            categories_map = open_category_manager(
                window=window,
                vocab=vocab,
                categories_map=categories_map,
                controller=controller,
                focus_add=focus_add,
            )

        setup_audio_test(group_about, tts_service, slider_wpm)
        setup_add_button(window, _open_category_manager, debug_open_add_item_dialog)
        _play_once, _play_sequence = build_playback(
            window,
            controller,
            tts_service,
            {
                "wpm": slider_wpm,
                "repeats": slider_repeats,
                "intro": slider_intro,
                "repeat": slider_repeat,
                "extro": slider_extro,
            },
        )
        try:
            import sys as _sys
            main_mod = _sys.modules.get("__main__")
            if main_mod is not None:
                setattr(main_mod, "_play_once", _play_once)
                setattr(main_mod, "_play_sequence", _play_sequence)
        except Exception:
            pass
        controller.show_current()
        setup_labels_and_reset(ui_setup, window, controller, save_one, reset_all)

        window.show()
        return app.exec()
    except Exception:
        logger.exception("Fatal error in main:")
        return 1
