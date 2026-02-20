import yaml


def test_load_categories_map_uses_vocab_yaml(tmp_path, monkeypatch):
    from services import vocab_loader

    p = tmp_path / "vocab.yaml"
    monkeypatch.setattr(
        "services.vocab_loader.data_path",
        lambda name: p,
    )

    payload = {
        "categories": {
            "animals": {},
            "numbers": {},
        },
        "entries": {},
    }
    with p.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=True)

    cats = vocab_loader.load_categories_map()
    assert isinstance(cats, dict)
    assert set(cats.keys()) == {"animals", "numbers", "unassigned"}


def test_persist_categories_block_adds_missing(tmp_path, monkeypatch):
    from services import vocab_loader

    p = tmp_path / "vocab.yaml"
    monkeypatch.setattr(
        "services.vocab_loader.data_path",
        lambda name: p,
    )

    payload = {
        "categories": {"animals": {}},
        "entries": {},
    }
    with p.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=True)

    vocab_loader.persist_categories_block(["animals", "colors"])

    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    cats = data.get("categories") or {}
    assert "animals" in cats
    assert "colors" in cats
