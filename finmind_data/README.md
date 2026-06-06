# Taiwan Equity Market Dataset (TWSE + TPEx, 2005-2024)

Per-stock daily / monthly / quarterly market data for common equities
listed on the Taiwan Stock Exchange (TWSE) and Taipei Exchange (TPEx),
covering **2005-01-01 to 2024-12-31**: OHLCV, institutional order flow,
shareholding, valuation multiples (PER/PBR), margin + short balances,
monthly revenue, fundamentals (IS/BS/CF), dividends, securities lending,
and capital-reduction events. Plus market-wide reference files for
delistings. Intended for informed-trading / return-reversal research as
a cross-market validation of Korean-market findings (paired with
`~/finance_db/fnguide_data`, which starts ~2000).

The window was originally 2015-01-01 → 2024-12-31; on 2026-04-27 the
start was rolled back to 2005-01-01 to give 20 years of overlap with
fnguide. The pre-rollback files are preserved in `<dataset>_2015_2024/`
backup directories (see "Directory layout").

## Universe

**2,154 common stocks** (4-digit ticker codes), as of the 2026-04-27
`build_universe.py` rebuild:

| Exchange | Count |
|---|---|
| TWSE                                   | 1,198 |
| TPEx                                   |   914 |
| Pre-2015 delistings (type unknown)     |    42 |
| **Total**                              | **2,154** |

Excludes: ETFs (`00xxx` codes), warrants, TDRs (industry categories
"存託憑證" / "臺灣存託憑證"), beneficiary certificates ("受益證券"),
ETNs, and the TWSE Innovation Board relaxed-disclosure tier
("創新版股票" / "創新板股票").

The 42 pre-2015 delistings are added on top of FinMind's live
`taiwan_stock_info` output — they are 4-digit common stocks present in
`delisted_universe.parquet` (delisting between 2005-01-01 and
2014-12-31) that the live endpoint no longer returns. They carry
`type=NaN` and `industry_category=NaN`. FinMind still serves
price/flow data for these names up to their delisting date. Without
them the Taiwan panel would be 0%-coverage on pre-2015 delistings
while fnguide is ~90%-coverage, breaking cross-market symmetry.

Per-stock files under earlier (2,111- and 2,112-ticker) universes
remain valid for the 2015-2024 window and are preserved as
`<dataset>_2015_2024/` backup dirs.

#### Mirroring the fnguide criterion

This filter set is deliberately aligned with the **fnguide root-level
"all codes"** universe used on the Korean side
(`~/finance_db/fnguide_data/data0203`–`data0208`, `data2_0203`; see
`fnguide_data/DELISTED_COVERAGE.md` for why the root-level files, not
the `currently_listed/` batch, are the correct Korean reference). Each fnguide
exclusion has an explicit Taiwan counterpart here:

| fnguide exclusion (KOSPI/KOSDAQ) | Taiwan counterpart | Mechanism in `build_universe.py` |
|---|---|---|
| Preferred shares (우 / 우B / 1우 / 2우 / MF suffixes) | A / B / C-suffix preferreds | `stock_id.str.fullmatch(r"\d{4}")` drops non-numeric suffixes |
| ETF                             | ETF                          | `industry_category == "ETF"` + 5-6-digit `00xxx` codes dropped by digit filter |
| ETN                             | ETN                          | `industry_category == "ETN"` |
| REIT / specialty funds (호 / 선박투자 / 리츠) | 受益證券 (beneficiary certificates) and T-suffix codes | `industry_category == "受益證券"` + digit filter |
| Foreign DRs                     | TDRs                         | `industry_category ∈ {"存託憑證", "臺灣存託憑證"}` |
| KONEX (separate relaxed-disclosure market) | TWSE Innovation Board   | `industry_category ∈ {"創新版股票", "創新板股票"}` |
| TPEx 興櫃 (emerging) — not in fnguide either | TPEx 興櫃 (emerging)   | `type.isin(["twse", "tpex"])` drops `emerging` |

Two deliberate *inclusions* also match fnguide behaviour:

- **F-/-KY foreign-domiciled primary listings** (e.g. 9802 鈺齊-KY,
  9136 凱羿-KY) are **kept**, mirroring fnguide's inclusion of
  foreign-domiciled primaries on KOSPI/KOSDAQ (e.g. 차이나하오란).
  These are primary listings, not depositary receipts.
- **Delisted-during-window tickers** are kept (82 of 91 eligible
  delistings, see `### Survivorship bias` below), mirroring
  fnguide's "all codes / 상폐 포함" filter which leaves 90.5% of
  genuine KOSPI/KOSDAQ common-stock delistings in the panel. The
  `currently_listed/` batch, by contrast, uses a currently-listed filter and
  retains 0% of delistings — that batch is *not* the Korean
  reference for this alignment.

Things **not** filtered at universe-build time on either side, by
design: liquidity floors, IPO seasoning, 警示股 / 全額交割 / 관리종목
flags. Apply those at analysis time per study, not at the universe
level, to keep the Taiwan/Korea comparison symmetric.

### Survivorship bias

**The universe includes stocks that were delisted during the sample window.**
FinMind's `taiwan_stock_info` endpoint returns recently-delisted
stocks alongside currently-listed ones; older delistings have to be
merged in from `delisted_universe.parquet`. Coverage:

- **2015-01-01 to today:** of 91 four-digit common stocks delisted in
  this window, **82 are present**; the 9 not present are ETFs or DRs
  (not common equity) and intentionally excluded.
- **2005-01-01 to 2014-12-31:** of 102 four-digit delistings in this
  window, **all 102 are present** — 60 were already in the live
  `taiwan_stock_info` output, the remaining 42 were added by
  `build_universe.py` from `delisted_universe.parquet`.

Per-stock parquet files for delisted tickers end on their delisting date,
so you should filter by `date` rather than assume uniform coverage.

## Directory layout

```
/home/st/finance_db/finmind_data/
├── README.md                          (this file)
├── universe.parquet                   2,154 common stocks (id, name, type, industry)
├── delisted_universe.parquet          315 historical delistings — `TaiwanStockDelisting` output
├── delisted_missing.parquet           9 delistings excluded from universe (ETFs/DRs)
├── capital_reduction.parquet          consolidated cap-reduction events (sparse)
├── ohlcv/<stock_id>.parquet           daily prices & volume                              (2005-2024)
├── instflow/<stock_id>.parquet        institutional order flow                           (2005-2024)
├── shares/<stock_id>.parquet          shares outstanding + foreign ownership             (2005-2024)
├── per_pbr/<stock_id>.parquet         daily PER / PBR / dividend yield                   (2005-2024)
├── margin_short/<stock_id>.parquet    margin balances + short-sale (informed-trader)     (2005-2024)
├── month_rev/<stock_id>.parquet       monthly revenue (TW 10-day disclosure)             (2005-2024)
├── fin_is/<stock_id>.parquet          quarterly income statement (incl. EPS row)         (2005-2024)
├── fin_bs/<stock_id>.parquet          quarterly balance sheet                            (2005-2024)
├── fin_cf/<stock_id>.parquet          quarterly cash-flow statement                      (2005-2024)
├── dividend/<stock_id>.parquet        cash + stock dividends                             (2005-2024)
├── sec_lending/<stock_id>.parquet     securities lending (借券 short proxy)              (2005-2024)
├── cap_red/<stock_id>.parquet         per-stock capital-reduction events (mostly empty)  (2005-2024)
├── *_2015_2024/<stock_id>.parquet     **backup** of pre-rollback (2015-2024) build       (~700 MB total)
├── build_universe.py                  universe construction script (incl. delisted merge)
├── download.py                        resumable downloader (--datasets to filter)
├── consolidate_capred.py              merges cap_red/*.parquet → capital_reduction.parquet
├── download.log                       per-stock progress log
├── nohup.bg2005.out                   2005-2024 re-download runtime log (started 2026-04-27)
└── .token                             FinMind API token (chmod 600)
```

The `*_2015_2024/` directories preserve the original 2,112-ticker /
10-year build downloaded 2026-04-20 to 2026-04-26. They can be deleted
once the 2005-2024 re-download has completed and been verified — until
then they are an in-place rollback target.

## File schemas

### `ohlcv/<stock_id>.parquet` — daily prices

One row per trading day (~4,850 rows per full 20-year series; ~2,439
in the 10-year backup).

| column | dtype | description |
|---|---|---|
| `date`             | str    | YYYY-MM-DD |
| `stock_id`         | str    | 4-digit ticker |
| `open/max/min/close` | float64 | TWD, adjusted for capital changes per FinMind |
| `spread`           | float64 | close − prior close (TWD) |
| `Trading_Volume`   | int64  | shares traded |
| `Trading_money`    | int64  | **trading value in TWD** (used for FFI normalization) |
| `Trading_turnover` | int64  | number of trades |

### `instflow/<stock_id>.parquet` — institutional order flow

**Long format.** One row per (date, investor type) — ~5 rows per trading
day (~22,000 rows per full 20-year series; ~11,485 in the 10-year backup).

| column | dtype | description |
|---|---|---|
| `date`     | str   | YYYY-MM-DD |
| `stock_id` | str   | |
| `name`     | str   | investor type (see below) |
| `buy`      | int64 | **shares** bought by this investor type |
| `sell`     | int64 | **shares** sold by this investor type |

Investor types (`name` values):

| value | meaning | analogue in Korean paper |
|---|---|---|
| `Foreign_Investor`     | Qualified Foreign Institutional Investors           | foreign flow |
| `Investment_Trust`     | Domestic securities investment trusts (funds)       | institutional flow |
| `Dealer_self`          | Broker-dealer proprietary (own account)             | dealer |
| `Dealer_Hedging`       | Broker-dealer hedging positions                     | dealer (hedging) |
| `Foreign_Dealer_Self`  | Foreign broker-dealer proprietary (often 0)         | — |

**Individual retail flow is not directly reported**; derive as
`Trading_Volume − Σ(buy+sell)/2` per stock-day, matching the approach
used by most Taiwan/Korea studies.

**Net flow** = `buy − sell` (shares). To convert to TWD, multiply by
VWAP or `close` from the ohlcv file.

### `shares/<stock_id>.parquet` — shares outstanding & foreign ownership

One row per trading day.

| column | dtype | description |
|---|---|---|
| `date`                               | str     | |
| `stock_id`                           | str     | |
| `stock_name`                         | str     | Chinese name |
| `InternationalCode`                  | str     | ISIN |
| `NumberOfSharesIssued`               | int64   | **total shares outstanding** (for market cap) |
| `ForeignInvestmentShares`            | int64   | shares owned by foreign investors |
| `ForeignInvestmentRemainingShares`   | int64   | shares still allowed for foreign purchase |
| `ForeignInvestmentSharesRatio`       | float64 | foreign ownership % |
| `ForeignInvestmentRemainRatio`       | float64 | remaining foreign quota % |
| `ForeignInvestmentUpperLimitRatio`   | float64 | regulatory cap (typically 100) |
| `ChineseInvestmentUpperLimitRatio`   | float64 | Chinese investor cap |
| `RecentlyDeclareDate`                | str     | most recent capital-change disclosure |
| `note`                               | str     | usually empty |

**Market cap** = `close * NumberOfSharesIssued` (join with ohlcv on
`date, stock_id`).

## Quick-start: load one stock

```python
import pandas as pd
from pathlib import Path

R = Path("/home/st/finance_db/finmind_data")
sid = "2330"  # TSMC

ohlcv = pd.read_parquet(R/"ohlcv"/f"{sid}.parquet")
flow  = pd.read_parquet(R/"instflow"/f"{sid}.parquet")
shr   = pd.read_parquet(R/"shares"/f"{sid}.parquet")

# Wide-format flow: one column per investor type
net = flow.assign(net=flow["buy"] - flow["sell"])
flow_wide = net.pivot(index="date", columns="name", values="net").reset_index()

# Merge and compute market cap
df = (ohlcv.merge(flow_wide, on="date", how="left")
           .merge(shr[["date","NumberOfSharesIssued"]], on="date", how="left"))
df["mktcap_twd"] = df["close"] * df["NumberOfSharesIssued"]
```

## Load the full panel

```python
import pandas as pd
from pathlib import Path

R = Path("/home/st/finance_db/finmind_data")
universe = pd.read_parquet(R/"universe.parquet")

ohlcv_all = pd.concat(
    [pd.read_parquet(p) for p in (R/"ohlcv").glob("*.parquet")],
    ignore_index=True,
)  # ~5M rows
```

## Provenance

- **Source:** FinMind API (`https://api.finmindtrade.com/api/v4/data`)
- **Datasets:** all 12 per-stock endpoints listed in `download.py`
  (`TaiwanStockPrice`, `TaiwanStockInstitutionalInvestorsBuySell`,
  `TaiwanStockShareholding`, `TaiwanStockPER`,
  `TaiwanStockMarginPurchaseShortSale`, `TaiwanStockMonthRevenue`,
  `TaiwanStockFinancialStatements`, `TaiwanStockBalanceSheet`,
  `TaiwanStockCashFlowsStatement`, `TaiwanStockDividend`,
  `TaiwanStockSecuritiesLending`,
  `TaiwanStockCapitalReductionReferencePrice`)
- **Upstream origin:** TWSE daily disclosures and TPEx daily disclosures
  (Taiwan's "three major institutional investors" reporting regime)
- **Original 2015-2024 build:** 2026-04-20 to 2026-04-26 via
  `download.py` (preserved in `*_2015_2024/` backup dirs).
- **Current 2005-2024 build:** started 2026-04-27 via `download.py`
  with default `--start 2005-01-01`. Total: 2,154 stocks × 12 datasets
  = ~25,800 requests at ~6.5 s/req under FinMind's 600/hr free-tier
  cap → ~43 hours wall-clock. Resumable (skip-existing). Background
  log: `nohup.bg2005.out`; per-stock log: `download.log`.
- **Verification (2015-2024 build):** 2,101 freshly downloaded + 10
  pilot = 2,111 stocks, 0 failures.

## Known gaps / caveats

1. **Individual retail flow** is not directly reported. Derive from total
   volume minus institutional volume, or use it as a residual sign.
2. **Partial-window stocks**: IPOs after 2015 or delistings before 2024
   will have shorter series. Always filter by `date` after concat.
3. **ETFs, DRs, warrants** are intentionally excluded. 9 delisted
   non-equity products are not present (see `delisted_universe.parquet`
   vs `universe.parquet` for the diff).
4. **Price adjustment**: FinMind returns close prices that reflect capital
   reductions and splits, but verify against `taiwan_stock_dividend` if
   doing dividend-inclusive total-return studies.

## Cross-market notes (Korea ↔ Taiwan)

When using this dataset to validate Korean-market findings, four
structural differences matter more than the usual market-level controls:

1. **Investor-flow category asymmetry.** Korean data typically splits flow
   into `{individual, institution-total, foreign, private-fund, other-corp}`
   (5-way). Taiwan's 三大法人 regime is 3-way:
   `{Foreign_Investor, Investment_Trust, Dealer_*}`. To run the same
   regression on both, coarsen Korea to `{foreign, all-institutions, individual}`
   — finer splits don't map.
2. **Price-limit regime change.** TWSE widened limits from ±7% → ±10% on
   **2015-06-01**, very close to Korea's ±15% → ±30% change the same year.
   Both events reshape volatility and reversal dynamics; a dummy + regime
   split is required, not a single pooled estimate.
3. **Short-sale regulation asymmetry.** Korea imposed long short-sale bans
   (2020-03 to 2023-05 for many segments). Taiwan had no equivalent
   continuous ban during 2015–2024, so Taiwan short-interest series is
   unbroken while the Korean series has large missing windows. Align
   sample windows or interact short-factor with `is_banned` dummies.
4. **Consensus depth gap.** Taiwan analyst coverage thins out fast below
   mid-caps (Korean sell-side coverage is relatively deeper). Any
   consensus-based factor will have systematically more missing values on
   the Taiwan side in small-cap universes — report coverage explicitly
   rather than silently dropping stocks.

## Data coverage & endpoint mapping

### ✅ Already downloaded (this dataset)

| Category | FinMind endpoint | Subdir |
|---|---|---|
| Daily OHLCV, volume, turnover | `TaiwanStockPrice` | `ohlcv/` |
| Shares outstanding, foreign ownership | `TaiwanStockShareholding` | `shares/` |
| Institutional investor flow (5 types) | `TaiwanStockInstitutionalInvestorsBuySell` | `instflow/` |

Market cap = `ohlcv.close × shares.NumberOfSharesIssued` (not stored;
compute on demand).

### 🔧 Available via FinMind — extension targets

Priority batch (see **Extension roadmap** below) — **all free-tier
verified on 2026-04-22**:

| Subdir | Endpoint | Notes |
|---|---|---|
| `per_pbr/` | `TaiwanStockPER` | Daily PER / PBR / dividend yield |
| `margin_short/` | `TaiwanStockMarginPurchaseShortSale` | Per-stock margin + short balances (informed-trader proxy) |
| `month_rev/` | `TaiwanStockMonthRevenue` | Monthly revenue (10th-of-month disclosure; TW-specific) |

Second batch (free-tier verified):

| Subdir | Endpoint | Notes |
|---|---|---|
| `fin_is/` | `TaiwanStockFinancialStatements` | Quarterly income statement (includes EPS as a `type` row) |
| `fin_bs/` | `TaiwanStockBalanceSheet` | Quarterly balance sheet |
| `fin_cf/` | `TaiwanStockCashFlowsStatement` | Quarterly cash-flow statement |
| `dividend/` | `TaiwanStockDividend` | Cash + stock dividends; also used to reconstruct total-return series |
| `sec_lending/` | `TaiwanStockSecuritiesLending` | 借券/議借 — institutional short proxy |

**Excluded — paid tier or not in FinMind enum:**

| Endpoint | Reason | Workaround |
|---|---|---|
| `TaiwanStockPriceAdj` | Paid tier only | Compute total return from `TaiwanStockPrice.close` + `TaiwanStockDividend` |
| `TaiwanStockHoldingSharesPer` | Paid tier only | Skip; use TEJ or MOPS for holder distribution if needed |
| `TaiwanStockEPS` | Not a FinMind dataset | EPS lives inside `TaiwanStockFinancialStatements` as `type == 'EPS'` rows |
| `TaiwanStockShareholdingClassification` | Not a FinMind dataset | Use MOPS insider-holdings disclosures directly |
| `TaiwanStockConvertibleBondInfo` | Paid tier only (verified 2026-04-26) | Use TEJ or paid FinMind sponsor tier |
| `TaiwanStockConvertibleBondDaily` | Paid tier only (verified 2026-04-26) | Use TEJ or paid FinMind sponsor tier |
| `TaiwanStockConvertibleBondDailyOverview` | Paid tier (assumed; not probed) | Same as above |
| `TaiwanStockConvertibleBondInstitutionalInvestors` | Paid tier (assumed; not probed) | Same as above |

Follow-up — delivered (top-level files, not in per-stock DATASETS):

| File | Endpoint | Notes |
|---|---|---|
| `delisted_universe.parquet` | `TaiwanStockDelisting` | Already in repo — the existing file *is* the `TaiwanStockDelisting` market-wide one-shot output (315 rows, 2001-2026). Verified 2026-04-26. Columns: `date`, `stock_id`, `stock_name`, `year` (year derived from date). No re-download needed. |
| `capital_reduction.parquet` | `TaiwanStockCapitalReductionReferencePrice` | Concatenated event log (sparse: most stocks have 0 events). 9 columns including `PostReductionReferencePrice`, `ExrightReferencePrice`, `ReasonforCapitalReduction`. Per-stock raw files in `cap_red/`; `consolidate_capred.py` merges them. |

Other follow-up not pursued:

- `TaiwanStockNews` — event-study material; size and dedup overhead not
  worth the default download.

### ⚠️ Not in FinMind — external sources required

| Category | What's missing | Source |
|---|---|---|
| Free float (유동주식비율) | Float ratio, not just shares outstanding | TEJ, Bloomberg `EQY_FREE_FLOAT_PCT` |
| 5%-rule major-shareholder changes | Structured event list | MOPS (公開資訊觀測站), TEJ |
| Analyst consensus (EPS, revenue) | Forward forecasts | Refinitiv I/B/E/S, Bloomberg BEST, TEJ |
| Analyst report volume | Coverage counts | Refinitiv I/B/E/S, Bloomberg |
| BW (warrant-bond) balances | Mezzanine debt | MOPS; low frequency in TW |
| IPO lockup (禁售期) schedule | Lockup expiry dates | TEJ, MOPS IPO prospectus |
| Rights offering (現金增資) details | Event + discount | MOPS, TEJ |
| Tick size / price-limit change history | Regime breaks | TWSE rulebook — record once, not a time series |

## Extension roadmap

Priority order corresponds to how directly each endpoint feeds the
informed-trading / return-reversal framework. `download.py` skips
existing files, so batches can be run sequentially without overlap.

1. **Priority batch** (`--datasets per_pbr margin_short month_rev`).
   3 × 2,111 = 6,333 requests. At ~6.5 s/request under FinMind's
   600/hr free-tier cap, roughly **11 hours**. Output dirs: `per_pbr/`,
   `margin_short/`, `month_rev/`.
2. **Second batch** (`--datasets fin_is fin_bs fin_cf dividend
   sec_lending`). 5 × 2,111 = 10,555 requests, roughly **19 hours**.
   Launch only after Pass 1 completes — the free-tier 600/hr quota is
   global, not per process.
3. **Follow-up — done** (2026-04-26):
   - `TaiwanStockDelisting` was already in the repo as
     `delisted_universe.parquet` (verified identical content on
     2026-04-26). No re-download.
   - `TaiwanStockCapitalReductionReferencePrice` → per-stock pass via
     `download.py --datasets cap_red` (~3.8 hr; capital reductions are
     sparse, most stocks return 0 rows). Consolidate per-stock files
     into `capital_reduction.parquet` with `consolidate_capred.py`.
   - CB endpoints (Info, Daily, DailyOverview, InstitutionalInvestors)
     are paid-tier; not pursued.

Run:

```bash
# Pass 1 — priority (~11 hr)
nohup python download.py \
  --datasets per_pbr margin_short month_rev \
  > nohup.priority.out 2>&1 &

# Pass 2 — second batch (~19 hr). Launch AFTER Pass 1 finishes.
nohup python download.py \
  --datasets fin_is fin_bs fin_cf dividend sec_lending \
  > nohup.batch2.out 2>&1 &

# Follow-up — capital reduction (~3.8 hr, sparse)
nohup python download.py --datasets cap_red \
  > nohup.cap_red.out 2>&1 &
# After completion:
python consolidate_capred.py    # → capital_reduction.parquet
# (Delisting events are already in delisted_universe.parquet — no
# separate fetch needed; `TaiwanStockDelisting` produced this file.)
```

Re-running any command is safe: `download.py` skips stock-subdir pairs
whose parquet file already exists.