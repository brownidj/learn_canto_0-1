"""Combo box arrow overlay for macOS visibility issues."""

from __future__ import annotations

from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtWidgets import QLabel, QComboBox


def install_combo_arrow_overlay(root) -> None:
    class ComboArrowOverlay(QObject):
        def __init__(self, combo: QComboBox):
            super().__init__(combo)
            self.combo = combo
            self.label = QLabel("▼", combo)
            self.label.setObjectName("comboArrowGlyph")
            self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.label.setStyleSheet(
                "color: #0C1B33; background: transparent; font-weight: 700; font-size: 14pt;"
            )
            self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._reposition()
            self.label.raise_()
            self.label.show()

        def _reposition(self):
            rect = self.combo.rect()
            glyph_w = 22
            x = max(0, rect.width() - glyph_w - 6)
            self.label.setGeometry(x, 0, glyph_w, rect.height())
            try:
                font_px = max(9, int(rect.height() * 0.45))
                self.label.setStyleSheet(
                    "color: #0C1B33; background: transparent; font-weight: 700; font-size: {}px;".format(font_px)
                )
            except Exception:
                pass

        def eventFilter(self, obj, event):
            if obj is self.combo and event.type() in (
                QEvent.Type.Resize,
                QEvent.Type.Move,
                QEvent.Type.StyleChange,
                QEvent.Type.FontChange,
                QEvent.Type.Show,
            ):
                self._reposition()
                try:
                    self.label.raise_()
                    self.label.show()
                except Exception:
                    pass
            return False

    overlays = []
    combos = []
    try:
        if isinstance(root, QComboBox):
            combos.append(root)
        combos.extend(root.findChildren(QComboBox))
    except Exception:
        pass
    for combo in combos:
        if combo.findChild(QLabel, "comboArrowGlyph") is not None:
            continue
        overlay = ComboArrowOverlay(combo)
        combo.installEventFilter(overlay)
        overlays.append(overlay)
    try:
        root._combo_arrow_overlays = overlays
    except Exception:
        pass
