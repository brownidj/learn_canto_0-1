import os
from types import SimpleNamespace

import pytest


def test_cantonese_language_service_parse_mock(monkeypatch, tmp_path):
    from services.cantonese_language_service import CantoneseLanguageService

    # Stub openai module so the import inside lookup() resolves to this.
    class _StubResponses:
        def parse(self, *, text_format=None, **kwargs):
            data = text_format(
                hanzi="開會",
                jyutping="hoi1 wui6",
                meaning_colloquial="have/attend a meeting",
                register="colloquial",
                confidence=0.9,
                notes="",
                examples=[],
            )
            return SimpleNamespace(output_parsed=data)

    class _StubOpenAI:
        def __init__(self, *args, **kwargs):
            self.responses = _StubResponses()

    monkeypatch.setitem(os.environ, "OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(__import__("sys").modules, "openai", SimpleNamespace(OpenAI=_StubOpenAI))

    cache_path = tmp_path / "cantonese_language_cache.json"
    svc = CantoneseLanguageService(cache_path=cache_path, model="gpt-4o-mini")
    info = svc.lookup(hanzi="開會", jyutping="hoi1 wui6")

    assert info is not None
    assert info.hanzi == "開會"
    assert info.jyutping == "hoi1 wui6"
    assert info.meaning_colloquial == "have/attend a meeting"
    assert cache_path.exists()
