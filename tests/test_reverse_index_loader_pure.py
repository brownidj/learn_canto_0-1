"""Pure tests for infra.reverse_index.load_reverse_index_files.

These tests deliberately avoid any Qt/UI imports.

Contract:
- Loader merges optional YAML sources.
- Manual overrides have highest priority, then bulk reverse_jyut, then cache.
- Loader is resilient to common wrapper shapes and unsupported item shapes.
- Loader never leaves empty placeholder keys.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from infra.reverse_index import load_reverse_index_files


def _write_yaml(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=True)


def _load(tmp_path: Path):
    return load_reverse_index_files(tmp_path)


def test_reverse_index_empty_when_no_files(tmp_path):
    assert _load(tmp_path) == {}


def test_reverse_index_loads_manual_file(tmp_path):
    payload = {
        "ngan4": [
            {"hanzi": "銀", "score": 100},
            {"hanzi": "银", "score": 50},
        ]
    }
    _write_yaml(tmp_path / "data" / "reverse_manual.yaml", payload)

    out = _load(tmp_path)

    assert out["ngan4"] == [
        ("銀", "reverse_manual", 100),
        ("银", "reverse_manual", 50),
    ]


def test_reverse_index_loads_reverse_jyut_file(tmp_path):
    """Loader should merge data/reverse_jyut.yaml (bulk generated map)."""
    payload = {
        "ngan4": [
            {"hanzi": "銀", "score": 50},
        ]
    }
    _write_yaml(tmp_path / "data" / "reverse_jyut.yaml", payload)

    out = _load(tmp_path)

    assert "ngan4" in out
    assert out["ngan4"] == [("銀", "reverse_jyut", 50)]


def test_reverse_index_merges_multiple_files_and_dedupes(tmp_path):
    manual = {
        "ngan4": [
            {"hanzi": "銀", "score": 100},
        ]
    }
    bulk = {
        "ngan4": [
            {"hanzi": "銀", "score": 50},  # duplicate hanzi but different score/source
            {"hanzi": "银", "score": 40},
        ],
        "ceng1": [
            {"hanzi": "青", "score": 10},
        ],
    }
    cache = {
        "ngan4": [
            {"hanzi": "银", "score": 40},
        ]
    }

    _write_yaml(tmp_path / "data" / "reverse_manual.yaml", manual)
    _write_yaml(tmp_path / "data" / "reverse_jyut.yaml", bulk)
    _write_yaml(tmp_path / "data" / "reverse_cache.yaml", cache)

    out = _load(tmp_path)

    # Manual should come first; tuples are deduped by full (hz, source, score) tuple.
    assert out["ngan4"][0] == ("銀", "reverse_manual", 100)

    # Bulk and cache entries should still be present if they are not identical tuples.
    assert ("銀", "reverse_jyut", 50) in out["ngan4"]
    assert ("银", "reverse_jyut", 40) in out["ngan4"]
    assert ("银", "reverse_cache", 40) in out["ngan4"]

    assert out["ceng1"] == [("青", "reverse_jyut", 10)]


def test_reverse_index_unwraps_one_key_wrapper_dict(tmp_path):
    payload = {
        "reverse": {
            "ngan4": [
                {"hanzi": "銀", "score": 50},
            ]
        }
    }
    _write_yaml(tmp_path / "data" / "reverse_jyut.yaml", payload)

    out = _load(tmp_path)

    assert out["ngan4"] == [("銀", "reverse_jyut", 50)]


def test_reverse_index_ignores_unsupported_shapes(tmp_path):
    """Loader should ignore unsupported scalars and wrapper placeholders, without creating empty keys.

    Note: list-of-strings is a supported shape for reverse_jyut.yaml (bulk maps).
    """
    payload = {
        "ngan4": ["銀", "银"],  # supported (list-of-strings)
        "ceng1": 123,  # unsupported scalar
        "reverse": [],  # common bad wrapper placeholder
    }
    _write_yaml(tmp_path / "data" / "reverse_jyut.yaml", payload)

    out = _load(tmp_path)

    assert out.get("ngan4") == [("銀", "reverse_jyut", 1000), ("银", "reverse_jyut", 999)]
    assert "ceng1" not in out
    assert "reverse" not in out
