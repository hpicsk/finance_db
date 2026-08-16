# finance_db — Korean & Taiwan equity research data

Container for the per-source data packages backing my quantitative-finance
research on Korean (and, for cross-market validation, Taiwanese) equities.
**This directory holds no analysis code and no methodology.** Each package
below owns its own loaders, its own documentation, and its own claim
assertions; what lives here is the map between them, the dependency-ordered
refresh runbook, and the ignore policy.

> **Licensing:** FnGuide DataGuide is a paid subscription. KRX/KIND data
> is publicly accessible but rate-limited. FinMind is a free-tier API
> (token required). The large raw data files are **not** committed to
> this repo — see `.gitignore`. What's tracked is code, documentation,
> and small index/calendar CSVs sufficient to reproduce universes.

## Layout

| Package | What it is | Start here |
|---|---|---|
| `fnguide_data/` | FnGuide DataGuide export tree — investor flow, financials, short-selling, and the **adjusted-price benchmark** research reads | [`README.md`](fnguide_data/README.md), [`DELISTED_COVERAGE.md`](fnguide_data/DELISTED_COVERAGE.md) |
| `kr_delisted/` | Korean delisting calendar (KIND + marcap + DART), 1,359 tickers with a genuine-vs-continuation flag | [`README.md`](kr_delisted/README.md) |
| `kr_marcap/` | KR OHLCV layer over marcap, plus the open-source reconstruction of FnGuide's 수정주가 and the unified PIT status panel | [`README.md`](kr_marcap/README.md), [`CONSTRUCTION.md`](kr_marcap/CONSTRUCTION.md), [`VERIFICATION.md`](kr_marcap/VERIFICATION.md) |
| `kr_status/` | Per-source PIT collectors for KRX status flags (admin / halt / alert / audit / insincere), one parquet each | [`README.md`](kr_status/README.md) |
| `krx_supplement/` | KRX/KOSPI200 panel reconstruction — index membership history, sector, foreign ownership | [`README.md`](krx_supplement/README.md), [`RECONSTRUCT.md`](krx_supplement/RECONSTRUCT.md) |
| `finmind_data/` | Taiwan equity data via the FinMind API (TWSE + TPEx, 2005–2024), and the Taiwanese adjusted series | [`README.md`](finmind_data/README.md), [`VERIFICATION.md`](finmind_data/VERIFICATION.md) |
| `marcap/` | External clone of [`FinanceData/marcap`](https://github.com/FinanceData/marcap) — gitignored entirely, re-clone when setting up | delisted-coverage notes in [`kr_delisted/README.md`](kr_delisted/README.md) |

Two files at this level, and nothing else: [`refresh.sh`](refresh.sh) (the
dependency-ordered runbook) and [`run_assertions.sh`](run_assertions.sh) (runs
every package's `test_assertions.py`).

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

## Adjusted price series — Korea vs Taiwan

Both markets expose both conventions — price return and total return — so a
raw → price-return → total-return comparison is constructible on either side.
Getting there is asymmetric, and that asymmetry is the reason the two
verification write-ups are worth reading as a pair. KRX splits the problem for
you, publishing a structural-only factor and nothing for cash, so Korea's
`adj_close` is free and `adj_close_tr` is derived. TWSE/TPEx do the opposite,
publishing **one fused reference price** per 除權息 event covering cash,
無償配股 and 現增 together, so Taiwan's `adj_close_tr` is free and
`adj_close_pr` is derived.

| | Korea | Taiwan |
|---|---|---|
| **Structural adjustment** | KRX `ChangesRatio` compounded (`kr_marcap.adjust`) | Exchange 除權息 / 減資 reference prices (`finmind_data/div_result`, `cap_red`) |
| **Cash-dividend layer** | SEIBro events, ex-date derived under KRX T+2 (`kr_marcap.dividend_events`) | Already inside the exchange factor (`after_price` nets the cash out) |
| **Exchange publishes a total-return factor?** | **No** — KRX 수정주가 is structural only | **Yes** — `after_price/before_price` covers cash *and* rights |
| **Raw input confirmed raw** | via KRX 수정주가 oracle | 99.87 % exact vs exchange `before_price` |
| **Factor reproduced from first principles** | 96.2 % vs DART (independent 2nd source) | 100 % identity on 8,478 `除` events; 93.8 % via the TWSE formula |
| **Residual after adjustment** | +82 bp on ex-dates | +29 bp on 除權息; +48 bp on 現金減資, −190 bp on 彌補虧損 |
| **Residual is a defect?** | **No** — prices fall ~66 % of the dividend; the rest is the real ex-day effect | Same |
| **Price-return series** | `adj_close` — free, it *is* `ChangesRatio` | `adj_close_pr` — derived by splitting the fused factor |
| **Total-return series** | `adj_close_tr` — derived by adding SEIBro cash | `adj_close_tr` — free, it *is* `after_price/before_price` |
| **Builder** | `kr_marcap.adjust.load_adjusted(…, total_return=True)` | `finmind_data.adjust.load_adjusted` |
| **Write-up** | [`kr_marcap/VERIFICATION.md`](kr_marcap/VERIFICATION.md) | [`finmind_data/VERIFICATION.md`](finmind_data/VERIFICATION.md) |

Neither series ends at zero, and neither should. Both mark the affected sessions
instead — `is_ex_date` on both sides, plus `is_cap_red` on the Taiwanese one.

Korea has a check Taiwan does not: FnGuide DataGuide publishes both Korean
conventions, so the open-source reconstruction can be scored against the paid
vendor it reproduces — 99.977 % and 99.969 % of daily returns on 10.26 M shared
ticker-days ([`kr_marcap/CONSTRUCTION.md`](kr_marcap/CONSTRUCTION.md)). Taiwan
has no counterpart; `TaiwanStockPriceAdj` is gated above this account's tier.

## Quick start

| Task | Where to look |
|---|---|
| Point-in-time KR common-stock universe | `kr_marcap/universe.py::universe(date, 'common')` (add `strict=True` to match fnguide exactly) |
| Tradable KR universe (PIT status + price/liquidity filters) | `kr_marcap.status.tradable_universe(date, ...)` |
| Per-flag KR event history (admin/halt/audit/insincere/alert) | `kr_marcap/status/events.parquet` (built by `kr_marcap.status.build_panel`) |
| **Adjusted KR close for research (price return + total return)** | `fnguide_data/price_loader.py::load_price_panel()` — the FnGuide series, 2005+ |
| Adjusted KR close reconstructed from open sources, whole panel | `kr_marcap/adjusted_loader.py::load_adjusted_panel()` — agrees with FnGuide on 99.98 % of ticker-days ([`kr_marcap/CONSTRUCTION.md`](kr_marcap/CONSTRUCTION.md)) |
| Adjusted KR OHLCV for one ticker, reconstructed from open sources | `kr_marcap/adjust.py::load_adjusted(ticker)` |
| Adjusted KR open/high/low from the vendor (currently-listed names only) | `fnguide_data/raw/0_{KOSPI,KOSDAQ} 주가(상폐제외).xlsx` — no delisted coverage, read [§10](fnguide_data/README.md) first |
| Raw KR OHLCV / market cap / shares | `kr_marcap.market_loader.load_market_data` over `marcap/data/marcap-YYYY.parquet` |
| List Korean delisted tickers (with merger vs bankruptcy flag) | `kr_delisted/delisted_loader.py::universe()` |
| Load one delisted ticker's *raw* (unadjusted) OHLCV | `kr_delisted/delisted_loader.py::load_delisted(ticker)` |
| Investor trading flow (granular, 14 types) | `fnguide_data/raw/data0203…0208.xlsx` |
| Investor trading flow (3-category Smart Money) | `fnguide_data/investor_aggregate/investor_trading_data.csv` |
| Short-selling / lending / free-float | `fnguide_data/raw/short_sale_lending.xlsx` |
| KOSPI 200 membership history | `krx_supplement/output/index_panel_daily.parquet` |
| Taiwan OHLCV / institutional flow | `finmind_data/ohlcv/`, `finmind_data/instflow/` |
| Taiwan adjusted close (both conventions) | `finmind_data/adjust.py::load_adjusted(ticker)` |

**Before joining two FnGuide sheets, read
[`fnguide_data/README.md`](fnguide_data/README.md#️-every-sheet-has-its-own-pull-date).**
The `raw/` exports span 2026-02-14 to 2026-08-13 and each carries its own end
date and its own ticker universe; a join silently truncates to the earliest of
them. It is per *sheet*, not per file — DataGuide builds a workbook one sheet at
a time, and sheets in the same file differ in both end date and universe.
`fnguide_data/vintages.csv` records each sheet's stamp so a join can be dated
with `min(end_date(...))` instead of a guess. The same applies across
packages — `kr_marcap`'s benchmark against FnGuide is bounded by the marcap
vintage, not the FnGuide pull.

## What's tracked vs ignored

**Tracked (committed to git):**
- All `*.py` code (loaders, downloaders, builders) and each package's
  `test_assertions.py`.
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
- Credentials: `.token`, `krx_id`, `*.key`, `.env`.

To rebuild the data trees from scratch: re-export FnGuide xlsx via
DataGuide (subscription needed, "all codes" filter); pull marcap parquets from
the upstream `FinanceData/marcap` repo; run `finmind_data/download.py` against
your FinMind token; run `kr_delisted/build_delisting_calendar.py` against KIND.

## Verifying

Each package owns the assertions behind the claims its documentation makes.
`./run_assertions.sh` runs all of them against the populated data trees and
exits non-zero if any fail; there is no CI, so this is the gate.
