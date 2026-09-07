# Claude notes for finance_db

Research repo, and this directory is a **container only** — no analysis code,
no methodology, no claim assertions at this level. Each package owns its own
loaders, its own documentation and its own `test_assertions.py`. What lives
here: `README.md` (the map between packages), `refresh.sh` (dependency-ordered
refresh runbook), `run_assertions.sh` (runs every package's assertions), and
`.gitignore`.

No CI; verification is ad-hoc via `./run_assertions.sh` or direct shell /
notebook runs.

## Keep the root a container, and each package self-contained

New documentation goes in the package it describes, not here, and it describes
*that* package only. A package's docs do not name another package's files,
methods or findings — not as a pointer, not as a contrast, not as "the same
question answered elsewhere". Those references read as free context and are
not: they turn one package's rewrite into an edit in every package that
mentioned it, and they go stale silently because nothing checks a prose
cross-reference. `README.md` here is the map between packages and is the only
place a reader is told both exist. Likewise a new claim assertion goes in the
`test_assertions.py` of the package whose documentation makes the claim.

## Don't propose merging the three top-level KR packages

- `kr_delisted/` exposes `delisted_loader.universe()` and
  `load_delisted(ticker)` as a public research API (see Quick Start).
- `kr_status/` is per-source PIT event collectors writing one parquet
  each to `kr_status/data/`.
- `kr_marcap/` is a thin price-layer over the marcap parquets, plus
  `kr_marcap.status/` which unifies kr_status events into a single panel
  and exposes `tradable_universe(date)`.

The boundaries are intentional. The newcomer-discoverability concern is
addressed by the dataflow diagram in `README.md` and `refresh.sh` — not
by collapsing packages.

## Research target is KOSPI + KOSDAQ common stock

KONEX rows are collected and kept filterable (`market == 'KONEX'`) but
are not the analysis target, and per-package methodology choices optimize for
KOSPI+KOSDAQ accuracy (see `kr_status/CLAUDE.md` for the halt mask, which is
the case where it matters most).

Filter to common stock with `kr_marcap.universe(date, kind='common')`
and `len(ticker) == 6` (drops warrants / rights / ETNs / ETFs / funds).

## Price-data conventions

- Prices in `marcap/` and `kr_delisted/` are **unadjusted** — they match
  KRX's raw history.
- **Adjusted prices for research come from FnGuide**, the academic
  standard: `fnguide_data.price_loader.load_price_panel()` →
  `adj_close_pr` (수정주가) and `adj_close_tr` (수정주가(현금배당포함)),
  2005+, delisted included. Difference returns within
  `['ticker', 'segment']` — a 6-digit code reissued after its first
  occupant delisted carries both companies in one series, and `segment`
  is where the handover is marked (59 codes).
- `kr_marcap.adjusted_loader.load_adjusted_panel()` (whole panel) and
  `kr_marcap.adjust.load_adjusted(ticker)` (one ticker, with OHLCV) build
  the same two conventions from openly available sources. That
  reconstruction is the *object* of the kr_marcap project, not the
  research input — don't substitute it for the FnGuide series or mix the
  two in one panel. Use it for the raw OHLCV / volume / market cap /
  share counts FnGuide's price export doesn't carry, and see
  `kr_marcap/CONSTRUCTION.md` for how close it gets (99.977 % / 99.969 %
  of daily returns).
- FnGuide's only adjusted **open/high/low** is
  `fnguide_data/raw/fnguide_price_ohlc_{kospi,kosdaq}_exdelisted_20260323.xlsx`,
  pulled under the "delisted excluded" filter — zero delisted coverage by
  construction, so it is not a research price source. See
  `fnguide_data/README.md` §10.
- **Vendor exports are not one snapshot.** Every sheet in
  `fnguide_data/raw/` was pulled in its own DataGuide session (2026-02-14
  through 2026-08-13) and carries its own end date and its own ticker
  universe — a join silently truncates to the earliest input, and column
  counts differ because the live universe moved between pulls. It is per
  *sheet*, not per file: sheets inside one workbook differ in both end date
  and universe. `fnguide_data/vintages.csv` carries every sheet's stamp
  (`fnguide_data.vintages.end_date`), so date a join by `min(...)` of its
  inputs rather than guessing, and never splice two pulls of one series.
  The same
  applies across packages: the `kr_marcap` benchmark against FnGuide is
  bounded by the marcap vintage, not the FnGuide pull. Before joining
  sheets or quoting a coverage figure, read
  `fnguide_data/README.md` § "Every sheet has its own pull date" and check
  which pull the figure came from.
- Tickers are 6-digit zero-padded strings throughout.
- No survivorship bias: marcap and `kr_delisted/delisting_calendar.csv`
  both retain delisted tickers.

## Prerequisites for any refresh / DART step

- conda env (e.g. `source /home/st/miniconda3/bin/activate`) with
  `pandas`, `pyarrow`, `requests`, `OpenDartReader`, `python-calamine`.
- `marcap/` populated from `github.com/FinanceData/marcap` (manual git
  clone — not vendored here).
- `OPEN_DART_API_KEY` env var for any step that hits DART.
