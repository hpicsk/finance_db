#!/usr/bin/env bash
# Resumable dart_audit harvester. Run daily until it exits 0.
# Exits 0 on success, non-zero when DART quota tripped (status 020/021) — that
# is the normal end-of-day exit; rerun tomorrow and it picks up from cache.
#
# Output: kr_status/data/dart_audit_opinions.parquet  (also the resume cache)
# Log:    kr_status/runtime/_log_audit.txt
#
# Runs from the repo root it sits under, with the interpreter on PATH (activate
# the conda env first) and OPEN_DART_API_KEY from the root .env, the same way
# refresh.sh does.
set -uo pipefail   # no -e: we want to log non-zero exits, not abort

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$PROJECT_DIR/kr_status/runtime/_log_audit.txt"

cd "$PROJECT_DIR"
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi
mkdir -p kr_status/runtime
{
  echo "[$(date -Iseconds)] dart_audit --year-from 2015 --year-to 2024 (resume)"
  python -m kr_status.dart_audit --year-from 2015 --year-to 2024
  rc=$?
  echo "[$(date -Iseconds)] exit=$rc"
  exit "$rc"
} >> "$LOG" 2>&1
