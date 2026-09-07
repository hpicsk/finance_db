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

# ── 4. kr_marcap price adjustment — official corporate-action ground truth ─
#    Cadence: after a marcap refresh. Replaces the old calibrated heuristics
#    with DART/KIND/KRX-수정주가 sources. See kr_marcap/CORPORATE_ACTIONS_SPEC.md.
#    Two-pass bootstrap (the DART collector keys off the candidate list the
#    build writes); collectors are resume-safe.
# python -m kr_marcap.adjust build                              # pass 0: seed candidates
# python -m kr_status.dart_corp_actions                        # DART 증자/감자/합병/분할 (~30m)
# python -m kr_marcap.krx_adj_oracle --all                     # KRX 수정주가 oracle (~1-2h)
# python -m kr_marcap.adjust build                             # rebuild with ground truth
# python -m kr_marcap.validate_against_oracle                  # inside gate vs KRX 수정주가

# ── 5. Benchmark the reconstruction against the paid FnGuide series ───────
#    Cadence: after any adjust rebuild, or a new DataGuide 수정주가 export.
#    The oracle gate above cannot see reset-override failures — adjust.py
#    assigns from the oracle there, so the two agree by construction. Only an
#    outside source can. See kr_marcap/CONSTRUCTION.md.
#    Note the two sides carry independent vintages: the comparison window is
#    their intersection, so re-pulling *either* side changes what was graded.
# python -m fnguide_data.price_loader                          # adjusted-price export → parquet (~1m)
# python -m kr_marcap.validate_against_fnguide                 # outside gate (~5m)

# ── 5b. Re-pulled any DataGuide export? Re-stamp the vintage manifest ─────
#    Cadence: after replacing ANY file in fnguide_data/raw/. Each sheet has its
#    own pull date and its own universe; vintages.csv is what makes those
#    readable without parsing 6.5 GB, and run_assertions.sh fails until it
#    matches what is on disk. ~30s — it streams headers, it does not read data.
# python -m fnguide_data.vintages

# ── 6. Re-run every package's claim assertions ────────────────────────────
#    Cadence: after ANY step above. Regenerated data invalidates the claims
#    the package documentation makes about it; this is the only gate (no CI).
# ./run_assertions.sh
