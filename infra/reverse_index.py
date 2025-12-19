from __future__ import annotations

import os
from typing import Dict, List, Tuple, Union

import yaml

ReverseIndex = Dict[str, List[Tuple[str, str, int]]]


def _norm_jyut_key(jy: str) -> str:
    """Normalize Jyutping keys for indexing."""
    try:
        return " ".join((jy or "").strip().lower().split())
    except Exception:
        return (jy or "").strip().lower()


def load_reverse_index_files(project_dir: Union[str, os.PathLike]) -> ReverseIndex:
    """Load reverse indices from optional YAML files.

    Accepts two optional files:
      - data/reverse_manual.yaml (authoritative, multi-candidate per jyut)
      - data/reverse_cache.yaml  (memoized fallback from previous runs)

    Returns:
      {jyut -> [(hanzi, source, score_int), ...]}

    Never raises; returns {} on failure.
    """
    base_dir = os.fspath(project_dir)
    out: ReverseIndex = {}

    def _merge_from_yaml(path: str, tag: str) -> None:
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        except Exception:
            return
        if not isinstance(raw, dict):
            return

        for jy, items in raw.items():
            try:
                jy_n = _norm_jyut_key(str(jy))
            except Exception:
                continue
            if not jy_n:
                continue
            lst = out.setdefault(jy_n, [])

            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict):
                        hz = str(it.get("hanzi", "")).strip()
                        if not hz:
                            continue
                        src = str(it.get("source", tag)).strip() or tag
                        sc = it.get("score", 0)
                        try:
                            sc_i = int(round(float(sc)))
                        except Exception:
                            sc_i = 0
                        tup = (hz, src, sc_i)
                        if tup not in lst:
                            lst.append(tup)
                continue

            if isinstance(items, (tuple, set)):
                for hz in items:
                    s = str(hz).strip()
                    if s and (s, tag, 0) not in lst:
                        lst.append((s, tag, 0))

    _merge_from_yaml(os.path.join(base_dir, "data", "reverse_manual.yaml"), tag="reverse_manual")
    _merge_from_yaml(os.path.join(base_dir, "data", "reverse_cache.yaml"), tag="reverse_cache")
    _merge_from_yaml(os.path.join(base_dir, "reverse_manual.yaml"), tag="reverse_manual")
    _merge_from_yaml(os.path.join(base_dir, "reverse_cache.yaml"), tag="reverse_cache")

    return out