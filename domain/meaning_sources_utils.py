"""Utilities for meaning source files and path discovery."""

from __future__ import annotations

import json
from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore[assignment]


def _project_root() -> Path:
    """Best-effort project root: assumes `domain/` lives directly under root."""
    try:
        return Path(__file__).resolve().parents[1]
    except Exception:
        return Path(".")


def _as_path(p: object) -> Path | None:
    """Coerce a candidate path (Path/str) to Path if possible."""
    if isinstance(p, Path):
        return p
    if isinstance(p, str) and p.strip():
        try:
            return Path(p)
        except Exception:
            return None
    return None


def _discover_best_under_data(*, patterns: list[str], exts: tuple[str, ...]) -> Path | None:
    """Heuristic: find a likely meanings-map file under <root>/data."""
    try:
        root = _project_root()
        data_dir = root / "data"
        if not data_dir.exists() or not data_dir.is_dir():
            return None

        hits: list[Path] = []
        for p in data_dir.rglob("*"):
            try:
                if not p.is_file():
                    continue
                if p.suffix.lower() not in exts:
                    continue
                name = p.name.lower()
                if all(tok in name for tok in patterns):
                    hits.append(p)
            except Exception:
                continue

        if not hits:
            return None

        hits.sort(key=lambda x: (x.stat().st_size if x.exists() else 0), reverse=True)
        return hits[0]
    except Exception:
        return None


def _first_existing_path(candidates: list[Path]) -> Path | None:
    for p in candidates:
        try:
            if p.exists() and p.is_file():
                return p
        except Exception:
            pass
    return None


def _load_yaml_dict(path: Path) -> dict[str, list[str]]:
    if yaml is None:
        return {}
    try:
        obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in obj.items():
        if not isinstance(k, str):
            continue
        if isinstance(v, list):
            out[k] = [str(x).strip() for x in v if str(x).strip()]
        elif isinstance(v, str) and v.strip():
            out[k] = [v.strip()]
    return out


def _load_json_dict(path: Path) -> dict[str, list[str]]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in obj.items():
        if not isinstance(k, str):
            continue
        if isinstance(v, list):
            out[k] = [str(x).strip() for x in v if str(x).strip()]
        elif isinstance(v, str) and v.strip():
            out[k] = [v.strip()]
    return out
