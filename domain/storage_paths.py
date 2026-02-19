"""Project storage path resolution.

Single source of truth for locating data files (YAML, indices, etc.).

Design goals
- UI-free and side-effect free.
- Tolerant: supports legacy root-level files while preferring `data/`.
- Explicit: callers should not guess paths ad-hoc.
"""

from __future__ import annotations

from domain.storage_paths_core import (
    ProjectPaths,
    get_project_paths,
    resolve_data_file,
    resolve_first_existing_data_file,
)
from domain.storage_paths_files import (
    andys_list_yaml_path,
    cantonese_language_cache_path,
    cccanto_meanings_map_path,
    cedict_meanings_map_json_path,
    cedict_meanings_map_yaml_path,
    cedict_path,
    cedict_ts_path,
    data_dir,
    reverse_jyut_yaml_path,
    reverse_manual_yaml_path,
    unihan_dir,
    vocab_yaml_path,
)
from domain.storage_paths_loaders import load_reverse_jyut_map

__all__ = [
    "ProjectPaths",
    "andys_list_yaml_path",
    "cantonese_language_cache_path",
    "cccanto_meanings_map_path",
    "cedict_meanings_map_json_path",
    "cedict_meanings_map_yaml_path",
    "cedict_path",
    "cedict_ts_path",
    "data_dir",
    "get_project_paths",
    "load_reverse_jyut_map",
    "resolve_data_file",
    "resolve_first_existing_data_file",
    "reverse_jyut_yaml_path",
    "reverse_manual_yaml_path",
    "unihan_dir",
    "vocab_yaml_path",
]
