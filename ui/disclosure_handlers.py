"""
UI disclosure/toggle handlers for collapsible sections.

This module handles the show/hide logic for collapsible UI sections like:
- Delays (advanced settings)
- About section
- Tones and Radicals panels
"""
import logging
from typing import Optional

from PySide6.QtWidgets import QToolButton, QPushButton, QGroupBox, QWidget

logger = logging.getLogger(__name__)


def setup_delays_disclosure(
    btn: Optional[QToolButton],
    group: Optional[QGroupBox]
):
    """Set up delays disclosure toggle.

    Args:
        btn: Disclosure button (toggles visibility)
        group: Group box to show/hide
    """
    if btn is None or group is None:
        return

    def _sync_delays(checked: bool):
        group.setVisible(checked)
        # Swap glyph and label
        btn.setText("▼ Delays" if checked else "▶ Delays (Advanced)")

    btn.toggled.connect(_sync_delays)
    _sync_delays(btn.isChecked())
    logger.debug("Delays disclosure configured")


def setup_about_disclosure(
    btn: Optional[QToolButton],
    group: Optional[QGroupBox]
):
    """Set up about section disclosure toggle.

    Args:
        btn: Disclosure button (toggles visibility)
        group: Group box to show/hide
    """
    if btn is None or group is None:
        return

    def _sync_about(checked: bool):
        group.setVisible(checked)
        btn.setText("▼ About" if checked else "▶ About")

    btn.toggled.connect(_sync_about)
    _sync_about(btn.isChecked())
    logger.debug("About disclosure configured")


def setup_tones_radicals_toggle(
    btn: Optional[QWidget],  # Can be QToolButton or QPushButton
    group_tones: Optional[QGroupBox],
    group_radicals: Optional[QGroupBox]
):
    """Set up tones & radicals toggle.

    Both groups are shown/hidden together.

    Args:
        btn: Toggle button (can be QToolButton or QPushButton)
        group_tones: Tones group box
        group_radicals: Radicals group box
    """
    if btn is None:
        return

    try:
        btn.setCheckable(True)
    except Exception:
        pass

    def _sync_tr(checked: bool):
        vis = bool(checked)
        if group_tones is not None:
            group_tones.setVisible(vis)
        if group_radicals is not None:
            group_radicals.setVisible(vis)

    try:
        btn.toggled.connect(_sync_tr)
        _sync_tr(btn.isChecked())
        logger.debug("Tones & Radicals toggle configured")
    except Exception as e:
        logger.debug("Failed to configure Tones & Radicals toggle: %r", e)
