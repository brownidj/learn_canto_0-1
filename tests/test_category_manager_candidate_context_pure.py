import pytest

from ui.category_manager_candidate_context import build_candidate_context


class _StubDialog:
    def __init__(self):
        self._reverse_index = None
        self._rev_index = {"jy": [("漢", "src", 1)]}
        self._reverse_jyut_index = {"jy2": [("字", "src", 1)]}
        self._style_index = object()
        self._candidate_curator = object()
        self.MAX_HANZI_CANDIDATES = 7


@pytest.mark.pure
def test_candidate_context_prefers_first_dict_reverse_index():
    dialog = _StubDialog()
    ctx = build_candidate_context(dialog)

    assert ctx.reverse_index is dialog._rev_index
    assert ctx.style_index is dialog._style_index
    assert ctx.candidate_curator is dialog._candidate_curator
    assert ctx.max_candidates == 7


@pytest.mark.pure
def test_candidate_context_defaults_when_missing():
    class _BareDialog:
        pass

    ctx = build_candidate_context(_BareDialog())
    assert ctx.reverse_index is None
    assert ctx.style_index is None
    assert ctx.candidate_curator is None
    assert ctx.max_candidates == 10
