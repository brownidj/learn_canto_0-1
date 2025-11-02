#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Expand categories.yaml by proposing +N high-frequency colloquial items per category.

Inputs
------
- categories.yaml (supports both old list form and new dict form with items/examples_en)
- data/frequency/cantonese_wordfreq.parquet with columns:
  hanzi (str), count_hkc (int), count_sub (int), count_app (int),
  tokens_hkc (int), tokens_sub (int), tokens_app (int),
  (optional) pos_hint (str)

State
-----
- data/frequency/category_expansion_state.json keeps a per-category set of
  previously added items to avoid re-adding across runs.

Usage
-----
python3 tools/expand_categories.py --dry-run
python3 tools/expand_categories.py --commit --only people,technology_media
python3 tools/expand_categories.py --commit --ppm-min 2.0 --hkc-min 2 --sub-min 8 --top-n 10
python3 tools/expand_categories.py --refresh-freq

Notes
-----
- This tool does not invent English examples; it only appends Hanzi items.
- Duplicates are prevented within a category; cross-category duplication is allowed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import re
import glob
from typing import Dict, List, Tuple, Any
from pathlib import Path

import pandas as pd
from ruamel.yaml import YAML

# ----------------------------- Config defaults ------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATEGORIES_PATH = str(REPO_ROOT / "categories.yaml")
DEFAULT_FREQ_PATH = str(REPO_ROOT / "data" / "frequency" / "cantonese_wordfreq.parquet")
DEFAULT_STATE_PATH = str(REPO_ROOT / "data" / "frequency" / "category_expansion_state.json")

# Stoplist of common function particles we do not want to add as content words
STOPLIST = set([
    "嘅", "咩", "吖", "啦", "喎", "咗", "嗎", "嗎", "嘛", "啫", "囉", "呀", "喇",
    "呀嘛", "哋", "嘞", "嗰", "咁", "喺", "哇", "啊", "么", "么呀"
])


# Some categories we typically skip expansion for (user requested no examples for unassigned)
SKIP_CATEGORIES = set(["unassigned"])

CJK_RANGE = re.compile(u"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")

def only_cjk(text):
    return "".join([ch for ch in text if CJK_RANGE.match(ch)])

def is_hanzi_token(tok):
    return bool(tok) and len(tok) <= 4 and all(CJK_RANGE.match(ch) for ch in tok)

def _read_subtitles(paths):
    texts = []
    for p in paths:
        try:
            with open(p, 'r', encoding='utf-8', errors='ignore') as fh:
                t = fh.read()
            # strip SRT artifacts
            t = re.sub(r"\d\d:\d\d:\d\d,\d\d\d\s+-->\s+\d\d:\d\d:\d\d,\d\d\d", " ", t)
            t = re.sub(r"\b\d+\b", " ", t)
            t = t.replace("-->", " ")
            texts.append(t)
        except Exception:
            continue
    return "\n".join(texts)

# Simple per-category patterns to constrain candidates (heuristics; expand as needed)
CATEGORY_PATTERNS = {
    'animals': set(['狗', '貓', '鳥', '魚', '馬', '牛', '羊', '豬', '雞', '鴨', '虎', '豹', '熊', '狼', '鼠', '兔']),
    'colors': set(['黑','白','紅','藍','綠','黃','紫','橙','灰','啡','金','銀']),
    'communication': set(['講','話','問','答','電','話','訊','息','信','郵','聊','討','論','通','告','叫','叫做']),
    'descriptions_adjectives': set(['靚','好','勁','難','易','快','慢','貴','平','高','矮','大','細','正','冇用','新','舊','長','短','深','淺']),
    'direction': set(['上','下','左','右','入','出','前','後','返']),
    'family': set(['媽','爸','阿','哥','姐','弟','妹','婆','爺','伯','叔','姨','舅','姑','媳','婿','奶']),
    'food, eating, drinking': set(['食','飲','飯','水','茶','湯','餅','菜','肉','糖','鹽','辣','甜','苦','酸']),
    'greetings': set(['你','好','早','晨','午','安','晚','拜','再','見','唔該','多謝','唔好意思','你好','拜拜']),
    'health': set(['醫','院','藥','病','痛','傷','感冒','頭痛','肚痛','發燒']),
    'household': set(['門','窗','椅','枱','床','櫃','燈','鏡','電','風','扇','雪','櫃','電視','電腦']),
    'languages': set(['廣','東','話','粵','語','普','通','話','英','文','中','文','學','語']),
    'measurements': set(['寸','尺','米','公','斤','克','升','毫','升','少','少','多','啲','幾','多']),
    'money_shopping': set(['錢','買','賣','平','貴','折','單','收','據','找','續','價','還','卡','刷','現','金']),
    'nature_air': set(['天','空','雲','風','氣','陽','光','雨','霧','雷','電']),
    'nature_land': set(['地','山','石','沙','泥','樹','林','草','田','路','土','地震']),
    'nature_ocean': set(['海','洋','潮','汐','灘','灣','浪','水','魚','船']),
    'numbers': set(list('零一二三四五六七八九十百千萬億兩')),
    'people': set(['人','男人','女人','男','女','仔','朋友','同事','老師','同學']),
    'places': set(['國','家','城','市','鄉','村','港','臺','灣','中','國','香','港','街','道','路','站','店','學','校','醫','院']),
    'pronouns_possessive': set(['我','你','佢','我哋','你哋','佢哋','我嘅','你嘅','佢嘅']),
    'roles_titles': set(['阿','sir','老師','先生','太太','阿姨','伯伯','叔叔','哥哥','姐姐','阿婆','老闆','同事','校長','醫生']),
    'school_tests': set(['學','校','課','堂','考','試','卷','分','數','作','業','功','課']),
    'technology_media': set(['電','網','手','機','視','腦','郵','相','收','音','機','訊','息','充','電','平','板']),
    'time_calendar': set(['年','月','日','時','分','秒','點','鐘','昨','今','明','週','期','星','期','春','夏','秋','冬']),
    'vehicle': set(['車','巴','士','鐵','路','飛','機','船','單','車','電','單','車','的','士']),
    'weather': set(['雨','風','雷','電','雪','雲','晴','陰','熱','凍','潮','濕']),
    'weekdays': set(['星期','禮拜']),
    'zodiac': set(['鼠','牛','虎','兔','龍','蛇','馬','羊','猴','雞','狗','豬']),
}

# ----------------------------- YAML helpers ---------------------------------

def _yaml_load(path):
    yaml = YAML(typ='rt')  # round-trip
    with open(path, 'r', encoding='utf-8') as fh:
        return yaml.load(fh)


def _yaml_save(path, data):
    yaml = YAML(typ='rt')
    yaml.default_flow_style = False
    with open(path, 'w', encoding='utf-8') as fh:
        yaml.dump(data, fh)


def load_categories(path: str) -> Tuple[Dict[str, Any], Dict[str, List[str]]]:
    """Return (raw_doc, items_map).
    items_map maps category -> list of Hanzi items.
    Accepts both styles:
      - list of hanzi
      - dict with 'items' and optional 'examples_en'
    """
    doc = _yaml_load(path)
    items_map: Dict[str, List[str]] = {}
    if not isinstance(doc, dict):
        return doc, items_map
    for cat, val in doc.items():
        if isinstance(val, list):
            items_map[cat] = [unicode_str(x) for x in val]
        elif isinstance(val, dict):
            items = val.get('items')
            if isinstance(items, list):
                items_map[cat] = [unicode_str(x) for x in items]
            else:
                items_map[cat] = []
        else:
            items_map[cat] = []
    return doc, items_map

def build_frequency_table(include_hkcancor, subtitles_glob, min_len, max_len):
    """Build a frequency DataFrame from HKCanCor (if requested) and subtitles."""
    counts_hkc = {}
    counts_sub = {}

    # HKCanCor via pycantonese (optional)
    if include_hkcancor:
        try:
            import pycantonese as pc
            corpus = pc.hkcancor()
            utter_attr = getattr(corpus, 'utterances', None)
            if callable(utter_attr):
                utter_iter = utter_attr()
            else:
                utter_iter = utter_attr if utter_attr is not None else []
            total_utts = 0
            for utt in utter_iter:
                total_utts += 1
                # Prefer tokens(); fallback to words or transcript
                toks = []
                try:
                    if hasattr(utt, 'tokens') and callable(utt.tokens):
                        toks = utt.tokens()
                    elif hasattr(utt, 'words'):
                        toks = utt.words
                    elif hasattr(utt, 'transcript'):
                        toks = list(utt.transcript)
                except Exception:
                    toks = []
                text = only_cjk("".join(toks))
                for ch in text:
                    if min_len <= 1 <= max_len:
                        counts_hkc[ch] = counts_hkc.get(ch, 0) + 1
            if total_utts == 0:
                print("[WARN] HKCanCor yielded 0 utterances (API shape: {}); continuing without it".format(type(utter_attr)))
        except Exception as e:
            print("[WARN] pycantonese not available or failed: {}".format(e))

    # Subtitles
    if subtitles_glob:
        paths = []
        for pat in subtitles_glob.split(','):
            paths.extend(glob.glob(pat.strip(), recursive=True))
        if paths:
            text = _read_subtitles(paths)
            text = only_cjk(text)
            for ch in text:
                if min_len <= 1 <= max_len:
                    counts_sub[ch] = counts_sub.get(ch, 0) + 1

    vocab = set(list(counts_hkc.keys()) + list(counts_sub.keys()))
    tokens_hkc = int(sum(counts_hkc.values()))
    tokens_sub = int(sum(counts_sub.values()))
    tokens_app = 0

    rows = []
    for hz in sorted(vocab):
        rows.append({
            'hanzi': hz,
            'count_hkc': int(counts_hkc.get(hz, 0)),
            'count_sub': int(counts_sub.get(hz, 0)),
            'count_app': 0,
            'tokens_hkc': tokens_hkc,
            'tokens_sub': tokens_sub,
            'tokens_app': tokens_app,
        })
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    # Compute per-source ppm for transparency; combined weighting is applied later in main()
    tokens_hkc = max(int(df['tokens_hkc'].iloc[0]) if len(df) else 0, 0)
    tokens_sub = max(int(df['tokens_sub'].iloc[0]) if len(df) else 0, 0)
    tokens_app = max(int(df['tokens_app'].iloc[0]) if len(df) else 0, 0)

    def _ppm(col, denom):
        denom = denom if denom > 0 else 1
        return (1e6 * df[col].astype(float)) / float(denom)

    df['ppm_hkc'] = _ppm('count_hkc', tokens_hkc)
    df['ppm_sub'] = _ppm('count_sub', tokens_sub)
    df['ppm_app'] = _ppm('count_app', tokens_app)
    # Do not set a combined ppm here; we will apply weights later so CLI flags take effect
    return df

def save_categories(path: str, raw_doc: Dict[str, Any], new_items: Dict[str, List[str]]) -> None:
    """Persist merged categories back to YAML, preserving structure/comments.
    Only appends to the list under each category (list or dict['items']).
    """
    for cat, app_list in new_items.items():
        if not app_list:
            continue
        node = raw_doc.get(cat)
        if isinstance(node, list):
            node.extend(app_list)
        elif isinstance(node, dict):
            items = node.get('items')
            if isinstance(items, list):
                items.extend(app_list)
            else:
                node['items'] = list(app_list)
        else:
            raw_doc[cat] = list(app_list)
    _yaml_save(path, raw_doc)


def unicode_str(x) -> str:
    try:
        return unicode(x)  # type: ignore  # for Py2-styled fallback, unlikely used
    except Exception:
        return str(x)

# ----------------------------- Frequency loading ----------------------------

def load_frequency_table(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        print("[ERROR] Frequency file missing: {}".format(path))
        return pd.DataFrame()
    try:
        df = pd.read_parquet(path)
    except Exception:
        try:
            df = pd.read_csv(path)
        except Exception as e:
            print("[ERROR] Failed to load frequency table: {}".format(e))
            return pd.DataFrame()
    # If 'hanzi' was accidentally saved as the index, recover it
    try:
        if 'hanzi' not in df.columns:
            if getattr(df.index, 'name', None) == 'hanzi':
                df = df.reset_index()
            else:
                # Try to find a near match (e.g., BOM or whitespace issues)
                for c in list(df.columns):
                    name_norm = str(c).strip().lower()
                    if name_norm == 'hanzi' or name_norm.endswith('hanzi'):
                        df = df.rename(columns={c: 'hanzi'})
                        break
    except Exception:
        pass
    required = [
        'hanzi', 'count_hkc', 'count_sub', 'count_app',
        'tokens_hkc', 'tokens_sub', 'tokens_app'
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print("[DEBUG] Frequency table columns: {}".format(list(df.columns)))
        print("[ERROR] Frequency table missing required columns: {}".format(", ".join(missing)))
        return pd.DataFrame()
    # ensure numeric types where appropriate
    for c in ['count_hkc', 'count_sub', 'count_app', 'tokens_hkc', 'tokens_sub', 'tokens_app']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    # Compute per-source ppm; combined weighting will be applied later using CLI flags
    tokens_hkc = max(int(df['tokens_hkc'].iloc[0]) if len(df) else 0, 0)
    tokens_sub = max(int(df['tokens_sub'].iloc[0]) if len(df) else 0, 0)
    tokens_app = max(int(df['tokens_app'].iloc[0]) if len(df) else 0, 0)

    def _ppm(col, denom):
        denom = denom if denom > 0 else 1
        return (1e6 * df[col].astype(float)) / float(denom)

    df['ppm_hkc'] = _ppm('count_hkc', tokens_hkc)
    df['ppm_sub'] = _ppm('count_sub', tokens_sub)
    df['ppm_app'] = _ppm('count_app', tokens_app)
    # basic cleaning
    df['hanzi'] = df['hanzi'].astype(str)
    return df

# ----------------------------- Weighting -----------------------------------
def apply_weights(df: pd.DataFrame, hkc_w: float, sub_w: float, app_w: float, rank_col: str = 'ppm_weighted') -> pd.DataFrame:
    """Add weighted columns and set a canonical 'ppm' used by the rest of the pipeline."""
    df = df.copy()
    for col in ['count_hkc','count_sub','count_app','tokens_hkc','tokens_sub','tokens_app']:
        if col not in df.columns:
            df[col] = 0

    # Weighted counts
    df['count_weighted'] = (hkc_w * df['count_hkc'].astype(float)
                            + sub_w * df['count_sub'].astype(float)
                            + app_w * df['count_app'].astype(float))

    # Weighted token denominator
    total_tokens_weighted = (hkc_w * float(df['tokens_hkc'].iloc[0] if len(df) else 0)
                             + sub_w * float(df['tokens_sub'].iloc[0] if len(df) else 0)
                             + app_w * float(df['tokens_app'].iloc[0] if len(df) else 0))
    if total_tokens_weighted <= 0:
        total_tokens_weighted = 1.0

    # Weighted ppm
    df['ppm_weighted'] = (1e6 * df['count_weighted']) / total_tokens_weighted

    # Ensure per-source ppm exists for inspection
    for src, tok_col in [('hkc','tokens_hkc'), ('sub','tokens_sub'), ('app','tokens_app')]:
        ppm_col = f'ppm_{src}'
        if ppm_col not in df.columns:
            denom = float(df[tok_col].iloc[0] if len(df) else 0)
            denom = denom if denom > 0 else 1.0
            df[ppm_col] = (1e6 * df[f'count_{src}'].astype(float)) / denom

    # Make downstream code use the requested rank column as 'ppm'
    if rank_col in df.columns:
        df['ppm'] = df[rank_col]
    else:
        df['ppm'] = df['ppm_weighted']
    return df

# ----------------------------- Gates ----------------------------------------

def presence_gate(row: pd.Series, hkc_min: int, sub_min: int, app_min: int) -> bool:
    return (int(row.get('count_hkc', 0)) >= int(hkc_min)) or (int(row.get('count_sub', 0)) >= int(sub_min)) or (int(row.get('count_app', 0)) >= int(app_min))


def ppm_gate(row: pd.Series, ppm_min: float) -> bool:
    try:
        return float(row.get('ppm', 0.0)) >= float(ppm_min)
    except Exception:
        return False


def percentile_threshold(ppm_series: pd.Series, fallback_min: float) -> float:
    if ppm_series is None or ppm_series.empty:
        return float(fallback_min)
    try:
        q = ppm_series.quantile(0.80)
        if pd.isna(q):
            return float(fallback_min)
        return float(max(fallback_min, q))
    except Exception:
        return float(fallback_min)

# ----------------------------- Filters --------------------------------------

def basic_filters(df: pd.DataFrame, category: str) -> pd.DataFrame:
    # Start from a minimal, known set of columns so empty results still keep schema
    base_cols = [c for c in ['hanzi', 'ppm', 'freq_w', 'count_hkc', 'count_sub', 'count_app'] if c in df.columns]
    if 'hanzi' not in base_cols and 'hanzi' in df.columns:
        base_cols = ['hanzi'] + base_cols
    out = df.loc[:, base_cols].copy()

    # 1..4 chars, remove stoplist
    if 'hanzi' in out.columns:
        out = out[out['hanzi'].astype(str).str.len().between(1, 4, inclusive='both')]
        out = out[~out['hanzi'].isin(STOPLIST)]

    # category-specific narrowing via pattern character overlap
    pat = CATEGORY_PATTERNS.get(category)
    if pat and 'hanzi' in out.columns and not out.empty:
        def _ok(s: str) -> bool:
            for ch in s:
                if ch in pat:
                    return True
            return False
        out = out[out['hanzi'].map(_ok)]

    # Special strict cases
    if 'hanzi' in out.columns and not out.empty:
        if category == 'numbers':
            allowed = set(list("一二三四五六七八九十百千萬亿零兩"))
            mask = out['hanzi'].map(lambda s: all((ch in allowed) for ch in s))
            out = out[mask]
        elif category == 'weekdays':
            out = out[out['hanzi'].str.startswith('星期') | out['hanzi'].str.startswith('禮拜')]
        elif category == 'colors':
            color_roots = CATEGORY_PATTERNS['colors']
            out = out[out['hanzi'].map(lambda s: (len(s) == 1 and s in color_roots) or s.endswith("色"))]
        elif category == 'roles_titles':
            out = out[out['hanzi'].map(lambda s: s.startswith('阿') or s.endswith('生') or s.endswith('師') or ('sir' in s.lower()))]

    # If 'hanzi' is the index by mistake, normalize
    if 'hanzi' not in out.columns and getattr(out.index, 'name', None) == 'hanzi':
        out = out.reset_index()

    # Ensure we always return a DataFrame with at least the schema of base_cols
    for col in base_cols:
        if col not in out.columns:
            out[col] = pd.Series(dtype=df[col].dtype if col in df.columns else 'object')
    # Reorder to base_cols last
    out = out[[c for c in base_cols if c in out.columns]]
    return out

# ----------------------------- State ----------------------------------------

def load_state(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"categories": {}}
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {"categories": {}}


def save_state(path: str, state: Dict[str, Any]) -> None:
    base = os.path.dirname(path)
    if base and not os.path.exists(base):
        os.makedirs(base)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)

# ----------------------------- Core propose logic ---------------------------

def propose_for_category(cat: str,
                         df: pd.DataFrame,
                         existing: List[str],
                         hkc_min: int,
                         sub_min: int,
                         app_min: int,
                         ppm_min: float,
                         top_n: int,
                         args=None) -> Tuple[List[str], pd.DataFrame, float]:
    """Return (picks, pool_after_gates, thr_used).
    Picks are the top_n unseen hanzi meeting the gates and sorted by ppm.
    """
    if cat in SKIP_CATEGORIES:
        return [], pd.DataFrame(), float(ppm_min)

    # Add a quick sanity at the top to catch broken inputs
    if 'hanzi' not in df.columns:
        print("[ERROR] Source frequency table lacks 'hanzi' column; columns={}".format(list(df.columns)))
        return [], pd.DataFrame(), float(ppm_min)

    pool = basic_filters(df, cat)

    # Ensure we have a DataFrame with expected columns
    if not hasattr(pool, 'columns'):
        print("[WARN] {}: candidate pool is not a DataFrame; repairing from source".format(cat))
        cols = [c for c in ['hanzi','ppm','freq_w','count_hkc','count_sub','count_app'] if c in df.columns]
        pool = df.loc[:, cols].copy()
    if 'hanzi' not in pool.columns:
        if getattr(pool.index, 'name', None) == 'hanzi':
            pool = pool.reset_index()
        elif 'hanzi' in df.columns:
            # Reconstruct minimal schema
            cols = [c for c in ['hanzi','ppm','freq_w','count_hkc','count_sub','count_app'] if c in df.columns]
            pool = df.loc[:, cols].copy()
        else:
            print("[WARN] {}: pool missing 'hanzi' column; columns={}".format(cat, list(pool.columns)))
            return [], pd.DataFrame(), float(ppm_min)

    # presence gate
    pool = pool[pool.apply(lambda r: presence_gate(r, hkc_min, sub_min, app_min), axis=1)].copy()
    # ppm hard gate
    pool = pool[pool.apply(lambda r: ppm_gate(r, ppm_min), axis=1)].copy()

    # dynamic percentile gate on ppm (per-category pool)
    if getattr(args, 'no_pct', False):
        thr = float(ppm_min)
        print(f"[INFO] {cat}: percentile disabled (--no-pct), using hard floor {thr}")
    else:
        thr = percentile_threshold(pool['ppm'] if 'ppm' in pool.columns else pd.Series([], dtype=float), ppm_min)
        print(f"[DEBUG] {cat}: using percentile {getattr(args, 'pct', 0.80):.2f} (thr={thr:.3f})")
        if 'ppm' in pool.columns:
            pool = pool[pool['ppm'] >= thr].copy()

    # exclude existing
    existing_set = set(existing)
    if 'hanzi' not in pool.columns:
        print("[WARN] {}: missing 'hanzi' before excluding existing; columns={}".format(cat, list(pool.columns)))
        return [], pd.DataFrame(), float(thr)
    pool = pool[~pool['hanzi'].isin(existing_set)].copy()

    # Defensive check before sorting/selecting
    if 'hanzi' not in pool.columns:
        print("[WARN] {}: skipping; pool lost 'hanzi' after gating".format(cat))
        return [], pd.DataFrame(), float(thr)

    # sort and select
    # Ensure a backward-compatible secondary sort key
    if 'freq_w' not in pool.columns:
        # Synthesize a frequency-like column for tie-breaking
        synth_cols = [c for c in ['count_weighted', 'count_hkc', 'count_sub', 'count_app'] if c in pool.columns]
        if 'count_weighted' in synth_cols:
            pool['freq_w'] = pool['count_weighted']
            print(f"[DEBUG] {cat}: synthesized freq_w from count_weighted")
        elif synth_cols:
            pool['freq_w'] = pool[synth_cols].sum(axis=1)
            print(f"[DEBUG] {cat}: synthesized freq_w from {synth_cols}")
        else:
            pool['freq_w'] = 0.0
            print(f"[DEBUG] {cat}: synthesized freq_w as zeros (no count columns present)")

    sort_keys = ['ppm'] + (['freq_w'] if 'freq_w' in pool.columns else [])
    pool = pool.sort_values(by=sort_keys, ascending=False, kind='mergesort')
    picks = []
    for hz in pool['hanzi'].tolist():
        if hz in existing_set:
            continue
        picks.append(hz)
        if len(picks) >= int(top_n):
            break
    return picks, pool, float(thr)

# ----------------------------- CLI ------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Expand categories.yaml with high-frequency colloquial items")
    ap.add_argument('--categories', default=DEFAULT_CATEGORIES_PATH, help='Path to categories.yaml')
    ap.add_argument('--freq-file', default=DEFAULT_FREQ_PATH, help='Path to parquet/csv frequency table')
    ap.add_argument('--state-file', default=DEFAULT_STATE_PATH, help='Path to expansion state JSON')
    ap.add_argument('--only', default='', help='Comma-separated category subset to process')
    ap.add_argument('--top-n', type=int, default=10, help='Number of new items per category')
    ap.add_argument('--pct', type=float, default=0.80,
                    help='Percentile cutoff for dynamic threshold (0–1 range; default=0.80)')
    ap.add_argument('--no-pct', action='store_true',
                    help='Disable percentile threshold and rely only on ppm-min and top-n')
    ap.add_argument('--ppm-min', type=float, default=2.0, help='Minimum ppm hard gate (try 1.0..2.0)')
    ap.add_argument('--hkc-min', type=int, default=2, help='Minimum HKCanCor hits for presence gate')
    ap.add_argument('--sub-min', type=int, default=8, help='Minimum subtitles hits for presence gate')
    ap.add_argument('--app-min', type=int, default=0, help='Minimum app-text hits for presence gate (bootstrap scenarios)')
    ap.add_argument('--dry-run', action='store_true', help='Preview proposed additions only')
    ap.add_argument('--commit', action='store_true', help='Write changes to categories.yaml and state')
    ap.add_argument('--refresh-freq', action='store_true', help='Rebuild frequency table')
    ap.add_argument('--undo', action='store_true', help='Remove previously added items recorded in state (respects --only)')
    ap.add_argument('--build-freq', action='store_true',
                    help='Build frequency table from corpora (HKCanCor, subtitles)')
    ap.add_argument('--include-hkcancor', action='store_true', help='Include HKCanCor counts via pycantonese')
    ap.add_argument('--subtitles-glob', default='',
                    help='Glob(s) for subtitles, comma-separated (e.g., data/subtitles/**/*.srt,data/subtitles/**/*.txt)')
    ap.add_argument('--min-len', type=int, default=1, help='Min Hanzi length considered in frequency build')
    ap.add_argument('--max-len', type=int, default=4, help='Max Hanzi length considered in frequency build')
    ap.add_argument('--hkc-weight', type=float, default=1.0, help='Weight for HKCanCor counts when ranking')
    ap.add_argument('--sub-weight', type=float, default=0.35, help='Weight for subtitles counts when ranking')
    ap.add_argument('--app-weight', type=float, default=0.10, help='Weight for in-app counts when ranking')
    ap.add_argument('--rank-col', default='ppm_weighted', help='Which column to rank by (e.g., ppm_weighted, ppm_hkc, ppm_sub)')


    args = ap.parse_args(argv)

    def _resolve_repo_path(p):
        # Absolute stays as-is; relative resolves under REPO_ROOT
        try:
            return p if os.path.isabs(p) else str(REPO_ROOT / p)
        except Exception:
            return p

    cat_path = _resolve_repo_path(args.categories)
    freq_path = _resolve_repo_path(args.freq_file)
    state_path = _resolve_repo_path(args.state_file)

    print("[PATH] categories: {}".format(cat_path))
    print("[PATH] freq-file : {}".format(freq_path))
    print("[PATH] state-file: {}".format(state_path))

    if args.build_freq:
        df = build_frequency_table(args.include_hkcancor, args.subtitles_glob, args.min_len, args.max_len)
        if df is None or df.empty:
            # Fallback: bootstrap from categories so we never exit empty
            print("[INFO] build-freq produced no rows; falling back to bootstrap from categories.yaml")
            raw_doc_boot, items_map_boot = load_categories(cat_path)
            all_items = []
            for _cat, _lst in items_map_boot.items():
                if isinstance(_lst, list):
                    all_items.extend([unicode_str(x) for x in _lst])
            uniq = sorted(list(dict.fromkeys(all_items)))
            if not uniq:
                print("[ERROR] No items in categories.yaml to bootstrap frequency table.")
                return 4
            import pandas as _pd
            df = _pd.DataFrame({
                'hanzi': uniq,
                'count_hkc': 0,
                'count_sub': 0,
                'count_app': 1,
                'tokens_hkc': 0,
                'tokens_sub': 0,
                'tokens_app': len(uniq),
            })
            df['ppm_hkc'] = 0.0
            df['ppm_sub'] = 0.0
            df['ppm_app'] = (1e6 * df['count_app'].astype(float)) / max(len(uniq), 1)
        freq_dir = os.path.dirname(freq_path)
        # Print matched subtitle files for debug
        paths = []
        if args.subtitles_glob:
            for pat in args.subtitles_glob.split(','):
                paths.extend(glob.glob(pat.strip(), recursive=True))
            print("[INFO] Subtitles glob matched {} files: '{}'".format(len(paths), args.subtitles_glob))
        if freq_dir and not os.path.exists(freq_dir):
            os.makedirs(freq_dir)
        try:
            df.to_parquet(freq_path, index=False)
            print("[INFO] Built frequency table with {} rows at {}".format(len(df), freq_path))
        except Exception as e:
            csv_path = freq_path + ".csv"
            df.to_csv(csv_path, index=False)
            print("[WARN] Could not write parquet ({}); wrote CSV to {}".format(e, csv_path))
        return 0

    if args.undo:
        raw_doc, items_map = load_categories(cat_path)
        state = load_state(state_path)
        changed = {}
        chosen = list(items_map.keys())
        if args.only:
            subset = [c.strip() for c in args.only.split(',') if c.strip()]
            chosen = [c for c in chosen if c in subset]
        for cat in chosen:
            rec = state.get('categories', {}).get(cat, {})
            to_remove = list(rec.get('added_items', []))
            if not to_remove:
                continue
            node = raw_doc.get(cat)
            removed_any = False
            if isinstance(node, list):
                before = len(node)
                node[:] = [x for x in node if x not in to_remove]
                removed_any = removed_any or (len(node) != before)
            elif isinstance(node, dict):
                items = node.get('items')
                if isinstance(items, list):
                    before = len(items)
                    items[:] = [x for x in items if x not in to_remove]
                    removed_any = removed_any or (len(items) != before)
            if removed_any:
                changed[cat] = to_remove
                # clear state for this category
                state['categories'].get(cat, {}).update({'added_items': []})
        if changed:
            _yaml_save(cat_path, raw_doc)
            save_state(state_path, state)
            print("[UNDO] Removed auto-added items from {} categories".format(len(changed)))
        else:
            print("[UNDO] No recorded auto-added items to remove.")
        return 0

    if args.refresh_freq:
        raw_doc, items_map = load_categories(cat_path)
        uniq = []
        for cat in items_map:
            uniq.extend(items_map[cat])
        uniq = list(dict.fromkeys(uniq))
        n = len(uniq)
        df = pd.DataFrame({
            'hanzi': uniq,
            'count_hkc': 0,
            'count_sub': 0,
            'count_app': 1,
            'tokens_hkc': 0,
            'tokens_sub': 0,
            'tokens_app': n,
        })
        df['ppm_hkc'] = 0.0
        df['ppm_sub'] = 0.0
        df['ppm_app'] = (1e6 * df['count_app'].astype(float)) / max(n, 1)

        freq_dir = os.path.dirname(freq_path)
        if freq_dir and not os.path.exists(freq_dir):
            os.makedirs(freq_dir)

        try:
            df.to_parquet(freq_path)
            print("[INFO] Bootstrapped frequency table written to {}".format(freq_path))
        except Exception as e:
            csv_path = freq_path + ".csv"
            df.to_csv(csv_path, index=False)
            print("[WARN] Failed to write parquet ({}). Wrote CSV instead to {}".format(e, csv_path))

        print("[INFO] Bootstrapped frequency table with {} items.".format(n))
        return 0

    raw_doc, items_map = load_categories(cat_path)
    if not isinstance(items_map, dict) or not items_map:
        print("[ERROR] Failed to read categories from {}".format(cat_path))
        return 2

    df = load_frequency_table(freq_path)
    # Apply source weights and expose a canonical 'ppm' for gating/sorting
    df = apply_weights(
        df,
        hkc_w=float(getattr(args, 'hkc_weight', 1.0)),
        sub_w=float(getattr(args, 'sub_weight', 0.35)),
        app_w=float(getattr(args, 'app_weight', 0.10)),
        rank_col=str(getattr(args, 'rank_col', 'ppm_weighted')),
    )
    print("[INFO] weighting: hkc={:.3f}, sub={:.3f}, app={:.3f}; rank-col='{}'".format(
        float(getattr(args, 'hkc_weight', 1.0)),
        float(getattr(args, 'sub_weight', 0.35)),
        float(getattr(args, 'app_weight', 0.10)),
        str(getattr(args, 'rank_col', 'ppm_weighted')),
    ))
    if df.empty:
        print("[ERROR] No frequency data available. Aborting.")
        return 3

    chosen_cats = list(items_map.keys())
    if args.only:
        subset = [c.strip() for c in args.only.split(',') if c.strip()]
        chosen_cats = [c for c in chosen_cats if c in subset]
        if not chosen_cats:
            print("[WARN] --only specified but no categories matched. Exiting.")
            return 0

    state = load_state(state_path)
    state.setdefault('categories', {})

    proposed_adds: Dict[str, List[str]] = {}

    for cat in chosen_cats:
        existing = items_map.get(cat, [])
        # merge previously added items from state to avoid re-adding if user reverted YAML
        added_set = set(state['categories'].get(cat, {}).get('added_items', []))
        all_existing = list(existing) + list(sorted(added_set))

        picks, pool, thr = propose_for_category(
            cat=cat,
            df=df,
            existing=all_existing,
            hkc_min=args.hkc_min,
            sub_min=args.sub_min,
            app_min=args.app_min,
            ppm_min=args.ppm_min,
            top_n=args.top_n,
            args=args,
        )

        if not picks:
            print("[INFO] {}: 0 items proposed (thr={:.3f}, existing={}, pool={})".format(cat, thr, len(existing), len(pool)))
            continue

        proposed_adds[cat] = picks
        print("[OK]   {}: +{} items proposed (thr={:.3f})".format(cat, len(picks), thr))
        print("      -> {}".format(", ".join(picks[:10])))

    if args.dry_run and not args.commit:
        print("\n[DRY-RUN] No changes written. Use --commit to apply.")
        return 0

    if not proposed_adds:
        print("[INFO] Nothing to add.")
        return 0

    # Apply changes
    save_categories(cat_path, raw_doc, proposed_adds)

    # Update state
    for cat, picks in proposed_adds.items():
        rec = state['categories'].setdefault(cat, {"added_items": []})
        merged = list(dict.fromkeys(list(rec.get('added_items', [])) + list(picks)))
        rec['added_items'] = merged
    save_state(state_path, state)

    print("\n[COMMIT] Wrote {} categories; state updated at {}".format(len(proposed_adds), state_path))
    return 0


if __name__ == '__main__':
    sys.exit(main())