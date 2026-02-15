import pytest

from ui.category_manager_add_edit_candidate_list import AddEditCandidateListService
from ui.category_manager_add_edit_candidate_selection import AddEditCandidateSelectionService


class _StubCombo:
    def __init__(self):
        self._items = ["開會"]
        self._data = [{"src": "tier2"}]
        self._index = 0

    def currentText(self):
        return self._items[self._index]

    def findText(self, text):
        try:
            return self._items.index(text)
        except ValueError:
            return -1

    def currentIndex(self):
        return self._index

    def itemText(self, idx):
        return self._items[idx]

    def itemData(self, idx, *_args, **_kwargs):
        return self._data[idx]


class _StubDialog:
    def __init__(self):
        self._cand_combo = _StubCombo()
        self._add_cat = None


class _StubSelection:
    def __init__(self):
        self.calls = []

    def apply_selection(self, **kwargs):
        self.calls.append(kwargs)


@pytest.mark.pure
def test_candidate_list_service_populates_initial_selection(monkeypatch):
    dialog = _StubDialog()
    svc = AddEditCandidateListService(dialog)

    monkeypatch.setattr("ui.category_manager_add_edit_candidate_list.get_candidates", lambda *_: [("開會", "tier2", 1.0)])
    monkeypatch.setattr("ui.category_manager_add_edit_candidate_list.preferred_hanzi_for_category", lambda *_: "")
    monkeypatch.setattr(svc, "_selection", _StubSelection())
    monkeypatch.setattr(svc._ui, "show_candidates", lambda *_: None)
    monkeypatch.setattr(svc._ui, "hide_candidates", lambda *_: None)
    monkeypatch.setattr(svc._ui, "hide_candidate_popup", lambda *_: None)
    monkeypatch.setattr(svc._ui, "focus_hanzi_later", lambda *args, **kwargs: None)
    monkeypatch.setattr(svc._ui, "set_candidate_index", lambda *_: None)
    monkeypatch.setattr(svc._combo, "populate_candidates", lambda *_: None)

    svc.fill_candidates("hoi1 wui6", category="work")

    assert svc._selection.calls


@pytest.mark.pure
def test_candidate_selection_service_reads_combo_data(monkeypatch):
    dialog = _StubDialog()
    svc = AddEditCandidateSelectionService(dialog)

    calls = []
    monkeypatch.setattr(svc, "apply_selection", lambda **kwargs: calls.append(kwargs))

    svc.apply_selection_from_combo_index(0)

    assert calls
    assert calls[0]["hanzi"] == "開會"
    assert calls[0]["src"] == "tier2"
