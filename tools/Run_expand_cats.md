```zsh
#!/usr/bin/env zsh
set -euo pipefail

echo "Stop any stray processes"
pkill -f expand_categories.py 2>/dev/null || true

echo "Clear derived artifacts (fresh rebuild)"
rm -f data/frequency/cantonese_wordfreq.parquet \
      data/frequency/cantonese_wordfreq.parquet.csv \
      data/frequency/category_expansion_state.json

echo "Quick sanity checks"
pwd
print -l data/subtitles/**/*.srt | wc -l

echo "Rebuild the frequency table (HKCanCor + your SRTs)"
python3 tools/expand_categories.py \
  --build-freq \
  --include-hkcancor \
  --subtitles-glob "data/subtitles/**/*.srt"

echo "Verify the frequency file is readable"
python3 - <<'PY'
import pandas as pd
df = pd.read_parquet("data/frequency/cantonese_wordfreq.parquet")
print("Rows:", len(df), "| columns:", list(df.columns)[:12])
print(df.head(8))
PY

echo "Minimal, safe dry-run (small workload first)"
python3 tools/expand_categories.py \
  --dry-run \
  --only greetings,measurements,nature_air \
  --rank-col ppm_weighted \
  --hkc-weight 1.0 --sub-weight 0.35 --app-weight 0.0 \
  --hkc-min 0 --sub-min 1 --app-min 0 \
  --no-pct --ppm-min 0.01 \
  --top-n 10

echo "Done."
```