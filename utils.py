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
import os
import io
import yaml

# Canonical value shape: [[english...], "jyutping"]

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
# 4) Pretty report helpers
# ----------------------------
def format_duplicate_report(dups):
  if not dups:
    return "No exact duplicates found."
  lines = ["Exact duplicates (same key + english list):"]
  for k, eng, locs in dups:
    lines.append("- {} :: {} at lines {}".format(k, eng, locs))
  return "\n".join(lines)


if __name__ == "__main__":
  try:
    canonical = load_andys_list_yaml()
    dups = find_same_english_across_keys_canonical(canonical)
    if not dups:
      print("Loaded andys_list.yaml successfully. No cross-key identical-English groups detected.")
    else:
      print("Groups sharing identical English lists across different Hanzi:")
      for eng, keys in sorted(dups.items(), key=lambda x: tuple(x[1])):
        print("- {} :: {}".format(keys, list(eng)))
  except IOError as e:
    print(str(e))