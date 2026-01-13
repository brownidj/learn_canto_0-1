"""
Tests for services/tts_service.py - TTS/Audio service
"""
import os
import tempfile
import pytest
from unittest.mock import Mock, MagicMock, patch, call

from services.tts_service import TTSService


@pytest.fixture
def mock_qprocess():
    """Mock QProcess for testing without actual system calls."""
    with patch('services.tts_service.QProcess') as mock:
        yield mock


@pytest.fixture
def tts_service():
    """Create a TTS service instance for testing."""
    with patch('services.tts_service.QProcess'):
        service = TTSService(window=None)
        # Override with test data
        service.available_voices = [
            ("Sin-ji", "zh_HK", "Sin-ji zh_HK # Cantonese (Hong Kong)"),
            ("Ting-Ting", "zh_CN", "Ting-Ting zh_CN # Chinese (China)"),
            ("Yuna", "ko_KR", "Yuna ko_KR # Korean"),
        ]
        service.default_voice = "Sin-ji"
        return service


class TestVoiceDetection:
    """Tests for voice detection and selection."""

    def test_detect_voices_parses_output(self, mock_qprocess):
        """Test that voice detection parses 'say -v ?' output correctly."""
        # Mock the QProcess
        mock_proc = MagicMock()
        mock_qprocess.return_value = mock_proc

        # Mock output
        mock_output = b"  Sin-ji              zh_HK    # Cantonese (Hong Kong)\n  Ting-Ting           zh_CN    # Chinese (China)\n"
        mock_proc.readAllStandardOutput.return_value.data.return_value = mock_output

        service = TTSService()
        voices = service.available_voices

        assert len(voices) >= 2
        # Check that voices contain expected data structure
        assert all(isinstance(v, tuple) and len(v) == 3 for v in voices)

    def test_pick_cantonese_voice_prefers_zh_hk(self, tts_service):
        """Test that zh_HK voices are preferred."""
        voice = tts_service.pick_cantonese_voice()
        assert voice == "Sin-ji"  # zh_HK voice

    def test_pick_cantonese_voice_fallback_to_zh(self):
        """Test fallback to other zh_* voices when zh_HK unavailable."""
        service = TTSService()
        service.available_voices = [
            ("Ting-Ting", "zh_CN", "Chinese China"),
            ("Yuna", "ko_KR", "Korean"),
        ]
        voice = service.pick_cantonese_voice()
        assert voice == "Ting-Ting"  # Best zh_* available

    def test_pick_cantonese_voice_fallback_to_preferred_names(self):
        """Test fallback to preferred names when no zh voices."""
        service = TTSService()
        service.available_voices = [
            ("Samantha", "en_US", "English US"),
            ("Yuna", "", "No locale"),  # Preferred name
        ]
        voice = service.pick_cantonese_voice()
        assert voice == "Yuna"

    def test_pick_cantonese_voice_returns_none_when_empty(self):
        """Test that None is returned when no voices available."""
        service = TTSService()
        service.available_voices = []
        voice = service.pick_cantonese_voice()
        assert voice is None

    def test_get_voice_returns_provided(self, tts_service):
        """Test that get_voice returns provided voice when specified."""
        assert tts_service.get_voice("Custom-Voice") == "Custom-Voice"

    def test_get_voice_returns_default_when_none(self, tts_service):
        """Test that get_voice returns default when None provided."""
        assert tts_service.get_voice(None) == "Sin-ji"

    def test_get_voice_strips_whitespace(self, tts_service):
        """Test that get_voice strips whitespace."""
        assert tts_service.get_voice("  Sin-ji  ") == "Sin-ji"


class TestSynthesis:
    """Tests for text synthesis."""

    def test_synthesize_to_file_success(self, tts_service, mock_qprocess):
        """Test successful synthesis to file."""
        mock_proc = MagicMock()
        mock_qprocess.return_value = mock_proc
        mock_proc.waitForFinished.return_value = True
        mock_proc.exitCode.return_value = 0

        with tempfile.NamedTemporaryFile(suffix='.aiff', delete=False) as f:
            output_path = f.name

        try:
            result = tts_service.synthesize_to_file("你好", output_path)
            assert result is True

            # Check that QProcess was configured correctly
            mock_proc.setProgram.assert_called_with("/usr/bin/say")
            args = mock_proc.setArguments.call_args[0][0]
            assert "-o" in args
            assert output_path in args
            assert "你好" in args
        finally:
            try:
                os.unlink(output_path)
            except:
                pass

    def test_synthesize_includes_voice(self, tts_service, mock_qprocess):
        """Test that synthesis includes voice argument."""
        mock_proc = MagicMock()
        mock_qprocess.return_value = mock_proc
        mock_proc.waitForFinished.return_value = True
        mock_proc.exitCode.return_value = 0

        tts_service.synthesize_to_file("你好", "/tmp/test.aiff", voice="Sin-ji")

        args = mock_proc.setArguments.call_args[0][0]
        assert "-v" in args
        assert "Sin-ji" in args

    def test_synthesize_includes_rate(self, tts_service, mock_qprocess):
        """Test that synthesis includes rate argument."""
        mock_proc = MagicMock()
        mock_qprocess.return_value = mock_proc
        mock_proc.waitForFinished.return_value = True
        mock_proc.exitCode.return_value = 0

        tts_service.synthesize_to_file("你好", "/tmp/test.aiff", rate=120)

        args = mock_proc.setArguments.call_args[0][0]
        assert "-r" in args
        assert "120" in args

    def test_synthesize_handles_timeout(self, tts_service, mock_qprocess):
        """Test handling of synthesis timeout."""
        mock_proc = MagicMock()
        mock_qprocess.return_value = mock_proc
        mock_proc.waitForFinished.return_value = False  # Timeout

        result = tts_service.synthesize_to_file("你好", "/tmp/test.aiff")
        assert result is False


class TestPlayback:
    """Tests for audio playback."""

    @patch('services.tts_service.os.remove')
    def test_play_file_calls_afplay(self, mock_remove, tts_service, mock_qprocess):
        """Test that play_file calls afplay correctly."""
        mock_proc = MagicMock()
        mock_qprocess.return_value = mock_proc

        callback = Mock()
        tts_service.play_file("/tmp/test.aiff", on_finished=callback)

        # Check afplay was configured
        mock_proc.setProgram.assert_called_with("/usr/bin/afplay")
        mock_proc.setArguments.assert_called_with(["/tmp/test.aiff"])
        mock_proc.start.assert_called_once()

    def test_play_once_full_workflow(self, tts_service, mock_qprocess):
        """Test play_once synthesizes and plays."""
        mock_proc = MagicMock()
        mock_qprocess.return_value = mock_proc
        mock_proc.waitForFinished.return_value = True
        mock_proc.exitCode.return_value = 0

        callback = Mock()
        tts_service.play_once("你好", voice="Sin-ji", rate=120, on_finished=callback)

        # Should have called QProcess twice (say + afplay)
        assert mock_qprocess.call_count >= 2


class TestSequencePlayback:
    """Tests for sequence playback with delays."""

    @patch('services.tts_service.QTimer')
    def test_play_sequence_with_repeats(self, mock_timer, tts_service, mock_qprocess):
        """Test that play_sequence handles repeats correctly."""
        mock_proc = MagicMock()
        mock_qprocess.return_value = mock_proc
        mock_proc.waitForFinished.return_value = True
        mock_proc.exitCode.return_value = 0

        callback = Mock()
        tts_service.play_sequence(
            "你好",
            repeats=3,
            intro_delay=0,
            repeat_delay=0,
            extro_delay=0,
            on_done=callback
        )

        # Should have started synthesis
        assert mock_proc.start.called

    @patch('services.tts_service.QTimer')
    def test_play_sequence_with_intro_delay(self, mock_timer, tts_service):
        """Test that intro delay is applied."""
        tts_service.play_sequence(
            "你好",
            intro_delay=2,
            on_done=Mock()
        )

        # Should have scheduled with delay
        assert mock_timer.singleShot.called
        args = mock_timer.singleShot.call_args[0]
        assert args[0] == 2000  # 2 seconds in ms

    @patch('services.tts_service.QTimer')
    def test_play_sequence_minimum_one_repeat(self, mock_timer, tts_service, mock_qprocess):
        """Test that at least one repeat always happens."""
        mock_proc = MagicMock()
        mock_qprocess.return_value = mock_proc
        mock_proc.waitForFinished.return_value = True
        mock_proc.exitCode.return_value = 0

        tts_service.play_sequence("你好", repeats=0, on_done=Mock())

        # Should still play once
        assert mock_proc.start.called


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_play_once_with_empty_text(self, tts_service):
        """Test handling of empty text."""
        callback = Mock()
        # Should not crash
        tts_service.play_once("", on_finished=callback)

    def test_synthesis_error_calls_callback(self, tts_service, mock_qprocess):
        """Test that synthesis errors trigger callback."""
        mock_proc = MagicMock()
        mock_qprocess.return_value = mock_proc
        mock_proc.waitForFinished.side_effect = Exception("Test error")

        callback = Mock()
        tts_service.play_once("你好", on_finished=callback)

        # Callback should be called even on error
        # (via QTimer.singleShot in the except block)

    def test_invalid_rate_handled(self, tts_service, mock_qprocess):
        """Test that invalid rate values are handled."""
        mock_proc = MagicMock()
        mock_qprocess.return_value = mock_proc
        mock_proc.waitForFinished.return_value = True
        mock_proc.exitCode.return_value = 0

        # Should not crash with string rate
        tts_service.synthesize_to_file("你好", "/tmp/test.aiff", rate="invalid")

        # Should not include rate arg
        args = mock_proc.setArguments.call_args[0][0]
        assert "-r" not in args
