

"""Project storage path resolution.

Single source of truth for locating data files (YAML, indices, etc.).

Design goals
- UI-free and side-effect free.
- Tolerant: supports legacy root-level files while preferring `data/`.
- Explicit: callers should not guess paths ad-hoc.

This module is intentionally small; add new helpers only when multiple callers need them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class ProjectPaths:
    """Resolved project directories."""

    project_dir: Path
    data_dir: Path


def _project_dir_from_this_file() -> Path:
    # domain/storage_paths.py -> project root
    return Path(__file__).resolve().parent.parent


def get_project_paths(project_dir: Optional[Path] = None) -> ProjectPaths:
    """Return canonical project and data directories."""

    root = Path(project_dir).resolve() if project_dir else _project_dir_from_this_file()
    return ProjectPaths(project_dir=root, data_dir=root / "data")


def _first_existing(candidates: Iterable[Path]) -> Optional[Path]:
    for p in candidates:
        try:
            if p.exists():
                return p
        except Exception:
            continue
    return None


def resolve_data_file(
    filename: str,
    *,
    project_dir: Optional[Path] = None,
    prefer_data_dir: bool = True,
) -> Path:
    """Resolve a data file path.

    If the file exists in either `data/` or project root, return the existing one.
    If neither exists, return the preferred location (default: `data/filename`).
    """

    paths = get_project_paths(project_dir)
    in_data = paths.data_dir / filename
    in_root = paths.project_dir / filename

    ordered = (in_data, in_root) if prefer_data_dir else (in_root, in_data)
    found = _first_existing(ordered)
    if found is not None:
        return found

    # Not found: return preferred location
    return ordered[0]


# --- Specific well-known files ---

def categories_yaml_path(*, project_dir: Optional[Path] = None) -> Path:
    return resolve_data_file("categories.yaml", project_dir=project_dir, prefer_data_dir=True)

def _project_root() -> Path:
    """Return the project root directory (two levels above this file)."""
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    """Return the project's data directory."""
    return _project_root() / "data"


def andys_list_yaml_path() -> Path:
    """Preferred location for andys_list.yaml (supports legacy root fallback)."""
    p = data_dir() / "andys_list.yaml"
    if p.exists():
        return p
    return _project_root() / "andys_list.yaml"


def reverse_jyut_yaml_path() -> Path:
    """Location for the phrase reverse index (data/reverse_jyut.yaml)."""
    return data_dir() / "reverse_jyut.yaml"


def cedict_ts_path() -> Path | None:
    """Return the first existing CC-CEDICT file path, if available."""
    candidates = [
        data_dir() / "cedict" / "cedict_ts.u8",
        data_dir() / "CC-CEDICT" / "cedict_ts.u8",
        data_dir() / "cedict_ts.u8",
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


def unihan_dir(*, project_dir: Optional[Path] = None) -> Path:
    paths = get_project_paths(project_dir)
    # Keep Unihan under data/Unihan
    return paths.data_dir / "Unihan"

from typing import Callable, Dict, List


def load_reverse_jyut_map(path, *, normalize_key: Callable[[str], str]) -> Dict[str, List[str]]:
    """Load the phrase reverse index (Jyutping -> [Hanzi...]) from YAML.

    Tolerant: missing file or malformed YAML yields an empty dict.
    Keys are normalised with `normalize_key`.
    """
    try:
        if hasattr(path, "exists") and not path.exists():
            return {}
    except Exception:
        return {}

    try:
        import yaml
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    out: Dict[str, List[str]] = {}
    for k, v in data.items():
        try:
            kk = normalize_key(str(k))
            if not kk:
                continue

            if isinstance(v, list):
                vals = [str(x) for x in v if x]
            elif isinstance(v, str):
                vals = [v]
            else:
                vals = []

            if vals:
                out[kk] = vals
        except Exception:
            continue

    return out