from __future__ import annotations

from PySide6.QtWidgets import QToolButton, QGroupBox, QPushButton, QComboBox

from app.main_window_widgets import resolve_main_window_widgets


def find_add_button(adapter):
    btn_add = resolve_main_window_widgets(adapter).get("btn_add")
    if btn_add is not None:
        return btn_add
    for btn in adapter.find_children(QPushButton):
        try:
            if btn.text().strip().lower() == "add":
                return btn
        except Exception:
            continue
    return None


def find_tones_radicals_toggle(adapter):
    widgets = resolve_main_window_widgets(adapter)
    return widgets.get("btn_tones_radicals_toggle_btn") or widgets.get("btn_tones_radicals_toggle_alt")


def find_group_delays(adapter):
    return resolve_main_window_widgets(adapter).get("group_delays")


def find_group_about(adapter):
    return resolve_main_window_widgets(adapter).get("group_about")


def find_delays_disclosure(adapter):
    return resolve_main_window_widgets(adapter).get("btn_delays_disclosure")


def find_about_disclosure(adapter):
    return resolve_main_window_widgets(adapter).get("btn_about_disclosure")


def find_group_sound_tone_mastery(adapter):
    return resolve_main_window_widgets(adapter).get("group_sound_tone_mastery")


def find_group_radicals(adapter):
    return resolve_main_window_widgets(adapter).get("group_radicals")


def find_combo_category(adapter):
    return resolve_main_window_widgets(adapter).get("combo_category")
