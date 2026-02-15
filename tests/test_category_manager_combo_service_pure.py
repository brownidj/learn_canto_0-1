import pytest

from ui.category_manager_combo_service import CategoryManagerComboService


class _StubCombo:
    def __init__(self):
        self._items = ["開會"]
        self._data = [{"src": "tier2"}]

    def itemText(self, idx):
        return self._items[idx]

    def itemData(self, idx, *_args, **_kwargs):
        return self._data[idx]


class _StubDialog:
    def __init__(self):
        self._cand_combo = _StubCombo()


@pytest.mark.pure
def test_combo_service_reads_candidate_src_from_user_data():
    dialog = _StubDialog()
    svc = CategoryManagerComboService(dialog)

    assert svc.candidate_text_for_index(0) == "開會"
    assert svc.candidate_src_for_index(0) == "tier2"
