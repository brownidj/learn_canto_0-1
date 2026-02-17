"""
Main window UI setup and widget wiring.

This module handles all the UI plumbing for the main window, including:
- Finding and configuring widgets
- Setting up font auto-sizing for Hanzi labels
- Wiring sliders, buttons, and combos
- Managing layout and sizing
"""
import logging
import re
from typing import Optional, Any, List, Callable

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QLineEdit, QTextEdit,
    QComboBox, QSlider, QGroupBox, QSizePolicy, QVBoxLayout,
    QHBoxLayout, QToolButton, QDockWidget
)
from PySide6.QtCore import Qt, QEvent, QObject
from PySide6.QtGui import QFontMetrics, QAction

from settings import load_all, save_one

logger = logging.getLogger(__name__)


class MainWindowSetup:
    """Handles main window UI setup and widget wiring."""

    def __init__(self, window: QWidget, controller: Any):
        """Initialize setup handler.

        Args:
            window: Main application window
            controller: MainController instance for wiring
        """
        self.window = window
        self.controller = controller

        # Widget references (populated during setup)
        self.label_hanzi: Optional[QLabel] = None
        self.edit_jyut: Optional[QLineEdit] = None
        self.text_meanings: Optional[QTextEdit] = None
        self.slider_wpm: Optional[QSlider] = None
        self.slider_repeats: Optional[QSlider] = None
        self.slider_intro: Optional[QSlider] = None
        self.slider_repeat: Optional[QSlider] = None
        self.slider_extro: Optional[QSlider] = None
        self.slider_auto: Optional[QSlider] = None
        self.btn_play: Optional[QPushButton] = None
        self.btn_next: Optional[QPushButton] = None
        self.btn_prev: Optional[QPushButton] = None
        self.btn_reset: Optional[QPushButton] = None
        self.combo_category: Optional[QComboBox] = None
        self.action_hamburger: Optional[QAction] = None
        self.nav_drawer: Optional[QDockWidget] = None

    def setup_all(self, bounds: dict, categories_map: dict, saved_category: str = "All"):
        """Run all setup steps.

        Args:
            bounds: Settings bounds from settings.bounds()
            categories_map: Category -> hanzi list mapping
            saved_category: Previously saved category selection
        """
        self._find_widgets()
        self._setup_hanzi_label()
        self._setup_buttons()
        self._setup_sliders(bounds)
        self._setup_category_combo(categories_map, saved_category)
        self._setup_nav_drawer()
        self._wire_button_clicks()
        logger.debug("MainWindowSetup complete")

    def _find_widgets(self):
        """Find all widgets by objectName."""
        w = self.window

        # Display widgets
        self.label_hanzi = w.findChild(QLabel, "labelHanzi")
        self.edit_jyut = w.findChild(QLineEdit, "jyutping")
        self.text_meanings = w.findChild(QTextEdit, "textMeanings")

        # Sliders
        self.slider_wpm = w.findChild(QSlider, "sliderWpm")
        self.slider_repeats = w.findChild(QSlider, "sliderRepeats")
        self.slider_intro = w.findChild(QSlider, "sliderIntroDelay")
        self.slider_repeat = w.findChild(QSlider, "sliderRepeatDelay")
        self.slider_extro = w.findChild(QSlider, "sliderExtroDelay")
        self.slider_auto = w.findChild(QSlider, "sliderAutoDelay")

        # Buttons
        self.btn_reset = w.findChild(QPushButton, "btnReset")

        # Category combo
        self.combo_category = w.findChild(QComboBox, "comboCategory")
        self.action_hamburger = w.findChild(QAction, "actionHamburger")
        self.nav_drawer = w.findChild(QDockWidget, "navDrawer")

        logger.debug("Found widgets: hanzi=%s jyut=%s meanings=%s sliders=%d combos=%d",
                    bool(self.label_hanzi), bool(self.edit_jyut), bool(self.text_meanings),
                    sum([bool(s) for s in [self.slider_wpm, self.slider_repeats, 
                         self.slider_intro, self.slider_repeat, self.slider_extro, self.slider_auto]]),
                    bool(self.combo_category))
        logger.debug("Found nav drawer: action=%s drawer=%s",
                    bool(self.action_hamburger), bool(self.nav_drawer))

    def _setup_hanzi_label(self):
        """Configure Hanzi label with auto-sizing font."""
        if self.label_hanzi is None:
            return

        label = self.label_hanzi

        # Configure label behavior
        label.setWordWrap(False)
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        try:
            label.setContentsMargins(0, 0, 0, 0)
        except Exception:
            # Sanitize stylesheet if it had padding
            ss = label.styleSheet() or ""
            if "padding-left" in ss or "padding-right" in ss:
                ss = ss.replace("padding-left:", "/*padding-left:*/")
                ss = ss.replace("padding-right:", "/*padding-right:*/")
            label.setStyleSheet(ss)

        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        logger.debug("labelHanzi sizePolicy set to Ignored/Preferred")

        # Capture base stylesheet
        self.window._hanzi_base_stylesheet = label.styleSheet() or ""
        self.window._hanzi_avail_w0 = None

        # Schedule baseline capture
        def _capture_baseline():
            try:
                w_total = int(label.width())
            except Exception:
                w_total = -1
            try:
                w_contents = int(label.contentsRect().width())
            except Exception:
                w_contents = w_total

            w0 = max(0, w_contents if w_contents is not None else w_total)
            if w0 > 0 and self.window._hanzi_avail_w0 is None:
                self.window._hanzi_avail_w0 = w0
                logger.debug("Hanzi baseline avail_w0 set to %d", w0)

        from ui.qt_timers import call_later
        call_later(_capture_baseline, delay_ms=0)

        # Install resize event filter
        class HanziSizer(QObject):
            def __init__(self, setup_instance):
                super().__init__()
                self.setup = setup_instance

            def eventFilter(self, obj, event):
                if obj is label and event.type() == QEvent.Type.Resize:
                    try:
                        cw = max(0, label.contentsRect().width())
                    except Exception:
                        cw = max(0, label.width())

                    if cw > 0 and isinstance(getattr(self.setup.window, "_hanzi_avail_w0", None), int):
                        if self.setup.window._hanzi_avail_w0 is None or cw < self.setup.window._hanzi_avail_w0:
                            self.setup.window._hanzi_avail_w0 = cw
                            logger.debug("Hanzi baseline reduced to %d due to shrink", cw)

                    # Trigger font update
                    if hasattr(self.setup.window, "_update_hanzi_font_now"):
                        self.setup.window._update_hanzi_font_now()

                return False

        sizer = HanziSizer(self)
        label.installEventFilter(sizer)
        self.window._hanzi_sizer = sizer

    def _setup_buttons(self):
        """Find and attach navigation buttons to controller."""
        # Find buttons using multiple strategies
        self.btn_play = self._find_button(
            ["btnPlay", "btnListen", "playButton", "listenButton", "pushButtonPlay"],
            ["Play", "Listen", "▶", "►"]
        )
        self.btn_next = self._find_button(
            ["btnNext", "nextButton", "pushButtonNext"],
            ["Next", "→", "›"]
        )
        self.btn_prev = self._find_button(
            ["btnPrevious", "btnPrev", "previousButton", "pushButtonPrev"],
            ["Previous", "Prev", "←", "‹"]
        )

        logger.debug("Buttons resolved -> play:%s next:%s prev:%s",
                    bool(self.btn_play), bool(self.btn_next), bool(self.btn_prev))

        # Attach to controller
        self.controller.attach_buttons(
            btn_play=self.btn_play,
            btn_next=self.btn_next,
            btn_prev=self.btn_prev
        )

    def _find_button(self, names: List[str], texts: List[str]) -> Optional[QPushButton]:
        """Find a button by objectName or visible text.

        Args:
            names: List of possible objectNames
            texts: List of possible button texts

        Returns:
            Button widget or None
        """
        # Try by objectName first
        for name in names:
            btn = self.window.findChild(QPushButton, name)
            if btn is not None:
                return btn

        # Fallback: search by visible text
        for btn in self.window.findChildren(QPushButton):
            try:
                btn_text = btn.text().strip().lower()
            except Exception:
                continue
            for text in texts:
                if btn_text == text.lower():
                    return btn

        return None

    def _setup_sliders(self, bounds: dict):
        """Configure slider ranges and load persisted values.

        Args:
            bounds: Settings bounds dict from settings.bounds()
        """
        # Set ranges
        if self.slider_wpm is not None:
            self.slider_wpm.setRange(bounds["wpm"][0], bounds["wpm"][1])
            self.slider_wpm.setSingleStep(bounds["wpm"][2])

        pairs = [
            ("intro_delay", self.slider_intro),
            ("repeat_delay", self.slider_repeat),
            ("extro_delay", self.slider_extro),
            ("auto_delay", self.slider_auto),
            ("repeats", self.slider_repeats),
        ]

        for name, slider in pairs:
            if slider is not None:
                slider.setRange(bounds[name][0], bounds[name][1])
                slider.setSingleStep(bounds[name][2])

        # Load persisted values
        vals = load_all()

        if self.slider_wpm is not None:
            self.slider_wpm.setValue(int(vals["wpm"]))
        if self.slider_intro is not None:
            self.slider_intro.setValue(int(vals["intro_delay"]))
        if self.slider_repeat is not None:
            self.slider_repeat.setValue(int(vals["repeat_delay"]))
        if self.slider_extro is not None:
            self.slider_extro.setValue(int(vals["extro_delay"]))
        if self.slider_auto is not None:
            self.slider_auto.setValue(int(vals["auto_delay"]))
        if self.slider_repeats is not None:
            self.slider_repeats.setValue(int(vals["repeats"]))

        logger.debug("Sliders configured with persisted values")

    def _setup_category_combo(self, categories_map: dict, saved_category: str):
        """Populate and configure category dropdown.

        Args:
            categories_map: Category -> hanzi list mapping
            saved_category: Previously saved category selection
        """
        if self.combo_category is None:
            logger.debug("comboCategory not found")
            return

        combo = self.combo_category

        try:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("All")
            for k in sorted(categories_map.keys()):
                combo.addItem(k)

            # Set saved selection
            idx = combo.findText(saved_category)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        finally:
            combo.blockSignals(False)

        logger.debug("comboCategory populated: %d categories, initial='%s'",
                    len(categories_map), saved_category)

    def _setup_nav_drawer(self):
        """Wire hamburger action to the navigation drawer."""
        if self.action_hamburger is None or self.nav_drawer is None:
            return

        action = self.action_hamburger
        drawer = self.nav_drawer

        try:
            drawer.setMinimumWidth(drawer.sizeHint().width() + 50)
        except Exception:
            pass
        action.setCheckable(True)
        drawer.setVisible(False)
        action.setChecked(False)
        action.toggled.connect(drawer.setVisible)
        drawer.visibilityChanged.connect(action.setChecked)
        logger.debug("Hamburger action wired to nav drawer")

        class _DrawerCloseFilter(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.MouseButtonPress and drawer.isVisible():
                    try:
                        if not drawer.geometry().contains(event.pos()):
                            drawer.setVisible(False)
                    except Exception:
                        pass
                return False

        self.window.installEventFilter(_DrawerCloseFilter(self.window))

    def _wire_button_clicks(self):
        """Connect button click signals to controller actions."""
        if self.btn_play is not None:
            logger.debug("Connecting Play button")
            self.btn_play.clicked.connect(self.controller.on_play_clicked)

        if self.btn_next is not None:
            self.btn_next.clicked.connect(self.controller.next_item)

        if self.btn_prev is not None:
            self.btn_prev.clicked.connect(self.controller.prev_item)

    def wire_category_change(self, callback: Callable[[str], None]):
        """Wire category combo to a callback.

        Args:
            callback: Function to call with selected category name
        """
        if self.combo_category is not None:
            self.combo_category.currentTextChanged.connect(callback)
            logger.debug("comboCategory change wired")

    def wire_slider_changes(self, update_labels_callback: Callable):
        """Wire slider value changes to persist and update labels.

        Args:
            update_labels_callback: Function to call after any slider changes
        """
        if self.slider_wpm is not None:
            self.slider_wpm.valueChanged.connect(
                lambda v: (save_one("wpm", int(v)), update_labels_callback())
            )

        if self.slider_intro is not None:
            self.slider_intro.valueChanged.connect(
                lambda v: (save_one("intro_delay", int(v)), update_labels_callback())
            )

        if self.slider_repeat is not None:
            self.slider_repeat.valueChanged.connect(
                lambda v: (save_one("repeat_delay", int(v)), update_labels_callback())
            )

        if self.slider_extro is not None:
            self.slider_extro.valueChanged.connect(
                lambda v: (save_one("extro_delay", int(v)), update_labels_callback())
            )

        if self.slider_auto is not None:
            self.slider_auto.valueChanged.connect(
                lambda v: (save_one("auto_delay", int(v)), update_labels_callback())
            )

        if self.slider_repeats is not None:
            self.slider_repeats.valueChanged.connect(
                lambda v: (save_one("repeats", int(v)), update_labels_callback())
            )

        logger.debug("Slider changes wired with persistence")

    def wire_reset_button(self, reset_callback: Callable):
        """Wire reset button to a callback.

        Args:
            reset_callback: Function to call when reset is clicked
        """
        if self.btn_reset is not None:
            self.btn_reset.clicked.connect(reset_callback)
            logger.debug("Reset button wired")

    def get_slider_values(self) -> dict:
        """Get current slider values.

        Returns:
            Dict of slider_name -> value
        """
        return {
            "wpm": int(self.slider_wpm.value()) if self.slider_wpm else None,
            "intro": int(self.slider_intro.value()) if self.slider_intro else None,
            "repeat": int(self.slider_repeat.value()) if self.slider_repeat else None,
            "extro": int(self.slider_extro.value()) if self.slider_extro else None,
            "auto": int(self.slider_auto.value()) if self.slider_auto else None,
            "repeats": int(self.slider_repeats.value()) if self.slider_repeats else None,
        }
