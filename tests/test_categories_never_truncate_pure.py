def test_persist_categories_does_not_truncate_existing(tmp_path, monkeypatch):
    from persistence import categories_store
    from domain.storage_paths import categories_yaml_path
    import yaml

    # Arrange: fake categories.yaml with many categories
    p = tmp_path / "categories.yaml"
    monkeypatch.setattr(
        "domain.storage_paths.categories_yaml_path",
        lambda: p,
    )

    original = {
        "animals": ["狗", "貓"],
        "verbs": ["食", "行"],
        "emotions": ["開心"],
        "work": ["做嘢"],
    }

    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(original, f)

    # Act: persist a *partial* map
    categories_store.persist_categories_yaml({
        "work": ["返工"],
    })

    # Assert: nothing else was lost
    with p.open("r", encoding="utf-8") as f:
        merged = yaml.safe_load(f)

    assert set(merged.keys()) == set(original.keys())
    assert "返工" in merged["work"]