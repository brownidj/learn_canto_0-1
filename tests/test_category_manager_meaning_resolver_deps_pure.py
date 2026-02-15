import pytest

from ui.category_manager_meaning_resolver import CategoryManagerMeaningResolver
from ui.category_manager_meaning_resolver_service import MeaningResolverService


class _StubDialog:
    pass


class _StubFacade:
    def __init__(self):
        self.calls = []

    def select_candidate(self, hz, src, preferred=False, max_items=2):
        self.calls.append((hz, src, preferred, max_items))
        class _Sel:
            meanings = ["from facade"]
        return _Sel()


class _StubVocab:
    def get_entry_raw(self, hz):
        if hz == "開會":
            return (["to meet", "to hold a meeting"], "hoi1 wui6")
        return None


@pytest.mark.pure
def test_meaning_resolver_uses_facade_when_injected():
    dialog = _StubDialog()
    facade = _StubFacade()
    svc = MeaningResolverService(
        get_facade=lambda: facade,
        get_vocab_service=lambda: None,
        get_jyutping_text=lambda: "",
    )
    resolver = CategoryManagerMeaningResolver(dialog, service=svc)

    meanings = resolver.resolve_meanings_for_candidate("開會", "tier2", preferred=True, max_items=1)
    assert meanings == ["from facade"]
    assert facade.calls


@pytest.mark.pure
def test_meaning_resolver_uses_vocab_with_injected_jyutping_getter():
    dialog = _StubDialog()
    vocab = _StubVocab()
    svc = MeaningResolverService(
        get_facade=lambda: None,
        get_vocab_service=lambda: vocab,
        get_jyutping_text=lambda: "hoi1 wui6",
    )
    resolver = CategoryManagerMeaningResolver(dialog, service=svc)

    meanings = resolver.resolve_meanings_for_candidate("開會", "tier2")
    assert "to meet" in meanings
