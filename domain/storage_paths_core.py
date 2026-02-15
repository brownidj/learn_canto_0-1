"""Project storage path resolution (core)."""

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
    # domain/storage_paths_core.py -> project root
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


def resolve_first_existing_data_file(
    filenames: Iterable[str],
    *,
    project_dir: Optional[Path] = None,
    prefer_data_dir: bool = True,
) -> Optional[Path]:
    """Return the first existing data file among multiple candidate filenames.

    Unlike `resolve_data_file`, this returns None when nothing exists.
    """
    paths = get_project_paths(project_dir)

    def _ordered_paths(name: str) -> tuple[Path, Path]:
        in_data = paths.data_dir / name
        in_root = paths.project_dir / name
        return (in_data, in_root) if prefer_data_dir else (in_root, in_data)

    for name in filenames:
        try:
            n = str(name).strip()
        except Exception:
            continue
        if not n:
            continue

        p1, p2 = _ordered_paths(n)
        for p in (p1, p2):
            try:
                if p.exists() and p.is_file():
                    return p
            except Exception:
                continue

    return None
