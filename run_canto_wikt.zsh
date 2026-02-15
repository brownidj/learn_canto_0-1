#!/usr/bin/env zsh
set -euo pipefail

# --- Paths
PROJ_ROOT="${PWD}"
SRC_BZ2="${PROJ_ROOT}/data/zhwiktionary-latest-pages-articles.xml.bz2"
CANTO_XML="${PROJ_ROOT}/data/zhwiktionary_cantonese.xml"
JSONL="${PROJ_ROOT}/data/zhwikt.jsonl"

# Try both possible locations for your builders
BUILD_PY_TOOLS="${PROJ_ROOT}/tools/build_canto_lists.py"
BUILD_PY_DATA="${PROJ_ROOT}/data/build_canto_lists.py"
if [[ -f "${BUILD_PY_TOOLS}" ]]; then
  BUILD_PY="${BUILD_PY_TOOLS}"
elif [[ -f "${BUILD_PY_DATA}" ]]; then
  BUILD_PY="${BUILD_PY_DATA}"
else
  echo "[FATAL] build_canto_lists.py not found in tools/ or data/"; exit 2
fi

echo "[INFO] Source dump: ${SRC_BZ2}"
if [[ ! -s "${SRC_BZ2}" ]]; then
  echo "[FATAL] Missing or empty source dump. Expected a non-zero file at ${SRC_BZ2}"
  exit 1
fi

# We now parse the FULL dump and post-filter inside the Python wrapper
INPUT_PATH="${SRC_BZ2}"
echo "[INFO] Using:\n       XML     : ${INPUT_PATH}\n       JSONL   : ${JSONL}\n       builder : ${BUILD_PY}"

# --- 2) Run wiktextract wrapper → JSONL
echo "[STEP] Extract Cantonese entries -> JSONL"
python3 "${PROJ_ROOT}/tools/run_wiktextract.py" \
  "${INPUT_PATH}" \
  zh \
  "${JSONL}"

if [[ ! -s "${JSONL}" ]]; then
  echo "[FATAL] wiktextract produced an empty JSONL at ${JSONL}"
  exit 1
fi

echo "[OK] Wrote ${JSONL} (lines: $(wc -l < "${JSONL}" | tr -d ' '))"

# --- 3) Build words & chars lists (uses whatever path your builder lives at)
echo "[INFO] Building wordslist.csv & charlist.csv from ${JSONL} using ${BUILD_PY}"
python3 "${BUILD_PY}"

# Sanity checks on CSVs
for CSV in "${PROJ_ROOT}/data/wordslist.csv" "${PROJ_ROOT}/data/charlist.csv"; do
  if [[ ! -s "${CSV}" ]]; then
    echo "[FATAL] ${CSV} is missing or empty."
    exit 1
  fi
done

echo "[OK] data/wordslist.csv (rows incl header): $(wc -l < "${PROJ_ROOT}/data/wordslist.csv" | tr -d ' ')"
echo "[OK] data/charlist.csv (rows incl header): $(wc -l < "${PROJ_ROOT}/data/charlist.csv" | tr -d ' ')"
echo "[OK] Done."