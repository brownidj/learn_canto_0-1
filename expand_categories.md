Here’s everything you can tweak besides --dry-run / --commit:
•	--categories PATH – path to categories.yaml (repo-root relative by default).
•	--freq-file PATH – path to the frequency table (Parquet or CSV).
•	--state-file PATH – path to the state JSON used for undo/dup-avoidance.
•	--only a,b,c – run on a subset of categories.
•	--top-n 10 – how many new items to propose per category.

Gates (what’s allowed into the pool)
•	--ppm-min 2.0 – minimum weighted frequency (ppm) hard gate.
•	--hkc-min 2 – minimum HKCanCor hits for presence gate.
•	--sub-min 8 – minimum subtitles hits for presence gate.
•	--app-min 0 – minimum “app/bootstrap” hits (useful after --refresh-freq).

Build/refresh frequency data
•	--build-freq – build a frequency table from corpora (see below).
•	--include-hkcancor – include HKCanCor via pycantonese in the build.
•	--subtitles-glob "data/subtitles/**/*.{srt,txt}" – subtitles to include.
•	--min-len 1 / --max-len 4 – token length bounds during build.
•	--refresh-freq – bootstrap a simple table from current categories (app counts).

Safety / maintenance
•	--undo – remove previously auto-added items (respects --only).


# Build real frequencies, then preview
python3 tools/expand_categories.py --build-freq --include-hkcancor \
--subtitles-glob "data/subtitles/**/*.{srt,txt}"

python3 tools/expand_categories.py --dry-run --ppm-min 1.5

# Work on just two categories, 5 items each
python3 tools/expand_categories.py --dry-run --only people,technology_media --top-n 5

# Bootstrap frequencies from current YAML, then allow app-only presence
python3 tools/expand_categories.py --refresh-freq
python3 tools/expand_categories.py --dry-run --hkc-min 0 --sub-min 0 --app-min 1

# Undo last auto-adds
python3 tools/expand_categories.py --undo