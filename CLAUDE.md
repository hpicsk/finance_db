# Claude notes for finance_db

Research repo. No CI; verification is ad-hoc via direct shell / notebook
runs. The authoritative quick-start table is in `README.md`; the
dependency-ordered refresh runbook is `refresh.sh`.

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

## Canonical source mapping for KR status flags

`STATUS_KINDS = ("admin", "audit_qualified", "insincere", "halt", "alert")`
in `kr_status/schema.py`.

- `halt`, `admin`, `alert` → `kr_status/marcap_halt_infer.py`. Halt is
  `marcap.ChangeCode == "0"` (KRX's own daily flag — not the older
  `(Volume==0) & (Open==0)` inference). Admin / alert are
  `marcap.Dept.str.contains("관리종목")` / `("투자주의환기")`.
- `audit_qualified` → `kr_status/dart_audit.py` (DART filings) +
  historical seed from the kr_delisted CSV via
  `kr_status/fdr_collect.py --seed-historical`.
- `insincere` → `kr_status/dart_insincere.py` (DART filings).

FDR `KRX-ADMINISTRATIVE` snapshots and per-corp DART 관리종목 harvests
were retired — marcap.Dept is the authoritative admin source. Don't
reintroduce them without checking with the user.

## Research target is KOSPI + KOSDAQ common stock

KONEX rows are collected and kept filterable (`market == 'KONEX'`) but
are not the analysis target. Methodology choices (e.g. the
`ChangeCode == "0"` halt mask, which over-counts KONEX no-trade days
under the older inference) optimize for KOSPI+KOSDAQ accuracy.

Filter to common stock with `kr_marcap.universe(date, kind='common')`
and `len(ticker) == 6` (drops warrants / rights / ETNs / ETFs / funds).

## Price-data conventions

- Prices in `marcap/` and `kr_delisted/` are **unadjusted** — they match
  KRX's raw history. Use `kr_marcap.adjust.load_adjusted(ticker)` only
  when you need a continuous series for splits / 무상증자 / 감자.
- Tickers are 6-digit zero-padded strings throughout.
- No survivorship bias: marcap and `kr_delisted/delisting_calendar.csv`
  both retain delisted tickers.

## Prerequisites for any refresh / DART step

- conda env (e.g. `source /home/st/miniconda3/bin/activate`) with
  `pandas`, `pyarrow`, `requests`, `OpenDartReader`.
- `marcap/` populated from `github.com/FinanceData/marcap` (manual git
  clone — not vendored here).
- `OPEN_DART_API_KEY` env var for any step that hits DART.