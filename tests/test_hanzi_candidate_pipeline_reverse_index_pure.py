def test_pipeline_uses_reverse_index_when_provider_is_internal_adapter():
    """Regression: internal CandidatePipelineProvider should not block reverse_index lookup."""
    from domain.hanzi_candidate_pipeline import build_pipeline_from_category_manager

    class CandidatePipelineProvider:
        __module__ = "ui.category_manager_candidate_pipeline"

        def get_candidates(self, _jy):
            # If used, would hide reverse index results.
            return []

    dialog = type("Dlg", (), {})()
    dialog._normalize_jy = lambda s: (s or "").strip().lower()
    dialog._reverse_index = {"aa1": [("呀", "reverse_jyut", 1000)]}
    dialog._candidate_provider = CandidatePipelineProvider()

    pipeline = build_pipeline_from_category_manager(dialog)
    cands = pipeline.candidates_for("aa1")

    assert any(getattr(c, "hanzi", "") == "呀" for c in cands)
