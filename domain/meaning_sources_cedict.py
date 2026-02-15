"""CC-CEDICT meaning source loading."""

from __future__ import annotations

from typing import Sequence

from domain.storage_paths import (
    cedict_meanings_map_json_path,
    cedict_meanings_map_yaml_path,
    cedict_ts_path as _cedict_ts_path,
)
from domain.meaning_sources_utils import _load_json_dict, _load_yaml_dict

_CEDICT_MEANINGS_MAP: dict[str, list[str]] | None = None


def reset_cedict_cache() -> None:
    global _CEDICT_MEANINGS_MAP
    _CEDICT_MEANINGS_MAP = None


def cedict_ts_path():
    """Return the first existing CC-CEDICT source file path, if available."""
    try:
        return _cedict_ts_path()
    except Exception:
        return None


def _get_cedict_meanings_map(*, project_dir=None) -> dict[str, list[str]]:
    global _CEDICT_MEANINGS_MAP
    if isinstance(_CEDICT_MEANINGS_MAP, dict) and _CEDICT_MEANINGS_MAP:
        return _CEDICT_MEANINGS_MAP

    p_yaml = cedict_meanings_map_yaml_path(project_dir=project_dir)
    if p_yaml and p_yaml.exists():
        data = _load_yaml_dict(p_yaml)
        if isinstance(data, dict):
            _CEDICT_MEANINGS_MAP = data
            return data

    p_json = cedict_meanings_map_json_path(project_dir=project_dir)
    if p_json and p_json.exists():
        data = _load_json_dict(p_json)
        if isinstance(data, dict):
            _CEDICT_MEANINGS_MAP = data
            return data

    p_raw = _cedict_ts_path()
    if p_raw and p_raw.exists():
        out3: dict[str, list[str]] = {}
        try:
            import re
            pat = re.compile(r"^([^\s]+)\s+([^\s]+)\s+\[[^]]*]\s+/(.+)/\s*$")
            with p_raw.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    s = line.strip()
                    if not s or s.startswith("#"):
                        continue
                    m = pat.match(s)
                    if not m:
                        continue
                    trad = m.group(1)
                    simp = m.group(2)
                    defs_raw = m.group(3)
                    defs = [d.strip() for d in defs_raw.split("/") if d.strip()]
                    if defs:
                        out3[trad] = defs
                        out3[simp] = defs
        except Exception:
            out3 = {}

        _CEDICT_MEANINGS_MAP = out3
        return out3

    _CEDICT_MEANINGS_MAP = {}
    return {}


def _cedict_meanings_for(hz: str) -> Sequence[str]:
    mp = _get_cedict_meanings_map()
    try:
        val = mp.get(hz)
        return val if isinstance(val, list) else []
    except Exception:
        return []


def get_cedict_meanings_for(hanzi: str) -> list[str]:
    """Public wrapper for CEDICT meanings (back-compat)."""
    try:
        return list(_cedict_meanings_for(hanzi) or [])
    except Exception:
        return []
