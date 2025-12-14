#!/usr/bin/env zsh
# Absolute-path runner for expand_categories.py
# Run:  zsh /Users/david/PycharmProjects/LearnCanto_01/tools/run_expand_cats.zsh

# --- Project paths (robust defaults) ---
PROJ_ROOT=${PROJ_ROOT:-"$(cd "$(dirname "$0")/.." && pwd)"}
CAT_PATH="${CAT_PATH:-${PROJ_ROOT}/categories.yaml}"
FREQ_PATH="${FREQ_PATH:-${PROJ_ROOT}/data/frequency/cantonese_wordfreq.parquet}"
STATE_PATH="${STATE_PATH:-${PROJ_ROOT}/data/frequency/category_expansion_state.json}"

set -euo pipefail

# -------- Args --------
CONTINUE_MODE=0
if [[ ${#@} -gt 0 ]]; then
  case "$1" in
    --continue)
      CONTINUE_MODE=1
      shift
      ;;
  esac
fi

# -------- Absolute paths (edit ROOT if your project moved) --------
ROOT="/Users/david/PycharmProjects/LearnCanto_01"
DATA_SUBS_ABS="$ROOT/data/subtitles"
FREQ_ABS="$ROOT/data/frequency/cantonese_wordfreq.parquet"
FREQ_CSV_ABS="$ROOT/data/frequency/cantonese_wordfreq.parquet.csv"
STATE_ABS="$ROOT/data/frequency/category_expansion_state.json"
SCRIPT_ABS="$ROOT/tools/expand_categories.py"

# -------- Helpers --------
snapshot_counts() {
  local OUT_JSON="$1"
  /usr/bin/env python3 - "$CAT_PATH" "$OUT_JSON" <<'PY'
import sys, json
cat_path, out_path = sys.argv[1], sys.argv[2]

# Robust YAML loader: prefer PyYAML, fallback to ruamel.yaml
try:
    import yaml
    def _load(fp): return yaml.safe_load(fp)
except Exception:
    from ruamel.yaml import YAML
    _yaml = YAML(typ='safe')
    def _load(fp): return _yaml.load(fp)

with open(cat_path, 'r', encoding='utf-8') as fh:
    data = _load(fh) or {}

def _count(v):
    if isinstance(v, dict) and isinstance(v.get('items'), list):
        return len(v['items'])
    if isinstance(v, list):
        return len(v)
    return 0

sizes = {k: _count(v) for k, v in data.items()}
obj = {
    'total': sum(sizes.values()),
    'sizes': sizes,
    'keys_n': len(sizes),
}
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(obj, f, ensure_ascii=False)
print(f"[DEBUG] Snapshot written: {out_path}")
PY
}

print_counts_report() {
  local SNAP_JSON="$1"
  echo "[REPORT] Category sizes (total items & per category)"
  /usr/bin/env python3 - "$SNAP_JSON" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], 'r'))
# Expecting keys: total, sizes, keys_n
sizes = j.get('sizes', {})
print(f"Total items: {j.get('total',0)} across {j.get('keys_n',len(sizes))} categories")
for k in sorted(sizes.keys()):
    print(f"  - {k}: {sizes[k]}")
PY
}

print_diff_report() {
  local BEFORE_JSON="$1" AFTER_JSON="$2"
  echo "[REPORT] Additions by category (new_count = old + delta)"
  /usr/bin/env python3 - "$BEFORE_JSON" "$AFTER_JSON" <<'PY'
import json, sys
b = json.load(open(sys.argv[1], 'r'))
a = json.load(open(sys.argv[2], 'r'))
# Expect sizes/total; fallback to counts/total_items if old shape
cb = b.get('sizes') or b.get('counts', {})
ca = a.get('sizes') or a.get('counts', {})
keys = sorted(set(cb) | set(ca))
added_any = False
for k in keys:
    ob, oa = int(cb.get(k, 0)), int(ca.get(k, 0))
    d = oa - ob
    mark = f" (+{d})" if d>0 else ""
    if d>0:
        added_any = True
    print(f"  - {k}: {oa}{mark}")
if not added_any:
    print("  (no changes)")
bt = int(b.get('total', b.get('total_items', 0)))
at = int(a.get('total', a.get('total_items', 0)))
print(f"Totals: {bt} -> {at} (+{at-bt})")
PY
}

# -------- Tunables (env overrides OK) --------
: ${ONLY_CATS:=greetings,measurements,nature_air}
: ${HKC_WEIGHT:=1.0}
: ${SUB_WEIGHT:=0.35}
: ${APP_WEIGHT:=0.0}
: ${RANK_COL:=ppm_weighted}
: ${NO_PCT:=1}        # 1 = use floor; 0 = use percentile
: ${PPM_MIN:=0.01}
: ${PCT:=0.40}        # 0–1 (not 0–100)
: ${TOPN:=10}
# keep as a quoted string so zsh does NOT expand it; Python will
: ${SUB_GLOB:="$DATA_SUBS_ABS/**/*.srt"}
# If continuing, default to all categories and a +10 batch unless overridden
if [[ "$CONTINUE_MODE" == "1" ]]; then
  : ${ONLY_CATS:=''}
  : ${TOPN:=10}
fi

echo "[INFO] Stop any stray processes"
pkill -f expand_categories.py 2>/dev/null || true

echo "[INFO] Clear derived artifacts (fresh rebuild)"
rm -f "$FREQ_ABS" "$FREQ_CSV_ABS" "$STATE_ABS"

echo "[INFO] Quick sanity checks"
echo "$PWD"
SRT_COUNT=$(find "$DATA_SUBS_ABS" -type f -name '*.srt' 2>/dev/null | wc -l | tr -d ' ')
echo "[INFO] Subtitle .srt files under $DATA_SUBS_ABS: $SRT_COUNT"
if [[ "$SRT_COUNT" == "0" ]]; then
  echo "[ERROR] No .srt files found under $DATA_SUBS_ABS"
  exit 1
fi

echo "[INFO] Rebuild the frequency table (HKCanCor + your SRTs)"
/usr/bin/env python3 "${PROJ_ROOT}/tools/expand_categories.py" \
  --categories "${CAT_PATH}" \
  --freq-file "${FREQ_PATH}" \
  --state-file "${STATE_PATH}" \
  --build-freq \
  --include-hkcancor \
  --subtitles-glob "$SUB_GLOB"

echo "[INFO] Verify the frequency file is readable"
python3 - <<PY
import pandas as pd, pathlib
p = pathlib.Path(r"$FREQ_ABS")
assert p.exists(), f"freq parquet not found: {p}"
df = pd.read_parquet(p)
print("Rows:", len(df), "| columns:", list(df.columns)[:16])
print(df.head(8))
PY

echo "[INFO] Minimal, safe dry-run (small workload first)"
ARGS=(
  --dry-run
  --rank-col "$RANK_COL"
  --hkc-weight "$HKC_WEIGHT" --sub-weight "$SUB_WEIGHT" --app-weight "$APP_WEIGHT"
  --hkc-min 0 --sub-min 1 --app-min 0
  --top-n "$TOPN"
)
if [[ -n "$ONLY_CATS" ]]; then
  ARGS+=( --only "$ONLY_CATS" )
fi
if [[ -n "$NO_PCT" && "$NO_PCT" != "0" ]]; then
  ARGS+=( --no-pct --ppm-min "$PPM_MIN" )
else
  ARGS+=( --pct "$PCT" )
fi

SNAP_BEFORE=$(mktemp -t cat_counts_before)
snapshot_counts "$SNAP_BEFORE"
print_counts_report "$SNAP_BEFORE"

/usr/bin/env python3 "${PROJ_ROOT}/tools/expand_categories.py" \
  --categories "${CAT_PATH}" \
  --freq-file "${FREQ_PATH}" \
  --state-file "${STATE_PATH}" \
  "${ARGS[@]}"

echo "[INFO] Full dry-run across all categories (up to +10 per category)"
ARGS_ALL=(
  --dry-run
  --rank-col "$RANK_COL"
  --hkc-weight "$HKC_WEIGHT" --sub-weight "$SUB_WEIGHT" --app-weight "$APP_WEIGHT"
  --hkc-min 0 --sub-min 1 --app-min 0
  --top-n 10
)

# Apply the same thresholding mode as the first run
if [[ -n "$NO_PCT" && "$NO_PCT" != "0" ]]; then
  ARGS_ALL+=( --no-pct --ppm-min "$PPM_MIN" )
else
  ARGS_ALL+=( --pct "$PCT" )
fi

/usr/bin/env python3 "${PROJ_ROOT}/tools/expand_categories.py" \
  --categories "${CAT_PATH}" \
  --freq-file "${FREQ_PATH}" \
  --state-file "${STATE_PATH}" \
  "${ARGS_ALL[@]}"
# Pre-commit reminder of current sizes
print_counts_report "$SNAP_BEFORE"

if [[ "$CONTINUE_MODE" == "1" ]]; then
  echo "[INFO] Continue mode: committing full expansion (up to +$TOPN per category)"
  COMMIT_ALL=()
  for a in "${ARGS_ALL[@]}"; do
    [[ "$a" == "--dry-run" ]] || COMMIT_ALL+=("$a")
  done
  /usr/bin/env python3 "${PROJ_ROOT}/tools/expand_categories.py" \
    --categories "${CAT_PATH}" \
    --freq-file "${FREQ_PATH}" \
    --state-file "${STATE_PATH}" \
    --commit "${COMMIT_ALL[@]}"

  # Post-commit reporting
  SNAP_AFTER=$(mktemp -t cat_counts_after)
  snapshot_counts "$SNAP_AFTER"
  print_diff_report "$SNAP_BEFORE" "$SNAP_AFTER"
  echo "[REPORT] Category sizes after commit"
  print_counts_report "$SNAP_AFTER"

  echo "[OK] Continue mode commit complete."
fi

echo "[OK] Done. To apply, re-run with --commit (examples below):"
# Commit example for the first (possibly subset) dry-run
COMMIT_ARGS1=()
for a in "${ARGS[@]}"; do
  [[ "$a" == "--dry-run" ]] || COMMIT_ARGS1+=("$a")
done
echo "/usr/bin/env python3 ${PROJ_ROOT}/tools/expand_categories.py --categories ${CAT_PATH} --freq-file ${FREQ_PATH} --state-file ${STATE_PATH} --commit ${COMMIT_ARGS1[*]}"

# Commit example for the full dry-run (all categories, +10)
COMMIT_ARGS2=()
for a in "${ARGS_ALL[@]}"; do
  [[ "$a" == "--dry-run" ]] || COMMIT_ARGS2+=("$a")
done
echo "/usr/bin/env python3 ${PROJ_ROOT}/tools/expand_categories.py --categories ${CAT_PATH} --freq-file ${FREQ_PATH} --state-file ${STATE_PATH} --commit ${COMMIT_ARGS2[*]}"

if [[ "$CONTINUE_MODE" != "1" ]]; then
  echo "[OK] Done. To apply, re-run with --commit (examples below):"
  # Commit example for the first (possibly subset) dry-run
  COMMIT_ARGS1=()
  for a in "${ARGS[@]}"; do
    [[ "$a" == "--dry-run" ]] || COMMIT_ARGS1+=("$a")
  done
  echo "/usr/bin/env python3 ${PROJ_ROOT}/tools/expand_categories.py --categories ${CAT_PATH} --freq-file ${FREQ_PATH} --state-file ${STATE_PATH} --commit ${COMMIT_ARGS1[*]}"

  # Commit example for the full dry-run (all categories, +10)
  COMMIT_ARGS2=()
  for a in "${ARGS_ALL[@]}"; do
    [[ "$a" == "--dry-run" ]] || COMMIT_ARGS2+=("$a")
  done
  echo "/usr/bin/env python3 ${PROJ_ROOT}/tools/expand_categories.py --categories ${CAT_PATH} --freq-file ${FREQ_PATH} --state-file ${STATE_PATH} --commit ${COMMIT_ARGS2[*]}"
  # Also show current category sizes for reference
    print_counts_report "$SNAP_BEFORE"
fi

# --- Always-on final reporting (runs in both dry-run and continue modes) ---
echo "[REPORT] Final verification snapshot"
if [[ "${CONTINUE_MODE}" == "1" && -n "${SNAP_AFTER:-}" && -f "${SNAP_AFTER}" ]]; then
  SNAP_FINAL="$SNAP_AFTER"
else
  SNAP_FINAL=$(mktemp -t cat_counts_final)
  snapshot_counts "$SNAP_FINAL"
fi

echo "[REPORT] Additions by category (since first snapshot)"
print_diff_report "$SNAP_BEFORE" "$SNAP_FINAL"

echo "[REPORT] Final category sizes"
print_counts_report "$SNAP_FINAL"