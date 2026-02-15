import os

import pytest


def _skip_if_headless_ci() -> None:
    if os.environ.get("CI") and not os.environ.get("DISPLAY") and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        pytest.skip("Headless CI; skipping UI test")


@pytest.mark.ui
def test_meaning_source_is_canto_when_cache_applies(monkeypatch):
    _skip_if_headless_ci()
    pytest.importorskip("PySide6")

    from PySide6.QtWidgets import QApplication
    from category_manager import CategoryManagerDialog
    from domain.candidate_provider import SimpleCandidateProvider

    app = QApplication.instance() or QApplication([])
    dlg = CategoryManagerDialog(None, vocab_items={}, categories_map={"work": [], "unassigned": []})
    dlg.show()
    app.processEvents()

    dlg._candidate_provider = SimpleCandidateProvider(
        {
            "hoi1 wui6": [
                ("開會", "tier2-char-ranked", 1.0),
            ]
        }
    )
    dlg._vocab_service = None
    dlg._meaning_facade = None
    try:
        dlg._hanzi_pipeline = None
    except Exception:
        pass

    class _StubMeaningResolver:
        def resolve_meanings_for_candidate(self, *args, **kwargs):
            return []

        def meanings_for_hanzi(self, *args, **kwargs):
            return []

    dlg._meaning_resolver = _StubMeaningResolver()

    class _StubCantoCtrl:
        def __init__(self, dialog):
            self._dialog = dialog

        def apply_cached_if_available(self, *, hanzi: str = "", jyutping: str = "") -> bool:
            self._dialog._add_mn.setText("to meet")
            return True

        def request(self, *, hanzi: str = "", jyutping: str = "") -> None:
            return None

    dlg._canto_ctrl = _StubCantoCtrl(dlg)

    dlg._add_edit_flow.fill_hanzi_candidates("hoi1 wui6", category="work")
    app.processEvents()

    vm = getattr(dlg, "_add_edit_vm", None)
    assert vm is not None
    assert vm.meaning_source == "canto"

    dlg.close()


@pytest.mark.ui
def test_meaning_source_is_resolver_when_available(monkeypatch):
    _skip_if_headless_ci()
    pytest.importorskip("PySide6")

    from PySide6.QtWidgets import QApplication
    from category_manager import CategoryManagerDialog
    from domain.candidate_provider import SimpleCandidateProvider

    app = QApplication.instance() or QApplication([])
    dlg = CategoryManagerDialog(None, vocab_items={}, categories_map={"work": [], "unassigned": []})
    dlg.show()
    app.processEvents()

    dlg._candidate_provider = SimpleCandidateProvider(
        {
            "hoi1 wui6": [
                ("開會", "tier2-char-ranked", 1.0),
            ]
        }
    )
    dlg._vocab_service = None
    dlg._meaning_facade = None
    try:
        dlg._hanzi_pipeline = None
    except Exception:
        pass

    class _StubFacade:
        def select_candidate(self, *_args, **_kwargs):
            class _Sel:
                meanings = ["to meet"]
            return _Sel()

    from ui.category_manager_meaning_resolver import CategoryManagerMeaningResolver
    from ui.category_manager_meaning_resolver_service import MeaningResolverService
    dlg._meaning_resolver = CategoryManagerMeaningResolver(
        dlg,
        service=MeaningResolverService(
            get_facade=lambda: _StubFacade(),
            get_vocab_service=lambda: None,
            get_jyutping_text=lambda: "",
        ),
    )

    class _StubCantoCtrl:
        def apply_cached_if_available(self, *, hanzi: str = "", jyutping: str = "") -> bool:
            return False

        def request(self, *, hanzi: str = "", jyutping: str = "") -> None:
            return None

    dlg._canto_ctrl = _StubCantoCtrl()

    dlg._add_edit_flow.fill_hanzi_candidates("hoi1 wui6", category="work")
    app.processEvents()

    vm = getattr(dlg, "_add_edit_vm", None)
    assert vm is not None
    assert vm.meaning_source == "resolver"

    dlg.close()
