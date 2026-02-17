"""Main window wiring and application run loop."""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, cast

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QGroupBox, QLineEdit, QTextEdit, QProxyStyle, QStyle, QComboBox, QStyleFactory
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, Qt, QObject, QEvent
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtGui import QColor, QPen, QFont, QPixmap
from PySide6.QtWidgets import QStyledItemDelegate

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
    _apply_victoria_harbour_theme(app)
    combo_arrow_style = _create_combo_arrow_text_style(app)

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
        window._tts_service = tts_service
        ensure_char_map(window)
        ensure_reverse_index(window)
        reverse_lookup = build_reverse_lookup(window)
        attach_candidate_provider(window, reverse_lookup)
        setup_disclosures(window)
        setup_tones_radicals(window)
        group_about = window.findChild(QGroupBox, "groupAbout")

        def _open_category_manager(focus_add: bool = False):
            nonlocal categories_map
            categories_map = open_category_manager(
                window=window,
                vocab=vocab,
                categories_map=categories_map,
                controller=controller,
                focus_add=focus_add,
            )

        setup_audio_test(window, tts_service, slider_wpm)
        _apply_combo_arrow_style_to_window(window, combo_arrow_style)
        _install_combo_arrow_glyphs(window)
        _install_combo_selection_highlight(window)
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


def _apply_victoria_harbour_theme(app: QApplication) -> None:
    app.setStyleSheet(
        """
        QWidget {
            background: #E6E8EA;
            color: #0C1B33;
        }
        QMainWindow, QDialog {
            background: #E6E8EA;
        }
        QDockWidget, QWidget#dockContents {
            background: #D7DADF;
        }
        QGroupBox {
            background: #FFFFFF;
            border: 1px solid #4A5568;
            border-radius: 8px;
            margin-top: 10px;
        }
        QWidget#toneImageRow {
            background: #FFFFFF;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
            color: #0C1B33;
        }
        QLabel {
            color: #0C1B33;
        }
        QLineEdit, QTextEdit {
            background: #FFFFFF;
            color: #0C1B33;
            border: 1px solid #4A5568;
            border-radius: 6px;
            padding: 6px 8px;
            selection-background-color: #2C7A7B;
            selection-color: #E6E8EA;
        }
        QLineEdit:read-only, QTextEdit:read-only {
            background: #F3F4F6;
            color: #4A5568;
        }
        QComboBox {
            background: #FFFFFF;
            color: #0C1B33;
            border: 1px solid #4A5568;
            border-radius: 6px;
            padding: 4px 28px 4px 8px;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left: 1px solid #4A5568;
            background: #E6E8EA;
        }
        QComboBox QAbstractItemView {
            background: #FFFFFF;
            color: #0C1B33;
            selection-background-color: #2C7A7B;
            selection-color: #E6E8EA;
        }
        QComboBox QAbstractItemView::item:selected,
        QComboBox QAbstractItemView::item:selected:active,
        QComboBox QAbstractItemView::item:selected:!active {
            background: #2C7A7B;
            color: #E6E8EA;
        }
        QComboBox QAbstractItemView::item:hover {
            background: #D7DADF;
        }
        QPushButton {
            background: #246;
            color: #E6E8EA;
            border: 1px solid #2c7;
            border-radius: 6px;
            padding: 6px 12px;
        }
        QPushButton:hover {
            background: #2c7;
        }
        QPushButton:pressed {
            background: #1F5A5A;
        }
        QPushButton:disabled {
            background: #9AA6B2;
            color: #E6E8EA;
            border-color: #9AA6B2;
        }
        QToolButton {
            background: #2C7A7B;
            color: #E6E8EA;
            border: 1px solid #246B6B;
            border-radius: 6px;
            padding: 4px 8px;
        }
        QToolButton:hover {
            background: #246B6B;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #9AA6B2;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            width: 18px;
            margin: -6px 0;
            background: #FF6B6B;
            border: 1px solid #C85757;
            border-radius: 9px;
        }
        QScrollBar:vertical {
            background: #E6E8EA;
            width: 12px;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #4A5568;
            border-radius: 6px;
            min-height: 24px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        """
    )


def _create_combo_arrow_text_style(app: QApplication) -> QProxyStyle:
    class ComboArrowTextStyle(QProxyStyle):
        def drawComplexControl(self, control, option, painter, widget=None):
            super().drawComplexControl(control, option, painter, widget)
            if control == QStyle.ComplexControl.CC_ComboBox and isinstance(widget, QComboBox):
                arrow_rect = self.subControlRect(
                    QStyle.ComplexControl.CC_ComboBox,
                    option,
                    QStyle.SubControl.SC_ComboBoxArrow,
                    widget,
                )
                painter.save()
                painter.setPen(QPen(QColor("#0C1B33")))
                painter.drawText(arrow_rect, Qt.AlignmentFlag.AlignCenter, "▼")
                painter.restore()

        def drawPrimitive(self, element, option, painter, widget=None):
            if element == QStyle.PrimitiveElement.PE_IndicatorArrowDown and isinstance(widget, QComboBox):
                painter.save()
                painter.setPen(QPen(QColor("#0C1B33")))
                painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, "▾")
                painter.restore()
                return
            super().drawPrimitive(element, option, painter, widget)

    base = QStyleFactory.create("Fusion") or app.style()
    return ComboArrowTextStyle(base)


def _apply_combo_arrow_style_to_window(window, combo_style: QProxyStyle) -> None:
    try:
        combos = window.findChildren(QComboBox)
    except Exception:
        combos = []
    for combo in combos:
        try:
            combo.setStyle(combo_style)
        except Exception:
            pass


def _install_combo_arrow_glyphs(window) -> None:
    class ComboArrowOverlay(QObject):
        def __init__(self, combo: QComboBox):
            super().__init__(combo)
            self.combo = combo
            self.label = QLabel("▼", combo)
            self.label.setObjectName("comboArrowGlyph")
            self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.label.setStyleSheet("color: #0C1B33; background: transparent;")
            self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._reposition()

        def _reposition(self):
            rect = self.combo.rect()
            glyph_w = 18
            x = max(0, rect.width() - glyph_w - 6)
            self.label.setGeometry(x, 0, glyph_w, rect.height())

        def eventFilter(self, obj, event):
            if obj is self.combo and event.type() in (
                QEvent.Type.Resize,
                QEvent.Type.Move,
                QEvent.Type.StyleChange,
                QEvent.Type.FontChange,
            ):
                self._reposition()
            return False

    overlays = []
    try:
        combos = window.findChildren(QComboBox)
    except Exception:
        combos = []
    for combo in combos:
        if combo.findChild(QLabel, "comboArrowGlyph") is not None:
            continue
        overlay = ComboArrowOverlay(combo)
        combo.installEventFilter(overlay)
        overlays.append(overlay)
    window._combo_arrow_overlays = overlays


def _install_combo_selection_highlight(window) -> None:
    class ComboPopupSelector(QObject):
        def __init__(self, combo: QComboBox):
            super().__init__(combo)
            self.combo = combo
            self.view = combo.view()
            if self.view is not None:
                try:
                    self.view.setSelectionMode(self.view.SelectionMode.SingleSelection)
                    self.view.setSelectionBehavior(self.view.SelectionBehavior.SelectRows)
                except Exception:
                    pass
                try:
                    self.view.setItemDelegate(_ComboBoldDelegate(self.combo))
                except Exception:
                    pass

        def eventFilter(self, obj, event):
            if obj is self.view and event.type() == QEvent.Type.Show:
                self._sync_selection()
            return False

        def _sync_selection(self):
            try:
                model = self.combo.model()
                idx = model.index(self.combo.currentIndex(), self.combo.modelColumn())
                sel = self.view.selectionModel()
                if idx.isValid() and sel is not None:
                    try:
                        self.view.setCurrentIndex(idx)
                    except Exception:
                        pass
                    sel.select(idx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
                    try:
                        self.view.scrollTo(idx)
                    except Exception:
                        pass
            except Exception:
                pass

    selectors = []
    try:
        combos = window.findChildren(QComboBox)
    except Exception:
        combos = []
    for combo in combos:
        try:
            view = combo.view()
        except Exception:
            view = None
        if view is None:
            continue
        selector = ComboPopupSelector(combo)
        view.installEventFilter(selector)
        selectors.append(selector)
    window._combo_popup_selectors = selectors




class _ComboBoldDelegate(QStyledItemDelegate):
    def __init__(self, combo: QComboBox):
        super().__init__(combo)
        self.combo = combo

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        try:
            if index.isValid() and index.row() == self.combo.currentIndex():
                font = QFont(option.font)
                font.setBold(True)
                option.font = font
        except Exception:
            pass
