"""Google Cloud Text-to-Speech service wrapper."""

from __future__ import annotations

import os
import tempfile
import logging
import base64
from typing import Optional, Callable, List, Tuple, Any

from PySide6.QtCore import QProcess, QTimer

logger = logging.getLogger(__name__)


def _load_tts_module():
    try:
        from google.cloud import texttospeech_v1beta1 as tts
        return tts
    except Exception:
        pass
    try:
        from google.cloud import texttospeech_v1 as tts
        return tts
    except Exception:
        from google.cloud import texttospeech as tts
        return tts


class GoogleTTSService:
    """Google Cloud TTS service using the official client library."""

    def __init__(self, window: Optional[Any] = None):
        self.window = window
        self._tts_mod = _load_tts_module()
        self._tts = self._tts_mod.TextToSpeechClient()
        self.available_voices = self._detect_voices()
        self.default_voice = self._pick_default_voice()

    def _detect_voices(self) -> List[Tuple[str, str, str]]:
        try:
            voices = self._tts.list_voices().voices
            out = []
            for v in voices:
                name = v.name or ""
                locale = v.language_codes[0] if v.language_codes else ""
                short = name.split("-")[-1] if name else ""
                label = f"{short} ({locale})" if short else f"{name} ({locale})"
                out.append((name, locale, label))
            return out
        except Exception as e:
            logger.warning("Google TTS voice list failed: %s", e)
            return []

    def _pick_default_voice(self) -> Optional[str]:
        # Prefer Cantonese if available.
        for name, locale, _ in self.available_voices:
            if locale.startswith("yue") or locale == "yue-HK":
                return name
        return None

    def get_voice(self, voice_name: Optional[str] = None) -> Optional[str]:
        if voice_name and voice_name.strip():
            return voice_name.strip()
        return self.default_voice

    def _speaking_rate(self, wpm: Optional[int]) -> Optional[float]:
        if not isinstance(wpm, int) or wpm <= 0:
            return None
        # Rough mapping: 120 wpm ~ 1.0 speaking_rate
        rate = max(0.25, min(4.0, wpm / 120.0))
        return rate

    def synthesize_to_file(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
    ) -> bool:
        try:
            tts = self._tts_mod
            voice_name = self.get_voice(voice)
            voice_params = tts.VoiceSelectionParams(
                language_code="yue-HK",
                name=voice_name or "",
            )
            audio_config = tts.AudioConfig(
                audio_encoding=tts.AudioEncoding.MP3,
                speaking_rate=self._speaking_rate(rate) or 1.0,
            )
            synthesis_input = tts.SynthesisInput(text=text)

            resp = self._tts.synthesize_speech(
                input=synthesis_input,
                voice=voice_params,
                audio_config=audio_config,
            )
            if not resp.audio_content:
                return False
            with open(output_path, "wb") as f:
                f.write(resp.audio_content)
            return True
        except Exception as e:
            logger.warning("Google TTS synthesis failed: %s", e)
            return False

    def synthesize_ssml_with_timepoints(
        self,
        ssml: str,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
    ) -> tuple[bytes, list[tuple[str, float]]]:
        try:
            tts = self._tts_mod
            voice_name = self.get_voice(voice)
            voice_params = tts.VoiceSelectionParams(
                language_code="yue-HK",
                name=voice_name or "",
            )
            tp_type = getattr(tts, "TimepointType", None)
            if tp_type is not None and hasattr(tp_type, "SSML_MARK"):
                timepointing = [tp_type.SSML_MARK]
            else:
                # Older client libs accept string values.
                timepointing = ["SSML_MARK"]
            audio_config = tts.AudioConfig(
                audio_encoding=tts.AudioEncoding.MP3,
                speaking_rate=self._speaking_rate(rate) or 1.0,
            )
            synthesis_input = tts.SynthesisInput(ssml=ssml)
            try:
                request = tts.SynthesizeSpeechRequest(
                    input=synthesis_input,
                    voice=voice_params,
                    audio_config=audio_config,
                    enable_time_pointing=timepointing,
                )
                resp = self._tts.synthesize_speech(request=request)
            except Exception:
                resp = self._tts.synthesize_speech(
                    input=synthesis_input,
                    voice=voice_params,
                    audio_config=audio_config,
                )
            # Some client versions can't parse timepoints; fall back to REST if missing.
            timepoints = []
            for tp in getattr(resp, "timepoints", []) or []:
                if getattr(tp, "mark_name", None) is not None and getattr(tp, "time_seconds", None) is not None:
                    timepoints.append((tp.mark_name, float(tp.time_seconds)))
            if timepoints:
                logger.debug("Google TTS timepoints=%d", len(timepoints))
                return resp.audio_content or b"", timepoints
            audio, tps = self._synthesize_via_rest(ssml, voice_name, rate)
            if audio:
                logger.debug("Google TTS timepoints(rest)=%d", len(tps))
                return audio, tps
            return resp.audio_content or b"", []
        except Exception as e:
            logger.warning("Google TTS SSML/timepoints failed: %s", e)
            return b"", []

    def _synthesize_via_rest(
        self,
        ssml: str,
        voice_name: Optional[str],
        rate: Optional[int],
    ) -> tuple[bytes, list[tuple[str, float]]]:
        try:
            import google.auth
            from google.auth.transport.requests import Request
            import requests

            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            creds.refresh(Request())

            url = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"
            payload = {
                "input": {"ssml": ssml},
                "voice": {"languageCode": "yue-HK", "name": voice_name or ""},
                "audioConfig": {
                    "audioEncoding": "MP3",
                    "speakingRate": self._speaking_rate(rate) or 1.0,
                },
                "enableTimePointing": ["SSML_MARK"],
            }
            headers = {"Authorization": f"Bearer {creds.token}"}
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code != 200:
                logger.warning("Google TTS REST failed: %s %s", resp.status_code, resp.text[:200])
                return b"", []
            data = resp.json()
            audio = base64.b64decode(data.get("audioContent", "") or "")
            timepoints = []
            for tp in data.get("timepoints", []) or []:
                name = tp.get("markName")
                ts = tp.get("timeSeconds")
                if name is not None and ts is not None:
                    timepoints.append((str(name), float(ts)))
            return audio, timepoints
        except Exception as e:
            logger.warning("Google TTS REST exception: %s", e)
            return b"", []

    def play_file(self, audio_path: str, on_finished: Optional[Callable] = None) -> None:
        try:
            afplay = "/usr/bin/afplay"
            proc = QProcess(self.window)
            proc.setProgram(afplay)
            proc.setArguments([audio_path])
            proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

            def _on_play_finished(exit_code, exit_status):
                try:
                    os.remove(audio_path)
                except Exception:
                    pass
                if callable(on_finished):
                    on_finished()

            proc.finished.connect(_on_play_finished)
            proc.start()
        except Exception as e:
            logger.warning("Google TTS playback failed: %s", e)
            if callable(on_finished):
                QTimer.singleShot(0, on_finished)

    def play_once(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
        on_finished: Optional[Callable] = None,
    ) -> None:
        try:
            tmp = tempfile.NamedTemporaryFile(prefix="learncanto_", suffix=".mp3", delete=False)
            tmp_path = tmp.name
            tmp.close()

            success = self.synthesize_to_file(text, tmp_path, voice, rate)
            if not success:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                if callable(on_finished):
                    QTimer.singleShot(0, on_finished)
                return

            self.play_file(tmp_path, on_finished)
        except Exception as e:
            logger.warning("Google TTS play_once failed: %s", e)
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
        on_done: Optional[Callable] = None,
    ) -> None:
        total = max(1, repeats)
        ms_intro = max(0, intro_delay) * 1000
        ms_gap = max(0, repeat_delay) * 1000
        ms_extro = max(0, extro_delay) * 1000

        state = {"i": 0}

        def _after_one():
            if state["i"] + 1 < total:
                state["i"] += 1
                if ms_gap:
                    QTimer.singleShot(ms_gap, lambda: self.play_once(text, voice, rate, _after_one))
                else:
                    self.play_once(text, voice, rate, _after_one)
            else:
                if ms_extro and callable(on_done):
                    QTimer.singleShot(ms_extro, on_done)
                elif callable(on_done):
                    on_done()

        if ms_intro:
            QTimer.singleShot(ms_intro, lambda: self.play_once(text, voice, rate, _after_one))
        else:
            self.play_once(text, voice, rate, _after_one)
