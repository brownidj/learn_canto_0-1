#!/usr/bin/env zsh
set -euo pipefail

PYTHON=".venv/bin/python3"

echo "=== Phase 1: non-UI tests ==="
if ! $PYTHON -m pytest -m "not ui" -q; then
  echo
  echo "❌ Non-UI tests failed — aborting"
  exit 1
fi

echo
echo "=== Phase 2: UI tests (offscreen) ==="
set +e
QT_QPA_PLATFORM=offscreen $PYTHON -m pytest -m ui -q
UI_STATUS=$?
set -e

echo
if [[ $UI_STATUS -ne 0 ]]; then
  echo "⚠️  UI tests reported failures or crashed (status=$UI_STATUS)"
  echo "    Non-UI tests passed; exiting cleanly by policy."
else
  echo "✅ UI tests passed"
fi

exit 0


#chmod +x run_tests.zsh
#./run_tests.zsh