def test_persist_categories_does_not_truncate_existing(tmp_path, monkeypatch):
    from services import vocab_loader
    import yaml

    # Arrange: fake vocab.yaml with many categories
    p = tmp_path / "vocab.yaml"
    monkeypatch.setattr(
        "services.vocab_loader.data_path",
        lambda name: p,
    )

    original = {"animals": {}, "verbs": {}, "emotions": {}, "work": {}}

    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump({"categories": original, "entries": {}}, f)

    # Act: persist a *partial* map
    vocab_loader.persist_categories_block({
        "work": ["返工"],
    })

    # Assert: nothing else was lost
    with p.open("r", encoding="utf-8") as f:
        merged = (yaml.safe_load(f) or {}).get("categories")

    assert set(merged.keys()) == set(original.keys())
