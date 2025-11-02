#!/usr/bin/env zsh
# Absolute-path runner for expand_categories.py
# Run:  zsh /Users/david/PycharmProjects/LearnCanto_01/tools/run_expand_cats.zsh
set -euo pipefail

# -------- Absolute paths (edit ROOT if your project moved) --------
ROOT="/Users/david/PycharmProjects/LearnCanto_01"
DATA_SUBS_ABS="$ROOT/data/subtitles"
FREQ_ABS="$ROOT/data/frequency/cantonese_wordfreq.parquet"
FREQ_CSV_ABS="$ROOT/data/frequency/cantonese_wordfreq.parquet.csv"
STATE_ABS="$ROOT/data/frequency/category_expansion_state.json"
SCRIPT_ABS="$ROOT/tools/expand_categories.py"

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
python3 "$SCRIPT_ABS" \
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

python3 "$SCRIPT_ABS" "${ARGS[@]}"

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

python3 "$SCRIPT_ABS" "${ARGS_ALL[@]}"

echo "[OK] Done. To apply, re-run with --commit (examples below):"
# Commit example for the first (possibly subset) dry-run
COMMIT_ARGS1=()
for a in "${ARGS[@]}"; do
  [[ "$a" == "--dry-run" ]] || COMMIT_ARGS1+=("$a")
done
echo "python3 $SCRIPT_ABS --commit ${COMMIT_ARGS1[*]}"

# Commit example for the full dry-run (all categories, +10)
COMMIT_ARGS2=()
for a in "${ARGS_ALL[@]}"; do
  [[ "$a" == "--dry-run" ]] || COMMIT_ARGS2+=("$a")
done
echo "python3 $SCRIPT_ABS --commit ${COMMIT_ARGS2[*]}"