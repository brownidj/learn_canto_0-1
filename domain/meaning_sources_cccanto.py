"""CC-Canto meaning source loading."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from domain.storage_paths import cccanto_meanings_map_path, resolve_first_existing_data_file
from domain.meaning_sources_utils import _load_yaml_dict

_CC_CANTO_MEANINGS_MAP: dict[str, list[str]] | None = None


def reset_cccanto_cache() -> None:
    global _CC_CANTO_MEANINGS_MAP
    _CC_CANTO_MEANINGS_MAP = None


def _cccanto_raw_path(*, project_dir: Path | None = None) -> Path | None:
    """Return the CCCanto raw source file path (best-effort)."""
    try:
        return resolve_first_existing_data_file(
            [
                "cccanto.txt",
                "cccanto.u8",
                "cccanto.tsv",
                "cccanto.csv",
            ],
            project_dir=project_dir,
            prefer_data_dir=True,
        )
    except Exception:
        return None


def _get_cc_canto_meanings_map(*, project_dir: Path | None = None) -> dict[str, list[str]]:
    global _CC_CANTO_MEANINGS_MAP
    if isinstance(_CC_CANTO_MEANINGS_MAP, dict) and _CC_CANTO_MEANINGS_MAP:
        return _CC_CANTO_MEANINGS_MAP

    p_map = cccanto_meanings_map_path(project_dir=project_dir)
    if p_map and p_map.exists():
        data = _load_yaml_dict(p_map)
        if isinstance(data, dict):
            _CC_CANTO_MEANINGS_MAP = data
            return data

    p_raw = _cccanto_raw_path(project_dir=project_dir)
    if p_raw and p_raw.exists():
        out2: dict[str, list[str]] = {}
        try:
            with p_raw.open("r", encoding="utf-8", errors="ignore") as fh:
                import re

                pat = re.compile(r"^([^\s]+)\s+([^\s]+)\s+\[[^]]*]\s+\{[^}]*}\s+/(.+)/\s*$")

                for line in fh:
                    s = line.strip()
                    if not s or s.startswith("#"):
                        continue

                    hanzi: str | None = None
                    defs_raw: str | None = None

                    if "\t" in s:
                        parts = s.split("\t")
                        if len(parts) >= 2:
                            hanzi = parts[0].strip()
                            defs_raw = parts[-1].strip()
                    else:
                        m = pat.match(s)
                        if m:
                            trad = m.group(1).strip()
                            simp = m.group(2).strip()
                            defs_raw = m.group(3).strip()
                            hanzi = trad

                    if not hanzi or not defs_raw:
                        continue

                    items = [x.strip() for x in defs_raw.replace("/", ";").split(";") if x.strip()]
                    if not items:
                        continue

                    out2[hanzi] = items

                    if "\t" not in s:
                        try:
                            if m:
                                simp_key = m.group(2).strip()
                                if simp_key and simp_key != hanzi:
                                    out2[simp_key] = items
                        except Exception:
                            pass
        except Exception:
            out2 = {}

        _CC_CANTO_MEANINGS_MAP = out2
        return out2

    _CC_CANTO_MEANINGS_MAP = {}
    return {}


def _cc_glosses_for(hz: str) -> Sequence[str]:
    mp = _get_cc_canto_meanings_map()
    try:
        val = mp.get(hz)
        return val if isinstance(val, list) else []
    except Exception:
        return []


def get_cccanto_glosses_for(hanzi: str) -> list[str]:
    """Public wrapper for CC-Canto glosses (back-compat)."""
    try:
        return list(_cc_glosses_for(hanzi) or [])
    except Exception:
        return []
