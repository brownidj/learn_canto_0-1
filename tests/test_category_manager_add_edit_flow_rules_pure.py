import pytest

from ui.category_manager_add_edit_flow_rules import normalize_preview_payload


@pytest.mark.pure
def test_normalize_preview_payload_sets_gloss_and_categories():
    preview = {
        "jyutping": "hoi1 wui6",
        "hanzi": "開會",
        "meaning": "to meet",
        "category": "work",
    }
    payload = normalize_preview_payload(preview)

    assert payload["jyutping"] == "hoi1 wui6"
    assert payload["hanzi"] == "開會"
    assert payload["meaning"] == "to meet"
    assert payload["gloss"] == "to meet"
    assert payload["category"] == "work"
    assert payload["categories"] == ["work"]


@pytest.mark.pure
def test_normalize_preview_payload_ignores_unassigned_and_all():
    for cat in ("unassigned", "all", ""):
        payload = normalize_preview_payload({"category": cat, "meaning": "x"})
        assert payload["category"] == cat
        assert payload["categories"] == []
