import os
import pytest


def _skip_if_headless_ci() -> None:
    if os.environ.get("CI") and not os.environ.get("DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
        pytest.skip("Headless CI environment without a Qt platform")


@pytest.mark.ui
def test_category_manager_dialog_smoke_ui():
    """Basic UI smoke test: dialog can be constructed, shown, and closed.

    Run with:
        .venv/bin/python3 -m pytest -q -m ui
    """
    _skip_if_headless_ci()

    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from category_manager import CategoryManagerDialog

    app = QApplication.instance() or QApplication([])

    vocab = {"白": [["White"], "baak6"]}
    cats = {"colors": ["白"], "unassigned": []}

    dlg = CategoryManagerDialog(None, vocab_items=vocab, categories_map=cats)
    dlg.show()
    app.processEvents()
    dlg.close()
    app.processEvents()


@pytest.mark.ui
def test_category_manager_dialog_uses_domain_validate_jyut_syllables(monkeypatch):
    """Regression: CategoryManagerDialog must delegate detailed Jyutping validation to domain.jyutping_validation."""
    _skip_if_headless_ci()

    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    import category_manager as cm
    from category_manager import CategoryManagerDialog

    app = QApplication.instance() or QApplication([])

    vocab = {"白": [["White"], "baak6"]}
    cats = {"colors": ["白"], "unassigned": []}

    dlg = CategoryManagerDialog(None, vocab_items=vocab, categories_map=cats)

    called = {"n": 0}

    def fake_validate(jy: str):
        called["n"] += 1
        return True, None

    monkeypatch.setattr(cm, "validate_jyut_syllables", fake_validate)

    ok, reason = dlg._validate_jyut_syllables("nei5 hou2")
    assert ok is True
    assert reason is None
    assert called["n"] == 1

    dlg.close()
    app.processEvents()
def _extract_hanzi(item) -> str:
    if isinstance(item, str):
        return item
    try:
        for attr in ("hanzi", "hz", "char"):
            if hasattr(item, attr):
                v = getattr(item, attr)
                if isinstance(v, str) and v:
                    return v
    except Exception:
        pass
    if isinstance(item, dict):
        v = item.get("hanzi") or item.get("hz") or item.get("char")
        if isinstance(v, str) and v:
            return v
    return str(item)


def _get_candidates(pipeline, jy: str, active_cat: str | None):
    """Duck-typed access to the pipeline candidate method.

    This keeps the regression robust to small API refactors.
    """
    for name in (
        "candidates_for",
        "candidates",
        "get_candidates",
        "select_candidates",
        "select",
    ):
        fn = getattr(pipeline, name, None)
        if callable(fn):
            try:
                return fn(jy, active_cat)
            except TypeError:
                try:
                    return fn(jy)
                except TypeError:
                    continue
    raise AssertionError("No candidate method found on HanziCandidatePipeline")


def test_pipeline_candidate_ordering_ignores_gloss_punctuation_metadata():
    """Golden regression: gloss *display* differences must not change candidate ordering.

    We intentionally vary only punctuation/metadata in gloss strings and assert that the
    selected/ranked candidate order is unchanged.
    """
    from domain.hanzi_candidate_pipeline import HanziCandidatePipeline

    jy = "baak6"
    active_cat = "colors"

    # Two candidates returned in a fixed order from the reverse lookup.
    def tier1(_jy: str):
        return ["白", "柏"]

    # Meaning providers differing only by punctuation/metadata.
    def cc_a(hz: str):
        if hz == "白":
            return ["white, pale"]
        if hz == "柏":
            return ["cypress, cedar"]
        return []

    def cc_b(hz: str):
        if hz == "白":
            return ["white (pale)"]
        if hz == "柏":
            return ["cypress [cedar]"]
        return []

    pipe_a = HanziCandidatePipeline(
        normalize_jyutping=(lambda s: s),
        tier1_reverse_candidates=tier1,
        tier2_compose=None,
        tier2_shortlist=None,
        char_map={},
        cc_glosses_for=cc_a,
        cedict_meanings_for=(lambda _hz: []),
        gloss_cleaner=None,
        curate=None,
        max_candidates=10,
    )

    pipe_b = HanziCandidatePipeline(
        normalize_jyutping=(lambda s: s),
        tier1_reverse_candidates=tier1,
        tier2_compose=None,
        tier2_shortlist=None,
        char_map={},
        cc_glosses_for=cc_b,
        cedict_meanings_for=(lambda _hz: []),
        gloss_cleaner=None,
        curate=None,
        max_candidates=10,
    )

    cands_a = _get_candidates(pipe_a, jy, active_cat)
    cands_b = _get_candidates(pipe_b, jy, active_cat)

    order_a = [_extract_hanzi(c) for c in (cands_a or [])]
    order_b = [_extract_hanzi(c) for c in (cands_b or [])]

    assert order_a == order_b