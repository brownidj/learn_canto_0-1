"""Project storage path resolution (known files)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from domain.storage_paths_core import get_project_paths, resolve_data_file, resolve_first_existing_data_file


# --- Meaning source datasets ---


def cccanto_meanings_map_path(*, project_dir: Optional[Path] = None) -> Optional[Path]:
    """Best-effort location of the CC-Canto meanings map."""
    return resolve_first_existing_data_file(
        [
            "cccanto_meanings_map.yaml",
            "cccanto_meanings.yaml",
            "cccanto_meanings.yml",
        ],
        project_dir=project_dir,
        prefer_data_dir=True,
    )


def cedict_meanings_map_json_path(*, project_dir: Optional[Path] = None) -> Optional[Path]:
    """Best-effort location of a JSON CEDICT meanings map."""
    return resolve_first_existing_data_file(
        [
            "cedict_meanings_map.json",
            "cedict_meanings.json",
        ],
        project_dir=project_dir,
        prefer_data_dir=True,
    )


def cedict_meanings_map_yaml_path(*, project_dir: Optional[Path] = None) -> Optional[Path]:
    """Best-effort location of a YAML CEDICT meanings map."""
    return resolve_first_existing_data_file(
        [
            "cedict_meanings_map.yaml",
            "cedict_meanings.yaml",
            "cedict_meanings.yml",
        ],
        project_dir=project_dir,
        prefer_data_dir=True,
    )




def data_dir(*, project_dir: Optional[Path] = None) -> Path:
    """Return the project's data directory."""
    paths = get_project_paths(project_dir)
    return paths.data_dir


def andys_list_yaml_path(*, project_dir: Optional[Path] = None) -> Path:
    """Preferred location for andys_list.yaml (supports legacy root fallback)."""
    paths = get_project_paths(project_dir)
    p = paths.data_dir / "andys_list.yaml"
    if p.exists():
        return p
    return paths.project_dir / "andys_list.yaml"


def reverse_jyut_yaml_path(*, project_dir: Optional[Path] = None) -> Path:
    """Location for the phrase reverse index (data/reverse_jyut.yaml)."""
    return data_dir(project_dir=project_dir) / "reverse_jyut.yaml"


def cedict_ts_path(*, project_dir: Optional[Path] = None) -> Path | None:
    """Return the first existing CC-CEDICT file path, if available."""
    base = data_dir(project_dir=project_dir)
    candidates = [
        base / "cedict" / "cedict_ts.u8",
        base / "CC-CEDICT" / "cedict_ts.u8",
        base / "cedict_ts.u8",
        base / "cedict_1_0_ts_utf-8_mdbg.txt",
        base / "cedict" / "cedict_1_0_ts_utf-8_mdbg.txt",
    ]
    for p in candidates:
        try:
            if p.exists():
                return p
        except Exception:
            continue
    return None


def vocab_yaml_path(*, project_dir: Optional[Path] = None) -> Path:
    return resolve_data_file("vocab.yaml", project_dir=project_dir, prefer_data_dir=True)


def reverse_manual_yaml_path(*, project_dir: Optional[Path] = None) -> Path:
    return resolve_data_file("reverse_manual.yaml", project_dir=project_dir, prefer_data_dir=True)


def cedict_path(*, project_dir: Optional[Path] = None) -> Path:
    return resolve_data_file("cedict_ts.u8", project_dir=project_dir, prefer_data_dir=True)


def cantonese_language_cache_path(*, project_dir: Optional[Path] = None) -> Path:
    """Cache for Cantonese language service lookups."""
    return resolve_data_file("cantonese_language_cache.json", project_dir=project_dir, prefer_data_dir=True)


def unihan_dir(*, project_dir: Optional[Path] = None) -> Path:
    paths = get_project_paths(project_dir)
    return paths.data_dir / "Unihan"
