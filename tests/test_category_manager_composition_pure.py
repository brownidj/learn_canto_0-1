import pytest

from ui.category_manager_composition import CategoryManagerComposition


class _StubDialog:
    pass


@pytest.mark.pure
def test_composition_sets_core_controllers():
    dlg = _StubDialog()
    CategoryManagerComposition(dlg).build()

    assert getattr(dlg, "_initializer", None) is not None
    assert getattr(dlg, "_focus_ctrl", None) is not None
    assert getattr(dlg, "_typography_ctrl", None) is not None
    assert getattr(dlg, "_add_edit_flow", None) is not None
    assert getattr(dlg, "_meaning_resolver", None) is not None
    assert getattr(dlg, "_category_ops", None) is not None
    assert getattr(dlg, "_candidate_pipeline", None) is not None
    assert getattr(dlg, "_manual_hanzi", None) is not None
    assert getattr(dlg, "_field_reset", None) is not None
    assert getattr(dlg, "_save_commit", None) is not None
    assert getattr(dlg, "_preview_confirm", None) is not None
    assert getattr(dlg, "_state_svc", None) is not None
    assert getattr(dlg, "_state_coord", None) is not None
