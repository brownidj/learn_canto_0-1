"""Main window UI wiring helpers."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QLineEdit, QTextEdit, QToolButton, QGroupBox, QPushButton, QComboBox
from PySide6.QtCore import Qt, QTimer

from ui.hanzi_font_controller import HanziFontController
from ui.disclosure_handlers import setup_delays_disclosure, setup_about_disclosure, setup_tones_radicals_toggle
from ui.label_helpers import update_all_labels
from app.main_window_adapter import MainWindowAdapter
from app.main_window_ui_helpers import (
    find_about_disclosure,
    find_add_button,
    find_combo_category,
    find_delays_disclosure,
    find_group_about,
    find_group_delays,
    find_group_radicals,
    find_group_sound_tone_mastery,
    find_tones_radicals_toggle,
)
from app.main_window_ui_controls import setup_labels_and_reset as _setup_labels_and_reset
from app.main_window_ui_controls import setup_tortoise_and_auto as _setup_tortoise_and_auto
from app.main_window_ui_controls import setup_audio_test as _setup_audio_test


def _adapter(window_or_adapter) -> MainWindowAdapter:
    if isinstance(window_or_adapter, MainWindowAdapter):
        return window_or_adapter
    return MainWindowAdapter(window_or_adapter)


def setup_label_hanzi(window, label_hanzi: QLabel, edit_jyut: QLineEdit | None) -> None:
    if label_hanzi is None:
        return
    dlg = _adapter(window)
    label_hanzi.setWordWrap(False)
    label_hanzi.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
    try:
        label_hanzi.setContentsMargins(0, 0, 0, 0)
    except Exception:
        ss = label_hanzi.styleSheet() or ""
        if "padding-left" in ss or "padding-right" in ss:
            ss = ss.replace("padding-left:", "/*padding-left:*/")
            ss = ss.replace("padding-right:", "/*padding-right:*/")
        label_hanzi.setStyleSheet(ss)
    from PySide6.QtWidgets import QSizePolicy
    label_hanzi.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    hanzi_font_ctrl = HanziFontController(label_hanzi, dlg.window)
    QTimer.singleShot(0, hanzi_font_ctrl.capture_baseline)
    dlg.set("_update_hanzi_font_now", lambda: hanzi_font_ctrl.update_font_now(
        jyut_text=edit_jyut.text() if edit_jyut is not None else ""
    ))


def wire_category_change(ui_setup, window, controller, save_one):
    dlg = _adapter(window)
    def _on_category_changed(name):
        save_one("category", name)
        try:
            dlg.set("_tts_armed", False)
            dlg.set("_auto_mode", False)
            if ui_setup.btn_play is not None:
                ui_setup.btn_play.setText("Play")
        except Exception:
            pass
        try:
            btn_auto = window.findChild(QPushButton, "btnAuto")
            if btn_auto is not None:
                btn_auto.setChecked(False)
            btn_tortoise = window.findChild(QPushButton, "btnTortoise")
            if btn_tortoise is not None:
                btn_tortoise.setChecked(False)
        except Exception:
            pass
        controller.update_buttons()
        controller.apply_category_filter(name)
    ui_setup.wire_category_change(_on_category_changed)


def apply_initial_category(ui_setup, controller, categories_map, saved_category: str):
    if ui_setup.combo_category is not None:
        controller.apply_category_filter(ui_setup.combo_category.currentText())
    else:
        controller.apply_category_filter(
            saved_category if saved_category in categories_map or saved_category == "All" else "All")


def setup_tortoise_and_auto(window, controller, slider_wpm, btn_tortoise, btn_auto, bounds_data, save_one):
    dlg = _adapter(window)
    _setup_tortoise_and_auto(dlg, controller, slider_wpm, btn_tortoise, btn_auto, bounds_data, save_one)


def setup_disclosures(window):
    dlg = _adapter(window)
    setup_delays_disclosure(
        find_delays_disclosure(dlg),
        find_group_delays(dlg),
    )
    setup_about_disclosure(
        find_about_disclosure(dlg),
        find_group_about(dlg),
    )


def setup_tones_radicals(window):
    dlg = _adapter(window)
    btn_tr = find_tones_radicals_toggle(dlg)
    setup_tones_radicals_toggle(
        btn_tr,
        find_group_sound_tone_mastery(dlg),
        find_group_radicals(dlg),
    )


def setup_audio_test(window, tts_service, slider_wpm):
    dlg = _adapter(window)
    _setup_audio_test(find_about_disclosure(dlg), tts_service, slider_wpm)


def setup_add_button(window, open_category_manager, debug_open_add_item_dialog=None):
    dlg = _adapter(window)
    btn_add = find_add_button(dlg)

    DEBUG_ADD_ITEM_UI = False

    if btn_add is not None and not getattr(btn_add, "_lc_add_wired", False):
        if DEBUG_ADD_ITEM_UI and debug_open_add_item_dialog is not None:
            btn_add.clicked.connect(lambda: debug_open_add_item_dialog(dlg.window))
            QTimer.singleShot(300, lambda: debug_open_add_item_dialog(dlg.window))
        else:
            btn_add.clicked.connect(lambda: open_category_manager(focus_add=True))
        btn_add._lc_add_wired = True


def setup_labels_and_reset(ui_setup, window, controller, save_one, reset_all):
    dlg = _adapter(window)
    _setup_labels_and_reset(dlg, ui_setup, controller, save_one, reset_all, update_all_labels)
