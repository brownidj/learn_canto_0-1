"""Load HK word list data for candidate ranking (best-effort)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from infra.paths import data_path


def _detect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        return dialect.delimiter
    except Exception:
        return ","


def _first_nonempty(row: dict, keys: Iterable[str]) -> str:
    for k in keys:
        if k in row:
            v = str(row.get(k) or "").strip()
            if v:
                return v
    return ""


def load_words_hk(path: str | None = None) -> tuple[dict[str, float], set[str], set[str]]:
    """Return (freq_map, colloquial_set, attested_set) from words_hk.csv.

    - freq_map: word -> frequency score (higher = more common)
    - colloquial_set: word flagged as colloquial/spoken/HK
    - attested_set: word present in HK list
    """
    p = Path(path) if path else Path(data_path("words_hk.csv"))
    if not p.exists():
        return {}, set(), set()

    text = p.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        return {}, set(), set()

    delim = _detect_delimiter(text[:4096])
    rows = list(csv.DictReader(text.splitlines(), delimiter=delim))
    if not rows:
        return {}, set(), set()

    word_keys = ("hanzi", "word", "traditional", "trad", "text", "form")
    freq_keys = ("freq", "frequency", "count", "score", "pm", "ppm", "pmw")
    rank_keys = ("rank", "ranking")
    meta_keys = ("register", "style", "usage", "note", "notes", "tag", "tags")

    freq_map: dict[str, float] = {}
    colloq: set[str] = set()
    attested: set[str] = set()
    ranks: dict[str, float] = {}

    for row in rows:
        word = _first_nonempty(row, word_keys)
        if not word:
            # fall back to first column
            try:
                first = next(iter(row.values()))
                word = str(first or "").strip()
            except Exception:
                word = ""
        if not word:
            continue

        attested.add(word)

        freq_val = _first_nonempty(row, freq_keys)
        rank_val = _first_nonempty(row, rank_keys)

        if freq_val:
            try:
                freq_map[word] = float(freq_val)
            except Exception:
                pass
        elif rank_val:
            try:
                ranks[word] = float(rank_val)
            except Exception:
                pass

        meta = " ".join(str(row.get(k) or "") for k in meta_keys).lower()
        if any(m in meta for m in ("colloquial", "spoken", "slang", "hk")):
            colloq.add(word)

    if ranks and not freq_map:
        try:
            max_rank = max(ranks.values())
        except Exception:
            max_rank = 0.0
        for w, r in ranks.items():
            try:
                freq_map[w] = max(0.0, (max_rank - float(r)) + 1.0)
            except Exception:
                freq_map[w] = 0.0

    return freq_map, colloq, attested
