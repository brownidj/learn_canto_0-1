"""
Main window controller for vocabulary learning workflow.

The MainController centralizes high-level UI actions like:
- Displaying current vocabulary item
- Filtering by category
- Navigation (next/previous)
- Playback sequencing
- Auto-mode management

This allows core behaviors to be tested without signal/slot coupling.
"""
import logging
from typing import Optional, Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget, QLabel, QLineEdit, QTextEdit, QComboBox, QPushButton

logger = logging.getLogger(__name__)


def _get_window_attr(window: QWidget, name: str, default=None):
    try:
        return window.__dict__.get(name, default)
    except Exception:
        return default


class MainController:
    """Lightweight controller wrapper that centralises high-level UI actions.

    This groups the 'big' behaviours like showing the current item, changing category,
    playing the sequence, and moving next/previous, so they can be exercised in tests
    without going through button click signals.
    """

    def __init__(self, window: QWidget, label_hanzi: Optional[QLabel] = None,
                 edit_jyut: Optional[QLineEdit] = None, text_meanings: Optional[QTextEdit] = None):
        self.window = window
        self.label_hanzi = label_hanzi
        self.edit_jyut = edit_jyut
        self.text_meanings = text_meanings

        # Button references (wired later from __main__)
        self.btn_play: Optional[QPushButton] = None
        self.btn_next: Optional[QPushButton] = None
        self.btn_prev: Optional[QPushButton] = None

    def show_current(self):
        """Show the current vocab item in the UI."""
        window = self.window
        idx = _get_window_attr(window, "_vocab_index", -1)
        items = _get_window_attr(window, "_vocab_items", [])
        if idx < 0 or not items:
            return

        try:
            hanzi, val = items[idx]
        except Exception:
            return

        meanings = val[0] if isinstance(val, list) and len(val) > 0 else []
        jyut = val[1] if isinstance(val, list) and len(val) > 1 else ""
        # Inlined _ensure_jyut behaviour: only use supplied jyut
        jyut = jyut or ""

        logger.debug("Show index=%s hanzi='%s' jyut='%s' meanings=%s", idx, hanzi, jyut, meanings)

        label_hanzi = self.label_hanzi
        edit_jyut = self.edit_jyut
        text_meanings = self.text_meanings

        # Update Hanzi label + font fitting
        if label_hanzi is not None:
            try:
                label_hanzi.setText(hanzi)
                upd = _get_window_attr(window, "_update_hanzi_font_now", None)
                if callable(upd):
                    try:
                        upd()
                        QTimer.singleShot(0, upd)
                    except Exception:
                        pass
            except Exception:
                pass

        # Update Jyutping field
        if edit_jyut is not None:
            try:
                edit_jyut.setText(jyut)
            except AttributeError:
                # Fallback for QLabel vs QLineEdit differences
                try:
                    edit_jyut.setText(jyut)
                except Exception:
                    pass

        # Update meanings text
        if text_meanings is not None and isinstance(text_meanings, QTextEdit):
            try:
                text_meanings.setPlainText(", ".join(meanings))
            except Exception:
                pass

    def apply_category_filter(self, cat_name: str):
        """Filter the vocabulary list by the given category name; 'All' shows everything."""
        window = self.window

        # Guard: ignore category changes during playback
        if _get_window_attr(window, "_is_playing", False):
            logger.debug("Category change requested during playback -> ignored")
            return

        # Get vocab and categories from window or module globals
        try:
            # Try to get from window first
            vocab = _get_window_attr(window, "_vocab", None)
            categories_map = _get_window_attr(window, "_categories_map", None)

            # Fallback to module-level globals if not on window
            if vocab is None or categories_map is None:
                import sys
                main_module = sys.modules.get('__main__')
                if main_module is not None:
                    if vocab is None:
                        vocab = getattr(main_module, 'vocab', {})
                    if categories_map is None:
                        categories_map = getattr(main_module, 'categories_map', {})

            if vocab is None:
                vocab = {}
            if categories_map is None:
                categories_map = {}

        except Exception:
            vocab = {}
            categories_map = {}

        full_items = list(vocab.items())
        if cat_name and cat_name != "All" and cat_name in categories_map:
            hanzi_set = set(categories_map.get(cat_name, []))
            filtered = [item for item in full_items if item[0] in hanzi_set]
        else:
            filtered = full_items

        window._vocab_items = filtered
        window._vocab_index = 0 if filtered else -1
        logger.debug("Category set to %s -> %d items", cat_name, len(filtered))

        # Use the controller's show_current
        self.show_current()

    def next_item(self):
        """Advance to the next vocab item and play it, respecting playback guards."""
        window = self.window

        # Ignore if playing; (buttons are disabled while playing anyway)
        if _get_window_attr(window, "_is_playing", False):
            return
        # If not armed yet, ignore (Next is disabled; this is just a guard)
        if not _get_window_attr(window, "_tts_armed", False):
            return

        items = _get_window_attr(window, "_vocab_items", [])
        if not items:
            return

        try:
            idx = int(_get_window_attr(window, "_vocab_index", 0))
        except Exception:
            idx = 0

        window._vocab_index = (idx + 1) % len(items)
        self.show_current()

        # Delegate to the controller-managed playback entry point
        self.play_sequence()

    def prev_item(self):
        """Move to the previous vocab item and play it, respecting playback guards."""
        window = self.window

        if _get_window_attr(window, "_is_playing", False):
            return
        if not _get_window_attr(window, "_tts_armed", False):
            return

        items = _get_window_attr(window, "_vocab_items", [])
        if not items:
            return

        try:
            idx = int(_get_window_attr(window, "_vocab_index", 0))
        except Exception:
            idx = 0

        window._vocab_index = (idx - 1) % len(items)
        self.show_current()

        self.play_sequence()

    def attach_buttons(self, btn_play: Optional[QPushButton] = None,
                      btn_next: Optional[QPushButton] = None,
                      btn_prev: Optional[QPushButton] = None):
        """Attach navigation and play buttons so controller can manage their state."""
        self.btn_play = btn_play
        self.btn_next = btn_next
        self.btn_prev = btn_prev

    def update_buttons(self):
        """Enable/disable buttons based on playback, arming, and auto-mode state.

        Rules:
          - While _is_playing: everything disabled.
          - Until _tts_armed is True: Next/Prev disabled.
          - While _auto_mode is True: disable Play/Repeat, Next, Previous and the Category combobox.
        """
        window = self.window
        btn_play = self.btn_play
        btn_next = self.btn_next
        btn_prev = self.btn_prev

        auto_on = bool(_get_window_attr(window, "_auto_mode", False))
        if _get_window_attr(window, "_is_playing", False):
            play_enabled = False
            nav_enabled = False
        else:
            play_enabled = True
            nav_enabled = bool(_get_window_attr(window, "_tts_armed", False))

        if auto_on:
            play_enabled = False
            nav_enabled = False

        if btn_play is not None:
            btn_play.setEnabled(play_enabled)
        if btn_next is not None:
            btn_next.setEnabled(nav_enabled)
        if btn_prev is not None:
            btn_prev.setEnabled(nav_enabled)

        # Also manage the category combobox here so it stays disabled in auto mode
        try:
            combo = window.findChild(QComboBox, "comboCategory")
            if combo is not None:
                combo.setEnabled(not auto_on)
        except Exception:
            pass

    def on_play_clicked(self):
        """Handle Play/Repeat button clicks using the controller state."""
        window = self.window
        btn_play = self.btn_play

        # First time: arm and relabel
        if not _get_window_attr(window, "_tts_armed", False):
            window._tts_armed = True
            if btn_play is not None:
                try:
                    btn_play.setText("Repeat")
                except Exception:
                    pass
            # button enable/disable will be managed by playback sequence

        # Delegate to the controller-managed playback entry point
        self.play_sequence()

    def play_sequence(self, on_done: Optional[Any] = None):
        """Entry point for playing the current item sequence.

        This wraps the module-level _play_sequence so tests can call the
        controller directly without going through nested functions.
        """
        # Get _play_sequence from main module
        import sys
        main_module = sys.modules.get('__main__')
        if main_module is None:
            return

        _play_sequence = getattr(main_module, '_play_sequence', None)
        if not callable(_play_sequence):
            return

        try:
            if on_done is not None:
                _play_sequence(on_done=on_done)
            else:
                _play_sequence()
        except TypeError:
            # Fallback for older signature without on_done
            try:
                _play_sequence()
            except Exception:
                pass

    def play_once(self, *args, **kwargs):
        """Thin wrapper around the module-level _play_once for tests.

        Uses *args/**kwargs to avoid coupling to the exact signature.
        """
        # Get _play_once from main module
        import sys
        main_module = sys.modules.get('__main__')
        if main_module is None:
            return

        _play_once = getattr(main_module, '_play_once', None)
        if not callable(_play_once):
            return

        try:
            _play_once(*args, **kwargs)
        except Exception:
            # Do not crash the UI from test-only calls
            pass

    def set_auto_mode(self, on: bool):
        """Turn auto mode on or off and handle the first kick-off when turning on.

        When turning ON:
          - Mark auto mode flag on the window.
          - Ensure TTS is armed and Play label shows 'Repeat'.
          - Start a play sequence whose completion will trigger auto-advance.
        When turning OFF:
          - Just flip the flag; any in-progress playback will finish normally.
        """
        window = self.window
        btn_play = self.btn_play

        window._auto_mode = bool(on)
        logger.debug("Auto mode %s", "ON" if on else "OFF")

        # Recompute enabled states consistently
        self.update_buttons()

        if not on:
            # Nothing more to do; _play_sequence() will clear _is_playing when current run finishes.
            return

        # When turning auto mode ON, ensure TTS is armed and label shows Repeat
        try:
            if not _get_window_attr(window, "_tts_armed", False):
                window._tts_armed = True
                if btn_play is not None:
                    try:
                        btn_play.setText("Repeat")
                    except Exception:
                        pass
        except Exception:
            pass

        # Kick off a sequence; when it finishes, we auto-advance and schedule the next one.
        def _after_first():
            self.auto_advance_step()

        # Use the controller-managed playback entry point
        self.play_sequence(on_done=_after_first)

    def auto_advance_step(self):
        """In auto mode, advance to the next item and schedule its playback after the auto delay."""
        window = self.window

        # Abort if auto mode has been turned off meanwhile
        if not _get_window_attr(window, "_auto_mode", False):
            logger.debug("Auto advance skipped: auto mode OFF")
            return

        items = _get_window_attr(window, "_vocab_items", [])
        if not items:
            logger.debug("Auto advance skipped: no vocab items")
            return

        try:
            idx = int(_get_window_attr(window, "_vocab_index", 0))
        except Exception:
            idx = 0

        window._vocab_index = (idx + 1) % len(items)
        self.show_current()

        # Read auto delay (seconds) from the slider, if present
        # Get slider_auto from main module
        import sys
        main_module = sys.modules.get('__main__')
        slider_auto = None
        if main_module is not None:
            slider_auto = getattr(main_module, 'slider_auto', None)

        try:
            delay_sec = int(slider_auto.value()) if slider_auto is not None else 0
        except Exception:
            delay_sec = 0

        ms = max(0, delay_sec) * 1000

        def _kickoff_next():
            # Re-check auto mode at the moment of kicking off
            if not _get_window_attr(window, "_auto_mode", False):
                logger.debug("Auto advance kickoff aborted: auto mode OFF")
                return
            # Use the controller-managed playback entry point for the next cycle
            self.play_sequence(on_done=self.auto_advance_step)

        if ms:
            QTimer.singleShot(ms, _kickoff_next)
        else:
            _kickoff_next()
