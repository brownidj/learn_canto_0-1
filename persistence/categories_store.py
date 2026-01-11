

"""categories_store.py

This module is the single source of truth for category persistence.
It is responsible for loading and saving the categories.yaml file.
It must not import any UI or Qt code.
"""

# --- Category persistence API ---
from typing import Dict, Any
from pathlib import Path
import yaml
from domain.storage_paths import categories_yaml_path

# Public type alias for categories map
CatsMap = Dict[str, Any]

def load_categories() -> CatsMap:
    """
    Load the categories.yaml file and return its contents as a dict.
    Returns an empty dict if the file does not exist.
    Raises TypeError if the file does not contain a mapping.
    """
    path = categories_yaml_path()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        obj = yaml.safe_load(f)
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise TypeError("categories.yaml must contain a mapping (dict)")
    return dict(obj)

def save_categories(cats: CatsMap) -> None:
    """
    Save the given categories map to categories.yaml.
    Ensures the parent directory exists.
    """
    path = categories_yaml_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cats, f, allow_unicode=True, sort_keys=True)