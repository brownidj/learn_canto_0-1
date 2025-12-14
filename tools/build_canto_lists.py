# tools/build_canto_lists.py
# Reads data/zhwikt.jsonl and writes data/wordslist.csv and data/charlist.csv
# No f-strings per your preference.

import os, json, csv, re
from collections import defaultdict, Counter

DATA_JSONL = os.path.join("data", "zhwikt.jsonl")
WORDS_CSV = os.path.join("data", "wordslist.csv")
CHARS_CSV = os.path.join("data", "charlist.csv")

_jyut_sep_re = re.compile(r"[,\s/、；;]+")

def norm_jyut(s):
    if not isinstance(s, str):
        return None
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s or None

def extract_jyut_list(rec):
    out = []

    # 1) Common wiktextract field: "jyutping": list[str]  OR str
    jp = rec.get("jyutping")
    if isinstance(jp, list):
        for x in jp:
            x = norm_jyut(x)
            if x:
                out.append(x)
    elif isinstance(jp, str):
        for x in _jyut_sep_re.split(jp):
            x = norm_jyut(x)
            if x:
                out.append(x)

    # 2) Sometimes pronunciations live under "pronunciations" as list of dicts
    pr = rec.get("pronunciations")
    if isinstance(pr, list):
        for item in pr:
            if isinstance(item, dict):
                # common keys seen: "raw", "zh", "yue", "jyutping"
                for k in ("jyutping", "yue", "raw"):
                    v = item.get(k)
                    if isinstance(v, list):
                        for x in v:
                            x = norm_jyut(x)
                            if x:
                                out.append(x)
                    elif isinstance(v, str):
                        for x in _jyut_sep_re.split(v):
                            x = norm_jyut(x)
                            if x:
                                out.append(x)

    # Deduplicate but keep order
    seen = set()
    dedup = []
    for x in out:
        if x not in seen:
            seen.add(x)
            dedup.append(x)
    return dedup

def is_cantonese(rec):
    if not isinstance(rec, dict):
        return False
    if rec.get("redirect"):
        return False
    lc = rec.get("lang_code") or ""
    lang = rec.get("lang") or ""
    return lc == "yue" or (isinstance(lang, str) and "cantonese" in lang.lower())

def main():
    if not os.path.exists(DATA_JSONL):
        print("Missing " + DATA_JSONL)
        return

    words = {}  # hanzi -> {"jyut": set, "senses": int}
    char_jyut = defaultdict(set)   # char -> set(jyut)
    char_examples = defaultdict(Counter)  # char -> Counter(words)

    with open(DATA_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if not is_cantonese(rec):
                continue

            title = rec.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            title = title.strip()

            jyut_list = extract_jyut_list(rec)
            if not jyut_list:
                continue

            # Count senses to give a rough idea of richness
            sense_count = 0
            senses = rec.get("senses")
            if isinstance(senses, list) and senses:
                sense_count = len(senses)

            # Word bucket
            w = words.get(title)
            if not w:
                w = {"jyut": set(), "senses": 0}
                words[title] = w
            for j in jyut_list:
                w["jyut"].add(j)
            if sense_count > 0:
                w["senses"] = max(w["senses"], sense_count)

            # Character aggregation
            for ch in title:
                for j in jyut_list:
                    char_jyut[ch].add(j)
                # Track example words for characters
                if len(title) > 1:
                    char_examples[ch][title] += 1

    # Write wordslist.csv
    os.makedirs(os.path.dirname(WORDS_CSV), exist_ok=True)
    with open(WORDS_CSV, "w", encoding="utf-8", newline="") as wf:
        wwriter = csv.writer(wf)
        wwriter.writerow(["hanzi", "title_len", "jyutping_list", "count_senses"])
        for hanzi in sorted(words.keys(), key=lambda s: (len(s), s)):
            jy = sorted(words[hanzi]["jyut"])
            wwriter.writerow([hanzi, len(hanzi), ";".join(jy), words[hanzi]["senses"]])

    # Write charlist.csv
    with open(CHARS_CSV, "w", encoding="utf-8", newline="") as cf:
        cwriter = csv.writer(cf)
        cwriter.writerow(["char", "jyutping_list", "word_examples"])
        for ch in sorted(char_jyut.keys()):
            jy = sorted(char_jyut[ch])
            # top 5 example words, most frequent first, then alpha
            ex = char_examples[ch]
            top = [w for (w, _) in sorted(ex.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]
            cwriter.writerow([ch, ";".join(jy), " ".join(top)])

    print("Wrote " + WORDS_CSV)
    print("Wrote " + CHARS_CSV)

if __name__ == "__main__":
    main()