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
    Persist categories.yaml using merge-on-write semantics.

    This is safe by construction: existing on-disk categories are preserved,
    and only keys present in `cats` are updated or added.
    """
    persist_categories_yaml_merge_on_write(cats)


def persist_categories_yaml_merge_on_write(cats_map: dict) -> None:
    """Persist categories.yaml using merge-on-write.

    This is intentionally defensive:
      - Reads existing categories.yaml first.
      - Overlays/updates keys from `cats_map`.
      - Preserves existing keys not present in `cats_map`.

    This prevents accidental truncation when callers hold a partial in-memory map.
    """
    if not isinstance(cats_map, dict):
        return

    # Resolve the authoritative on-disk path.
    try:
        p = categories_yaml_path()
    except (FileNotFoundError, PermissionError):
        return

    # Load existing YAML document.
    existing: dict[str, Any] = {}
    try:
        with open(p, "r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        if isinstance(doc, dict):
            existing = dict(doc)
    except FileNotFoundError:
        existing = {}
    except (PermissionError, yaml.YAMLError):
        # If load fails, do not attempt to write (best-effort contract).
        return

    # Overlay merge.
    merged: dict[str, Any] = dict(existing)
    for k, v in cats_map.items():
        try:
            key = str(k).strip()
        except (TypeError, ValueError):
            key = ""
        if not key:
            continue

        if isinstance(v, list):
            merged[key] = list(v)
        elif v is None:
            merged[key] = []
        else:
            # Defensive: coerce iterables to list; otherwise scalar to single-item list.
            try:
                merged[key] = list(v)
            except (TypeError, ValueError):
                merged[key] = [str(v)]

    # Ensure parent exists.
    try:
        Path(str(p)).parent.mkdir(parents=True, exist_ok=True)
    except (FileNotFoundError, PermissionError, OSError):
        pass

    # Write merged YAML back.
    try:
        with open(p, "w", encoding="utf-8") as fh:
            yaml.safe_dump(merged, fh, allow_unicode=True, sort_keys=True)
    except (PermissionError, yaml.YAMLError, OSError):
        return

def persist_categories_yaml(cats_map: dict) -> None:
    persist_categories_yaml_merge_on_write(cats_map)
