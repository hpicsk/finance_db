#!/usr/bin/env bash
# finance_db/run_assertions.sh — run every package's claim assertions.
#
# This directory is a container and holds no test logic. Each package owns the
# assertions behind the claims its own documentation makes, in its own
# test_assertions.py; this script finds them, runs them, and fails if any
# package fails. There is no CI, so this is the gate.
#
# Prerequisites: the data trees populated (marcap/ cloned, caches built) and a
# conda env with pandas + pyarrow on PATH — e.g.
#   source /home/st/miniconda3/bin/activate

set -uo pipefail
cd "$(dirname "$0")"

files=(*/test_assertions.py)
if [ ! -e "${files[0]}" ]; then
  echo "no */test_assertions.py found — wrong directory?" >&2
  exit 1
fi

# The study window is duplicated in each package's file, because the container
# holds no shared module to import it from. Drift between the copies would
# silently change what every downstream check measures without failing anything,
# so the copies are compared here rather than trusted.
windows=$(grep -h '^WIN_START\|^WIN_END' "${files[@]}" | sort -u)
if [ "$(echo "$windows" | wc -l)" -ne 2 ]; then
  echo "FAIL  study-window constants disagree across packages:" >&2
  echo "$windows" >&2
  exit 1
fi

failed=()
for f in "${files[@]}"; do
  pkg=$(dirname "$f")
  echo "── $pkg ──────────────────────────────────────────────"
  python "$f" || failed+=("$pkg")
  echo
done

if [ ${#failed[@]} -ne 0 ]; then
  echo "FAILED: ${failed[*]}"
  exit 1
fi
echo "all packages passed"
