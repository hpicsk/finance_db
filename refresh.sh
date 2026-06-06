#!/usr/bin/env bash
# finance_db/refresh.sh — runbook for refreshing the Korean PIT data pipeline.
#
# Documents the dependency order; does NOT run end-to-end by default. Each
# step has its own cadence (yearly marcap pull, quarterly delisting refresh,
# annual DART audit re-pull, etc.). Uncomment the steps you want.
#
# Prerequisites (out-of-band):
#   * conda env with pandas, pyarrow, requests, OpenDartReader on PATH
#       e.g.  source /home/st/miniconda3/bin/activate
#   * marcap/  populated from github.com/FinanceData/marcap (manual git clone)
#   * API keys loaded from .env (gitignored). Includes OPEN_DART_API_KEY,
#     ECOS_API_KEY, FMP_API_KEY, FRED_API_KEY.

set -euo pipefail
cd "$(dirname "$0")"

# Load API keys from .env if present.
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi

# ── 1. kr_delisted — KIND scrape + DART is_genuine refinement ─────────────
#    Cadence: refresh when KIND publishes new delistings (~quarterly).
# python -m kr_delisted.build_delisting_calendar             # ~30s, no DART
# python -m kr_delisted.build_is_genuine_overrides           # few min, needs DART key

# ── 2. kr_status — per-source PIT event collectors ────────────────────────
#    Cadence: see kr_status/README.md. Each writes one parquet to data/,
#    independent of the others.
# python -m kr_status.marcap_halt_infer                       # after each marcap refresh
# python -m kr_status.fdr_collect --seed-historical           # after kr_delisted refresh
# python -m kr_status.dart_insincere                          # quarterly; DART
# python -m kr_status.dart_audit                              # annually (post-Mar); DART

# ── 3. kr_marcap.status — unify event parquets into a single panel ────────
#    Cadence: after any kr_status collector runs. Pure local read.
# python -m kr_marcap.status.build_panel
