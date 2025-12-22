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

    Accepts optional YAML files (merged in priority order):
      - data/reverse_manual.yaml (authoritative, curated overrides)
      - data/reverse_jyut.yaml   (bulk reverse map; generated)
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

        def _iter_pairs(m: dict):
            # Unwrap common one-key wrapper dicts like {"reverse": {...}} or {"index": {...}}
            try:
                if isinstance(m, dict) and len(m) == 1:
                    only_k = next(iter(m.keys()))
                    only_v = m.get(only_k)
                    if isinstance(only_v, dict):
                        return only_v.items()
            except Exception:
                pass
            return m.items()

        for jy, items in _iter_pairs(raw):
            try:
                jy_n = _norm_jyut_key(str(jy))
            except Exception:
                continue
            if not jy_n:
                continue

            # If items is itself a mapping of jyut->items (another wrapper level), merge recursively.
            if isinstance(items, dict):
                for sub_jy, sub_items in items.items():
                    try:
                        sub_jy_n = _norm_jyut_key(str(sub_jy))
                    except Exception:
                        continue
                    if not sub_jy_n:
                        continue
                    sub_lst = out.setdefault(sub_jy_n, [])
                    _added_any = False

                    if isinstance(sub_items, list):
                        for pos, it in enumerate(sub_items):
                            # Shape 1: dict entries
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
                                if tup not in sub_lst:
                                    sub_lst.append(tup)
                                    _added_any = True
                                continue

                            # Shape 2: plain string Hanzi
                            if isinstance(it, str):
                                hz = it.strip()
                                if not hz:
                                    continue
                                # Preserve list ordering by giving earlier items a higher score.
                                sc_i = max(0, 1000 - int(pos))
                                tup = (hz, tag, sc_i)
                                if tup not in sub_lst:
                                    sub_lst.append(tup)
                                    _added_any = True
                                continue

                            # Shape 3: small tuples/lists
                            if isinstance(it, (tuple, list)) and len(it) >= 1:
                                try:
                                    hz = str(it[0] or "").strip()
                                except Exception:
                                    hz = ""
                                if not hz:
                                    continue

                                src = tag
                                sc_i = max(0, 1000 - int(pos))

                                if len(it) == 2:
                                    # Could be (hanzi, score) or (hanzi, source)
                                    try:
                                        sc_i = int(round(float(it[1])))
                                    except Exception:
                                        try:
                                            src = str(it[1] or "").strip() or tag
                                        except Exception:
                                            src = tag
                                else:
                                    # (hanzi, source, score, ...)
                                    try:
                                        src = str(it[1] or "").strip() or tag
                                    except Exception:
                                        src = tag
                                    try:
                                        sc_i = int(round(float(it[2])))
                                    except Exception:
                                        sc_i = 0

                                tup = (hz, src, sc_i)
                                if tup not in sub_lst:
                                    sub_lst.append(tup)
                                    _added_any = True
                                continue

                        # Clean up empty key if nothing was added
                        if not _added_any and not sub_lst:
                            try:
                                out.pop(sub_jy_n, None)
                            except Exception:
                                pass
                        continue

                    if isinstance(sub_items, (tuple, set)):
                        for hz in sub_items:
                            s = str(hz).strip()
                            if s and (s, tag, 0) not in sub_lst:
                                sub_lst.append((s, tag, 0))
                                _added_any = True
                        if not _added_any and not sub_lst:
                            try:
                                out.pop(sub_jy_n, None)
                            except Exception:
                                pass
                        continue

                # Don't treat the wrapper key as a jyutping entry
                continue

            lst = out.get(jy_n)
            if not isinstance(lst, list):
                lst = []
                out[jy_n] = lst
            _added_any = False

            if isinstance(items, list):
                for pos, it in enumerate(items):
                    # Shape 1: dict entries
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
                            _added_any = True
                        continue

                    # Shape 2: plain string Hanzi
                    if isinstance(it, str):
                        hz = it.strip()
                        if not hz:
                            continue
                        # Preserve list ordering by giving earlier items a higher score.
                        sc_i = max(0, 1000 - int(pos))
                        tup = (hz, tag, sc_i)
                        if tup not in lst:
                            lst.append(tup)
                            _added_any = True
                        continue

                    # Shape 3: small tuples/lists
                    if isinstance(it, (tuple, list)) and len(it) >= 1:
                        try:
                            hz = str(it[0] or "").strip()
                        except Exception:
                            hz = ""
                        if not hz:
                            continue

                        src = tag
                        sc_i = max(0, 1000 - int(pos))

                        if len(it) == 2:
                            # Could be (hanzi, score) or (hanzi, source)
                            try:
                                sc_i = int(round(float(it[1])))
                            except Exception:
                                try:
                                    src = str(it[1] or "").strip() or tag
                                except Exception:
                                    src = tag
                        else:
                            # (hanzi, source, score, ...)
                            try:
                                src = str(it[1] or "").strip() or tag
                            except Exception:
                                src = tag
                            try:
                                sc_i = int(round(float(it[2])))
                            except Exception:
                                sc_i = 0

                        tup = (hz, src, sc_i)
                        if tup not in lst:
                            lst.append(tup)
                            _added_any = True
                        continue

                # If the list contained no usable items, remove any placeholder key.
                if not _added_any and not lst:
                    try:
                        out.pop(jy_n, None)
                    except Exception:
                        pass
                continue

            if isinstance(items, (tuple, set)):
                for hz in items:
                    s = str(hz).strip()
                    if s and (s, tag, 0) not in lst:
                        lst.append((s, tag, 0))
                        _added_any = True

            # Remove empty placeholders (prevents size=1 maps like {'reverse': []})
            if not _added_any and not lst:
                try:
                    out.pop(jy_n, None)
                except Exception:
                    pass

    _merge_from_yaml(os.path.join(base_dir, "data", "reverse_manual.yaml"), tag="reverse_manual")
    _merge_from_yaml(os.path.join(base_dir, "data", "reverse_jyut.yaml"), tag="reverse_jyut")
    _merge_from_yaml(os.path.join(base_dir, "data", "reverse_cache.yaml"), tag="reverse_cache")

    _merge_from_yaml(os.path.join(base_dir, "reverse_manual.yaml"), tag="reverse_manual")
    _merge_from_yaml(os.path.join(base_dir, "reverse_jyut.yaml"), tag="reverse_jyut")
    _merge_from_yaml(os.path.join(base_dir, "reverse_cache.yaml"), tag="reverse_cache")

    return out