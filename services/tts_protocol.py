"""Shared protocol for TTS implementations."""

from __future__ import annotations

from typing import Protocol, Optional, Callable


class TTSServiceProtocol(Protocol):
    default_voice: Optional[str]

    def play_once(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
        on_finished: Optional[Callable] = None,
    ) -> None:
        ...

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
        ...

    def play_file(self, audio_path: str, on_finished: Optional[Callable] = None) -> None:
        ...
