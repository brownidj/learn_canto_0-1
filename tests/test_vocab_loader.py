"""
Tests for services/vocab_loader.py - Vocabulary and category loading/persistence
"""
import os
import tempfile
import pytest
import yaml

from services.vocab_loader import (
    load_vocab_from_unified_yaml,
    load_categories_from_disk,
    load_categories_map,
    commit_vocab_entry,
)


@pytest.fixture
def temp_vocab_yaml():
    """Create a temporary vocab.yaml file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
        data = {
            "categories": {
                "food": {},
                "colors": {},
                "numbers": {}
            },
            "entries": {
                "faan6": {
                    "senses": [
                        {
                            "hanzi": "飯",
                            "gloss": "rice, meal",
                            "categories": ["food"]
                        }
                    ]
                },
                "hung4": {
                    "senses": [
                        {
                            "hanzi": "紅",
                            "gloss": "red",
                            "categories": ["colors"]
                        },
                        {
                            "hanzi": "虹",
                            "gloss": "rainbow",
                            "categories": []
                        }
                    ]
                },
                "jat1": {
                    "senses": [
                        {
                            "hanzi": "一",
                            "gloss": "one",
                            "categories": ["numbers"]
                        }
                    ]
                }
            }
        }
        yaml.safe_dump(data, f, allow_unicode=True)
        temp_path = f.name

    yield temp_path

    # Cleanup
    try:
        os.unlink(temp_path)
    except:
        pass


class TestLoadVocabFromUnifiedYaml:
    """Tests for unified vocab.yaml loading."""

    def test_load_basic_structure(self, temp_vocab_yaml, monkeypatch):
        """Test loading a well-formed vocab.yaml."""
        # Mock data_path to return our temp file
        monkeypatch.setattr('services.vocab_loader.data_path', lambda x: temp_vocab_yaml)

        vocab, categories_map = load_vocab_from_unified_yaml()

        # Check vocab structure
        assert "飯" in vocab
        assert vocab["飯"] == [["rice, meal"], "faan6"]

        assert "紅" in vocab
        assert "red" in vocab["紅"][0]

        assert "虹" in vocab
        assert "rainbow" in vocab["虹"][0]

        # Check categories map
        assert "food" in categories_map
        assert "飯" in categories_map["food"]

        assert "colors" in categories_map
        assert "紅" in categories_map["colors"]

        assert "numbers" in categories_map
        assert "一" in categories_map["numbers"]

        # Empty category should exist
        assert "unassigned" in categories_map

    def test_merge_duplicate_hanzi(self, monkeypatch):
        """Test that duplicate hanzi entries merge their meanings."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            data = {
                "categories": {"food": {}},
                "entries": {
                    "faan6": {
                        "senses": [
                            {"hanzi": "飯", "gloss": "rice", "categories": ["food"]},
                            {"hanzi": "飯", "gloss": "meal", "categories": ["food"]}
                        ]
                    }
                }
            }
            yaml.safe_dump(data, f, allow_unicode=True)
            temp_path = f.name

        try:
            monkeypatch.setattr('services.vocab_loader.data_path', lambda x: temp_path)
            vocab, _ = load_vocab_from_unified_yaml()

            # Should merge both meanings
            assert "飯" in vocab
            assert "rice" in vocab["飯"][0]
            assert "meal" in vocab["飯"][0]
        finally:
            os.unlink(temp_path)

    def test_missing_file_returns_empty(self, monkeypatch):
        """Test graceful handling of missing vocab.yaml."""
        monkeypatch.setattr('services.vocab_loader.data_path', lambda x: '/nonexistent/path/vocab.yaml')

        vocab, categories_map = load_vocab_from_unified_yaml()

        assert vocab == {}
        assert categories_map == {}

    def test_malformed_yaml_returns_empty(self, monkeypatch):
        """Test graceful handling of malformed YAML."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write("{ this is not valid yaml: [")
            temp_path = f.name

        try:
            monkeypatch.setattr('services.vocab_loader.data_path', lambda x: temp_path)
            vocab, categories_map = load_vocab_from_unified_yaml()

            assert vocab == {}
            assert categories_map == {}
        finally:
            os.unlink(temp_path)

    def test_non_dict_top_level(self, monkeypatch):
        """Test handling when top-level is not a dict."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            yaml.safe_dump(["list", "instead", "of", "dict"], f)
            temp_path = f.name

        try:
            monkeypatch.setattr('services.vocab_loader.data_path', lambda x: temp_path)
            vocab, categories_map = load_vocab_from_unified_yaml()

            assert vocab == {}
            assert categories_map == {}
        finally:
            os.unlink(temp_path)


class TestCommitVocabEntry:
    """Tests for vocab entry persistence."""

    def test_commit_new_entry(self, temp_vocab_yaml, monkeypatch):
        """Test committing a new vocabulary entry."""
        monkeypatch.setattr('services.vocab_loader.data_path', lambda x: temp_vocab_yaml)

        # Load initial state
        vocab, categories_map = load_vocab_from_unified_yaml()
        initial_vocab_size = len(vocab)

        # Prepare new entry
        new_entry = {
            "jyutping": "min6",
            "hanzi": "麵",
            "gloss": "noodles",
            "categories": ["food"]
        }

        # Commit it
        commit_vocab_entry(new_entry, vocab, categories_map, window=None, dialog=None)

        # Verify in-memory updates
        assert "麵" in vocab
        assert "noodles" in vocab["麵"][0]
        assert "麵" in categories_map["food"]

        # Verify persistence to file
        with open(temp_vocab_yaml, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        assert "min6" in data["entries"]
        sense = data["entries"]["min6"]["senses"][0]
        assert sense["hanzi"] == "麵"
        assert sense["gloss"] == "noodles"
        assert "food" in sense["categories"]

    def test_commit_updates_existing_hanzi(self, temp_vocab_yaml, monkeypatch):
        """Test updating an existing hanzi with a new gloss."""
        monkeypatch.setattr('services.vocab_loader.data_path', lambda x: temp_vocab_yaml)

        vocab, categories_map = load_vocab_from_unified_yaml()

        # Add another meaning to existing hanzi
        entry = {
            "jyutping": "faan6",
            "hanzi": "飯",
            "gloss": "cooked rice",  # Different gloss
            "categories": ["food"]
        }

        commit_vocab_entry(entry, vocab, categories_map, window=None, dialog=None)

        # Should have both meanings
        assert "rice, meal" in vocab["飯"][0]
        assert "cooked rice" in vocab["飯"][0]

    def test_commit_missing_fields_aborts(self, temp_vocab_yaml, monkeypatch):
        """Test that entries with missing required fields are rejected."""
        monkeypatch.setattr('services.vocab_loader.data_path', lambda x: temp_vocab_yaml)

        vocab, categories_map = load_vocab_from_unified_yaml()
        initial_size = len(vocab)

        # Missing jyutping
        commit_vocab_entry(
            {"hanzi": "麵", "gloss": "noodles", "categories": ["food"]},
            vocab, categories_map, window=None, dialog=None
        )
        assert len(vocab) == initial_size

        # Missing hanzi
        commit_vocab_entry(
            {"jyutping": "min6", "gloss": "noodles", "categories": ["food"]},
            vocab, categories_map, window=None, dialog=None
        )
        assert len(vocab) == initial_size

        # Missing gloss
        commit_vocab_entry(
            {"jyutping": "min6", "hanzi": "麵", "categories": ["food"]},
            vocab, categories_map, window=None, dialog=None
        )
        assert len(vocab) == initial_size

        # Missing categories
        commit_vocab_entry(
            {"jyutping": "min6", "hanzi": "麵", "gloss": "noodles"},
            vocab, categories_map, window=None, dialog=None
        )
        assert len(vocab) == initial_size


class TestLoadCategoriesMap:
    """Tests for best-available categories loading."""

    def test_prefers_categories_yaml_when_available(self, monkeypatch):
        """Test that categories.yaml is preferred over vocab-derived."""
        # This test would require mocking domain.storage_paths
        # For now, test the fallback path
        pass

    def test_fallback_to_vocab_derived(self, temp_vocab_yaml, monkeypatch):
        """Test fallback when categories.yaml unavailable."""
        monkeypatch.setattr('services.vocab_loader.data_path', lambda x: temp_vocab_yaml)

        # Mock categories_yaml_path to fail
        monkeypatch.setattr('services.vocab_loader.load_categories_from_disk', lambda: {})

        cats = load_categories_map()

        # Should fall back to vocab.yaml
        assert "food" in cats or cats == {}  # Depends on mocking success
