# finance_db — Korean & Taiwan equity research data

Central data repository backing my quantitative-finance research on Korean
(and, for cross-market validation, Taiwanese) equities. Holds **raw
exports**, **per-source loaders**, and **methodology notes** documenting
exactly how each universe was pulled, filtered, and joined.

> **Licensing:** FnGuide DataGuide is a paid subscription. KRX/KIND data
> is publicly accessible but rate-limited. FinMind is a free-tier API
> (token required). The large raw data files are **not** committed to
> this repo — see `.gitignore`. What's tracked is code, documentation,
> and small index/calendar CSVs sufficient to reproduce universes.

## Layout

```
finance_db/
├── README.md                 (this file — overview + universe rules)
├── .gitignore                (excludes large data + credentials)
│
├── fnguide_data/             FnGuide DataGuide export tree (Korean equities)
│   ├── fnguide_io.py / investor_loader.py   Loader modules (flat, sys.path-imported)
│   ├── raw/                  Raw vendor xlsx exports
│   │   ├── data0203.xlsx ..  Investor trading flow, "all-codes" filter
│   │   ├── data0208.xlsx       (99.8% of live marcap commons, 98% of 2021+ delistings)
│   │   ├── data2_0203.xlsx   Annual financials (IFRS-C) + monthly market cap
│   │   └── currently_listed/ Daily price/cap/short data, "currently-listed" filter
│   │                           (0% delisted coverage — combine with kr_delisted/)
│   └── investor_aggregate/   2020–2024 net-buy CSV pipeline (data1229/1230 → CSV)
│
├── kr_delisted/              Korean delisting calendar (KIND + marcap + DART)
│   ├── delisting_calendar.csv         1,359 tickers × {ticker, name, market,
│   │                                     delisting_date, reason, is_genuine}
│   ├── delisted_loader.py             universe() / load_delisted(ticker) API
│   ├── build_delisting_calendar.py    end-to-end regenerator
│   ├── build_is_genuine_overrides.py  DART + manual is_genuine refinement
│   ├── is_genuine_overrides.csv       80 override rows (consumed by builder)
│   └── delisting_calendar.kind.csv    intermediate KIND-only output
│
├── kr_marcap/                Primary KR OHLCV layer on top of marcap
│   ├── classify.py           Single classify_ticker(code, name, market) → kind
│   ├── universe.py           Point-in-time common-stock universe (marcap-only)
│   ├── adjust.py             ChangesRatio price adjustment (splits / 무상·유상증자 / 감자)
│   └── status/               Unified PIT status panel + tradable_universe(date) query
│
├── kr_status/                Per-source collectors for KRX status flags
│   ├── marcap_halt_infer.py      canonical for halt/admin/alert (marcap.Dept + ChangeCode)
│   ├── dart_insincere.py / dart_audit.py   DART-sourced insincere / audit events
│   ├── fdr_collect.py            historical audit_qualified seed from kr_delisted CSV
│   └── data/*_events.parquet     PIT event tables consumed by kr_marcap/status
│
├── marcap/                   External clone of github.com/FinanceData/marcap
│                             (gitignored entirely — re-clone when setting up;
│                              see kr_delisted/README.md "marcap coverage
│                              verification" section for delisted coverage notes)
│
├── finmind_data/             Taiwan equity data via FinMind API (TWSE + TPEx, 2005–2024)
│   ├── universe.parquet      2,154 common stocks (4-digit codes)
│   ├── delisted_universe.parquet
│   ├── download.py           Resumable per-stock parquet downloader
│   ├── build_universe.py     "TWSE + TPEx, 4-digit common, ETF/warrant/preferred excluded"
│   └── ohlcv/, instflow/, shares/, …  per-stock files (gitignored)
│
└── krx_supplement/           KRX/KOSPI200 panel reconstruction
    ├── output/index_panel_daily.parquet  KOSPI 200 membership history (used by qf_paper)
    ├── runtime/              process logs / PIDs from long-running scrapers (nohup output)
    ├── reconstruct_index_panel.py
    └── collect_*.py          KRX scrapers
```

## Korean PIT pipeline — package dataflow

Arrows show dependency direction; downstream packages read what upstream
packages write.

```
external sources              local packages                      research-time API
----------------              --------------                      -----------------
marcap parquets ──────────────────────────────────────────────►   kr_marcap.universe(date, kind=…)
       │                                                          kr_marcap.adjust.load_adjusted(t)
       │
       └────────┐  ┌─► kr_delisted/ ─────────────────────────►    delisted_loader.universe()
                ├──┤                                              delisted_loader.load_delisted(t)
KIND scrape ────┤  │
                │  └─► kr_status/  ─► data/*_events.parquet
DART API ───────┘                              │
                                               ▼
                                    kr_marcap.status.build_panel
                                               │
                                               ▼
                                    kr_marcap.status.tradable_universe(date)
```

`kr_marcap.universe` and `kr_marcap.adjust.load_adjusted` read marcap
parquets directly and don't depend on the kr_status / build_panel chain.

Cadence per step: `kr_delisted` ~quarterly (when KIND publishes new
delistings); `kr_status` per-collector (see
[`kr_status/README.md`](kr_status/README.md)); `kr_marcap.status` rebuilds in
seconds after any kr_status run. Dependency-ordered runbook at
[`refresh.sh`](refresh.sh).

## How each universe was chosen

The single biggest source of analysis error in equity research is a
survivorship-biased universe. This repo's universes were assembled to be
**point-in-time correct** — every stock that traded in the analysis window
is present, with prices ending on its true delisting date.

### Korean — FnGuide `raw/` files (`data0203` … `data0208`, `data2_0203`)

- **DataGuide universe filter: "all codes" (전체 / 상폐 포함).**
- **Result:** 3,902 KOSPI + KOSDAQ tickers. With the `kr_marcap.classify`
  common-stock filter applied to the marcap universe, FnGuide covers
  **2,544 / 2,548 (99.8 %)** of *live* commons (the 4 misses are
  infrastructure-fund issuers) and **112 / 114 (98.2 %)** of common-stock
  delistings since 2021 — one of those 2 misses is already in
  `kr_marcap.universe.STRICT_COMMON_EXCLUDE`, so `strict=True` lifts the
  post-2021 figure to 112 / 113 (99.1 %). Overall delisted-common
  coverage is 563 / 619 (91.0 %); the older gap is dominated by pre-2015
  names FnGuide has purged from its master table.
- **Why it's effectively survivorship-bias-free:** FnGuide retains
  delisted codes in its master table for several years before purging.
  Each delisted ticker's column carries data through its delisting date
  and goes NaN after. For analyses staying within these files,
  no external delisted-data merge is required.
- **Caveats:** ~56 older common-stock delistings (pre-2015) are
  permanently absent. KONEX, preferred shares, REITs, and specialty
  funds (선박투자/호) are typically excluded on methodological grounds
  anyway.

### Korean — FnGuide `raw/currently_listed/` batch

- **DataGuide universe filter: "currently listed" (live tickers at export time).**
- **Result:** 2,311 KOSPI + 1,813 KOSDAQ = today's live tickers.
  **0% coverage of delisted names.**
- **Use only with the kr_delisted overlay.** This batch was downloaded
  separately (2026-03-23) for daily price/market-cap/shares/short-selling,
  which the `raw/data0203…0208` set doesn't carry. For survivorship-
  bias-free historical panels, join on `"A" + 6-digit ticker` with the
  marcap-backed `kr_delisted/` series.
- **⚠️ Known defect — prefer `marcap/` for OHLCV.** The
  `raw/currently_listed/` export has a hard step change on **2023-10-23**:
  the ticker count drops from ~3,253 (Fri 2023-10-20) to ~1,843
  (Mon 2023-10-23) in a single session, then climbs back via IPOs.
  ~1,400 currently-listed common stocks silently disappear from the export
  from late-Oct-2023 onward; **only 10 of them are genuine delistings**, so
  the `kr_delisted/` overlay cannot recover them. The export was almost
  certainly pulled in two phases with different universe filters and
  concatenated horizontally. **Until a clean re-pull is done with a
  uniform "currently listed" filter across the full date range, source
  OHLCV / market-cap / shares from `marcap/data/marcap-YYYY.parquet`
  instead** — marcap covers every ticker that traded on every date with
  100% coverage, and the same `kr_delisted/` machinery already reads it.
  See `kr_delisted/README.md` for the marcap loader API.

### Korean — `kr_delisted/` (KIND + marcap-proxy + DART overrides)

- **Sources:** three stitched together (see `kr_delisted/README.md`):
  KIND (`kind.krx.co.kr`, `investwarn/delcompany.do`) for main-share
  delistings, marcap parquets for preferred-share proxy rows, DART
  (OpenDartReader) for `is_genuine` refinement on ambiguous reason families.
- **Universe:** 1,359 KOSPI + KOSDAQ + KONEX delisted tickers,
  2005-01-04 to present (currently 2026-05), 6-digit codes only
  (warrants/rights/funds with 7–8 char codes excluded — marcap doesn't
  carry them, and their lifecycle structure confounds survival analysis).
- **Two-way `is_genuine` classification (after DART + manual overrides):**
  - *Genuine* `Y` (1,004): bankruptcy, audit refusal, voluntary delisting,
    REIT/SPC ends — what survivorship analysis wants. Includes 118
    preferred-share proxy rows recovered from marcap.
  - *Continuation* `N` (355): 107 exchange transfers (KOSPI↔KOSDAQ
    migration, stock still trades) + 248 mergers / 주식교환 / SPC dissolutions
    (shares swapped into acquirer — exclude, since merger premia
    contaminate return-based analyses).
- **OHLCV source:** `marcap/data/marcap-YYYY.parquet`, 100% coverage,
  unadjusted prices.

### Taiwan — `finmind_data/` (FinMind API, TWSE + TPEx)

- **Filter set:** 4-digit numeric codes on TWSE + TPEx — drops ETFs
  (00xxx, 5–6 digits), warrants (alphanumeric), TDRs (industry
  category 存託憑證), beneficiary certificates (受益證券), ETNs,
  TWSE Innovation Board (창新版).
- **Pre-2015 delisting overlay:** 42 4-digit common stocks present in
  `delisted_universe.parquet` (delistings between 2005-01-01 and
  2014-12-31) that FinMind's live `taiwan_stock_info` no longer
  returns. These are added on top of the live universe so the panel
  isn't survivorship-biased against pre-2015 names — restoring
  symmetry with the Korean "all-codes" coverage.
- **Window:** 2005-01-01 → 2024-12-31 (rolled back from 2015-01-01 on
  2026-04-27 to give 20 years of overlap with FnGuide). The original
  2015–2024 per-stock files are preserved in `<dataset>_2015_2024/`
  backup directories.

## FnGuide DataGuide export settings (for replicators)

The two FnGuide batches in `fnguide_data/` differ only in the **universe
filter** chosen at export time:

| Batch | Filter setting in DataGuide | Tickers | Delisted retention |
|---|---|---|---|
| `raw/data0203…0208`, `raw/data2_0203` | **"All codes" (전체 / 상폐 포함)** | 3,902 | Yes — ~90% common-stock delistings retained for as long as FnGuide keeps the master code |
| `raw/currently_listed/` (12 files) | **"Currently listed"** (KOSPI + KOSDAQ live) | 2,311 + 1,813 | No — filtered out at export time |

**To re-pull or extend:** set the universe filter to "all codes" in the
DataGuide export wizard. Same vendor, same data — the universe setting
matters more than any other choice. A current-day "all codes" pull will
not recover the ~60 pre-2015 commons that FnGuide has since purged from
its master code table; treat those as irrecoverable.

For the per-file investor-type / item-code mapping (which DataGuide
field went into which xlsx), see `fnguide_data/README.md` and the
`fnguide_data/integrity_report.md` cross-validation tables.

## What's tracked vs ignored

**Tracked (committed to git):**
- All `*.py` code (loaders, downloaders, builders).
- All `*.md` documentation, including methodology and integrity reports.
- Small index files: `delisting_calendar.csv`, `missing_*.csv`,
  `universe.parquet`, `delisted_universe.parquet`,
  `krx_supplement/output/*` (membership panels, sector mappings).
- Small images / diagrams.

**Ignored (kept locally only — see `.gitignore`):**
- All FnGuide xlsx files (200 MB – 1.4 GB each, exceed GitHub 100 MB
  per-file limit).
- The entire `marcap/` directory (external clone of github.com/FinanceData/marcap, ~3.8 GB) — re-clone when setting up.
- All FinMind per-stock parquets (`ohlcv/`, `instflow/`, `shares/`,
  fundamentals dirs, ~1.6 GB).
- Backup zips (`*.zip`), `*.bak` files, `__pycache__/`, `nohup.*`, `*.log`.
- Credentials: `.token`, `krx_id`, `*.key`.

To rebuild the data trees from scratch: re-export FnGuide xlsx via
DataGuide (subscription needed); pull marcap parquets from the upstream
`FinanceData/marcap` repo; run `finmind_data/download.py` against your
FinMind token; run `kr_delisted/build_delisting_calendar.py` against
KIND.

## Quick start

| Task | Where to look |
|---|---|
| Point-in-time KR common-stock universe | `kr_marcap/universe.py::universe(date, 'common')` (add `strict=True` to match fnguide exactly) |
| Tradable KR universe (PIT status + price/liquidity filters) | `kr_marcap.status.tradable_universe(date, ...)` |
| Per-flag KR event history (admin/halt/audit/insincere/alert) | `kr_marcap/status/events.parquet` (built by `kr_marcap.status.build_panel`) |
| Adjusted KR OHLCV for one ticker (splits/무상증자/감자) | `kr_marcap/adjust.py::load_adjusted(ticker)` |
| List Korean delisted tickers (with merger vs bankruptcy flag) | `kr_delisted/delisted_loader.py::universe()` |
| Load one delisted ticker's *raw* (unadjusted) OHLCV | `kr_delisted/delisted_loader.py::load_delisted(ticker)` |
| Pull daily KOSPI prices (FnGuide, defective post-2023-10-23) | `fnguide_data/raw/currently_listed/0_KOSPI 주가.xlsx` |
| Investor trading flow (granular, 14 types) | `fnguide_data/raw/data0203…0208.xlsx` |
| Investor trading flow (3-category Smart Money) | `fnguide_data/investor_aggregate/investor_trading_data.csv` |
| KOSPI 200 membership history | `krx_supplement/output/index_panel_daily.parquet` |
| Taiwan OHLCV / institutional flow | `finmind_data/ohlcv/`, `finmind_data/instflow/` |

For deep dives on coverage and validation: `fnguide_data/DELISTED_COVERAGE.md`,
`fnguide_data/integrity_report.md`, `kr_delisted/README.md` (methodology +
marcap coverage section), `finmind_data/README.md`.
