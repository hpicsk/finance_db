# Taiwan Equity Market Dataset (TWSE + TPEx, 2005-2024)

Per-stock daily / monthly / quarterly market data for common equities
listed on the Taiwan Stock Exchange (TWSE) and Taipei Exchange (TPEx),
covering **2005-01-01 to 2024-12-31**: OHLCV, institutional order flow,
shareholding, valuation multiples (PER/PBR), margin + short balances,
monthly revenue, fundamentals (IS/BS/CF), dividends, securities lending,
and capital-reduction events. Plus market-wide reference files for
delistings. Intended for informed-trading / return-reversal research as
a cross-market validation of Korean-market findings (paired with
`~/research/finance_db/fnguide_data`, which starts ~2000).

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
(`~/research/finance_db/fnguide_data/data0203`–`data0208`, `data2_0203`; see
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

**Boundary caveat — the overlay stops at 2014.** `build_universe.py`
gates the `delisted_universe.parquet` re-add to `date < 2015-01-01` (at
build time the live `taiwan_stock_info` still returned post-2014
delistings, so no re-add was needed). The 2015+ completeness therefore
relies on **FinMind's live retention**, not on an explicit overlay
safety net. A genuine common stock delisted in 2015–2017 that FinMind
later purged *and* that `delisted_universe.parquet` failed to record
would be silently missing. Verified not to occur: every post-2014
4-digit absentee is an ETF or DR (the 9 above), so no genuine common is
lost. To harden the guarantee, widen the gate past 2014 **and** add an
instrument-type screen — `delisted_universe.parquet` carries no
`industry_category`, so a naive widening would wrongly re-add those
ETFs/DRs as `type=NaN` commons.

Per-stock parquet files for delisted tickers end on their delisting date,
so you should filter by `date` rather than assume uniform coverage.

## Directory layout

```
/home/st/research/finance_db/finmind_data/
├── README.md                          (this file)
├── universe.parquet                   2,154 common stocks (id, name, type, industry)
├── delisted_universe.parquet          315 historical delistings — `TaiwanStockDelisting` output
├── delisted_missing.parquet           9 delistings excluded from universe (ETFs/DRs)
├── capital_reduction.parquet          consolidated cap-reduction events         (2011-01-25→2024)
├── unpriced_actions.parquet           share cancellations no filing explains    (2005-2024)
├── exright_reference.parquet          TWSE 除權除息計算結果表 (權值/息值 split)   (2005-2024)
├── ohlcv/<stock_id>.parquet           daily prices & volume                              (2005-2024)
├── instflow/<stock_id>.parquet        institutional order flow                           (2005-2024)
├── shares/<stock_id>.parquet          shares outstanding + foreign ownership             (2005-2024)
├── per_pbr/<stock_id>.parquet         daily PER / PBR / dividend yield                   (2005-2024)
├── margin_short/<stock_id>.parquet    margin balances + short-sale (informed-trader)     (2005-2024)
├── month_rev/<stock_id>.parquet       monthly revenue (TW 10-day disclosure)             (2005-2024)
├── fin_is/<stock_id>.parquet          quarterly income statement (incl. EPS row)         (2005-2024)
├── fin_bs/<stock_id>.parquet          quarterly balance sheet                            (2005-2024)
├── fin_cf/<stock_id>.parquet          quarterly cash-flow statement                      (2005-2024)
├── dividend/<stock_id>.parquet        cash + stock dividends, declaration level          (2005-2024)
├── div_result/<stock_id>.parquet      除權息 exchange reference prices → adj. factor      (2005-2024)
├── sec_lending/<stock_id>.parquet     securities lending (借券 short proxy)              (2005-2024)
├── cap_red/<stock_id>.parquet         per-stock capital-reduction events (mostly empty)  (2011-2024)
├── *_2015_2024/<stock_id>.parquet     **backup** of pre-rollback (2015-2024) build       (~700 MB total)
├── build_universe.py                  universe construction script (incl. delisted merge)
├── download.py                        resumable downloader (--datasets to filter)
├── consolidate_capred.py              merges cap_red/*.parquet → capital_reduction.parquet
├── detect_unpriced_actions.py         share drops no filing explains → unpriced_actions.parquet
├── download_exright.py                TWSE TWT49U (free, keyless) → exright_reference.parquet
├── adjust.py                          back-adjusted close, price-return and total-return
├── validate_adjust.py                 read-only checks on what `adjust.py` builds
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
| `open/max/min/close` | float64 | TWD, **raw/unadjusted** — verified 99.87 % exact against the exchange's own pre-event `before_price` (see [`VERIFICATION.md`](VERIFICATION.md)) |
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

R = Path("/home/st/research/finance_db/finmind_data")
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

## Adjusted prices

`ohlcv/close` is raw, so any return spanning a 除權息 or 減資 session
carries the full reference-price step. `adjust.py` rebuilds the
back-adjusted series from the exchange's own published reference
prices, in both conventions:

```python
from finmind_data.adjust import load_adjusted

df = load_adjusted("2330")   # + pr_factor / adj_close_pr, tr_factor / adj_close_tr
```

| | removes | leaves | use when |
|---|---|---|---|
| `adj_close_pr` | 無償配股, 現增, and the share-cancellation half of 減資 | every cash drop as a real return — dividends *and* 現金減資 refunds | you want a price series — the usual vendor "adjusted close", and the symmetric counterpart to KRX `ChangesRatio` |
| `adj_close_tr` | all of it, cash included | +29 bp ex-day residual | you want what a holder earned |

The factors are the primary output — any other price column adjusts the
same way (`adj_open_tr = open * tr_factor`) — and both are normalised to
1.0 on the last row, so the adjusted close there is the raw close.

`pr` costs something `tr` does not: the ex-day drop survives as a large
mechanical negative return (−311 bp mean on 除權息 sessions, against
+29 bp under `tr`) on a seasonally clustered set of dates, which a
flow-return study has to handle rather than ignore. `pr` is also NaN
before the last fused cash-and-share event whose cash leg could not be
recovered — 107 events in 61 stocks — rather than silently guessing a
split. Two sources are tried for that leg: the declaration in `dividend/`,
then TWSE's own 息值 in `exright_reference.parquet`, which resolves 143
events the declaration never covered. What remains is the 上櫃 side, which
publishes no reachable archive, and the 權息 events from 2009 on, the year
TWSE stopped printing the split (see caveat 7).

Two columns say which rows to trust, and both need filtering, not
reading past:

```python
df = load_adjusted("2330")
df = df[df["is_valid"] & (df["close"] > 0)]   # then take returns
```

`is_valid` is False for history behind a series break — a share
cancellation no filing priced, or a multi-year trading gap after which
the ticker came back as a different listing (309 breaks in 231 stocks,
3.0 % of rows). `close == 0` is FinMind's encoding for a session the
stock did not trade, not a price, so both adjusted closes are NaN there
(179,749 rows, 2.34 %).

Verification results, the free parameters and the residual ex-day
effect are in
[`VERIFICATION.md`](VERIFICATION.md);
`python -m finmind_data.validate_adjust` reproduces them.

## Load the full panel

```python
import pandas as pd
from pathlib import Path

R = Path("/home/st/research/finance_db/finmind_data")
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
4. **Price adjustment**: `TaiwanStockPrice` closes are **raw** — they reflect
   nothing, not splits and not capital reductions. Build the adjusted series by
   chaining the exchange's own reference prices: `div_result/` (除權息,
   `after_price/before_price`, covers cash *and* rights) and `cap_red/` (減資).
   The two event sets are disjoint, so the chains compose without double
   counting. See [`VERIFICATION.md`](VERIFICATION.md).
5. **減資 events start on 2011-01-25**, six years after the prices do. This is
   the *exchange's* limit, not FinMind's and not the download's: TWSE's own
   TWTAUU report refuses any start date before ROC 100/1/1 and its first row is
   the same 2011-01-25, so no tier and no mirror reaches further back and
   nothing reconstructs the step. `detect_unpriced_actions.py` finds the
   cancellations from
   `shares/NumberOfSharesIssued` instead (92.6 % precision, 92.0 % recall where
   the filed events can score it) and `adjust.py` marks the history behind each
   one `is_valid=False`. 250 such cancellations in 193 stocks fall in the
   uncovered window. Run it after `consolidate_capred.py`; `load_adjusted`
   raises if its output is missing rather than adjusting as if the window were
   clean.
6. **A handful of raw prices are wrong**, and no adjustment can repair a bad
   input. `validate_adjust` check [7] lists what is left after adjustment on
   rows the series vouches for: stale near-zero quotes, sporadic pre-listing
   興櫃 sessions (2007-03-03 and 2007-04-14 carry clusters of them, all TPEx),
   and at least one corrupted row — 8454 on 2014-09-09 reports `open` 241.04
   and `max` 242.49 against `min` = `close` = 3.43, which reads as −98.6 %
   followed by +6,853 %.
7. **TWSE stopped publishing the 除權息 split in 2009.** `exright_reference.parquet`
   carries 權值 and 息值 as separate columns for 2005-2008 and only their sum
   `權值+息值` from 2009 on, alongside a `權/息` label. The label still settles a
   pure 息 or 權 event, so only a fused 權息 after 2008 is left without a cash
   leg. There is no OTC counterpart at all: TPEX's `exDailyQ_result.php` has the
   identical field list but serves a rolling few-day window and ignores every
   date parameter, and its `preAnnounce` table likewise returns only current
   forward announcements. Both limits are the publisher's, not the download's.

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
| `dividend/` | `TaiwanStockDividend` | Cash + stock dividends, at **declaration** level — the per-component split (`CashEarningsDistribution`, `StockEarningsDistribution`, `CashIncreaseSubscriptionRate`). Units differ per field: stock dividends are per NT$10 par, rights are 每仟股. Also carries `CashExDividendTradingDate`, a **declared ex-date usable as an independent second source** for `div_result`'s event date — the two agree on 19,722 of 19,730 comparable events (**99.96 %**; of 2,228 non-matches, 2,220 are outside that stock's `div_result` span and only 8 are real). Present for 1,768 of 2,154 stocks. |
| `div_result/` | `TaiwanStockDividendResult` | 除權除息結果表 — the exchange's **published reference prices** per ex-event (`before_price`, `after_price`). 22,369 events / 1,926 stocks. This, not `dividend/`, is what the adjusted series is built from. |
| `sec_lending/` | `TaiwanStockSecuritiesLending` | 借券/議借 — institutional short proxy |

**Excluded — paid tier or not in FinMind enum:**

| Endpoint | Reason | Workaround |
|---|---|---|
| `TaiwanStockPriceAdj` | Above `register`, our token's level. This is a **tier gate, not a dead endpoint**: the name is in the v4 dataset enum, and where a bogus name returns HTTP 422 with an empty body, this returns HTTP 400 `"Your level is register. Please update your user level"`. Identical across all four calling conventions — with `data_id`, one-day range, no `data_id`, no dates — so the docs' "Free (with data_id)" line is simply wrong. No other host serves it (`api.web…/v2/data`, `/api/v3/data` both 404). Which paid tier unlocks it is not stated; the API only points at the Sponsor page. Re-probed 2026-07-29. | **Not needed.** `div_result/` (`TaiwanStockDividendResult`) is free at register level and gives the exchange's own per-event factor, which is strictly better than a pre-built series. Chain it with `cap_red/`. |
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
| `capital_reduction.parquet` | `TaiwanStockCapitalReductionReferencePrice` | Concatenated event log (sparse: most stocks have 0 events). 9 columns including `PostReductionReferencePrice`, `ExrightReferencePrice`, `ReasonforCapitalReduction`. Per-stock raw files in `cap_red/`; `consolidate_capred.py` merges them. **The endpoint's earliest row is 2011-01-25**, six years after the price series starts — see caveat 5. |

Not a FinMind endpoint at all — the exchange serves it free and without a key:

| File | Source | Notes |
|---|---|---|
| `exright_reference.parquet` | TWSE **TWT49U** 除權除息計算結果表, `www.twse.com.tw/rwd/zh/exRight/TWT49U?startDate=&endDate=&response=json` | 15,314 events / 1,269 stocks, 2005-01-11 → 2024-12-31. Whole-year queries are not truncated (2007 returns 538 rows either way), so `download_exright.py` needs 20 requests. Carries the same two reference prices as `div_result/` — they agree to 1e-6 on **100.00 %** of the 13,891 joined events — plus the **權值 / 息值 split** `div_result` lacks, which resolves 143 fused events whose cash dividend was never declared. Schema narrows in 2009; see caveat 7. Probed 2026-08-01. |
| — | TWSE **TWTAUU** 股票減資恢復買賣參考價格, `…/rwd/zh/reducation/TWTAUU` | **Not downloaded, and it settles caveat 5.** The exchange refuses any start date before ROC 100/1/1 (`查詢開始日期小於100年1月1日，請重新查詢!`) and its first row is 100/01/25 = **2011-01-25**, byte-identical to where FinMind's `cap_red/` begins. The pre-2011 gap is therefore TWSE's own publication limit, not a vendor tier — no paid plan and no other mirror can close it. Probed 2026-08-01. |

Other follow-up not pursued:

- `TaiwanStockNews` — event-study material; size and dedup overhead not
  worth the default download.
- `TaiwanStockTotalReturnIndex` — free at register level, but requires
  `data_id` (`TAIEX`; passing none is an error). Market-level 報酬指數, so it is
  a benchmark, not a per-stock adjustment — irrelevant to the 還原股價 build,
  worth a one-shot pull if a study ever needs a dividend-inclusive market
  return. Probed 2026-07-29.

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

# Adjustment — needs div_result/, capital_reduction.parquet and shares/
python -m finmind_data.detect_unpriced_actions --calibrate   # → unpriced_actions.parquet
python -m finmind_data.download_exright   # TWSE TWT49U, ~20 requests, no key
python -m finmind_data.validate_adjust    # checks what adjust.py builds
```

Re-running any command is safe: `download.py` skips stock-subdir pairs
whose parquet file already exists.