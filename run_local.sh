#!/usr/bin/env bash
# One-click local run.
#
#   ./run_local.sh                  # process every date found in samples/
#   ./run_local.sh 20260410 20260414  # only these dates
#   ./run_local.sh --install        # pip install -r requirements.txt first
#
# For each date it runs the per-image pipeline (md/csv/chart + records.csv),
# then a combined report (xlsx + 3 charts) across all dates. Works fully
# offline using the sidecar JSON in samples/ and the cached benchmarks.
set -euo pipefail

cd "$(dirname "$0")"

PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || { echo "ERROR: python not found on PATH" >&2; exit 1; }

ARGS=()
for a in "$@"; do
  if [ "$a" = "--install" ]; then
    "$PY" -m pip install -r requirements.txt
  else
    ARGS+=("$a")
  fi
done

# Resolve the list of YYYYMMDD dates: explicit args, else everything that has
# a sidecar JSON or an image in samples/.
DATES=()
if [ "${#ARGS[@]}" -gt 0 ]; then
  DATES=("${ARGS[@]}")
else
  while IFS= read -r d; do DATES+=("$d"); done < <(
    ls samples/ 2>/dev/null \
      | grep -oE '^[0-9]{8}' \
      | sort -u
  )
fi

if [ "${#DATES[@]}" -eq 0 ]; then
  echo "ERROR: no dates found. Put 20260410.json (or .png) in samples/." >&2
  exit 1
fi

echo "Processing ${#DATES[@]} date(s): ${DATES[*]}"

for d in "${DATES[@]}"; do
  echo "--- $d ---"
  "$PY" -m pipeline.run "samples/${d}.png"
done

echo "--- combined report ---"
"$PY" -m pipeline.combined "${DATES[@]}"

echo
echo "Done. See the output/ folder:"
ls -1 output/ | tail -n 12
