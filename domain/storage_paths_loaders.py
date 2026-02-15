"""Loaders for data files resolved by storage_paths."""

from __future__ import annotations

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
