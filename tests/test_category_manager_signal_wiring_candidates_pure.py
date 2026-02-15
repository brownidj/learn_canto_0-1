import pytest

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_signal_wiring_basic import wire_add_edit


class _StubSignal:
    def __init__(self):
        self._slot = None

    def connect(self, slot):
        self._slot = slot

    def emit(self, *args, **kwargs):
        if self._slot is not None:
            self._slot(*args, **kwargs)

    def __getitem__(self, _):
        return self


class _StubCombo:
    def __init__(self):
        self._activated = _StubSignal()
        self._items = ["開會"]
        self._data = [{"src": "tier2"}]

    def activated(self, *args, **kwargs):  # pragma: no cover
        pass

    @property
    def activated(self):
        return self._activated

    def itemText(self, idx):
        return self._items[idx]

    def itemData(self, idx):
        return self._data[idx]


class _StubLineEdit:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


class _StubCanto:
    def __init__(self):
        self.requested = False

    def request(self, *, hanzi: str = "", jyutping: str = ""):
        self.requested = True


class _StubDialog:
    def __init__(self):
        self._cand_combo = _StubCombo()
        self._add_hz = _StubLineEdit()
        self._add_mn = _StubLineEdit()
        self._add_jy = _StubLineEdit()
        self._canto_ctrl = _StubCanto()
        self._meaning_resolver = _StubMeaningResolver()

class _StubMeaningResolver:
    def resolve_meanings_for_candidate(self, hz, src):
        return ["to meet"]

    def meanings_for_hanzi(self, hz):
        return []


class _StubWiring:
    def __init__(self, dialog):
        self.dialog = dialog
        self._dlg = CategoryManagerDialogAdapter(dialog)

    def _wire_line_edit_common(self, *_args, **_kwargs):
        return

    def _wire_combo_common(self, *_args, **_kwargs):
        return

    def _try_connect(self, signal, slot):
        if signal is not None and callable(slot):
            signal.connect(slot)

    def _resolve_meanings_for_combo(self, hz_text, combo, idx_override=None):
        resolver = self._dlg.get("_meaning_resolver")
        meanings = resolver.resolve_meanings_for_candidate(hz_text, "tier2") if resolver is not None else []
        joined = ", ".join([m for m in meanings if m])
        return meanings, joined

    def _apply_meaning_text(self, w_mn_local, joined):
        if w_mn_local is not None:
            w_mn_local.setText(joined)


@pytest.mark.pure
def test_candidate_selection_uses_resolver_and_skips_canto():
    dialog = _StubDialog()
    wiring = _StubWiring(dialog)
    wire_add_edit(wiring, fn_gate=None)

    dialog._cand_combo.activated.emit(0)

    assert dialog._add_hz.text == "開會"
    assert dialog._add_mn.text == "to meet"
    assert dialog._canto_ctrl.requested is False
