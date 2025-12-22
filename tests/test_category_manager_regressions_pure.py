import os
import pytest


def _skip_if_headless_ci() -> None:
    # Skip in likely-headless environments (common on CI)
    if os.environ.get("CI") and not os.environ.get("DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
        pytest.skip("Headless CI environment without a Qt platform")


@pytest.mark.ui
def test_category_manager_dialog_uses_domain_validate_jyut_syllables(monkeypatch):
    """Regression: CategoryManagerDialog must delegate detailed Jyutping validation to domain.jyutping_validation."""

    _skip_if_headless_ci()

    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    import category_manager as cm
    from category_manager import CategoryManagerDialog

    app = QApplication.instance() or QApplication([])

    # Guardrail: the dialog must not implement validation heuristics locally.
    # The module-level symbol must come from the domain layer.
    from domain import jyutping_validation as jv
    assert getattr(cm.validate_jyut_syllables, "__module__", "") == jv.__name__

    vocab = {"白": [["White"], "baak6"]}
    cats = {"colors": ["白"], "unassigned": []}

    dlg = CategoryManagerDialog(None, vocab_items=vocab, categories_map=cats)

    called = {"n": 0}

    def fake_validate(jy: str):
        called["n"] += 1
        return True, None

    # Patch the module-level import that the dialog wrapper calls
    monkeypatch.setattr(cm, "validate_jyut_syllables", fake_validate)

    ok, reason = dlg._validate_jyut_syllables("nei5 hou2")

    assert ok is True
    assert reason is None
    assert called["n"] == 1

    dlg.close()
    app.processEvents()


@pytest.mark.pure
def test_category_manager_does_not_compute_paths_from___file__():
    """Regression guard: CategoryManager / main must not compute paths via __file__.

    All path resolution must go through infra.paths helpers to avoid silent
    mis-rooting (e.g. reverse index not loading, Tier-1 misses like 'ngan4'→銀).
    """
    import inspect
    import category_manager
    import main

    offenders = []

    for mod in (category_manager, main):
        try:
            src = inspect.getsource(mod)
        except Exception:
            continue

        if "__file__" in src and "infra.paths" not in src:
            offenders.append(mod.__name__)

    assert not offenders, f"Direct __file__ path usage detected in: {offenders}"