# tests/test_categories_store_pure.py
import yaml


def test_save_categories_merge_on_write_preserves_existing_and_adds_new(tmp_path, monkeypatch):
    """
    Contract: persist_categories_block() must be merge-on-write.
      - preserves existing keys on disk that are not present in the input map
      - updates keys that are present in the input map
      - adds brand-new keys from the input map
    """
    from services import vocab_loader

    # Arrange: point data_path() at a temp vocab.yaml
    p = tmp_path / "vocab.yaml"
    monkeypatch.setattr(
        "services.vocab_loader.data_path",
        lambda name: p,
    )

    # Existing on-disk categories (simulate a "real" file already in data/)
    existing = {
        "direction": ["=D1", "=D2"],
        "unassigned": [],
        "animals": ["=D10"],
        "colors": ["=D20"],
        "weather": ["=D30"],
    }
    with p.open("w", encoding="utf-8") as fh:
        yaml.safe_dump({"categories": existing, "entries": {}}, fh, allow_unicode=True, sort_keys=True)

    # Act: caller holds only a partial map + one new category
    incoming = {
        "colors": ["=D20", "=D21"],          # update existing
        "emotions_feelings": ["=D99"],       # add new
    }
    vocab_loader.persist_categories_block(incoming)  # must merge-on-write, not truncate

    # Assert: reload file and verify merge semantics
    with p.open("r", encoding="utf-8") as fh:
        merged = (yaml.safe_load(fh) or {}).get("categories")

    assert isinstance(merged, dict)

    # Preserved keys
    assert "direction" in merged
    assert "unassigned" in merged
    assert "animals" in merged
    assert "weather" in merged

    # Updated key
    assert "colors" in merged

    # New key
    assert "emotions_feelings" in merged

    # No truncation: original keys still there
    for k in existing.keys():
        assert k in merged


def test_save_categories_with_non_dict_is_noop(tmp_path, monkeypatch):
    """
    Best-effort contract: non-dict input should not crash and should not overwrite the file.
    """
    from services import vocab_loader

    p = tmp_path / "vocab.yaml"
    monkeypatch.setattr(
        "services.vocab_loader.data_path",
        lambda name: p,
    )

    existing = {"direction": ["=D1"], "unassigned": []}
    with p.open("w", encoding="utf-8") as fh:
        yaml.safe_dump({"categories": existing, "entries": {}}, fh, allow_unicode=True, sort_keys=True)

    # Act: non-dict input
    vocab_loader.persist_categories_block(None)  # type: ignore[arg-type]

    # Assert: file unchanged
    with p.open("r", encoding="utf-8") as fh:
        after = (yaml.safe_load(fh) or {}).get("categories")

    assert after == existing
