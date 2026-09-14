# Taiwan Equity Market Dataset (TWSE + TPEx, 2011-2026)

Per-stock daily / monthly / quarterly market data for common equities listed on
the Taiwan Stock Exchange (TWSE) and Taipei Exchange (TPEx), covering
**2011-01-25 to 2026-09-09**: OHLCV raw and back-adjusted, institutional order
flow, shareholding, valuation multiples (PER/PBR), margin and short balances,
monthly revenue, fundamentals (IS/BS/CF), dividends, securities lending and
capital-reduction events, plus market-wide reference files for delistings.
Built so that every name that delisted inside the window is in the panel with
a return series, and dated so that a backtest can ask which names were listed
on a given session. Intended for informed-trading / return-reversal research.

| document | what it holds |
|---|---|
| `README.md` | this: the window, the universe, the layout, the schemas, how to load, provenance, the runbook |
| `CAVEATS.md` | every known defect a study meets, one entry each: what, how much, which check pins it, what to do |
| `ADJUSTED_PRICES.md` | the total-return adjusted close: what the vendor serves, what is rebuilt, patched and carried, and the measurements behind each |
| `delisting/README.md` | the delisting study: what each exit paid, read off the tape and the filings |
| `NOTES.md` | dated records of how each correction was found |

## The window

The trees hold prices from 2005-01-01 and this package will not answer
questions about them.

A capital reduction cuts the share count and the quoted price together, and
without the filing that says so the cut is indistinguishable from a −70 % day:
the adjusted series carries the whole mechanical jump as a return, and nothing
in the chain reports that it did. The filings begin on 2011-01-25 and cannot be
pushed back. TWSE publishes them in 股票減資恢復買賣參考價格 (TWTAUU), which
refuses any query beginning before ROC 100/1/1, and its first row is
2011-01-25; FinMind's `TaiwanStockCapitalReductionReferencePrice` mirrors that
table and begins the same day. No paid tier and no second vendor reaches
further back. The limit is the publisher's, not the download's.

Six years of prices with no event log underneath them is not a shorter panel,
it is a panel whose errors are silent, and the choice is which of the two this
package hands a researcher. It hands the shorter one. The earlier prices stay on
disk because they cost nothing to keep and a study that brings its own event log
can use them; nothing here is measured over them.

`window.py` declares `COVERAGE_START` and `COVERAGE_END` once, with the `clip`
that applies them, and every module that reads the trees imports from it rather
than restating the date. `test_taiwan_tree_readers_import_the_window` asserts
the import rule itself, and `test_taiwan_coverage_does_not_outrun_the_data`
checks both ends against the artifacts: the calendar stops exactly where
coverage does, the 興櫃 registry was pulled no earlier, and every name the tape
quotes on the last session carries a row in the price tree. `COVERAGE_END` is
where the download reached, not a period a study reports on; a study names its
own span through `clip(start=, end=)` and `load_adjusted(start=, end=)`.

## Universe

**2,159 common stocks** (4-digit codes), from the 2026-09-10
`derive/build_universe.py` rebuild:

| Exchange | Count |
|---|---|
| TWSE | 1,178 |
| TPEx | 924 |
| In-window delistings the endpoint dropped (type unknown) | 57 |
| **Total** | **2,159** |

**2,117 of them trade inside the window**, and that is the number a study
meets. The other 42 delisted before 2011-01-25 and are carried because the live
registry still lists them; none delisted inside the window, and a study that
assumes uniform coverage over 2,159 is measuring 42 empty series. Both counts
are checked against the tape in
`test_taiwan_universe_holds_every_common_the_tape_shows`.

The universe is **listed common stock on the two main boards**. Every exclusion
removes something that is not common stock, or is common stock on a tier with
different disclosure obligations:

| Excluded | Why | Mechanism in `derive/build_universe.py` |
|---|---|---|
| A / B / C-suffix preferreds | not common stock | `stock_id.str.fullmatch(r"\d{4}")` drops non-numeric suffixes |
| ETF | a fund, not a company | `industry_category == "ETF"`, 5-6-digit `00xxx` codes dropped by the digit filter, `00xx` codes dropped from the overlay |
| ETN | a note, not equity | `industry_category == "ETN"` |
| 受益證券, T-suffix codes | REIT and specialty-fund structures | `industry_category == "受益證券"`, digit filter |
| TDR (存託憑證 / 臺灣存託憑證) | a receipt over a foreign listing, priced off its home market | `industry_category`, 6-digit `91xxxx` codes dropped by the digit filter, `91xx` codes dropped from the overlay |
| TWSE Innovation Board (創新版股票 / 創新板股票) | relaxed-disclosure startup tier, opened 2021-07-20 | `industry_category` |
| TPEx 興櫃 (emerging) | pre-listing board, quote-driven rather than order-driven | `type.isin(["twse", "tpex"])` drops `emerging` |

A filter drops the *stock* on the evidence of any of its rows:
`taiwan_stock_info` returns one row per (market, industry) a stock has been
classified under, and dropping rows then deduplicating kept a stock alive on
whichever row the response listed first (`NOTES.md`).

Two inclusions are deliberate. **F-/-KY foreign-domiciled primary listings**
(9802 鈺齊-KY, 1590 亞德客-KY) are kept: the shares are a primary listing that
prices here. **Every name that delisted inside the window** is kept, below.
Liquidity floors, IPO seasoning and 警示股 / 全額交割 flags are study-specific
screens and are not applied here.

### Survivorship

FinMind's `taiwan_stock_info` is a list of names the vendor still serves. Of the
190 four-digit codes `TaiwanStockDelisting` dates inside the window, 11 are
`00xx` ETFs or `91xx` depositary receipts, leaving **179 commons, all 179
present**: 122 still in the live registry and **57 re-added** from the
delisting table by `derive/build_universe.py`, on the test of whether the endpoint
still serves the *company* rather than the code (a 4-digit code is reissued
after its first occupant delists). The overlay's gate is the window itself, not
a date inside it (`NOTES.md` records the gate it replaced). Per-stock files
for delisted names end on their delisting date, so filter by `date` rather than
assume uniform coverage.

**This completeness is about prices.** The 179 all carry a return series;
`fin_is/` carries a statement for 84 of them and `fin_bs/` for 97, because the
endpoints serving filings answer for a company that still reports. A
fundamentals study on this panel is therefore still survivorship-biased where a
price study is not (`CAVEATS.md` 10).

### A universe is a name list until it is dated

`data/universe.parquet` carries the same 2,159 names on every session. Screening
it at a 2013-06-28 rebalance puts 586 names in that session's universe that were
not listed that day: 522 not yet listed, 42 delisted before the window, 19
already delisted, 3 listed but not quoted. `derive/pit_universe.py` dates the
universe against the tape, what actually traded, and corrects it in the two
places the tape alone is wrong:

```python
from finmind_data.derive.pit_universe import universe_at, sessions
universe_at("2016-06-30")     # 1,702 codes; 1,458 on the first session, 1,935 on the last
sessions()                    # the 3,823 sessions the exchange held, to snap a rebalance date onto
```

A date the market was shut **raises** rather than returning an empty index.

**興櫃 sessions are removed**: 90,406 code-sessions across 135 names, 1.35 % of
the panel. A code is excluded on every session up to the day its `emerging`
classification was retired, the only point-in-time market fact the registry
carries; `data/listing_spans.parquet` stamps the registry pull it was read from.

**The suspension before a delisting is added back**: 5,538 sessions across 150
of the 179. The tape's last session is the last trade, not the delisting (台一
stopped trading 229 days before its listing ended); in between the company is
still listed and the terminal value still owed, so a span runs to the session
before the delisting date.

**An interior gap is the caller's rule.** 609 codes have at least one session
between their first and last quote that the tape does not carry, over 1,281
gaps, and the span table splits on every one. The median gap is 7 sessions,
which is a halt; 48 codes have a gap of 60 sessions or more, which is not, and
no threshold separating them is available that is not simply chosen.
`universe_at(date, bridge_gaps_upto=n)` closes gaps of at most `n` sessions at
query time; the default 0 is the artifact's own semantics. Bridging never
extends a code's last run, so no setting resurrects a delisted name
(`test_taiwan_universe_bridges_a_halt_only_when_asked`).

`test_taiwan_pit_universe_is_dated_and_keeps_its_delistings` pins, from
committed artifacts alone, that every one of the 179 is in the universe on its
last trading session, through the suspension, and gone on the day its listing
ends. `test_taiwan_listing_spans_reconcile_with_the_tape` needs `raw/tape/` and
reconciles all 6.6 M code-sessions against it; that is the only check that sees
a 興櫃 name admitted for the middle of the window.

## Layout

```
finmind_data/
├── README.md  CAVEATS.md  ADJUSTED_PRICES.md  NOTES.md
├── paths.py          where each kind of file lives, named once
├── datasets.py       the 14 FinMind datasets: tree, vendor name, key, cadence
├── client.py         the one request loop: header auth, pacing to the quota, 402 → top of the hour
├── auth.py  window.py  catalogue.py  raw_store.py
├── collect/          asks a vendor, writes what it answered
│   ├── sweep.py          date-keyed, every stock at once per date → raw/<vintage>/
│   ├── download.py       per stock → trees/ (resumable; --extend tops files up)
│   ├── tape_universe.py  the price tape → raw/tape/, data/tape_universe.parquet
│   ├── refresh_delisting.py  download_exright.py  download_split_price.py
│   ├── filing_dates.py   TWSE document server → trees/filing_dates/, data/filing_dates.parquet
│   ├── mops_filings.py   公開資訊觀測站 filings for the delisted names
│   └── ohlcv_repull.py   the 60-stock second reading of the price tree
├── derive/           the universe, the calendar, the adjusted panel, the dates a figure became readable
│   ├── build_universe.py  pit_universe.py  adjusted_loader.py  adjust.py
│   ├── available_date.py  vendor_event_audit.py  detect_unpriced_actions.py
│   └── consolidate_capred.py
├── repair/           changed rows in trees/, each leaving its record in records/
│   ├── backfill_make_up_sessions.py  volume_repair.py  fin_bs_vintage.py
│   └── date_keyed_fill.py  repull_fill.py  short_sale_repair.py
├── delisting/        the delisting study (own README)
│   └── delisting_sign.py  mops_reason.py  swap_ratios.py  tender_offers.py
├── checks/           the checks behind every claim here, one module per topic, each with its CHECKS
│   └── window.py  universe.py  adjusted.py  trees.py  fundamentals.py  delisting.py  _common.py
├── test_assertions.py  populations.json    the runner over checks/, and what each check last read
│
├── raw/              gitignored. What the vendor answered, as it answered it
│   ├── <vintage>/<tree>/<year>.parquet   one dated sweep; manifest.json per (tree, year)
│   └── tape/<year>.parquet               the price tape, four columns
├── trees/            gitignored. The per-stock panel the loaders and checks read
│   ├── ohlcv/ price_adj/ instflow/ shares/ per_pbr/ margin_short/ month_rev/
│   ├── fin_is/ fin_bs/ fin_cf/ dividend/ div_result/ sec_lending/ cap_red/   <stock_id>.parquet
│   └── filing_dates/<stock_id>.parquet
├── data/             tracked. The small artifacts the checks read
│   ├── universe.parquet  delisted_universe.parquet  listing_spans.parquet  trading_sessions.parquet
│   ├── tape_universe.parquet  vendor_event_audit.parquet  split_reference.parquet  filing_dates.parquet
│   ├── filing_deadlines.csv  ohlcv_repull.parquet  finmind_catalogue_<date>.txt
│   ├── capital_reduction.parquet  unpriced_actions.parquet  exright_reference.parquet   (regenerable, ignored)
│   └── delisting_*.{parquet,csv}  mops_reason.parquet  tender_offers.parquet  mops_*/   (the delisting study)
├── records/          tracked. What each repair added or replaced, old value beside new
│   └── volume_repair.parquet  short_sale_repair.parquet  fin_bs_vintage*.parquet  date_keyed_fill/  repull_fill/  fill_2026-09-13/
└── _internal/        gitignored. Logs, run state, fingerprints
```

Every module takes its paths from `paths.py`; every dataset name, key and
cadence from `datasets.py`; every FinMind request goes through `client.get`.
Three source-level checks hold that: `test_taiwan_tree_readers_import_the_window`,
`test_taiwan_dataset_names_in_code_resolve`, `test_taiwan_token_travels_in_a_header`.

## Datasets and schemas

The 14 trees, as `datasets.py` names them. `cadence` is what the date-keyed
endpoint keys a dataset on, which is what `collect/sweep.py` asks it at.

| tree | FinMind dataset | cadence | what it is |
|---|---|---|---|
| `ohlcv` | `TaiwanStockPrice` | day | daily prices and volume, **raw** |
| `price_adj` | `TaiwanStockPriceAdj` | session | 還原股價, back-adjusted, total-return convention, sponsor tier |
| `instflow` | `TaiwanStockInstitutionalInvestorsBuySell` | session | institutional order flow, one row per investor type |
| `shares` | `TaiwanStockShareholding` | session | shares outstanding, foreign ownership |
| `per_pbr` | `TaiwanStockPER` | session | daily PER / PBR / dividend yield |
| `margin_short` | `TaiwanStockMarginPurchaseShortSale` | session | margin balances, short-sale flows and balances |
| `sec_lending` | `TaiwanStockSecuritiesLending` | session | 借券, one row per transaction type |
| `div_result` | `TaiwanStockDividendResult` | session | 除權息 exchange reference prices, the factor's first chain |
| `dividend` | `TaiwanStockDividend` | day | declared distributions, with announcement dates |
| `month_rev` | `TaiwanStockMonthRevenue` | month | monthly revenue; `date` is the month after the revenue month |
| `fin_is` `fin_bs` `fin_cf` | `TaiwanStockFinancialStatements` `…BalanceSheet` `…CashFlowsStatement` | quarter | statements keyed on the quarter that closed |
| `cap_red` | `TaiwanStockCapitalReductionReferencePrice` | range | 減資 reference prices, the factor's second chain |

Three market-wide tables are not trees: `data/delisted_universe.parquet`
(`TaiwanStockDelisting`, 725 rows), `data/split_reference.parquet`
(`TaiwanStockSplitPrice`, the factor's third chain) and
`data/exright_reference.parquet` (TWSE's own TWT49U, keyless).

### `trees/ohlcv/<stock_id>.parquet`: daily prices

One row per trading day (~5,300 rows in a full 2005-2026 series; ~3,820 of them
inside the window).

| column | dtype | description |
|---|---|---|
| `date` | str | YYYY-MM-DD |
| `stock_id` | str | 4-digit ticker |
| `open/max/min/close` | float64 | TWD, **raw/unadjusted**: the cum-session close matches the exchange's own pre-event `before_price` on 99.83 % of the 21,417 除權息 events inside the window, at the two decimals the exchange publishes (`test_taiwan_ohlcv_is_raw`) |
| `spread` | float64 | close − prior close (TWD) |
| `Trading_Volume` | int64 | shares traded |
| `Trading_money` | int64 | trading value in TWD |
| `Trading_turnover` | int64 | number of trades |

A session the stock did not trade is a row with `close == 0`, not a missing
row (136,383 in-window rows, 2.04 %).

### `trees/instflow/<stock_id>.parquet`: institutional order flow

Long format, one row per (date, investor type), ~5 rows a trading day.

| column | dtype | description |
|---|---|---|
| `date` | str | YYYY-MM-DD |
| `stock_id` | str | |
| `name` | str | `Foreign_Investor`, `Investment_Trust`, `Dealer_self`, `Dealer_Hedging`, `Foreign_Dealer_Self` |
| `buy` | int64 | shares bought by this investor type |
| `sell` | int64 | shares sold by this investor type |

Individual retail flow is not reported; derive it as
`Trading_Volume − Σ(buy+sell)/2` per stock-day. Net flow is `buy − sell` in
shares; multiply by `close` for TWD.

### `trees/shares/<stock_id>.parquet`: shares outstanding and foreign ownership

One row per trading day.

| column | dtype | description |
|---|---|---|
| `date`, `stock_id`, `stock_name` | str | |
| `InternationalCode` | str | ISIN |
| `NumberOfSharesIssued` | int64 | total shares outstanding; market cap is `close * NumberOfSharesIssued` |
| `ForeignInvestmentShares` | int64 | shares owned by foreign investors |
| `ForeignInvestmentRemainingShares` | int64 | shares still open to foreign purchase |
| `ForeignInvestmentSharesRatio` | float64 | foreign ownership % |
| `ForeignInvestmentRemainRatio` | float64 | remaining foreign quota % |
| `ForeignInvestmentUpperLimitRatio` | float64 | regulatory cap (typically 100) |
| `ChineseInvestmentUpperLimitRatio` | float64 | Chinese investor cap |
| `RecentlyDeclareDate` | str | most recent capital-change disclosure |
| `note` | str | usually empty |

The other trees carry the vendor's columns as served; `datasets.py` names the
key under which a row is one row of its stock.

## Quick start

```python
import pandas as pd
from finmind_data.paths import TREES, DATA
from finmind_data.window import clip

sid = "2330"
ohlcv = clip(pd.read_parquet(TREES / "ohlcv" / f"{sid}.parquet"))
flow  = clip(pd.read_parquet(TREES / "instflow" / f"{sid}.parquet"))
shr   = clip(pd.read_parquet(TREES / "shares" / f"{sid}.parquet"))

net = flow.assign(net=flow["buy"] - flow["sell"])
flow_wide = net.pivot(index="date", columns="name", values="net").reset_index()
df = (ohlcv.merge(flow_wide, on="date", how="left")
           .merge(shr[["date", "NumberOfSharesIssued"]], on="date", how="left"))
df["mktcap_twd"] = df["close"] * df["NumberOfSharesIssued"]
```

`clip` applies the window; the trees are wider than it on both sides. The
adjusted close, the dated universe and the dates a fundamental figure became
readable:

```python
from finmind_data.derive.adjusted_loader import load_adjusted
from finmind_data.derive.pit_universe import universe_at, sessions
from finmind_data.derive.available_date import with_available_date, with_observed_date

adj = load_adjusted("2330", start="2011-01-25", end="2024-12-31")
adj = adj[adj["is_valid"] & adj["adj_close_tr"].notna()]          # then take returns
names = universe_at("2016-06-30", bridge_gaps_upto=5)
fin = with_observed_date(pd.read_parquet(TREES / "fin_is" / "2330.parquet"))
```

The whole panel:

```python
universe = pd.read_parquet(DATA / "universe.parquet")
ohlcv_all = pd.concat([clip(pd.read_parquet(TREES / "ohlcv" / f"{s}.parquet"))
                       for s in universe["stock_id"]], ignore_index=True)
```

## Adjusted prices

`ohlcv/close` is raw, so any return spanning a 除權息 or 減資 session carries
the full reference-price step. `price_adj/` is FinMind's `TaiwanStockPriceAdj`,
bought at the sponsor tier, and `derive/adjusted_loader.py` joins it onto the
raw series, fills the 54 stocks it does not serve, replaces its step on the one
event where it disagrees with the exchange in size rather than in a cent, and
carries its factor onto the first traded session it starts late on. Every row
says where its factor came from (`adj_source`), which convention produced its
steps (`adj_method`), whether the vendor served it (`adj_covered`), and whether
a study could have held it (`is_valid`, with `invalid_reason`).

**One convention, and it is total return.** Cash dividends come out along with
無償配股, 現增 and 減資. There is no price-return variant of the endpoint at any
tier, and the exchange publishes one fused reference price per event, so a
study that needs the price alone has no source here.

**The survivorship hole is filled from the exchange.** `price_adj/` serves
nothing inside the window for 54 stocks, 50 of them in-window delistings dropped
from the vendor's registry, and the date-keyed endpoint lacks them too (probed
2026-09-13). `derive/adjust.py` rebuilds the factor from `div_result/`,
`capital_reduction.parquet` and `split_reference.parquet`, the exchange's own
reference prices, which do not depend on the registry. On the 131 in-window
delistings the vendor does cover, the rebuild reproduces 99.952 % of 247,422
daily adjusted returns to 1e-6.

`ADJUSTED_PRICES.md` carries the rest: the vendor's methodology and where it
differs from the exchange by a cent, the one defective event, the edges, the
make-up sessions, the anchor rule, and the validity flags. `CAVEATS.md` 4, 5
and 6 are the short form.

## Two regime facts about the window

**The daily price limit widened on 2015-06-01**, from ±7 % to ±10 %.
Volatility and reversal dynamics are not comparable across that date; a regime
dummy or a split sample is required.

**The short-sale series has no regime gap in it.** Across the 189 in-window
months, on 2,082 names, not one month has zero short-sale volume and not one has
zero short balance; March 2020 carries 1.59× the 2019 monthly mean. A missing
stretch in `margin_short/` is a download that failed, never a rule that changed
(`test_taiwan_short_sale_series_has_no_regime_gap`).

## Provenance

- **Source:** FinMind API, `https://api.finmindtrade.com/api/v4/data`, through
  `client.py`: the token from the gitignored `.token` travels in an
  `Authorization: Bearer` header, requests are paced to the quota `user_info`
  reports, and a 402 is answered by sleeping to the top of the hour
  (`test_taiwan_token_travels_in_a_header`).
- **Tier:** sponsor (level 3, 6,000 requests/hour) from 2026-08-16, expiring
  2026-09-16. `price_adj/` and every date-keyed sweep need Backer or Sponsor;
  the per-stock queries for the other trees are free.
- **Datasets:** the 14 in `datasets.py`, checked against the vendored catalogue
  `data/finmind_catalogue_20260825.txt` by `test_taiwan_dataset_names_in_code_resolve`.
- **Upstream origin:** TWSE and TPEx daily disclosures.
- **2005-2024 build:** started 2026-04-27 via `collect/download.py`
  (`--start 2005-01-01`), ~25,800 requests under the 600/hr register quota,
  ~43 hours. It superseded a 2015-2024 build of 2026-04-20..26, deleted 2026-08-18.
- **Adjusted prices:** 2026-08-16, 2,154 requests under the 6000/hr quota.
- **Extension to 2026-09-09:** 2026-09-10, `download.py --extend --end 2026-09-15
  --start 2025-01-01` over the rebuilt 2,159-name universe, 11:24 to 17:20, 0
  failures; the 2011-01-25..2024-12-31 rows of all 31,220 existing files were
  byte-identical after it. The pull crossed the exchange's close, which is why
  coverage stops a day short of its last row.
- **Re-pull, 2026-09-11:** `collect/ohlcv_repull.py` pulled `TaiwanStockPrice`
  again for 60 stocks drawn at random (40 of the 684 with an `open` outside
  `[min, max]`, 20 of the rest); `data/ohlcv_repull.parquet` is that pull as
  served. All 159,684 in-window rows came back with the same prices; 138 came
  back with a higher count, every one a make-up Saturday.
- **Adjusted re-pull, 2026-09-12:** `download.py --extend --datasets price_adj`
  re-pulled all 2,159 universe files whole, 20:14 to 20:48 (`ADJUSTED_PRICES.md`,
  "One pull per adjusted file").
- **Balance-sheet revision, 2026-09-12..13:** `TaiwanStockBalanceSheet` pulled
  date-keyed, graded against MOPS by `repair/fin_bs_vintage.py`, the revision
  written where the filing sides with it (`CAVEATS.md` 13).
- **Date-keyed fill, 2026-09-12..13:** statements and revenue pulled date-keyed,
  the company-periods the trees lacked added by `repair/date_keyed_fill.py`
  (`CAVEATS.md` 14).
- **Whole re-pull of the daily trees, 2026-09-13:** six trees pulled again per
  stock, 13,386 requests, 13:26 to 15:57; `repair/repull_fill.py` added what
  the trees lacked (`CAVEATS.md` 15). The pull is not committed.
- **Date-keyed sweep, 2026-09-13:** `collect/sweep.py` swept all 14 datasets
  date-keyed into `raw/2026-09-13/`, 2011-01-25..2026-09-12, every stock at
  once per date, 4-digit codes only: 38,571 requests and 70,781,092 rows
  (889 MB), 20:26 to 03:39 the next morning under the 6,000/hr quota.
  `raw/2026-09-13/manifest.json` records per (tree, year) the dates asked and
  answered, the rows and the time, and every entry finished. The balance sheet
  answers date-keyed from 2012-12-31, so 7 of its 62 quarter ends came back
  empty; the trees hold 2012's quarters from the per-stock query. It is the
  first dated vintage of the raw store and the reference a later fill reads.
  The capital-reduction table came back 671 rows against the 674 committed in
  `data/capital_reduction.parquet`: the vendor has withdrawn 2327's 2022-10-21,
  3018's 2023-11-11 and 6109's 2020-09-25, the three duplicate filings
  `derive/adjust.py` already drops before building a factor.
- **Fill from the vintage, 2026-09-14:** `repair/fill_from_vintage.py` added
  the 82,669 rows the trees lacked and `raw/2026-09-13/` carries, in eight
  trees; `records/fill_2026-09-13/` holds every added row and every stock-date
  the vintage lacks (`CAVEATS.md` 18).

## Coverage and endpoint mapping

**The whole Taiwan catalogue was swept on 2026-08-25.** FinMind publishes a
machine-readable index at `finmind.github.io/llms-full.txt`, vendored as
`data/finmind_catalogue_20260825.txt` and read by `catalogue.py`, so "is there a
dataset for this?" is answered locally. A wrong name is not a loud failure at
this API, so every dataset name spelled in the package is checked against the
enum, and the two names `catalogue.KNOWN_ABSENT` records as refused
(`TaiwanStockEPS`, `TaiwanStockShareholdingClassification`) are re-confirmed
absent.

**The exit price is not in the catalogue.** `TaiwanStockDelisting` carries
`date`, `stock_id`, `stock_name` and nothing else, and no other dataset carries
a reason or a settlement price; what a holder received is read one filing at a
time (`delisting/README.md`).

Not a FinMind endpoint, served free by the exchange: `data/exright_reference.parquet`
from TWSE's TWT49U (17,940 除權息 events, 2005-2026, with the 權值 / 息值 split
through 2008; `collect/download_exright.py`, 22 requests). TWSE's TWTAUU
減資 table is not downloaded; it settles the window's start (above).

| Reachable, not taken | What it is | Why not |
|---|---|---|
| `TaiwanStockDispositionSecuritiesPeriod` | 處置有價證券, 6,405 rows from 2011-01-25 | marks abnormal trading, not a reason; points the wrong way on the delisting band (`delisting/README.md`) |
| `TaiwanStockSuspended` | 暫停交易公告 from 2011-11-04 | 266 of 7,114 rows are 4-digit commons; most are warrants |
| `TaiwanStockTradingDate` | the session calendar | already held as `data/trading_sessions.parquet`, derived from the tape |
| `TaiwanStockMarginShortSaleSuspension`, `TaiwanStockDayTradingSuspension` | routine pre-ex-dividend suspensions | not distress |
| `TaiwanStockParValueChange` | 面額變更 under other names | a strict subset of `TaiwanStockSplitPrice`, which is taken |
| `TaiwanStockMarketValue` | 市值 | returns 0 rows market-wide; market cap is `close × NumberOfSharesIssued` here |
| `TaiwanStockHoldingSharesPer`, the CB datasets, `TaiwanStockNews`, `TaiwanStockTotalReturnIndex` | reachable on the sponsor token | none feeds a current question |

| Not in FinMind | Source |
|---|---|
| Free float | TEJ, Bloomberg `EQY_FREE_FLOAT_PCT` |
| 5 %-rule major-shareholder changes, rights-offering details, IPO lockups, BW balances | MOPS, TEJ |
| Analyst consensus and coverage | Refinitiv I/B/E/S, Bloomberg |
| Tick size / price-limit change history | TWSE rulebook, recorded once |

## Runbook

Prerequisites: the conda env (`source /home/st/miniconda3/bin/activate`), the
FinMind token in `finmind_data/.token`, and for anything date-keyed or
back-adjusted a Backer or Sponsor subscription. Every command runs from the
repository root as a module.

**Rebuild from a clone**, in this order, each step reading what the one above
wrote:

```bash
python -m finmind_data.collect.download                   # trees/, per stock (~5 h at 6000/hr)
python -m finmind_data.collect.refresh_delisting          # data/delisted_universe.parquet
python -m finmind_data.derive.build_universe              # data/universe.parquet
python -m finmind_data.collect.tape_universe              # raw/tape/, data/tape_universe.parquet (~1 h)
python -m finmind_data.derive.pit_universe                # data/trading_sessions, listing_spans
python -m finmind_data.derive.consolidate_capred          # data/capital_reduction.parquet
python -m finmind_data.collect.download_exright           # data/exright_reference.parquet
python -m finmind_data.collect.download_split_price       # data/split_reference.parquet
python -m finmind_data.derive.detect_unpriced_actions --calibrate   # data/unpriced_actions.parquet
python -m finmind_data.derive.vendor_event_audit          # data/vendor_event_audit.parquet
python -m finmind_data.collect.filing_dates               # trees/filing_dates/ (budget a day)
python -m finmind_data.collect.filing_dates --consolidate # data/filing_dates.parquet
python finmind_data/test_assertions.py
```

A clone's trees are a new vintage of the vendor and will not reproduce the
committed records in `records/`: those record what the first pull held and what
each repair changed, and the checks that read them pin today's trees.

**Extend the far end.** Sweep date-keyed: one request per new session per
dataset, every stock at once, delisted names included.

```bash
python -m finmind_data.collect.sweep --end <YYYY-MM-DD>                   # raw/<today>/, resumable per (tree, year)
python -m finmind_data.repair.fill_from_vintage --vintage <today> --dry-run
python -m finmind_data.repair.fill_from_vintage --vintage <today>         # adds what the trees lack, records/fill_<today>/
```

The fill adds rows the trees lack under each tree's key and touches no row
they hold; what the vintage no longer serves is recorded, not dropped, and a
back-adjusted tree is skipped (`repair/fill_from_vintage.py`). Against the
2026-09-13 vintage it added 82,669 rows in eight trees, most of them the daily
PER and margin histories of delisted names, and nothing to the price, dividend,
revenue and capital-reduction trees (`CAVEATS.md` 18).

The per-stock route still exists and costs one request per file per dataset:
`python -m finmind_data.collect.download --extend --end <YYYY-MM-DD>`. Rebuild
the universe before a per-stock pull, because a name absent from it is never
fetched. Then set `window.COVERAGE_END` to the last session the pull finished
whole (`test_taiwan_coverage_does_not_outrun_the_data` names the date to move
back to) and the `--end` default in `collect/download.py` to the same session,
and re-run from `tape_universe` down in the rebuild list above, ending with
`python finmind_data/test_assertions.py --write-populations`.

**After any refresh**, run the checks. Each prints PASS, FAIL or SKIP with `n`,
the size of the population it examined, and `n` is held against
`populations.json`: a shrunk population fails, a grown one is re-seeded with
`--write-populations` once understood. A check whose artifact is absent raises
`Skipped`, and the runner exits non-zero unless `--allow-skips` is given, so a
green result means every check read something. `../run_assertions.sh` runs
every package's suite.
