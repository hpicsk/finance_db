#!/usr/bin/env bash
# Resumable dart_audit harvester. Run daily until the events parquet appears.
# Exits 0 on success, non-zero when DART quota tripped (status 020/021) — that
# is the normal end-of-day exit; rerun tomorrow and it picks up from cache.
#
# Cache:  kr_status/data/dart_audit_opinions.parquet
# Output: kr_status/data/dart_audit_events.parquet  (only on full completion)
# Log:    kr_status/runtime/_log_audit.txt
set -uo pipefail   # no -e: we want to log non-zero exits, not abort

PROJECT_DIR="${PROJECT_DIR:-/home/st/finance_db}"
PYTHON="${PYTHON:-/home/st/miniconda3/bin/python}"
LOG="$PROJECT_DIR/kr_status/runtime/_log_audit.txt"

[ -f "$HOME/.dart_env" ] && { set -a; . "$HOME/.dart_env"; set +a; }

cd "$PROJECT_DIR"
{
  echo "[$(date -Iseconds)] dart_audit --year-from 2015 --year-to 2024 (resume)"
  "$PYTHON" -m kr_status.dart_audit --year-from 2015 --year-to 2024
  rc=$?
  echo "[$(date -Iseconds)] exit=$rc"
  exit "$rc"
} >> "$LOG" 2>&1
