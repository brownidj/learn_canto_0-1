from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QComboBox, QGroupBox, QPushButton, QToolButton


@dataclass(frozen=True)
class MainWindowWidgetNames:
    btn_add: str = "btnAdd"
    btn_delays_disclosure: str = "btnDelaysDisclosure"
    btn_about_disclosure: str = "btnAboutDisclosure"
    btn_tones_radicals_toggle: str = "btnTonesAndRadicalsToggle"
    group_delays: str = "groupDelays"
    group_about: str = "groupAbout"
    group_sound_tone_mastery: str = "groupSoundToneMastery"
    group_radicals: str = "groupRadicals"
    combo_category: str = "comboCategory"


def resolve_main_window_widgets(
    adapter,
    names: MainWindowWidgetNames | None = None,
    *,
    cls_map: dict[str, type] | None = None,
) -> dict:
    names = names or MainWindowWidgetNames()
    if cls_map is None:
        from PySide6.QtWidgets import QComboBox, QGroupBox, QPushButton, QToolButton
        cls_map = {
            "QPushButton": QPushButton,
            "QToolButton": QToolButton,
            "QGroupBox": QGroupBox,
            "QComboBox": QComboBox,
        }
    QPushButton = cls_map["QPushButton"]
    QToolButton = cls_map["QToolButton"]
    QGroupBox = cls_map["QGroupBox"]
    QComboBox = cls_map["QComboBox"]
    return {
        "btn_add": adapter.widget(QPushButton, names.btn_add),
        "btn_delays_disclosure": adapter.widget(QToolButton, names.btn_delays_disclosure),
        "btn_about_disclosure": adapter.widget(QToolButton, names.btn_about_disclosure),
        "btn_tones_radicals_toggle_btn": adapter.widget(QToolButton, names.btn_tones_radicals_toggle),
        "btn_tones_radicals_toggle_alt": adapter.widget(QPushButton, names.btn_tones_radicals_toggle),
        "group_delays": adapter.widget(QGroupBox, names.group_delays),
        "group_about": adapter.widget(QGroupBox, names.group_about),
        "group_sound_tone_mastery": adapter.widget(QGroupBox, names.group_sound_tone_mastery),
        "group_radicals": adapter.widget(QGroupBox, names.group_radicals),
        "combo_category": adapter.widget(QComboBox, names.combo_category),
    }
