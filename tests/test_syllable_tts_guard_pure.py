import pytest

from controllers.main_controller import _mark_syllable_tts_busy, _clear_syllable_tts_busy

pytestmark = pytest.mark.pure


class DummyWindow:
    pass


def test_syllable_tts_guard():
    w = DummyWindow()
    assert _mark_syllable_tts_busy(w) is True
    assert _mark_syllable_tts_busy(w) is False
    _clear_syllable_tts_busy(w)
    assert _mark_syllable_tts_busy(w) is True
