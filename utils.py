"""Utility helpers for dictionary maintenance and data hygiene.

This module contains small tools we discussed to:
1) convert entries to the canonical shape: [[english...], "jyutping"],
2) scan for potential duplicates before they sneak into the code,
3) sanitize Hanzi keys (remove punctuation like ？, ！, ，, 。),
4) pretty-print quick reports while you’re editing.

Notes
-----
- Python dicts cannot contain duplicate keys at runtime; the later one wins.
  If you want to *detect* duplicates as you edit, pass a list of pairs
  ([(key, english_list), ...]) to the duplicate scanner before turning it
  into a dict.
- All helpers are pure and have no side effects (no file I/O).
"""

import io, re, csv
import logging
import math
# --- add (or keep) these imports near the top ---
import os
from statistics import mean, pstdev
from functools import lru_cache


logger = logging.getLogger(__name__)
# Cache for CC-Canto meanings by Hanzi (filled by get_cccanto_reverse_map)
_CCC_MEANINGS_BY_HANZI: dict[str, list[str]] = {}

# Canonical value shape: [[english...], "jyutping"]

# === Unihan config (single source of truth) ===
UNIHAN_JSON_PATH = os.path.join("data", "Unihan", "unihan_cantonese_chars.json")
_CHAR_MAP_CACHE = None  # type: ignore


# ----------------------------
# 1) Canonical conversion
# ----------------------------
def convert_entry(entry, jyutping_map):
    """Convert {hanzi: meanings|[meanings]|[[meanings], jp]} to canonical shape.

    Parameters
    ----------
    entry : dict
        A mapping of Hanzi -> value. Value may be:
        - a single English string,
        - a list of English strings,
        - already in canonical form [[english...], "jyutping"].
    jyutping_map : dict
        A mapping of Hanzi -> jyutping string to use when the input entry
        does not already provide the jyutping.

    Returns
    -------
    dict
        { hanzi: [[english...], "jyutping"] }
    """
    out = {}
    for hanzi, val in entry.items():

        if isinstance(val, list) and len(val) == 2 and isinstance(val[0], list) and isinstance(val[1], str):
            # Already canonical
            meanings = [str(x) for x in val[0]]
            jyut = str(val[1])
        elif isinstance(val, list):
            # List of meanings only
            meanings = [str(x) for x in val]
            jyut = jyutping_map.get(hanzi, "")
        elif isinstance(val, str):
            meanings = [val]
            jyut = jyutping_map.get(hanzi, "")
        else:
            # Unknown structure -> coerce to string and carry on
            meanings = [str(val)]
            jyut = jyutping_map.get(hanzi, "")

        out[hanzi] = [meanings, jyut]
    return out


def merge_canonical(base, overrides):
    """Merge two canonical dicts, with overrides taking precedence.

    Useful when auto-generated jyutping needs to be corrected by a small
    hand-curated map.
    """
    out = dict(base)
    for k, v in overrides.items():
        out[k] = v
    return out


# ----------------------------
# 2) Duplicate scanners
# ----------------------------
def find_exact_duplicates_in_pairs(pairs):
    """Find exact duplicates by (key, english_list) in a *list of pairs*.

    Use this on source data *before* creating a dict, so we can catch the
    classic "later duplicate overwrote earlier" issue.

    Returns a list of (key, english_list, line_numbers) for any duplicates.
    Line numbers are 1-based positions within the provided sequence.
    """
    index = {}
    for i, (k, eng_list) in enumerate(pairs, start=1):
        key = (k, tuple(eng_list))
        index.setdefault(key, []).append(i)
    dups = []
    for (k, eng_tuple), lines in index.items():
        if len(lines) > 1:
            dups.append((k, list(eng_tuple), lines))
    return dups


def find_same_english_across_keys_canonical(data):
    """Report different Hanzi keys that share the *same* English list.

    This is not an error by itself, but it helps surface copy-paste issues
    or places where senses should be disambiguated.
    Returns: { tuple(english_list): [hanzi1, hanzi2, ...] }
    """
    buckets = {}
    for hanzi, val in data.items():
        if not (isinstance(val, list) and len(val) == 2 and isinstance(val[0], list)):
            # Skip non-canonical
            continue
        eng = tuple(val[0])
        buckets.setdefault(eng, []).append(hanzi)
    return {eng: ks for eng, ks in buckets.items() if len(ks) > 1}


# ----------------------------
# YAML loading for ANDYS_LIST
# ----------------------------
def load_andys_list_yaml(path="andys_list.yaml"):
    """Load and validate the canonical mapping from a YAML file.

    Expected YAML structure:
        Hanzi: [[english...], jyutping]
    Returns: { hanzi: [[english...], jyutping] }
    """
    if not os.path.exists(path):
        raise IOError("andys_list.yaml not found at: {}".format(os.path.abspath(path)))
    with io.open(path, 'r', encoding='utf-8') as fh:
        data = yaml.safe_load(fh.read()) or {}

    out = {}

    for hanzi, val in data.items():
        if isinstance(val, list) and len(val) == 2 and isinstance(val[0], list) and isinstance(val[1], str):
            meanings = [str(x) for x in val[0]]
            jyut = str(val[1])
        elif isinstance(val, list):
            meanings = [str(x) for x in val]
            jyut = ""
        elif isinstance(val, str):
            meanings = [val]
            jyut = ""
        else:
            meanings = [str(val)]
            jyut = ""
        out[str(hanzi)] = [meanings, jyut]
    return out


def load_pairs_for_duplicate_scan_from_yaml(path="andys_list.yaml"):
    """Return (hanzi, english_list) pairs from YAML for duplicate scanning."""
    if not os.path.exists(path):
        raise IOError("andys_list.yaml not found at: {}".format(os.path.abspath(path)))
    with io.open(path, 'r', encoding='utf-8') as fh:
        data = yaml.safe_load(fh.read()) or {}
    pairs = []
    for hanzi, val in data.items():
        if isinstance(val, list) and len(val) >= 1 and isinstance(val[0], list):
            eng = [str(x) for x in val[0]]
        elif isinstance(val, list):
            eng = [str(x) for x in val]
        elif isinstance(val, str):
            eng = [val]
        else:
            eng = [str(val)]
        pairs.append((str(hanzi), eng))
    return pairs


def load_canonical_from_yaml(path="andys_list.yaml"):
    """Alias kept for clarity where code expects canonical."""
    return load_andys_list_yaml(path)


# ----------------------------
# 3) Sanitize Hanzi keys
# ----------------------------
_HANZI_PUNCT = "，。？！；：「」『』、．⋯…—＂＇﹑〔〕（）［］〈〉《》｣"


def sanitize_hanzi_key(hanzi):
    """Remove Chinese punctuation commonly seen in teaching material titles.

    Examples
    --------
    >>> sanitize_hanzi_key("呢個係咩？")
    '呢個係咩'
    >>> sanitize_hanzi_key("你食左飯未呀？")
    '你食左飯未呀'
    """
    return "".join(ch for ch in hanzi if ch not in _HANZI_PUNCT)


# ----------------------------
# Frequency merge utilities
# ----------------------------

FREQ_DIR_DEFAULT = os.path.join("data", "frequency")


def load_freq_csv(path: str) -> dict:
    """Load a frequency CSV with headers hanzi,jyut,freq -> {(hanzi,jyut): int}.
    Missing file returns empty dict.
    """
    out = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        for row in rdr:
            try:
                h = (row.get("hanzi") or "").strip()
                j = (row.get("jyut") or "").strip()
                f = int((row.get("freq") or "0").strip())
            except Exception:
                continue
            if not h or not j:
                continue
            out[(h, j)] = out.get((h, j), 0) + max(0, f)
    return out


def _log1p_series(values):
    return [math.log1p(v) for v in values]


def normalize_layer(counts: dict) -> dict:
    """Z-score on log1p(freq) per layer. Returns {(hanzi,jyut): zscore}.
    If layer is empty or stdev == 0, returns zeros.
    """
    if not counts:
        return {}
    keys = list(counts.keys())
    vals = _log1p_series([counts[k] for k in keys])
    mu = mean(vals)
    sd = pstdev(vals) if len(vals) > 1 else 0.0
    if sd == 0 or not math.isfinite(sd):
        return {k: 0.0 for k in keys}
    return {k: (v - mu) / sd for k, v in zip(keys, vals)}


def merge_layers(hkc: dict, subs: dict, ccc: dict, weights=(0.5, 0.3, 0.2)) -> dict:
    """Merge three layers using weighted sum of z-scores.
    Returns mapping {(hanzi,jyut): {"score": float, "counts": {"hkc":int,"subs":int,"ccc":int}, "norm": {"hkc":float,"subs":float,"ccc":float}}}
    """
    norm_hkc = normalize_layer(hkc)
    norm_sub = normalize_layer(subs)
    norm_ccc = normalize_layer(ccc)

    keys = set(hkc.keys()) | set(subs.keys()) | set(ccc.keys())
    w_h, w_s, w_c = weights
    merged = {}
    for k in keys:
        c_h = hkc.get(k, 0)
        c_s = subs.get(k, 0)
        c_c = ccc.get(k, 0)
        n_h = norm_hkc.get(k, 0.0)
        n_s = norm_sub.get(k, 0.0)
        n_c = norm_ccc.get(k, 0.0)
        score = w_h * n_h + w_s * n_s + w_c * n_c
        merged[k] = {
            "score": float(score),
            "counts": {"hkc": int(c_h), "subs": int(c_s), "ccc": int(c_c)},
            "norm": {"hkc": float(n_h), "subs": float(n_s), "ccc": float(n_c)},
        }
    return merged


def write_freq_rank_yaml(merged: dict, out_path: str = None) -> str:
    """Write a YAML mapping grouped by Hanzi.
    Structure:
    Hanzi:
      - jyut: "..."
        score: 1.23
        counts: {hkc: 12, subs: 34, ccc: 5}
        norm: {hkc: 0.1, subs: 0.3, ccc: -0.2}
    Returns absolute path.
    """
    if out_path is None:
        os.makedirs(FREQ_DIR_DEFAULT, exist_ok=True)
        out_path = os.path.join(FREQ_DIR_DEFAULT, "freq_rank.yaml")

    grouped = {}
    for (hanzi, jyut), payload in merged.items():
        grouped.setdefault(hanzi, []).append({
            "jyut": jyut,
            "score": round(float(payload.get("score", 0.0)), 6),
            "counts": {
                "hkc": int(payload.get("counts", {}).get("hkc", 0)),
                "subs": int(payload.get("counts", {}).get("subs", 0)),
                "ccc": int(payload.get("counts", {}).get("ccc", 0)),
            },
            "norm": {
                "hkc": round(float(payload.get("norm", {}).get("hkc", 0.0)), 6),
                "subs": round(float(payload.get("norm", {}).get("subs", 0.0)), 6),
                "ccc": round(float(payload.get("norm", {}).get("ccc", 0.0)), 6),
            }
        })

    # Within each Hanzi group, sort by score desc
    for h in list(grouped.keys()):
        grouped[h].sort(key=lambda d: d.get("score", 0.0), reverse=True)

    with open(out_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(grouped, fh, allow_unicode=True, sort_keys=True)
    return os.path.abspath(out_path)


def write_freq_rank_top_csv(merged: dict, out_path: str = None, limit: int = 5000) -> str:
    """Write a flat CSV of top-N items by score for quick inspection."""
    if out_path is None:
        os.makedirs(FREQ_DIR_DEFAULT, exist_ok=True)
        out_path = os.path.join(FREQ_DIR_DEFAULT, "freq_rank_top.csv")

    rows = [((h, j), d.get("score", 0.0), d.get("counts", {})) for (h, j), d in merged.items()]
    rows.sort(key=lambda r: r[1], reverse=True)
    rows = rows[:limit]

    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["hanzi", "jyut", "score", "hkc", "subs", "ccc"])
        for (h, j), sc, cnt in rows:
            w.writerow([h, j, f"{sc:.6f}", int(cnt.get("hkc", 0)), int(cnt.get("subs", 0)), int(cnt.get("ccc", 0))])
    return os.path.abspath(out_path)


def build_freq_rank(freq_dir: str = FREQ_DIR_DEFAULT,
                    hkc_file: str = "hkcancor_words.csv",
                    subs_file: str = "subtitles_words.csv",
                    ccc_file: str = "cccanto_words.csv",
                    weights=(0.5, 0.3, 0.2)) -> tuple[str, str]:
    """High-level pipeline: load 3 CSVs, normalize, merge, write outputs.
    Returns (yaml_path, csv_path).
    """
    hkc = load_freq_csv(os.path.join(freq_dir, hkc_file))
    subs = load_freq_csv(os.path.join(freq_dir, subs_file))
    ccc = load_freq_csv(os.path.join(freq_dir, ccc_file))

    merged = merge_layers(hkc, subs, ccc, weights=weights)

    ypath = write_freq_rank_yaml(merged)
    cpath = write_freq_rank_top_csv(merged)
    return ypath, cpath


# ----------------------------
# Reverse Lookup (Tier 1): in-memory reverse index
# ----------------------------
from collections import Counter, defaultdict

REVERSE_MANUAL_DEFAULT = os.path.join("data", "reverse_manual.yaml")
UNIHAN_CHARMAP_DEFAULT = os.path.join("data", "Unihan", "unihan_cantonese_chars.json")


# utils.py
import os, csv, re, logging
logger = logging.getLogger(__name__)

def _norm_jy_key(s: str) -> str:
    return " ".join((s or "").strip().lower().split())

@lru_cache(maxsize=1)
def get_cccanto_reverse_map() -> dict:
    """Return a mapping { jyutping (normalized) -> [hanzi, …] }.

    Searches:
      data/CC-CANTO/cccanto.txt
      data/CC-Canto/cccanto.txt
      data/cccanto.txt
      data/cccanto.csv
      data/cccanto.txt   (CC-CEDICT-like lines)
    Safe if files are missing; logs diagnostics.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        # os.path.join(base_dir, "data", "CC-CANTO", "cccanto.txt"),
        # os.path.join(base_dir, "data", "CC-Canto", "cccanto.txt"),
        os.path.join(base_dir, "data", "cccanto.txt"),
        # os.path.join(base_dir, "data", "cccanto.csv"),
        # os.path.join(base_dir, "data", "cccanto.txt"),
    ]
    path = next((p for p in candidates if os.path.exists(p)), None)
    if not path:
        logger.debug("get_cccanto_reverse_map: no CC-Canto file found in expected paths")
        return {}

    rev: dict[str, list[str]] = {}
    meanings_map: dict[str, list[str]] = {}
    try:
        if path.endswith((".tsv", ".csv")):
            delim = "\t" if path.endswith(".tsv") else ","
            with open(path, "r", encoding="utf-8") as fh:
                try:
                    sample = fh.read(4096); fh.seek(0)
                    dialect = csv.Sniffer().sniff(sample)
                    reader = csv.reader(fh, dialect)
                except Exception:
                    reader = csv.reader(fh, delimiter=delim)

                # Peek a row to detect header
                try:
                    first = next(reader)
                except StopIteration:
                    first = None

                header = [h.strip().lower() for h in first] if first else []
                def looks_like_header(cols): return any(any(c.isalpha() for c in col) for col in cols)

                # If not a header, treat as data and process the first row
                def add_row(row, idx_hz, idx_jy):
                    if not row or len(row) <= max(idx_hz, idx_jy): return
                    hz = str(row[idx_hz]).strip()
                    jy = str(row[idx_jy]).strip()
                    if not hz or not jy: return
                    key = _norm_jy_key(jy)
                    if not key: return
                    rev.setdefault(key, [])
                    if hz not in rev[key]:
                        rev[key].append(hz)

                if first and not looks_like_header(header):
                    # assume [hanzi, jyut, ...]
                    add_row(first, 0, 1)
                    header = []  # no header

                idx_hz, idx_jy = 0, 1
                if header:
                    def find(names):
                        for n in names:
                            if n in header: return header.index(n)
                        return None
                    idx_hz = find(("hanzi","word","token","chars","traditional")) or 0
                    idx_jy = find(("jyut","jyutping","jy","jyutping_str","reading")) or 1

                for row in reader:
                    add_row(row, idx_hz, idx_jy)

            logger.debug("get_cccanto_reverse_map: built %d keys from %s",
                         len(rev), os.path.basename(path))

        else:
            # CC-CEDICT-like .txt with variations, e.g.
            #   傳說 传说 [chuan2 shuo1] {cyun4 syut3} /legend/
            #   阿爸 阿爸 {aa3 baa1} /dad/
            #   亞爸 亚爸 [ya4 ba4] {aa3 baa1} /dad, father-in-law/
            # Capture strategy:
            #  - hz = first token (traditional form)
            #  - jyutping preferred from {...}; fallback to [...] if only Cantonese appears there
            curly_re = re.compile(r"^(?P<hz>\S+)\s+\S+\s+(?:\[[^\]]*\]\s+)?\{(?P<jy>[^}]+)\}\s+/.*?/")
            square_re = re.compile(r"^(?P<hz>\S+)\s+\S+\s+\[(?P<jy>[^\]]+)\]\s+/.*?/")
            added = 0
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    if not line or line.startswith('#'):
                        continue
                    s = line.strip()
                    m = curly_re.match(s)
                    if not m:
                        m = square_re.match(s)
                    if not m:
                        continue
                    hz = (m.group("hz") or "").strip()
                    jy = (m.group("jy") or "").strip()
                    if not hz or not jy:
                        continue
                    key = _norm_jy_key(jy)
                    if not key:
                        continue
                    bucket = rev.setdefault(key, [])
                    if hz not in bucket:
                        bucket.append(hz)
                        added += 1
            logger.debug("get_cccanto_reverse_map: built %d rows (keys=%d) from %s",
                         added, len(rev), os.path.basename(path))
    except Exception:
        logger.exception("get_cccanto_reverse_map: failed to build reverse map from %s", path)
        return {}

    global _CCC_MEANINGS_BY_HANZI
    _CCC_MEANINGS_BY_HANZI = meanings_map
    return rev

def get_cccanto_meanings_map() -> dict[str, list[str]]:
    """Return the cached Hanzi -> [meanings] built by get_cccanto_reverse_map()."""
    global _CCC_MEANINGS_BY_HANZI
    if not _CCC_MEANINGS_BY_HANZI:
        try:
            _ = get_cccanto_reverse_map()
        except Exception:
            pass
    return _CCC_MEANINGS_BY_HANZI or {}


# utils.py
def get_cccanto_glosses_for(hz: str) -> list[str]:
    """Return glosses for a given Hanzi by scanning the CC-Canto source file on demand.
    Works for both TSV/CSV and the CC-CEDICT-like .txt with {jyut} and /gloss/.
    """
    if not hz:
        return []
    base_dir = os.path.dirname(os.path.abspath(__file__))
    paths = [
        os.path.join(base_dir, "data", "CC-CANTO", "cccanto.tsv"),
        os.path.join(base_dir, "data", "CC-Canto", "cccanto.tsv"),
        os.path.join(base_dir, "data", "cccanto.tsv"),
        os.path.join(base_dir, "data", "cccanto.csv"),
        os.path.join(base_dir, "data", "cccanto.txt"),
    ]
    path = next((p for p in paths if os.path.exists(p)), None)
    if not path:
        return []

    try:
        if path.endswith((".tsv", ".csv")):
            delim = "\t" if path.endswith(".tsv") else ","
            with open(path, "r", encoding="utf-8") as fh:
                try:
                    sample = fh.read(4096); fh.seek(0)
                    dialect = csv.Sniffer().sniff(sample)
                    reader = csv.reader(fh, dialect)
                except Exception:
                    reader = csv.reader(fh, delimiter=delim)
                # header?
                try:
                    first = next(reader)
                except StopIteration:
                    return []
                header = [c.strip().lower() for c in first] if first else []
                idx_hz, idx_mean = 0, None
                if header and any(any(ch.isalpha() for ch in col) for col in header):
                    def _find(cols, names):
                        for n in names:
                            if n in cols:
                                return cols.index(n)
                        return None
                    idx_hz = _find(header, ("hanzi", "word", "token", "chars", "traditional")) or 0
                    idx_mean = _find(header, ("meaning", "meanings", "english", "gloss", "glosses", "definition", "defs"))
                for row in reader:
                    if not row or len(row) <= idx_hz:
                        continue
                    if str(row[idx_hz]).strip() != hz:
                        continue
                    raw = str(row[idx_mean]).strip() if (isinstance(idx_mean, int) and len(row) > idx_mean) else ""
                    parts = [p.strip() for p in re.split(r"[;/,]|，|；", raw) if p.strip()]
                    return parts[:5]
        else:
            # CC-CEDICT-style .txt:  Trad Simp [pinyin] {jyut} /gloss/
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    if not line or line.startswith("#"):
                        continue
                    s = line.strip()
                    if not s.startswith(hz + " "):
                        continue
                    first = s.find("/")
                    last = s.rfind("/")
                    if first == -1 or last == -1 or last <= first:
                        continue
                    raw = s[first+1:last].strip()
                    parts = [p.strip() for p in re.split(r"[;/,]|，|；", raw) if p.strip()]
                    return parts[:5]
    except Exception:
        return []
    return []

def load_reverse_manual_yaml(path: str = REVERSE_MANUAL_DEFAULT) -> dict:
    """Load reverse_manual.yaml mapping: jyut -> [hanzi, ...]. Missing file -> {}.
    Expected YAML:
        "nei5 hou2": ["你好"]
        "sin1 saang1": ["先生"]
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        # normalise keys and values
        out = {}
        for jy, hz_list in (data.items() if isinstance(data, dict) else []):
            jy_n = _norm_jy_key(str(jy))
            clean = [str(h).strip() for h in (hz_list or []) if str(h).strip()]
            if jy_n and clean:
                out[jy_n] = clean
        return out
    except FileNotFoundError:
        return {}


# @lru_cache(maxsize=1)
# def get_cccanto_reverse_map() -> dict:
#     """
#     Build a reverse map from CC-Canto TSV (hanzi, jyutping, glosses...).
#     Expected filename (first found wins):
#       - ./data/cccanto.txt
#       - ./cccanto.txt
#     Returns: dict[jy_norm] -> list[{"hanzi": ..., "meanings": [...]}]
#     """
#     import os, re
#     candidates = [
#         os.path.join("data", "cccanto.txt"),
#         "cccanto.txt",
#     ]
#     path = None
#     for p in candidates:
#         if os.path.exists(p):
#             path = p
#             break
#
#     rev = {}
#     if not path:
#         return rev  # file not present; silently empty
#
#     # Heuristic parser for common CC-Canto TSV export:
#     # hanzi \t jyutping \t english (maybe comma-/slash-separated)
#     with io.open(path, "r", encoding="utf-8", errors="ignore") as f:
#         for line in f:
#             line = line.strip()
#             if not line or line.startswith("#"):
#                 continue
#             parts = line.split("\t")
#             if len(parts) < 2:
#                 continue
#             hanzi = parts[0].strip()
#             jy = _norm_jy_key(parts[1])
#             meanings_raw = parts[2].strip() if len(parts) >= 3 else ""
#             # split meanings on common delimiters
#             segs = re.split(r"[;/,]|，|；", meanings_raw) if meanings_raw else []
#             meanings = [s.strip() for s in segs if s.strip()]
#             if not jy or not hanzi:
#                 continue
#             rev.setdefault(jy, []).append({"hanzi": hanzi, "meanings": meanings})
#
#     return rev

def _aggregate_freq_scores(freq_dir: str = FREQ_DIR_DEFAULT,
                           files: tuple[str, str, str] = ("hkcancor_words.csv",
                                                          "subtitles_words.csv",
                                                          "cccanto_words.csv")) -> dict:
    """Load frequency CSV layers and return {(hanzi, jyut): count} aggregated across layers.
    Uses existing load_freq_csv(). Missing files are ignored.
    """
    paths = [os.path.join(freq_dir, f) for f in files]
    merged = Counter()
    for p in paths:
        layer = load_freq_csv(p)
        for (h, j), c in layer.items():
            merged[(h, _norm_jy_key(j))] += int(c)
    return dict(merged)


def build_reverse_index(andys_path: str = "andys_list.yaml",
                        reverse_manual_path: str = REVERSE_MANUAL_DEFAULT,
                        freq_dir: str = FREQ_DIR_DEFAULT) -> dict:
    """Build a reverse index: { jyut -> {hanzi: score, ...} }.

    Sources (in order of increasing strength):
      1) andys_list.yaml (canonical app vocab) — low base score
      2) reverse_manual.yaml (curated overrides) — strong base score
      3) data/frequency/*.csv (HKCANCOR, Subtitles, CC-Canto) — add frequency score

    Scoring heuristic (simple, fast, explainable):
      - Base points: andys_list = +1, manual = +10
      - Frequency: +log1p(total_count_across_layers)

    Returns: dict mapping jyut (normalised) -> dict(hanzi -> float score)
    """
    # 1) Start with andys_list
    vocab = load_andys_list_yaml(andys_path)
    rev = defaultdict(float)  # temporary collector per jy; we will expand below
    index = defaultdict(dict)  # final {jy: {hanzi: score}}

    for hanzi, val in (vocab or {}).items():
        try:
            meanings, jy = val[0], val[1]
        except Exception:
            continue
        jy_n = _norm_jy_key(jy)
        if not jy_n:
            continue
        index[jy_n][hanzi] = index[jy_n].get(hanzi, 0.0) + 1.0  # base for andys_list

    # 2) Manual overrides — strong base
    manual = load_reverse_manual_yaml(reverse_manual_path)
    for jy_n, hz_list in (manual or {}).items():
        for h in hz_list:
            index[jy_n][h] = index[jy_n].get(h, 0.0) + 10.0

    # 3) Frequency layers — add log1p(count)
    counts = _aggregate_freq_scores(freq_dir)
    for (h, j), cnt in (counts or {}).items():
        jn = _norm_jy_key(j)
        if not jn:
            continue
        # ensure the candidate exists in bucket first
        base = index[jn].get(h, 0.0)
        boost = math.log1p(max(0, int(cnt)))
        index[jn][h] = base + boost

    # sort dicts by score desc for stable downstream behaviour
    sorted_index = {}
    for jy_n, m in index.items():
        items = sorted(m.items(), key=lambda kv: kv[1], reverse=True)
        sorted_index[jy_n] = {h: float(sc) for h, sc in items}

    return sorted_index


def reverse_candidates(jy: str, reverse_index: dict, top_n: int = 10) -> list[tuple[str, float]]:
    """Return top-n (hanzi, score) for a Jyutping query using a prebuilt reverse index.
    If not found, returns an empty list.
    """
    jn = _norm_jy_key(jy)
    if not jn or not isinstance(reverse_index, dict):
        return []
    bucket = reverse_index.get(jn) or {}
    return list(bucket.items())[: max(0, int(top_n))]


# ----------------------------
# Reverse Lookup (Tier 2): character-composition via Unihan char map
# ----------------------------

# utils.py — robust Unihan loader + composer
import os, json
from itertools import product


## _resolve_data_path left as-is, but not used by the loader below


# --- Enhanced Unihan loader with logging and fallback to txt ---
## _parse_unihan_readings_txt left as-is, but not used by the loader below


def load_unihan_char_map(path: str | None = None) -> dict[str, list[str]]:
    """Load char→[jyutping] strictly from data/Unihan/unihan_cantonese_chars.json.
    This is intentionally strict to avoid accidental mismatches.
    """
    use_path = path or UNIHAN_JSON_PATH
    full = os.path.abspath(use_path)
    if not os.path.exists(full):
        logger.debug("Unihan JSON missing at: %s", full)
        return {}
    try:
        with open(full, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        logger.debug("Failed to read Unihan JSON: %s", full, exc_info=True)
        return {}

    out: dict[str, list[str]] = {}

    def _norm_readings(val):
        if val is None:
            return []
        if isinstance(val, str):
            return [p for p in val.replace("/", " ").lower().split() if p]
        if isinstance(val, (list, tuple, set)):
            acc = []
            for x in val:
                if x:
                    acc += str(x).replace("/", " ").lower().split()
            return [p for p in acc if p]
        s = str(val).strip().lower()
        return [s] if s else []

    def _push(ch, readings):
        if not ch or len(ch) != 1:
            return
        arr = _norm_readings(readings)
        if not arr:
            return
        bucket = out.setdefault(ch, [])
        for r in arr:
            if r not in bucket:
                bucket.append(r)

    # Flexible schema handling
    if isinstance(data, dict):
        for k, v in data.items():
            readings = v.get("kCantonese") if isinstance(v, dict) else v
            if isinstance(k, str) and len(k) == 1:
                ch = k
            elif isinstance(k, str) and k.upper().startswith("U+"):
                try:
                    ch = chr(int(k[2:], 16))
                except Exception:
                    ch = None
            else:
                ch = None
            if ch:
                _push(ch, readings)
    elif isinstance(data, list):
        for rec in data:
            if not isinstance(rec, dict):
                continue
            ch = rec.get("char")
            if not ch:
                cp = rec.get("codepoint") or rec.get("cp")
                if isinstance(cp, str) and cp.upper().startswith("U+"):
                    try:
                        ch = chr(int(cp[2:], 16))
                    except Exception:
                        ch = None
            readings = rec.get("kCantonese") or rec.get("cantonese") or rec.get("jyutping") or rec.get("jyut")
            if ch:
                _push(ch, readings)

    logger.debug("Unihan JSON loaded (%d entries) from %s", len(out), full)
    return out


# Singleton accessor for Unihan char map
def get_unihan_char_map(force_reload: bool = False) -> dict[str, list[str]]:
    global _CHAR_MAP_CACHE
    if force_reload or _CHAR_MAP_CACHE is None:
        _CHAR_MAP_CACHE = load_unihan_char_map()
        # Log once at creation time
        try:
            logger.debug("get_unihan_char_map: cache %s with %d entries", "created" if not force_reload else "reloaded",
                         len(_CHAR_MAP_CACHE))
        except Exception:
            pass
    return _CHAR_MAP_CACHE or {}


def compose_candidates_from_chars(jy, char_map, cap_per_syl=30, cap_combos=100):
    """Compose Hanzi candidates for a Jyutping phrase using a char->readings map.

    Strategy per syllable:
      1) Try exact tone match (e.g., 'baa4').
      2) If none, relax tone: match by base (strip digits) against any reading with same base.

    Then take a limited Cartesian product across syllables.
    """
    if not jy:
        return []
    parts = " ".join(str(jy).strip().lower().split()).split()
    if not parts or not isinstance(char_map, dict) or not char_map:
        return []

    def _base(s: str) -> str:
        return "".join(c for c in s if not c.isdigit())

    def _match_syl(syl: str) -> list[str]:
        exact, relaxed = [], []
        base = _base(syl)
        for ch, readings in (char_map or {}).items():
            if not _is_cjk(ch):
                continue
            try:
                if syl in readings:
                    exact.append(ch)
                    if len(exact) >= cap_per_syl:
                        break
            except Exception:
                continue
        if exact:
            return exact
        # tone-relaxed fallback
        for ch, readings in (char_map or {}).items():
            if not _is_cjk(ch):
                continue
            try:
                for r in (readings or []):
                    if _base(r) == base:
                        relaxed.append(ch)
                        break
                if len(relaxed) >= cap_per_syl:
                    break
            except Exception:
                continue
        return relaxed

    per = []
    for syl in parts:
        bucket = _match_syl(syl)
        if not bucket:
            return []
        per.append(bucket)

    out, seen = [], set()
    for tup in product(*per):
        hz = "".join(tup)
        if hz and hz not in seen:
            out.append(hz)
            seen.add(hz)
            if len(out) >= cap_combos:
                break
    return out


def _is_cjk(ch: str) -> bool:
    """Heuristic CJK check to avoid composing punctuation/latin."""
    if not ch:
        return False
    code = ord(ch)
    # Unified CJK, Extension A/B/C/D/E/F, Compatibility Ideographs
    return (
            0x4E00 <= code <= 0x9FFF or
            0x3400 <= code <= 0x4DBF or
            0x20000 <= code <= 0x2CEAF or
            0xF900 <= code <= 0xFAFF
    )


# ----------------------------
# HKCANCOR -> frequency CSV builder (via pycantonese)
# ----------------------------

def build_hkcancor_csv(out_path: str = os.path.join("data", "frequency", "hkcancor_words.csv")) -> str:
    """Build a word frequency CSV from the HKCANCOR corpus using pycantonese.

    Output CSV headers: hanzi,jyut,freq
    Returns absolute path to the written CSV.
    """
    try:
        import pycantonese
    except ImportError as e:
        raise ImportError(
            "pycantonese is required for build_hkcancor_csv(). Please add 'pycantonese' to requirements.txt and pip install it.") from e

    # Load (and auto-download on first run) the HKCANCOR corpus
    corpus = pycantonese.hkcancor()

    counts = Counter()

    # Iterate utterances; prefer aligned word/jyutping tokens when available
    try:
        utter_iter = corpus.utterances()
    except Exception:
        utter_iter = getattr(corpus, "utterances", lambda: [])()

    for utt in utter_iter or []:
        words = getattr(utt, "words", None)
        jyuts = getattr(utt, "jyutping", None)

        if words and jyuts and len(words) == len(jyuts):
            for w, j in zip(words, jyuts):
                w = (w or "").strip()
                j = (j or "").strip()
                if w and j:
                    counts[(w, j)] += 1
            continue

        # Fallback path: segment the traditional text and map to jyutping
        text = getattr(utt, "text_trad", getattr(utt, "text", "")) or ""
        if not text:
            continue
        try:
            tokens = pycantonese.segment(text) or []
        except Exception:
            tokens = []
        for tok in tokens:
            hanzi = (tok or "").strip()
            if not hanzi:
                continue
            try:
                jps = pycantonese.characters_to_jyutping(hanzi)
            except Exception:
                jps = None
            if jps:
                jy = " ".join([s for s in jps if s])
                if jy:
                    counts[(hanzi, jy)] += 1

    # Write CSV
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["hanzi", "jyut", "freq"])
        for (h, j), f in counts.items():
            w.writerow([h, j, int(f)])

    return os.path.abspath(out_path)


# ----------------------------
# 4) Pretty report helpers
# ----------------------------


def sync_unassigned_category(andys_path="andys_list.yaml", cats_path="categories.yaml"):
    """
    Ensure all Hanzi from andys_list.yaml appear in categories.yaml.
    Any missing ones are added to the 'unassigned' category.
    """
    vocab = load_andys_list_yaml(andys_path)
    cats = load_categories_yaml(cats_path)

    # build index of which Hanzi are already assigned to at least one category
    assigned = set()
    for cat, items in cats.items():
        assigned.update(items)

    # ensure 'unassigned' category exists
    cats.setdefault("unassigned", [])

    # add missing Hanzi
    added = []
    for h in vocab.keys():
        if h not in assigned:
            cats["unassigned"].append(h)
            added.append(h)

    # remove duplicates and sort alphabetically
    cats["unassigned"] = sorted(set(cats["unassigned"]))

    # save updated categories.yaml
    with open(cats_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cats, fh, sort_keys=True, allow_unicode=True)

    print(f"Added {len(added)} unassigned items to 'unassigned' in {cats_path}")
    return added


# ----------------------------
# 5) Pretty report helpers
# ----------------------------
def format_duplicate_report(dups):
    if not dups:
        return "No exact duplicates found."
    lines = ["Exact duplicates (same key + english list):"]
    for k, eng, locs in dups:
        lines.append("- {} :: {} at lines {}".format(k, eng, locs))
    return "\n".join(lines)


# -------------------------
# Categories I/O Utilities
# -------------------------
def load_categories_yaml(path: str = "categories.yaml") -> dict:
    """Load categories.yaml -> {category: [hanzi, ...]} (empty dict if missing)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
            if not isinstance(data, dict):
                return {}
            # normalise values to lists of strings
            norm = {}
            for k, v in data.items():
                if isinstance(v, list):
                    norm[k] = [str(x) for x in v]
                elif isinstance(v, str):
                    norm[k] = [v]
                else:
                    norm[k] = []
            return norm
    except FileNotFoundError:
        return {}


def _normalise_vocab(vocab: dict) -> dict:
    """Ensure vocab is {hanzi: [[eng...], jyut]}. Returns a shallow-copied normalised dict."""
    out = {}
    for hanzi, val in vocab.items():
        if isinstance(val, list) and len(val) >= 2:
            meanings = val[0] if isinstance(val[0], list) else [str(val[0])]
            jyut = val[1] if isinstance(val[1], str) else ""
        else:
            meanings, jyut = [], ""
        out[str(hanzi)] = [[str(m) for m in meanings], str(jyut)]
    return out


def _build_category_index(categories: dict) -> dict:
    """Invert {cat:[hanzi]} -> {hanzi:set([cat,...])}."""
    idx = defaultdict(set)
    for cat, items in (categories or {}).items():
        for h in items or []:
            idx[str(h)].add(str(cat))
    return idx


def export_categories_overview_md(andys_path: str = "andys_list.yaml",
                                  categories_path: str = "categories.yaml",
                                  out_path: str = "categories_overview.md") -> str:
    """Write a readable Markdown overview: per-category lists + a global index table."""
    from utils import load_andys_list_yaml  # reuse your existing loader
    vocab = _normalise_vocab(load_andys_list_yaml(andys_path))
    cats = load_categories_yaml(categories_path)
    idx = _build_category_index(cats)

    lines = []
    lines.append("# Categories Overview\n")

    # Per-category sections
    for cat in sorted(cats.keys()):
        lines.append(f"\n## {cat}\n")
        seen = set()
        for h in sorted(cats.get(cat, [])):
            if h in seen:
                continue
            seen.add(h)
            eng = "; ".join(vocab.get(h, [[""], ""])[0])
            jyut = vocab.get(h, [[""], ""])[1]
            lines.append(f"- {h} — {jyut} — {eng}")

    # Global index table
    lines.append("\n## Item Index\n")
    lines.append("| Hanzi | Jyutping | Meanings | Categories |")
    lines.append("|------:|:---------|:---------|:-----------|")
    for h in sorted(vocab.keys()):
        jyut = vocab[h][1]
        eng = "; ".join(vocab[h][0])
        cats_for_h = "; ".join(sorted(idx.get(h, [])))
        lines.append(f"| {h} | {jyut} | {eng} | {cats_for_h} |")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return os.path.abspath(out_path)


def export_categories_csv(andys_path: str = "andys_list.yaml",
                          categories_path: str = "categories.yaml",
                          out_path: str = "categories_export.csv") -> str:
    """Write CSV: Hanzi,Jyutping,Meanings,Categories (multi-values are '; ' joined)."""
    from utils import load_andys_list_yaml
    vocab = _normalise_vocab(load_andys_list_yaml(andys_path))
    cats = load_categories_yaml(categories_path)
    idx = _build_category_index(cats)

    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Hanzi", "Jyutping", "Meanings", "Categories"])
        for h in sorted(vocab.keys()):
            jyut = vocab[h][1]
            eng = "; ".join(vocab[h][0])
            cats_for_h = "; ".join(sorted(idx.get(h, [])))
            w.writerow([h, jyut, eng, cats_for_h])
    return os.path.abspath(out_path)


def validate_categories_md(andys_path: str = "andys_list.yaml",
                           categories_path: str = "categories.yaml",
                           out_path: str = "categories_validation.md") -> str:
    """Write a validation report (Markdown) and return its absolute path."""
    from utils import load_andys_list_yaml
    vocab = _normalise_vocab(load_andys_list_yaml(andys_path))
    cats = load_categories_yaml(categories_path)
    idx = _build_category_index(cats)

    hanzi_all = set(vocab.keys())
    # duplicates inside andys_list (same Hanzi appears more than once)
    dup_counter = Counter([h for h in vocab.keys()])
    dups = [h for h, c in dup_counter.items() if c > 1]

    # unassigned present in vocab but not in any category
    unassigned = sorted([h for h in hanzi_all if not idx.get(h)])
    # unknown listed in categories but not in vocab
    unknown = sorted([h for h in idx.keys() if h not in hanzi_all])
    # empty categories
    empty_cats = sorted([c for c, items in cats.items() if not items])
    # multi-membership (FYI)
    multi = sorted([h for h, cc in idx.items() if len(cc) > 1])

    lines = []
    lines.append("# Category Validation\n")

    lines.append("## Unassigned (in andys_list.yaml but not in any category)")
    if unassigned:
        for h in unassigned:
            eng = "; ".join(vocab[h][0])
            jyut = vocab[h][1]
            lines.append(f"- {h} — {jyut} — {eng}")
    else:
        lines.append("- None")

    lines.append("\n## Duplicates (same Hanzi appears more than once in andys_list.yaml)")
    if dups:
        for h in sorted(dups):
            lines.append(f"- {h}")
    else:
        lines.append("- None")

    lines.append("\n## Multi-membership (FYI only; allowed)")
    if multi:
        for h in multi:
            cats_for_h = ", ".join(sorted(idx.get(h, [])))
            eng = "; ".join(vocab.get(h, [[""], ""])[0])
            jyut = vocab.get(h, [[""], ""])[1]
            lines.append(f"- {h} — {jyut} — {eng} — in: {cats_for_h}")
    else:
        lines.append("- None")

    lines.append("\n## Unknown in categories.yaml (listed but not in andys_list.yaml)")
    if unknown:
        for h in unknown:
            lines.append(f"- {h}")
    else:
        lines.append("- None")

    lines.append("\n## Empty categories")
    if empty_cats:
        for c in empty_cats:
            lines.append(f"- {c}")
    else:
        lines.append("- None")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return os.path.abspath(out_path)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Utilities: categories export/validate and frequency rank builder")
    sub = p.add_subparsers(dest="cmd", required=True)

    # categories: export/validate/all
    pc = sub.add_parser("categories", help="Export/validate categories")
    pc.add_argument("action", choices=["export", "validate", "all"], help="What to generate")
    pc.add_argument("--andys", dest="andys", default="andys_list.yaml")
    pc.add_argument("--cats", dest="cats", default="categories.yaml")
    pc.add_argument("--outdir", dest="outdir", default=".")

    # frequency: build-freq-rank
    pf = sub.add_parser("build-freq-rank", help="Build merged frequency rank from CSV layers")
    pf.add_argument("--freqdir", default=FREQ_DIR_DEFAULT)
    pf.add_argument("--hkc", default="hkcancor_words.csv")
    pf.add_argument("--subs", default="subtitles_words.csv")
    pf.add_argument("--ccc", default="cccanto_words.csv")
    pf.add_argument("--weights", default="0.5,0.3,0.2", help="Comma weights hkc,subs,ccc")

    # hkcancor -> CSV
    pb = sub.add_parser("build-hkcancor", help="Build HKCANCOR words CSV via pycantonese")
    pb.add_argument("--out", default=os.path.join(FREQ_DIR_DEFAULT, "hkcancor_words.csv"))

    args = p.parse_args()

    if args.cmd == "categories":
        os.makedirs(args.outdir, exist_ok=True)
        if args.action in ("export", "all"):
            md_path = os.path.join(args.outdir, "categories_overview.md")
            csv_path = os.path.join(args.outdir, "categories_export.csv")
            print("MD:", export_categories_overview_md(args.andys, args.cats, md_path))
            print("CSV:", export_categories_csv(args.andys, args.cats, csv_path))
        if args.action in ("validate", "all"):
            v_path = os.path.join(args.outdir, "categories_validation.md")
            print("VALIDATION:", validate_categories_md(args.andys, args.cats, v_path))

    elif args.cmd == "build-freq-rank":
        try:
            w = tuple(float(x.strip()) for x in str(args.weights).split(","))
            if len(w) != 3:
                raise ValueError
        except Exception:
            w = (0.5, 0.3, 0.2)
        ypath, cpath = build_freq_rank(args.freqdir, args.hkc, args.subs, args.ccc, weights=w)
        print("YAML:", ypath)
        print("CSV:", cpath)
    elif args.cmd == "build-hkcancor":
        try:
            path = build_hkcancor_csv(args.out)
            print("HKCANCOR CSV:", path)
        except ImportError as e:
            print("ERROR:", e)

from typing import Iterable, Dict, List, Tuple, Optional
import os, csv, yaml

COMMON_CJK_MIN = 0x4E00
COMMON_CJK_MAX = 0x9FFF


def is_common_cjk(s: str) -> bool:
    if not s:
        return False
    return all(COMMON_CJK_MIN <= ord(ch) <= COMMON_CJK_MAX for ch in s)


def filter_common_cjk(cands: Iterable[str]) -> List[str]:
    return [w for w in (cands or []) if isinstance(w, str) and w and is_common_cjk(w)]


def _load_freq_map(csv_paths: Iterable[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for path in (csv_paths or []):
        try:
            if not path or not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as fh:
                r = csv.DictReader(fh)
                cols = [c.lower() for c in (r.fieldnames or [])] if r.fieldnames else []
                hz_col = next((n for n in ("hanzi", "word", "token", "char", "chars") if n in cols), None)
                fq_col = next((n for n in ("freq", "frequency", "count", "token_count") if n in cols), None)
                for row in r:
                    hz = (row.get(hz_col, "") if hz_col else "").strip()
                    if not hz:
                        continue
                    try:
                        fv = int(row.get(fq_col, 0)) if fq_col else 0
                    except Exception:
                        fv = 0
                    out[hz] = out.get(hz, 0) + max(0, fv)
        except Exception:
            continue
    return out


def _load_reverse_manual(path: Optional[str]) -> Dict[str, List[str]]:
    """
    Load reverse_manual.yaml and normalize to { jyut (str) : [hanzi (str), ...] }.

    Accepted YAML shapes:
      # Simple mapping
      "nei5 hou2": ["你好", "您好"]

      # Mapping with objects
      "aa3 baa1":
        - hanzi: "阿爸"
          weight: 12
        - hanzi: "亞爸"

      # List of records
      - jyut: "sin1 saang1"
        hanzi: ["先生", "先生成"]
      - jy: "nei5 hou2"
        hanzi: "你好"
    """
    try:
        if not path or not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        out: Dict[str, List[str]] = {}

        def _coerce_hz_list(v) -> List[str]:
            """Normalize any list/value to a list[str] of Hanzi."""
            hz_list: List[str] = []
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        val = item.get("hanzi")
                        if isinstance(val, list):
                            for x in val:
                                sx = str(x).strip()
                                if sx:
                                    hz_list.append(sx)
                        else:
                            sx = str(val or "").strip()
                            if sx:
                                hz_list.append(sx)
                    else:
                        sx = str(item).strip()
                        if sx:
                            hz_list.append(sx)
            else:
                sx = str(v).strip()
                if sx:
                    hz_list.append(sx)
            # de-dup while preserving order
            seen = set()
            deduped = []
            for s in hz_list:
                if s not in seen:
                    deduped.append(s)
                    seen.add(s)
            return deduped

        # Case 1: mapping at top level
        if isinstance(data, dict):
            for k, v in data.items():
                jy = str(k or "").strip()
                if not jy:
                    continue
                out[jy] = _coerce_hz_list(v)
            return out

        # Case 2: list of records
        if isinstance(data, list):
            for rec in data:
                if not isinstance(rec, dict):
                    continue
                jy = str(rec.get("jyut") or rec.get("jy") or "").strip()
                if not jy:
                    continue
                v = rec.get("hanzi")
                out.setdefault(jy, [])
                for hz in _coerce_hz_list(v):
                    if hz not in out[jy]:
                        out[jy].append(hz)
            return out
    except Exception:
        # On parse/IO error, return empty rather than raising; callers will treat missing as {}
        return {}
    return {}


def shortlist_candidates(
        jy: str,
        cands: Iterable[str],
        vocab: Optional[Dict[str, List]] = None,
        reverse_manual_path: Optional[str] = None,
        freq_csvs: Optional[Iterable[str]] = None,
        top_n: int = 10,
) -> List[Tuple[str, int]]:
    j = " ".join((jy or "").strip().lower().split())
    base = filter_common_cjk(cands)
    vset = set((vocab or {}).keys())
    manual = _load_reverse_manual(reverse_manual_path) if reverse_manual_path else {}
    mj = set(manual.get(j, []) if manual else [])
    fmap = _load_freq_map(freq_csvs or []) if freq_csvs else {}
    ranked: List[Tuple[str, int]] = []
    for hz in base:
        score = 0
        if hz in vset:
            score += 1000
        if hz in mj:
            score += 900
        score += int(fmap.get(hz, 0))
        if len(hz) >= 2 and (len(set(hz)) < len(hz)) and hz != "爸爸":
            score -= 5
        ranked.append((hz, score))
    ranked.sort(key=lambda t: (-t[1], t[0]))
    return ranked[: max(1, int(top_n or 10))]


'''
Hanzi
Jyutping
Meaning
Notes
爸爸
baa4 baa1
father / dad
most common and colloquial (spoken Cantonese)
父親
fu6 can1
father (formal)
written / formal
阿爸
aa3 baa1
dad / daddy
affectionate, very common in speech
老豆
lou5 dau6
dad / old man
informal slang
'''
