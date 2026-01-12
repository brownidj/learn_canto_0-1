"""categories_store.py

This module is the single source of truth for category persistence.
It is responsible for loading and saving the categories.yaml file.
It must not import any UI or Qt code.
"""

# --- Category persistence API ---
from typing import Dict, Any
import yaml
import logging
import domain.storage_paths as _paths

logger = logging.getLogger(__name__)
# Public type alias for categories map
CatsMap = Dict[str, Any]

def load_categories() -> CatsMap:
    """
    Load the categories.yaml file and return its contents as a dict.
    Returns an empty dict if the file does not exist.
    Raises TypeError if the file does not contain a mapping.
    """
    path = _paths.categories_yaml_path()
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

    Safety-by-construction: merge-on-write.
      - Reads existing categories.yaml first (if present)
      - Overlays/updates keys from `cats`
      - Preserves existing keys not present in `cats`
      - For list values, appends new items (deduped) instead of replacing

    This prevents accidental truncation when callers hold a partial in-memory map.
    """
    path = _paths.categories_yaml_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing mapping (best-effort)
    existing: CatsMap = {}
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                obj = yaml.safe_load(f)
            if isinstance(obj, dict):
                existing = dict(obj)
    except Exception:
        # If we cannot load the existing file, do not risk overwriting it.
        return

    def _as_list(v: Any) -> list:
        if v is None:
            return []
        if isinstance(v, list):
            return list(v)
        try:
            return list(v)
        except Exception:
            return [str(v)]

    merged: CatsMap = dict(existing)

    # Overlay merge (append for lists)
    for k, v in (cats or {}).items():
        try:
            key = str(k).strip()
        except Exception:
            key = ""
        if not key:
            continue

        incoming = _as_list(v)

        prev = merged.get(key)
        if isinstance(prev, list):
            out = list(prev)
            for item in incoming:
                if item not in out:
                    out.append(item)
            merged[key] = out
        else:
            merged[key] = incoming

    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(merged, f, allow_unicode=True, sort_keys=True)

def persist_categories_yaml(cats_map: dict) -> None:
    save_categories(cats_map)