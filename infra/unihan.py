from __future__ import annotations

import json
import os
from typing import Dict, List, Union

UnihanCharMap = Dict[str, List[str]]


def load_unihan_char_map(project_dir: Union[str, os.PathLike]) -> UnihanCharMap:
    """Load and normalize the Unihan Cantonese char map JSON.

    Expected default location:
      data/Unihan/unihan_cantonese_chars.json

    Returns:
      {single_hanzi_char: [jyutping_syllables...]}

    Never raises; returns {} on failure.
    """
    base_dir = os.fspath(project_dir)
    json_path = os.path.join(base_dir, "data", "Unihan", "unihan_cantonese_chars.json")
    if not os.path.exists(json_path):
        return {}

    try:
        with open(json_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    norm: UnihanCharMap = {}
    for ch, vals in raw.items():
        if not ch or not isinstance(ch, str) or len(ch) != 1:
            continue

        try:
            if isinstance(vals, str):
                items = [vals]
            elif isinstance(vals, (list, tuple, set)):
                items = [str(v) for v in vals if v is not None]
            else:
                items = [str(vals)]
        except Exception:
            continue

        cleaned: List[str] = []
        for v in items:
            s = str(v).strip()
            if s:
                cleaned.append(s)

        if cleaned:
            norm[ch] = cleaned

    return norm