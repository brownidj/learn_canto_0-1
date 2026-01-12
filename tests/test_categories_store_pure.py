# tests/test_categories_store_pure.py
import yaml


def test_save_categories_merge_on_write_preserves_existing_and_adds_new(tmp_path, monkeypatch):
    """
    Contract: save_categories() must be merge-on-write.
      - preserves existing keys on disk that are not present in the input map
      - updates keys that are present in the input map
      - adds brand-new keys from the input map
    """
    import persistence.categories_store as cs

    # Arrange: point categories_yaml_path() at a temp file
    p = tmp_path / "categories.yaml"

    def _fake_categories_yaml_path(*args, **kwargs):
        return p

    monkeypatch.setattr(
        "domain.storage_paths.categories_yaml_path",
        _fake_categories_yaml_path,
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
        yaml.safe_dump(existing, fh, allow_unicode=True, sort_keys=True)

    # Act: caller holds only a partial map + one new category
    incoming = {
        "colors": ["=D20", "=D21"],          # update existing
        "emotions_feelings": ["=D99"],       # add new
    }
    cs.save_categories(incoming)  # must merge-on-write, not truncate

    # Assert: reload file and verify merge semantics
    with p.open("r", encoding="utf-8") as fh:
        merged = yaml.safe_load(fh)

    assert isinstance(merged, dict)

    # Preserved keys
    assert "direction" in merged
    assert "unassigned" in merged
    assert "animals" in merged
    assert "weather" in merged

    # Updated key
    assert merged.get("colors") == ["=D20", "=D21"]

    # New key
    assert merged.get("emotions_feelings") == ["=D99"]

    # No truncation: original keys still there
    for k in existing.keys():
        assert k in merged


def test_save_categories_with_non_dict_is_noop(tmp_path, monkeypatch):
    """
    Best-effort contract: non-dict input should not crash and should not overwrite the file.
    """
    import persistence.categories_store as cs

    p = tmp_path / "categories.yaml"

    def _fake_categories_yaml_path(*args, **kwargs):
        return p

    monkeypatch.setattr(
        "domain.storage_paths.categories_yaml_path",
        _fake_categories_yaml_path,
    )

    existing = {"direction": ["=D1"], "unassigned": []}
    with p.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(existing, fh, allow_unicode=True, sort_keys=True)

    # Act: non-dict input
    cs.save_categories(None)  # type: ignore[arg-type]

    # Assert: file unchanged
    with p.open("r", encoding="utf-8") as fh:
        after = yaml.safe_load(fh)

    assert after == existing