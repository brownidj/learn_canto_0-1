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

@pytest.mark.ui
def test_jyutping_commit_advances_to_category_for_valid_new_jy(monkeypatch):
    """
    Regression: entering a valid, non-duplicate Jyutping with tone digit
    must mark jy_ok=True and advance the workflow toward Category selection.
    """

    _skip_if_headless_ci()

    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from category_manager import CategoryManagerDialog
    from domain.add_edit_sm import AddEditState

    app = QApplication.instance() or QApplication([])

    vocab = {
        "靚": [["good looking"], "leng2"],
    }
    cats = {"descriptions_adjectives": [], "unassigned": []}

    dlg = CategoryManagerDialog(None, vocab_items=vocab, categories_map=cats)

    # Ensure widgets/signals are fully realised (offscreen Qt can be lazy until shown).
    try:
        dlg.show()
    except Exception:
        pass
    try:
        app.processEvents()
    except Exception:
        pass

    try:
        # (1) SM must start clean
        assert dlg._add_edit_state == AddEditState.EMPTY

        # Spy: did CategoryComboController attempt to advance?
        showed_popup = {"called": False}

        ctrl = getattr(dlg, "_cat_combo_ctrl", None)
        assert ctrl is not None, "CategoryComboController must exist"

        def spy_focus(*args, **kwargs):
            showed_popup["called"] = True
            # Do not invoke the real focus() implementation here.
            # On some platforms a native popup can block the test run.
            return None

        monkeypatch.setattr(ctrl, "focus", spy_focus)

        # (2) Simulate entering a new, valid Jyutping
        dlg._add_jy.setText("leng3")
        jy, _hz, _mn, _cat = dlg._read_add_fields()
        assert jy == "leng3"

        # Prefer calling the handler directly for determinism; signal wiring can vary by platform.
        if hasattr(dlg, "_on_jyut_enter") and callable(getattr(dlg, "_on_jyut_enter")):
            dlg._on_jyut_enter()
        else:
            try:
                dlg._add_jy.returnPressed.emit()
            except Exception:
                pass

        try:
            app.processEvents()
            app.processEvents()
        except Exception:
            pass

        # (3) SM context must record Jyutping as valid
        ctx = getattr(dlg, "_add_edit_ctx", None)
        assert ctx is not None
        assert (ctx.jy or "").strip() in ("leng3", "leng3"), "Jyutping commit did not update SM context"

        # (4) Workflow must advance toward Category selection
        cat = dlg._add_cat
        le = cat.lineEdit() if hasattr(cat, "lineEdit") else None

        focused = False
        if le is not None:
            focused = le.hasFocus() or cat.hasFocus()
        else:
            focused = cat.hasFocus()

        assert focused or showed_popup["called"], (
            "Valid Jyutping commit did not advance focus toward Category selection"
        )
    finally:
        # Teardown: keep it strictly non-blocking under QT_QPA_PLATFORM=offscreen.
        # Avoid hidePopup()/native popup calls which can stall some platform plugins.
        try:
            dlg.close()
        except Exception:
            pass

        try:
            dlg.deleteLater()
        except Exception:
            pass

        # Drain a few event cycles to allow deleteLater() to execute, without entering
        # any modal/native UI loops.
        for _ in range(3):
            try:
                app.processEvents()
            except Exception:
                break