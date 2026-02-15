```zsh
/usr/bin/env python3 tools/expand_categories.py \
  --categories categories.yaml \
  --freq-file data/frequency/cantonese_wordfreq.parquet \
  --state-file data/frequency/category_expansion_state.json \
  --commit \
  —-below 20  \
  --rank-col ppm_weighted \
  --hkc-weight 1.0 --sub-weight 0.5 --app-weight 0.0 \
  --hkc-min 0 --sub-min 0 --app-min 0 \
  --no-cat-filter \
  --no-pct --ppm-min 0.001 \
  --min-len 1 --max-len 4 \
  --top-n 30
```