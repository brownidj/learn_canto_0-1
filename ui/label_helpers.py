"""
Label update helpers for the main window.

This module provides functions for updating label text with
dynamic ranges and current values for sliders and settings.
"""
import logging
from typing import Optional

from PySide6.QtWidgets import QLabel, QGroupBox, QSlider

logger = logging.getLogger(__name__)


def set_delay_label(label: Optional[QLabel], base_text: str, current_val: int):
    """Update a delay label with range and current value.

    Args:
        label: Label widget to update
        base_text: Base label text (e.g. "Intro delay")
        current_val: Current slider value
    """
    if label is not None:
        label.setText("{} (0–10): {}".format(base_text, int(current_val)))


def update_delay_labels(
    slider_intro: Optional[QSlider],
    slider_repeat: Optional[QSlider],
    slider_extro: Optional[QSlider],
    slider_auto: Optional[QSlider],
    lbl_intro: Optional[QLabel],
    lbl_repeat: Optional[QLabel],
    lbl_extro: Optional[QLabel],
    lbl_auto: Optional[QLabel],
):
    """Update all delay labels with current slider values.

    Args:
        slider_intro: Intro delay slider
        slider_repeat: Repeat delay slider
        slider_extro: Extro delay slider
        slider_auto: Auto delay slider
        lbl_intro: Intro delay label
        lbl_repeat: Repeat delay label
        lbl_extro: Extro delay label
        lbl_auto: Auto delay label
    """
    if slider_intro is not None:
        set_delay_label(lbl_intro, "Intro delay", slider_intro.value())
    if slider_repeat is not None:
        set_delay_label(lbl_repeat, "Repeat delay", slider_repeat.value())
    if slider_extro is not None:
        set_delay_label(lbl_extro, "Extro delay", slider_extro.value())
    if slider_auto is not None:
        set_delay_label(lbl_auto, "Auto delay", slider_auto.value())


def update_wpm_label(group: Optional[QGroupBox], slider: Optional[QSlider]):
    """Update WPM group title with range and current value.

    Args:
        group: WPM group box
        slider: WPM slider
    """
    if group is not None and slider is not None:
        group.setTitle("WPM (60–220): {}".format(int(slider.value())))


def update_repeats_label(group: Optional[QGroupBox], slider: Optional[QSlider]):
    """Update Repeats group title with range and current value.

    Args:
        group: Repeats group box
        slider: Repeats slider
    """
    if group is not None and slider is not None:
        group.setTitle("Repeats (1–10): {}".format(int(slider.value())))


def update_all_labels(
    window,
    slider_wpm: Optional[QSlider],
    slider_repeats: Optional[QSlider],
    slider_intro: Optional[QSlider],
    slider_repeat: Optional[QSlider],
    slider_extro: Optional[QSlider],
    slider_auto: Optional[QSlider],
):
    """Update all labels with ranges and current values.

    Args:
        window: Main window (for finding child widgets)
        slider_wpm: WPM slider
        slider_repeats: Repeats slider
        slider_intro: Intro delay slider
        slider_repeat: Repeat delay slider
        slider_extro: Extro delay slider
        slider_auto: Auto delay slider
    """
    # Update WPM group title
    update_wpm_label(window.findChild(QGroupBox, "groupWpm"), slider_wpm)

    # Update delay labels
    update_delay_labels(
        slider_intro,
        slider_repeat,
        slider_extro,
        slider_auto,
        window.findChild(QLabel, "labelIntroDelay"),
        window.findChild(QLabel, "labelRepeatDelay"),
        window.findChild(QLabel, "labelExtroDelay"),
        window.findChild(QLabel, "labelAutoDelay"),
    )

    # Update repeats group title
    update_repeats_label(window.findChild(QGroupBox, "groupRepeats"), slider_repeats)
