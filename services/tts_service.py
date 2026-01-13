"""
TTS (Text-to-Speech) service for macOS using the 'say' command.

This module handles voice detection, synthesis, and playback using
macOS system tools (say + afplay).
"""
import os
import tempfile
import shlex
import logging
from typing import Optional, Callable, List, Tuple, Any

from PySide6.QtCore import QProcess, QTimer

logger = logging.getLogger(__name__)


class TTSService:
    """macOS text-to-speech service using 'say' command and afplay.

    This service:
    - Detects available macOS voices
    - Picks the best Cantonese voice
    - Synthesizes text to AIFF files
    - Plays audio with configurable delays and repeats
    """

    def __init__(self, window: Optional[Any] = None):
        """Initialize TTS service.

        Args:
            window: Optional Qt parent widget (for QProcess parent)
        """
        self.window = window
        self.available_voices = self.detect_voices()
        self.default_voice = self.pick_cantonese_voice()
        logger.debug("TTSService initialized: %d voices, default=%s", 
                    len(self.available_voices), self.default_voice)

    def detect_voices(self) -> List[Tuple[str, str, str]]:
        """Detect available voices from `say -v '?'`.

        Returns:
            List of (name, locale, full_description) tuples
        """
        try:
            proc = QProcess(self.window)
            proc.setProgram("/usr/bin/say")
            proc.setArguments(["-v", "?"])
            proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            proc.start()
            proc.waitForFinished(3000)
            qba = proc.readAllStandardOutput()
            try:
                out = qba.data().decode("utf-8", "ignore")
            except Exception:
                out = bytes(qba).decode("utf-8", "ignore")

            voices = []
            for line in out.splitlines():
                # Example: "  Sin-ji              zh_HK    # Cantonese (Hong Kong)"
                parts = line.strip().split()
                if len(parts) >= 2:
                    name = parts[0]
                    locale = parts[1] if parts[1].startswith("zh") else ""
                    voices.append((name, locale, line.strip()))

            logger.debug("Detected %d voices", len(voices))
            return voices

        except Exception as e:
            logger.warning("Voice detection failed: %s", e)
            return []

    def pick_cantonese_voice(self) -> Optional[str]:
        """Select the best available Cantonese voice.

        Priority:
        1. zh_HK voices (Cantonese Hong Kong)
        2. Other zh_* voices (Chinese variants)
        3. Preferred names: Sin-ji, Sinji, Yuna, Ting-Ting, Mei-Jia

        Returns:
            Voice name or None if no suitable voice found
        """
        prefs = ["Sin-ji", "Sinji", "Yuna", "Ting-Ting", "Mei-Jia"]

        # Prefer zh_HK voices
        zh_hk = [v for v in self.available_voices if v[1] == "zh_HK"]
        if zh_hk:
            return zh_hk[0][0]

        # Fallback to any zh_* voice
        zh_any = [v for v in self.available_voices if v[1].startswith("zh")]
        if zh_any:
            return zh_any[0][0]

        # Fallback to preferred names
        for pref in prefs:
            for v in self.available_voices:
                if v[0] == pref:
                    return pref

        return None

    def get_voice(self, voice_name: Optional[str] = None) -> Optional[str]:
        """Get voice to use (provided or default).

        Args:
            voice_name: Specific voice name, or None for default

        Returns:
            Voice name to use
        """
        if voice_name and voice_name.strip():
            return voice_name.strip()
        return self.default_voice

    def synthesize_to_file(
        self, 
        text: str, 
        output_path: str,
        voice: Optional[str] = None,
        rate: Optional[int] = None
    ) -> bool:
        """Synthesize text to an AIFF file using 'say'.

        Args:
            text: Text to synthesize
            output_path: Path to output .aiff file
            voice: Voice name (None = use default)
            rate: Words per minute (None = system default)

        Returns:
            True if synthesis succeeded, False otherwise
        """
        try:
            say_path = "/usr/bin/say"
            voice_to_use = self.get_voice(voice)

            args = []
            if voice_to_use:
                args += ["-v", voice_to_use]
            if isinstance(rate, int) and rate > 0:
                args += ["-r", str(rate)]
            args += ["-o", output_path, "--", text]

            logger.debug("Synthesizing: %s %s", say_path, " ".join(shlex.quote(a) for a in args))

            proc = QProcess(self.window)
            proc.setProgram(say_path)
            proc.setArguments(args)
            proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            proc.start()

            if not proc.waitForFinished(10000):
                logger.warning("say command did not finish in time")
                return False

            exit_code = proc.exitCode()
            logger.debug("say finished: exit_code=%s", exit_code)
            return exit_code == 0

        except Exception as e:
            logger.warning("Synthesis failed: %s", e)
            return False

    def play_file(
        self,
        audio_path: str,
        on_finished: Optional[Callable] = None
    ) -> None:
        """Play an audio file using afplay (async).

        Args:
            audio_path: Path to audio file
            on_finished: Callback when playback finishes
        """
        try:
            afplay = "/usr/bin/afplay"

            proc = QProcess(self.window)
            proc.setProgram(afplay)
            proc.setArguments([audio_path])
            proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

            def _on_play_finished(exit_code, exit_status):
                logger.debug("afplay finished: code=%s status=%s file=%s", 
                           exit_code, exit_status, audio_path)
                try:
                    os.remove(audio_path)
                except Exception:
                    pass
                if callable(on_finished):
                    on_finished()

            proc.finished.connect(_on_play_finished)
            proc.start()
            logger.debug("Playing audio: %s", audio_path)

        except Exception as e:
            logger.warning("Playback failed: %s", e)
            if callable(on_finished):
                QTimer.singleShot(0, on_finished)

    def play_once(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
        on_finished: Optional[Callable] = None
    ) -> None:
        """Synthesize text and play it once (async).

        Args:
            text: Text to speak
            voice: Voice name (None = use default)
            rate: Words per minute (None = system default)
            on_finished: Callback when playback finishes
        """
        try:
            # Create temp file for synthesis
            tmp = tempfile.NamedTemporaryFile(
                prefix="learncanto_", 
                suffix=".aiff", 
                delete=False
            )
            tmp_path = tmp.name
            tmp.close()

            # Synthesize
            success = self.synthesize_to_file(text, tmp_path, voice, rate)

            if not success:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                if callable(on_finished):
                    QTimer.singleShot(0, on_finished)
                return

            # Play
            self.play_file(tmp_path, on_finished)

        except Exception as e:
            logger.warning("play_once failed: %s", e)
            if callable(on_finished):
                QTimer.singleShot(0, on_finished)

    def play_sequence(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
        repeats: int = 1,
        intro_delay: int = 0,
        repeat_delay: int = 0,
        extro_delay: int = 0,
        on_done: Optional[Callable] = None
    ) -> None:
        """Play text with repeats and configurable delays (async).

        Args:
            text: Text to speak
            voice: Voice name (None = use default)
            rate: Words per minute
            repeats: Number of times to play (min 1)
            intro_delay: Delay before first play (seconds)
            repeat_delay: Delay between repeats (seconds)
            extro_delay: Delay after last play (seconds)
            on_done: Callback when entire sequence finishes
        """
        total = max(1, repeats)
        ms_intro = max(0, intro_delay) * 1000
        ms_gap = max(0, repeat_delay) * 1000
        ms_extro = max(0, extro_delay) * 1000

        logger.debug("play_sequence: text='%s' repeats=%d intro=%d gap=%d extro=%d",
                    text[:20], total, intro_delay, repeat_delay, extro_delay)

        state = {"i": 0}

        def _after_one():
            """Called after each playback completes."""
            if state["i"] + 1 < total:
                state["i"] += 1
                if ms_gap:
                    QTimer.singleShot(ms_gap, lambda: self.play_once(text, voice, rate, _after_one))
                else:
                    self.play_once(text, voice, rate, _after_one)
            else:
                # All repeats done -> extro delay then callback
                if ms_extro and callable(on_done):
                    QTimer.singleShot(ms_extro, on_done)
                elif callable(on_done):
                    on_done()

        # Kick off after intro delay
        if ms_intro:
            QTimer.singleShot(ms_intro, lambda: self.play_once(text, voice, rate, _after_one))
        else:
            self.play_once(text, voice, rate, _after_one)
