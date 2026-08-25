# Taiwan Equity Market Dataset (TWSE + TPEx, 2011-2024)

Per-stock daily / monthly / quarterly market data for common equities
listed on the Taiwan Stock Exchange (TWSE) and Taipei Exchange (TPEx),
covering **2011-01-25 to 2024-12-31**: OHLCV raw and back-adjusted,
institutional order flow, shareholding, valuation multiples (PER/PBR),
margin + short balances, monthly revenue, fundamentals (IS/BS/CF),
dividends, securities lending, and capital-reduction events. Plus
market-wide reference files for delistings.
Intended for informed-trading / return-reversal research as
a cross-market validation of Korean-market findings (paired with
`~/research/finance_db/fnguide_data`, which starts ~2000).

## Why coverage starts on 2011-01-25

The trees hold prices from 2005-01-01 and this package will not answer
questions about them.

A capital reduction cuts the share count and the quoted price together, and
without the filing that says so the cut is indistinguishable from a −70 %
day: the adjusted series carries the whole mechanical jump as a return, and
nothing in the chain reports that it did. The filings begin on 2011-01-25
and cannot be pushed back. TWSE publishes them in 股票減資恢復買賣參考價格
(TWTAUU), which refuses any query beginning before ROC 100/1/1, and its
first row is 2011-01-25; FinMind's
`TaiwanStockCapitalReductionReferencePrice` mirrors that table and begins
the same day. No paid tier and no second vendor reaches further back — the
limit is the publisher's, not the download's.

Six years of prices with no event log underneath them is not a shorter
panel, it is a panel whose errors are silent, and the choice is which of the
two this package hands a researcher. It hands the shorter one. The earlier
prices stay on disk because they cost nothing to keep and a study that
brings its own event log can use them; nothing here is measured over them.

`window.py` declares `COVERAGE_START` and `COVERAGE_END` once, along with the
`clip` that applies them, and every script that reads the trees imports from it
rather than restating the date. That is also what makes the boundary checkable:
`test_assertions.py` asserts the package's coverage sits inside the shared study
window rather than re-deriving it, and asserts the import rule itself — a new
module that reads the trees without going through `window.py` fails the suite,
because an unclipped read measures the sessions outside the window into a figure
published as being about it.

The window was originally 2015-01-01 → 2024-12-31; on 2026-04-27 the start
was rolled back to 2005-01-01 to give 20 years of overlap with fnguide, and
on 2026-08-17 the answerable range was cut to 2011-01-25 for the reason
above.

## Universe

**2,158 common stocks** (4-digit ticker codes), from the 2026-08-17
`build_universe.py` rebuild:

| Exchange | Count |
|---|---|
| TWSE                                   | 1,178 |
| TPEx                                   |   923 |
| In-window delistings the endpoint dropped (type unknown) | 57 |
| **Total**                              | **2,158** |

**2,095 of them trade inside the window**, and that is the number a study
meets. The other 63 hold a code and contribute no observation: **42 delisted
before 2011-01-25** and are carried because the live endpoint still lists them
— 1107, 2341, 2381 and 2396 among them, quoted on 興櫃 after their exit but
never again on a board — and **21 first traded after 2024-12-31**, the earliest
on 2025-01-03, which `build_universe.py` does not filter on because it reads a
registry rather than a calendar. **None of the 63 delisted inside the window**,
which is the case that would have been a coverage failure rather than dead
weight. Nothing is biased by their presence; a study that assumes uniform
coverage over 2,158 is measuring 63 empty series. Both counts are checked
against the tape rather than asserted, in
`test_taiwan_universe_holds_every_common_the_tape_shows`.

Excludes: ETFs (`00xxx` codes), warrants, TDRs (industry categories
"存託憑證" / "臺灣存託憑證"), beneficiary certificates ("受益證券"),
ETNs, and the TWSE Innovation Board relaxed-disclosure tier
("創新版股票" / "創新板股票") — 375 names in all.

The 57 delistings are added on top of FinMind's live `taiwan_stock_info`
output — they are 4-digit common stocks whose *company* the live endpoint no
longer returns, delisting inside the window per `delisted_universe.parquet`.
They carry `type=NaN` and `industry_category=NaN`. FinMind still serves
price/flow data for these names up to their delisting date. Without them the
Taiwan panel would be 0 %-coverage on the delistings fnguide covers at
~90 %, breaking cross-market symmetry.

### The overlay gate was never evidence for its own premise

The re-add used to be gated at `date < 2015-01-01`, on the premise that the
live endpoint keeps every name that delisted from 2015 on. It does not, and
the gate could not have caught that: the delisting table it was checked
against held 315 rows and simply did not know about the names that would
have falsified it. The 2026-08-17 refresh brings the table to 723, and 46 of
the names it adds delisted in 2015 or later with no row in the live endpoint
at all — so the universe was survivorship-biased across 2015-2020, not only
before 2015 as the gate assumed.

The gate is now the window itself, and the test of whether a name needs
re-adding is the one the date was standing in for: whether the endpoint
still serves the company. Company rather than code, because a 6-digit code
can be reissued after its first occupant delists, and the endpoint answers
for the successor — testing the code would report the predecessor as still
listed and drop it from the overlay.

A 4-digit code is not by itself a common stock, either: Taiwan numbers its
ETFs `00xx` and its depositary receipts `91xx`, and the refreshed table puts
11 of them inside the window. They are excluded by instrument type rather
than by the accident that the endpoint still happens to serve them.

### The exclusions ran against rows, and admitted 33 names

`taiwan_stock_info` returns one row per (market, industry) a stock has
been classified under — 835 of 2,162 four-digit TWSE/TPEx codes carry
more than one, rows still in force stamped with the query date and
retired ones with the date they were retired. Until 2026-08-17 the
filters above dropped matching *rows* and deduplicated afterwards, which
drops nothing when a stock has a second row: every Innovation Board name
also carries an ordinary industry row, so all 30 in the file survived on
it — 29 of them wrongly, and 2432 under a name and industry three years
stale, kept only because its row stands for the predecessor rather than
the Innovation Board company now holding the code. Four TDRs — 9101
福雷電, 9102 東亞科, 9104 萬宇科, 9151 旺旺 — came back by the other route,
since the overlay asked whether a code was absent from the *filtered*
table and the filter had just removed them.

The count beside this section was asserted and the criterion was not, so
2,154 stayed green while 33 of the names under it were forbidden. Both
filters now drop the stock on the evidence of any of its rows,
`build_universe.py` asserts that no excluded instrument survived, and
`test_taiwan_universe_excludes_the_instruments_it_claims_to` checks the
criterion rather than the total.

Six of the 29 have since transferred to the ordinary board and are
excluded here too: the earliest retired Innovation Board classification
is stamped 2024-11-25, so each was on the relaxed-disclosure tier for
all but the last five weeks of the 2011-2024 window.

Two things this correction did not do. Per-stock files under
`ohlcv/`, `price_adj/` and the rest still exist for the 33 removed
names and are simply unread — no download was rerun. And the rest of
the file is the 2026-04-27 snapshot: 675 of the retained rows still
carry the industry the endpoint listed first rather than the one in
force, which only a full rebuild refreshes.

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
- **Delisted-during-window tickers** are kept (all 164 eligible
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

**The universe includes every stock delisted during the sample window.**
FinMind's `taiwan_stock_info` endpoint returns recently-delisted stocks
alongside currently-listed ones, and the rest are merged in from
`delisted_universe.parquet`. Of the **175** four-digit codes the table
dates inside 2011-01-25 → 2024-12-31, 11 are ETFs or depositary receipts
excluded by instrument type (`00xx` and `91xx`), leaving **164 commons,
all 164 present** — 107 already in the live endpoint's output and **57
added by the overlay**.

The overlay's gate is the window, not a date chosen inside it, and the
test of whether a name needs re-adding is whether the endpoint still
serves the *company*. The earlier `date < 2015-01-01` gate rested on the
premise that the endpoint keeps every name delisted from 2015 on; the
refreshed table falsifies it in 46 places, and the version of the table
the gate was checked against could not have shown that. Because the gate
is now a window rather than a retention assumption, there is no residual
reliance on FinMind's live retention to state: a common delisted inside
the window is re-added on the evidence of the delisting table, and the
instrument-type screen is what stops the ETFs and DRs from coming back
with it as `type=NaN` commons.

Per-stock parquet files for delisted tickers end on their delisting date,
so you should filter by `date` rather than assume uniform coverage.

**This completeness is about prices, and does not reach the filings.** The
164 names are all here with a return series, but `fin_is/` carries a
statement for 63 of them and `fin_bs/` for 82, because the endpoints serving
company filings answer for a company that still reports rather than for a
code that once listed. A fundamentals study on this panel is therefore still
survivorship-biased where a price study is not; caveat 10 measures it.

## Directory layout

```
/home/st/research/finance_db/finmind_data/
├── README.md                          (this file)
├── universe.parquet                   2,158 common stocks (id, name, type, industry)
├── delisted_universe.parquet          723 historical delistings — `TaiwanStockDelisting` output
├── capital_reduction.parquet          consolidated cap-reduction events         (2011-01-25→2024)
├── unpriced_actions.parquet           share cancellations no filing explains    (2005-2024)
├── vendor_event_audit.parquet         every 除權息 graded against the exchange  (2005-2024)
├── delisting_sign.parquet             each market exit as failure / payout / undecided (2011-2024)
├── delisting_labels.csv               reasons read off announcements; the drawn sample
├── delisting_band.csv                 the 9 held-out band names + the pre-registered cut
├── delisting_consideration.csv        deal terms read for the payouts, incl. pre-window names
├── filing_dates.parquet                when each statement first became public (1997-2026)
├── mops_reason.parquet                why each exit happened, read off MOPS subjects (2011-2024)
├── tender_offers.parquet              every filed 公開收購 and its per-share price (2016-2024)
├── mops_detail_refusals.csv           the names MOPS will not serve a 說明 for
├── filing_deadlines.csv               versioned statutory filing deadlines, cited (2005-2024)
├── exright_reference.parquet          TWSE 除權除息計算結果表 (權值/息值 split)   (2005-2024)
├── filing_dates/<stock_id>.parquet    every 財務報告書 this company filed, with 上傳日期
├── mops_listing/<stock_id>.parquet    重大訊息 主旨, delisting ROC year and the two before
├── mops_detail/<stock_id>.parquet     同, with 符合條款 / 事實發生日 / 說明 where served
├── ohlcv/<stock_id>.parquet           daily prices & volume, **raw**                     (2005-2024)
├── price_adj/<stock_id>.parquet       同, back-adjusted (還原股價, total return)          (2005-2024)
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
├── build_universe.py                  universe construction script (incl. delisted merge)
├── refresh_delisting.py               re-pulls the market-wide TaiwanStockDelisting table
├── window.py                          COVERAGE_START / COVERAGE_END, declared once
├── download.py                        resumable downloader (--datasets to filter, --extend to move --end)
├── consolidate_capred.py              merges cap_red/*.parquet → capital_reduction.parquet
├── detect_unpriced_actions.py         share drops no filing explains → unpriced_actions.parquet
├── download_exright.py                TWSE TWT49U (free, keyless) → exright_reference.parquet
├── vendor_event_audit.py              grades price_adj/ per event → vendor_event_audit.parquet
├── delisting_sign.py                  last close vs prior-year high → delisting_sign.parquet
├── adjust.py                          rebuilds a factor from exchange reference prices (the 54 holes)
├── adjusted_loader.py                 price_adj/ + the two above + ohlcv/ → adj_close_tr, adj_source
├── available_date.py                  fiscal period end + filing_deadlines.csv → available_date
├── test_assertions.py                 executable checks behind this file's claims
├── populations.json                   what each check last read, so a shrunk tree fails
├── download.log                       per-stock progress log
├── nohup.bg2005.out                   2005-2024 re-download runtime log (started 2026-04-27)
└── .token                             FinMind API token (chmod 600)
```

## File schemas

### `ohlcv/<stock_id>.parquet` — daily prices

One row per trading day (~5,300 rows in a full 2005-2026 series; ~3,410
of them inside the window).

| column | dtype | description |
|---|---|---|
| `date`             | str    | YYYY-MM-DD |
| `stock_id`         | str    | 4-digit ticker |
| `open/max/min/close` | float64 | TWD, **raw/unadjusted** — the cum-session close matches the exchange's own pre-event `before_price` on 99.84 % of the 18,276 除權息 events inside the window (99.87 % of the 7,543 since 2020), at the two decimals the exchange publishes. This is what says `ohlcv/` reflects nothing, which is why `price_adj/` exists; `test_assertions.py` re-derives it |
| `spread`           | float64 | close − prior close (TWD) |
| `Trading_Volume`   | int64  | shares traded |
| `Trading_money`    | int64  | **trading value in TWD** (used for FFI normalization) |
| `Trading_turnover` | int64  | number of trades |

### `instflow/<stock_id>.parquet` — institutional order flow

**Long format.** One row per (date, investor type) — ~5 rows per trading
day (~20,800 rows in a full 2005-2026 series).

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
carries the full reference-price step. The back-adjusted series is
`price_adj/` — FinMind's `TaiwanStockPriceAdj`, bought at the sponsor
tier — and `adjusted_loader.py` joins it onto the raw series, fills the
54 stocks it does not serve, and replaces its step on the one event where
it disagrees with the exchange in size rather than in a cent:

```python
from finmind_data.adjusted_loader import load_adjusted

df = load_adjusted("2330")   # raw OHLCV + tr_factor / adj_close_tr
                             #   + adj_source / adj_method / is_valid
```

**One convention, and it is total return.** Cash dividends come out
along with 無償配股, 現增 and 減資, so `adj_close_tr` measures what a
holder earned, not what the price did. There is no price-return variant
of the endpoint at any tier, and the exchange makes one hard to build:
TWSE/TPEx publish a single fused reference price per 除權息 event
covering cash and shares together, so recovering the price-only half
means splitting that number event by event. A study that needs the
price alone has no source here.

The factor is the primary output — any other price column adjusts the
same way (`adj_open_tr = open * tr_factor`) — and it is re-anchored to
1.0 on the last covered session, so the adjusted close there is the raw
close. The vendor anchors its own series to the latest session in
FinMind's database, which moves on every re-download; re-anchoring is
what makes a repeated download reproduce the same numbers rather than
merely the same returns.

**What the vendor computes**, and where it is wrong. Each 除權息 event
should contribute the exchange's own `before_price / after_price`, and
`vendor_event_audit.py` grades all 18,277 filed events against it —
18,087 of them sit between two adjacent covered sessions and can be
read. Both numbers come out of the same file and neither is a filter
that moved: `checkable` is the column that separates them, and the 190
it excludes are 174 events in the stocks the vendor serves nothing for
and 16 whose bracketing sessions sit more than ten days apart. Every
*rate* below is over the 18,087; every count of what was filed is over
the 18,277. The step matches to 1e-6 on 84.2 % and to 1e-3 on 99.5 % (p99
7.6e-4, max 3.0e-2). The residual is FinMind reaching the same number a
different way: it subtracts the *declared* distribution from the prior
close instead of reading the reference price, and the two land a whole
cent apart in the per-share amount. 3006's 2011-07-04 event is typical —
the exchange repriced 38.65 → 37.64 (息值 1.01) and the vendor removed
1.00. That difference is bounded per event, does not accumulate, and
lives only on the ex-date session.

One event is not a cent apart but wrong, and `adjusted_loader` replaces
the vendor's step with the exchange's on it. It is filed twice, so it
carries two defect labels:

| defect | n | what it is |
|---|---|---|
| `malformed_twin` | 1 | the real leg of 3454 on 2011-07-27, 84.20 → 79.07. The vendor removed 7.42 = 5.12 + 2.30, reading both filings as one distribution |
| `nonpositive_leg` | 1 | the other filing of the same event, reading before 0.00 / after −2.30 — not gradable itself, and the reason the first leg is wrong |

The patch moves the ex-date factor by 2.98 %, taking that session's
adjusted return from +4.19 % to +1.19 %. The defect is found by *shape* —
a date carrying a non-positive reference leg — so a re-download is graded
rather than matched against a list of stock ids.

**A second defect class exists and the window holds none of it.** A
現金增資 subscribed **above** the market raises the reference price, and on
six such events the vendor scaled the history the other way — `sign_flip`
in the audit's vocabulary. All six are dated between 2005-04-21 and
2008-09-16, which is before this package answers for anything, so the
class is a fact about the vendor rather than a rate in the panel: the
window's 14 upward reprices, 2011-09-15 through 2024-12-12, all carry the
exchange's own direction and none is flagged. Two consequences for
anyone extending the coverage backwards: a search for more of these can
be confined to pre-2009, and a defect rate measured on a 2005-2007
delisting sample cannot be extrapolated to the panel, because that sample
would sit entirely inside the defective era.

`vendor_event_audit.parquet` is the fixed record of all of this, one row
per filed event. A step found later at a `vendor`/`rebuilt` boundary is
answered by that file rather than re-derived from scratch;
`test_assertions.py` regenerates it and fails if the committed copy has
drifted.

**Two columns say which rows to trust**, and both need filtering, not
reading past:

```python
df = load_adjusted("2330")
df = df[df["is_valid"] & df["adj_close_tr"].notna()]   # then take returns
```

`is_valid` is "this row is a position a study could have held", and it
fails three ways. Two are the ends of the series: behind the last break
— a share cancellation no filing priced, or a multi-year trading gap
after which the ticker came back as a different listing (52 breaks in 50
stocks, 22,401 rows, 0.38 % of the panel) — and past the delisting date,
the 1,134 quotes in the four delisted names below. The third is one
session anywhere between them: the stock did not trade (125,055 rows in
1,141 stocks), so no level the panel carries was a price anyone could
transact at.

`invalid_reason` says which, because the flag is one column and the four
are not the same problem: `unpriced_cancellation` means a step is
missing from the chain, `series_break` means the rows behind belong to
another company, `post_delisting_emerging` means the price is right and
the exchange had ended the listing before it, `no_trade` means there was
nothing to buy. None of them means "this price is wrong". The vendor
marks none of them: 8101 stopped trading 2024-08-21 at 1.90, cancelled
80 % of its shares over a 90-day suspension no filing prices, and came
back on 2024-11-19 at 10.45 — and the vendor's series carries both
numbers at a factor step of exactly 1, leaving a +450 % return across the
gap (caveat 5).

The two segment reasons win where they overlap the third, so the 2,783
no-trade sessions a segment claims keep the segment's name — a row in a
history this series does not continue, or one printed after the listing
ended, would not have been holdable had it traded either. `adj_close_tr` was already NaN on all 128,442, so
the two-column filter above dropped them before this reason existed;
what changed is that `is_valid` alone now drops them too, and that every
False row in the panel's 5,883,919 carries a reason for being one.

**`adj_source` says where the row's factor came from**, and `adj_method`
which convention produced its ex-date steps. Split a panel on them
before comparing anything across the boundary:

| `adj_source` | `adj_method` | rows |
|---|---|---|
| `vendor` | `declared_dividend` | FinMind's series as served |
| `vendor_patched` | `declared_dividend` | behind the one replaced event (120 rows) |
| `vendor_carried` | `declared_dividend` | the first traded session, ahead of where the vendor series starts — factor carried from the adjacent session (492) |
| `rebuilt_factored` | `exchange_reference` | 37 of the 54 holes, with a factor chain (50,064 rows) |
| `rebuilt_noevent` | `none` | 17 of the 54, no corporate action in window — factor is 1.0 (11,441 rows) |
| `""` | `""` | no price: the stock did not trade, or nothing covers the session |

`vendor_patched` is a **span, not a session**. A factor anchored at the
present carries every step in the rows behind it, so replacing one
rescales that stock's history from the ex date back to its first
session: 3454's 2011-07-27 event carries the 120 sessions behind it, back
to the first one in the window. Flagging only the ex date would say one
session differs from FinMind's series when the whole span does.

The two rebuilt values are kept apart on purpose: the cumulative-product
path is the one with somewhere to go wrong, and separating it lets a
later check isolate it without re-deriving which stocks had events.

**There is no `raw_covered` column any more.** It used to say whether `ohlcv/`
served the date, and was False on 303 rows — the make-up sessions the raw tree
had no row for, reconstructed from the adjusted series, whose prices and volumes
were derived rather than read. `backfill_make_up_sessions.py` has since read all
1,941 missing sessions back from the endpoint that serves them, and the loader
now *refuses* to derive one rather than deriving it and flagging it, so the
column could no longer take its False value under any input. A boolean that
cannot vary is not provenance; the guard that raises is, and the flag was
dropped rather than kept as a constant nothing reads.

`adj_close_tr` is NaN where the raw `close` is 0 — FinMind's encoding
for a session the stock did not trade (**128,442 rows, 2.18 %, in 1,152
stocks**, and the same figure in `ohlcv/` as in the panel: the 93-row
difference the two used to show was the no-trade sessions the loader
reconstructed, and the raw tree now holds them). The vendor prices
126,027 of the ones `ohlcv/` holds anyway, at the last traded price, so
the zero that identifies them survives only in `ohlcv/`; filtering on
`adj_close_tr > 0` alone would keep every one of them, and so would
filtering on `is_valid` alone before `no_trade` existed.

### The vendor's survivorship hole, and the rebuild that fills it

`price_adj/` reaches 5,692,446 of the 5,755,477 traded sessions in
`ohlcv/` — 98.90 % — and the 63,031 it misses are not missing at
random. They split four ways: **61,505** in the 54 stocks with no adjusted
series at all, **0** past the end of a vendor series that stopped at a
delisting, **493** first sessions the vendor opens one day late on, and
**1,033** make-up sessions the raw endpoint serves and the adjusted product
does not. Only the first is a bias.

**50 of the 164 in-window universe delistings have raw prices
and no adjusted series at all** (60,371 sessions). They delisted
between 2012 and 2020, scattered rather than banked against either edge
of the window, which is the shape the 2026-08-17 delisting refresh
exposed: the hole was read as a pre-2015 artifact only because the
vendor's own table did not yet know about the later names. They are 50
of the 57 names `build_universe.py` carries as its survivorship overlay
— added precisely because FinMind's live `taiwan_stock_info` had dropped
them — and `TaiwanStockPriceAdj` drops them on the same registry.

Four more names sit in the same hole without being in-window exits.
1107, 2341, 2381 and 2396 delisted between 2007 and 2010 and went on
being quoted on 興櫃 into the window; the vendor's series for each ends
at its delisting, which is before `COVERAGE_START`, so inside the window
they have raw prices and no adjusted row to carry a factor from. That
makes them a hole rather than the ragged end of a covered series, and
the rebuild takes them on the same path as the 50: 54 stocks, 61,505
traded sessions in all.

113 downloaded adjusted files are empty inside the window: the 54 above,
and 59 that have no raw prices in it either — 37 delisted before it opens,
21 listed after it closes, and one is a zero-row file. Quoting the 99.99 % these
same files give once the 54 leave the denominator reports the coverage of
a panel the bias has already been removed from — the vendor's coverage is
98.90 %, and `available_stocks()` lists the 2,139 names it serves.

`load_adjusted` fills all 54 rather than returning a column of NaN a
panel build would drop. `adjust.py` rebuilds the factor from the
exchange's own per-event reference prices — `div_result/` and
`capital_reduction.parquet`, never `price_adj/` — which is why the hole
is recoverable at all: the reference prices are published per event and
do not depend on the registry that dropped the names. All 54 come back
priced across all 61,505 traded sessions, 37 with a factor chain and 17
with no corporate action in window at all. That last figure is checked
against two sources the factor path never reads: none of the 17 has a
declaration in `dividend/` or a row in `exright_reference.parquet`,
either — a distribution with no reference price behind it would leave the
factor flat across an event that happened, and `div_result/` and
`capital_reduction.parquet` are the two chains that decided it was flat
in the first place.

**The rebuild is validated where the vendor exists.** The gate set is
the 116 in-window delistings `price_adj/` *does* cover — same era, same
delisting situation — run through the identical code path. Across
203,655 daily adjusted returns the rebuild reproduces the vendor on
99.954 % to 1e-6 and 99.998 % to 1e-3; what is left is the declared-vs-
published cent above, on the ex-date session only.

`adj_covered` stays False across all 54 even though they now carry a
price, so the vendor's hole remains countable after it is filled — as a
column rather than frame metadata, because `DataFrame.attrs` survives
`pd.concat` only when every frame agrees. A panel of uniformly covered
stocks would keep an `adj_coverage` nobody needs, and one mixing covered
with uncovered stocks drops it silently; `merge` and `groupby` drop it
always. The warning would go missing in exactly the case it exists to
raise, so `df.attrs` is single-stock only.

Five of the 54 carry invalid traded sessions, and none of it is a defect
of the rebuild. Four are the pre-window exits above, invalid end to end
under `post_delisting_emerging` because every in-window session they have
is past their delisting date. The fifth is a break: code 4415's first
occupant traded 2005-01-03 to 2011-11-07, 台原藥 took the code over after
a 1,249-day gap and delisted 2019-12-16, and the earlier company's 192
in-window traded sessions come back `is_valid=False` with
`invalid_reason == "series_break"` rather than NaN, because they are
ordinary prices of a different issuer rather than unrecoverable ones —
and NaN could not have said which.

The share cancellations that used to claim sessions here reach nothing
now: 970 rows across 1207, 1462, 2544 and 2811, all four delisted between
2005 and 2007, so the 2011-01-25 window start drops them and the
survivorship overlay reinstates in-window delistings only — none is in
`universe.parquet` either. The behaviour is unchanged; the population
moved.

### The edge of the vendor series, and the edge that left with the window

The other 492 carried sessions are not whole stocks but one end of a
series the vendor serves. 493 stocks are short exactly one traded
session — their first, one per stock, verified as that and nothing else.
492 of them are carried and the 493rd is refused, below.

The window has **one** edge, not two. A vendor series that stops at a
delisting while `ohlcv/` keeps printing used to be the other, and inside
2011-01-25..2024-12-31 no such stretch exists: every name it applied to
delisted before the window opens, so the vendor covers none of its
in-window sessions and there is no adjacent covered factor to carry.
Those names are the four in the hole above, filled by the rebuild rather
than by a carry. The edge did not disappear because the vendor changed;
it stopped being an edge because the window no longer contains a covered
session next to it.

The head is filled, and it is not a splice. A back-adjustment factor
moves only on an ex date, so across a gap with no filing in it the
adjacent covered session's factor *is* the missing one — the same
number, not an interpolation, and the level is continuous by
construction. The condition is checked per row against every filed 除權息
and 減資 plus the share cancellations no filing explains, and a row whose
gap holds one is left NaN. It refuses exactly one: 4141's first print
sits 376 days before the vendor's first session, with a cancellation on
that session. Those rows are `adj_source == "vendor_carried"`.

What the head fill recovers is **492 first returns**, not 492 prices.
The price was never the loss — the session-1-to-session-2 return was,
and in a listing study that is the observation.

The quoted tails are still in the panel; they are rebuilt rather than
carried, and what they recover is evidence, not tradable history. 興櫃 is
a negotiated market: `open` is the previous session's average rather than
a trade, a quote depends on a recommending broker standing behind it, and
median volume across the four names runs at 3.0-49 % of each one's own
listed-era median. So those rows carry `is_valid=False` under
`invalid_reason == "post_delisting_emerging"`, which keeps a backtest out
of them automatically — 1,134 in-window sessions, and the flag reaches
nothing else. What they are good for is the **terminal value**: where a
delisted name converges over the months after it leaves the exchange is
a market observation, and the last exchange close is not one. A name
that left by merger does not go to 興櫃 at all, so the presence of a
tail is itself a weak signal on the delisting reason (caveat 8).

And `ohlcv/` itself is a zero-row file for one stock while 58 more hold
prices only outside the window; `load_adjusted` raises on all 59.

### The gap that runs the other way, and the 1,941 returns it cost

Every figure above counts sessions `ohlcv/` has and `price_adj/` does not. The
reverse difference used to be quoted as **303 sessions in 96 stocks** on 14
Saturdays, each a 補行交易日 worked to make up a holiday. That number is a set
difference between two local trees, so it can only see a session at least one
of them holds, and it was read as the size of the hole rather than as the part
of it the other tree could still reach.

`tape_universe.py` measures the same hole against the vendor instead — one
date-keyed request per session, so the reference is what the endpoint serves
rather than what either tree stored. The hole is **1,941 rows in 507 stocks**,
on 15 dates: the same 14 Saturdays, carrying 1,940 of the rows, and a single
no-trade row for 2910 on an ordinary Wednesday, 2021-01-20. Of them **303 had a
`price_adj/` row** — exactly the set the loader could reconstruct, which is why
the count reproduced — and **1,638 were in neither tree**, so nothing reported
them and no flag marked them.

**The cost is not the missing rows.** A gap in the calendar makes the *next*
session's return span two sessions rather than one, so the 1,940 absent
Saturdays were 1,940 overstated returns, clustered on 14 holiday-adjacent dates
rather than scattered, which is the shape a study reads as an effect. The coverage
decomposition above cannot see it: it counts rows, and the damage is in the
gaps between them.

**The endpoint serves them, so the trees were behind a backfill.** A `data_id`
request for 1338 on 2012-02-04 returns the row `ohlcv/1338.parquet` lacked;
the same holds for every one checked. That is the behaviour
`TaiwanStockDelisting` showed between the 315-row and 723-row pulls — the
vendor fills history in after the fact, and a tree downloaded once does not
follow. `backfill_make_up_sessions.py` reads the 15 dates back and inserts
them, 1,311 traded sessions and 630 zero-volume rows, and the insert is
additive: 507 files, 1,941 rows added, not one pre-existing row altered.

The recovered rows are the vendor's own, not a reconstruction. `spread` is
present on all 1,941 where the arithmetic recovery left it NaN, and the volume
is the raw endpoint's answer rather than the adjusted endpoint's — the two
disagree on 1,943 rows across 12 of the 14 Saturdays, never with the vendor's
adjusted number the smaller, and that disagreement no longer enters the tree.

**What the repair costs, stated plainly.** Of the 1,941 restored rows, only
**303 have an adjusted counterpart** — 210 traded and 93 no-trade, exactly the
set the loader used to reconstruct. The other 1,638 are sessions the vendor's
*adjusted* product does not cover at all, so they enter the panel with
`adj_close_tr` NaN and `adj_covered` False: **1,101 of them traded** (1,067 in
universe names) and 537 did not. That is a real change in what a study meets.
Before the repair those sessions were absent, so a return computed across one
of them silently spanned two sessions and looked like an ordinary observation;
after it, the same span is an explicit NaN. The raw calendar is now correct and
the adjusted series is now visibly incomplete where the vendor is, which is the
trade this makes: one silently wrong return exchanged for two missing ones. The
adjusted gap cannot be closed from the endpoint — it does not serve those rows.

**The reconstruction is retired and a guard stands where it was.**
`_recover_make_up_sessions` is now `_require_raw_covers_vendor`, which raises
instead of deriving a row: the trees fell behind a vendor backfill once and
nothing in the package noticed, so the answer to it happening again is to stop
and repair the tree, not to paper over the gap on every load. It is the cheap
per-load half of the check — it sees only what `price_adj/` exposes, and the
1,638 rows neither tree held were invisible to it by construction. The full
measurement is `test_taiwan_no_session_the_tape_holds_is_missing`, which pins
the condition from both directions against the tape: no session the tape holds
is absent from the interior of a raw series, across 5,906,434 vendor-served
ticker-days, and `price_adj/` carries none `ohlcv/` lacks.

#### Why the adjusted tree was not repaired the same way

A raw print carries no factor. A back-adjusted close is anchored at the
present, so a row fetched today carries every event since the file was written
and a row already in the file does not. Measured across four dates the trees
already cover, `ohlcv/` reproduces the endpoint **exactly** on every one of
~1,500 closes, while `price_adj/` differs on **38 stocks by up to 32 %** —
re-anchorings, not errors, and inserting one into a file at the older anchor
would splice two vintages inside a single series.

So the adjusted insert is gated per stock against the dates its file already
holds, and it refuses **44 rows in 12 stocks** — 1597, 2066, 2496, 3147, 4162,
4432, 5206, 5222, 6432, 6574, 6691, 8077 — whose committed values disagree
with the endpoint. Those need the whole file re-downloaded rather than a row
added, and that is left undone: re-anchoring them would move every adjusted
value they carry and invalidate the `vendor_event_audit.parquet` rows over
them. Nothing else is missing from `price_adj/`; the 1,649 sessions the tape
holds and it does not are sessions the adjusted endpoint does not serve for
those stocks at all, and the 506 rows before a file's first session are the
documented `vendor_carried` edge.

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
- **Datasets:** all 13 per-stock endpoints listed in `download.py`
  (`TaiwanStockPrice`, `TaiwanStockPriceAdj`,
  `TaiwanStockInstitutionalInvestorsBuySell`,
  `TaiwanStockShareholding`, `TaiwanStockPER`,
  `TaiwanStockMarginPurchaseShortSale`, `TaiwanStockMonthRevenue`,
  `TaiwanStockFinancialStatements`, `TaiwanStockBalanceSheet`,
  `TaiwanStockCashFlowsStatement`, `TaiwanStockDividend`,
  `TaiwanStockSecuritiesLending`,
  `TaiwanStockCapitalReductionReferencePrice`)
- **Upstream origin:** TWSE daily disclosures and TPEx daily disclosures
  (Taiwan's "three major institutional investors" reporting regime)
- **Original 2015-2024 build:** 2026-04-20 to 2026-04-26 via
  `download.py`. Superseded by the build below and deleted 2026-08-18.
- **Current 2005-2024 build:** started 2026-04-27 via `download.py`
  with default `--start 2005-01-01`. Total: 2,154 stocks × 12 datasets
  = ~25,800 requests at ~6.5 s/req under FinMind's 600/hr free-tier
  cap → ~43 hours wall-clock. Resumable (skip-existing). Background
  log: `nohup.bg2005.out`; per-stock log: `download.log`.
- **Verification (2015-2024 build):** 2,101 freshly downloaded + 10
  pilot = 2,111 stocks, 0 failures.
- **Adjusted prices:** 2026-08-16, after the account moved to the
  sponsor tier. 2,154 requests at `--sleep 0.7` under the 6000/hr
  quota, ~40 min, 0 failures. Log: `nohup.price_adj.out`.

## Known gaps / caveats

1. **Individual retail flow** is not directly reported. Derive from total
   volume minus institutional volume, or use it as a residual sign.
2. **Partial-window stocks**: IPOs after 2011-01-25 or delistings before
   2024 will have shorter series. Always filter by `date` after concat.
3. **ETFs, DRs, warrants** are intentionally excluded. 11 of the
   in-window delistings are `00xx` ETFs or `91xx` depositary receipts and
   are not present (see `delisted_universe.parquet` vs `universe.parquet`
   for the diff).
4. **Price adjustment**: `TaiwanStockPrice` closes are **raw** — they reflect
   nothing, not splits and not capital reductions. `price_adj/` carries the
   adjusted series, in the total-return convention only; there is no
   price-return variant to buy. It also serves nothing at all for 54 stocks —
   50 of the 164 in-window delistings and four names quoted into the window
   after a pre-window exit — is wrong on one event, and stops one traded session
   short at the start of the series; `load_adjusted` rebuilds the first,
   patches the second and carries the third, marking all of them in
   `adj_source`. Read `price_adj/` directly and you get none of it. See
   **Adjusted prices**.
5. **減資 events start on 2011-01-25**, six years after the prices do. This is
   the *exchange's* limit, not FinMind's and not the download's: TWSE's own
   TWTAUU report refuses any start date before ROC 100/1/1 and its first row is
   the same 2011-01-25, so no tier and no mirror reaches further back and
   nothing reconstructs the step — including FinMind, whose adjusted series
   carries such a reduction through at a factor step of exactly 1.
   `detect_unpriced_actions.py` finds the cancellations from
   `shares/NumberOfSharesIssued` instead (92.6 % precision, 92.0 % recall where
   the filed events can score it) and `adjusted_loader.py` marks the history
   behind each one `is_valid=False`. The uncovered years are the reason the
   window opens where it does, so what is left inside it is the cancellations no
   filing explains at all: of the 616 the share count shows, 574 match a filed
   減資 and 42 in 40 stocks do not. Run it after `consolidate_capred.py`;
   `load_adjusted` raises if its output is missing rather than serving the
   vendor series as if the window were clean.
6. **A handful of raw prices are wrong**, and no adjustment can repair a bad
   input: stale near-zero quotes, sporadic pre-listing 興櫃 sessions
   (2007-03-03 and 2007-04-14 carry clusters of them, all TPEx, both outside
   the window and so absent from the panel), and at least one corrupted row — 8454 on 2014-09-09 reports `open` 241.04 and `max`
   242.49 against `min` = `close` = 3.43, which reads as −98.6 % followed by
   +6,853 %. `is_valid` does not cover these; they are bad prices, not broken
   series.
7. **TWSE stopped publishing the 除權息 split in 2009.** `exright_reference.parquet`
   carries 權值 and 息值 as separate columns for 2005-2008 and only their sum
   `權值+息值` from 2009 on, alongside a `權/息` label. The label still settles a
   pure 息 or 權 event, so only a fused 權息 after 2008 is left without a cash
   leg. There is no OTC counterpart at all: TPEX's `exDailyQ_result.php` has the
   identical field list but serves a rolling few-day window and ignores every
   date parameter, and its `preAnnounce` table likewise returns only current
   forward announcements. Both limits are the publisher's, not the download's.
8. **No delisting reason, and no terminal value.** `delisted_universe.parquet`
   carries `date`, `stock_id`, `stock_name` and a derived `year` — that is the
   whole of `TaiwanStockDelisting`. Nothing separates a bankruptcy from a
   merger, a voluntary buyout or a move to another venue, and no field records
   what a holder received when trading stopped. Treating the last observed
   price as the terminal value therefore books −100 % where a merger paid a
   premium, and a premium where the shell was worthless; which error you make
   is decided by the reason the table omits. This is delisting-return bias, and
   it is **not** the survivorship bias the universe overlay fixes — a panel can
   hold every delisted name and still misprice each one's final return. The
   reasons live in 公開資訊觀測站 (`mops.twse.com.tw`) filings, which no FinMind
   endpoint mirrors. Those filings are pulled — `mops_filings.py`, and the block
   at the end of this caveat says how far they reach — and they settle the
   *reason* for 146 of the 164. They do not settle the *amount*: 說明 is served
   only for a company still registered as 公開發行, which 14 are, so what a
   holder received is still read one filing at a time and a delisting return
   that substitutes the last close is still an assumption wearing a number.

    The obvious cheaper source is empty, and it is worth saying so because it is
    the first place anyone looks. TWSE's own 終止上市公司 table
    (`www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?type=csv`) returns
    264 rows over 2001-2026 under exactly three headers — 終止上市日期, 公司名稱,
    上市編號 — which is date, name and code, the same three fields
    `TaiwanStockDelisting` already carries. Joining it adds nothing. TPEx's
    終止櫃檯買賣 list does filter by reason, but reaches back only to 2021 — 46
    of the 164 in-window exits, and only the TPEx names among them. Both probed
    2026-08-17. The reason is published per company
    in a filing, never in a table, and that is what makes it expensive.

    The 1,134 post-delisting sessions are the one piece of direct evidence
    the package does hold against this. Four delisted names — 1107, 2341, 2381
    and 2396 — go on being quoted for 367 to 1,151 sessions after leaving the
    exchange, 67 to 415 of them inside the window, and where each converges over
    that stretch is a market observation of what the shell was worth, which the
    last exchange close is not. It is also a weak signal on the reason, since a
    name that left by merger does not go to 興櫃 at all. Four quoted tails is a
    sample, not a fix; MOPS is where the fix came from, and
    the part of it still owed is the consideration, not the sign.

    All four delisted between 2007 and 2010, so the exit itself sits before the
    window even though the quotes reach into it — which is also why the vendor
    serves no adjusted row for them and the rebuild has to. They are evidence
    about the mechanism — that a shell goes on being priced, and where it
    settles — and not a check on any name in the frame below.

    None of the four invites the opposite reading. Post-delisting median volume
    runs at 3.0 % to 49 % of each name's own listed-era median, which is what a
    negotiated market looks like rather than a demotion to another board, and
    all four stop for good by 2012-11. No ticker in the table outlives the
    panel: the 2026-08-17 refresh retracted the one board transfer the table
    used to carry and both reused codes, which is why the assertion over this
    now reads two empty lists rather than three names.

    The reason the table omits is partly legible in the price path, and
    `delisting_sign.py` reads it there. An acquisition is announced, jumps to a
    premium and converges flat to the consideration, stopping at its own high; a
    failure collapses. On the ratio of the last traded close to the highest
    close of the preceding year, **29 of the 164 market exits are
    failure-shaped, 98 payout-shaped, and 37 sit between the two cuts**.
    Balance-sheet equity would be the obvious second opinion and is available
    for all but nine: the vendor's statement history starts 2012-03-31, and nine
    of the 164 delisted before it.

    The two cuts were fixed before a single reason was looked up, which is the
    only thing that makes an accuracy measured against them worth reading, and
    `delisting_labels.csv` plus the assertion over it keep that true — the draw
    is a function of the cuts, so a cut edited after the labels arrive changes
    which names were sampled and fails the suite. 41 names in the frame carry a
    label read off exchange announcements and contemporary reporting: 33 drawn
    stratified across the cuts and the eras, 8 more that carried no
    corroborating feature and were resolved by hand rather than classified. The
    file holds 27 further labels marked `prior` — names bought against the frame
    the package answered about before 2026-08-17, kept as the record of what was
    read and excluded from every rate below, since they were not drawn from the
    population those rates are about.

    Scored on the names the cuts actually decide, the shape is right on **98.7 %
    of the 126** carrying a verdict. That is an estimate from 15 labelled
    verdicts weighted up by stratum, not 126 verified ones, and it turns on a
    single miss: **1613 台一** stopped 25 % below its peak, which reads as an
    acquisition, and was in fact thrown off the exchange for failing to file its
    China subsidiary's accounts. A failure that never panicked the tape is the
    error this method makes, and forced delistings for non-filing are where to
    expect it.

    A single cut inside the band was registered on the frame the package
    answered about before the refresh, on the reading that the truth turns over
    near a drawdown of 0.50. On the corrected frame that reading has weakened
    and the alternative registered beside it has overtaken it. Of the 28
    labelled names between the cuts, 8 of the 13 below 0.50 are failures and 12
    of the 15 above are payouts — 20 right out of 28 — while the free rule that
    reads the halt instead of the price is right 25 times on the same 28. The
    price path is not doing the work the registered cut assumed, and registering
    the alternative at the same time is what made that visible rather than
    arguable.

    `delisting_band.csv` records what 0.50 calls each of the **9 band names that
    were never looked up**, committed while all 9 were blank, along with the
    pass mark and the halt rule it has to beat. The 9 are the entire test set —
    the band does not grow — and their labels come free with any consideration
    pulled, since an announcement names its own reason. But the gate can no
    longer be read on them: the smallest sample at which anything short of a
    perfect score clears the base rate is 11, and 9 names are held out, so the
    threshold is undefined however many of the 9 get labelled. The 8420
    correction is what took that minimum from 10 to 11 — it raised the band's
    majority class from 16 payouts in 28 to 17, so the free reading a rule has
    to beat went from 0.571 to 0.607 and the gate moved further out of reach. That is reported
    rather than repaired. Lowering the bar to fit nine names is the move the
    registration exists to stop, and the way back is a larger held-out set.
    Until then the cuts leave the band undecided at 37 names, ~24 of them
    payouts.

    The payout's **size** is a separate gap, and smaller than it looked. A name
    classified as one books its last traded close, and against the 7 deals whose
    consideration is recorded in a form needing no ratio convention, that
    substitute is wrong in one direction every time — it understates. By a
    median **+0.9 %** on the five cash deals (+0.47 % to +1.34 %) and **+11.2 %**
    on the two share swaps (+9.9 % and +12.5 %). The split is the usable part:
    cash lands the last close to within 1.5 %, so those names never need a filing
    pulled at all. Seven deals is few and the direction is what survives that; it
    is a downward bias on a portfolio rather than noise that averages out. Two of
    the original six delisted before the window starts and left the frame with
    it; they stay in `delisting_consideration.csv` as the record of what was
    read. The sample can still be grown without another afternoon of searching:
    the re-registered draw added payout labels whose `source` already states a
    price or a ratio, and transcribing them would take the swap convention to
    roughly n=15 — which is now the only way it moves, since the tender table
    below reaches cash deals alone.

    Where the deals sit was itself read as a finding, and the corrected frame
    refutes it. On the 18 payouts labelled before the refresh, all 9 whose form
    was stated inside the band were share exchanges and no cash deal had ever
    been labelled there, which invited the reading that a conversion's discount
    is what drags a payout into the band — the mechanism being that a cash offer
    at a premium stops near its own high and should land above the upper cut.
    The re-registered draw takes the stated forms to **26 labelled payouts, 17
    share exchanges and 9 cash**, and four of the nine cash deals sit *inside*
    the band: 4965, 8913, 6211 and 8266, at drawdowns of 0.56 to 0.63. The
    mechanism is the part that was wrong. Drawdown is measured against the
    highest close of the *preceding year*, so a cash offer at a premium to the
    recent price is routinely far below the price a year earlier — 商店街市集 was
    bought in at NT$44 after falling most of the way there from its own high,
    and the offer was a premium while the drawdown was 0.56. On the 16 stated
    forms now in the band, 12 exchanges against a base rate of 17 of 26 is what
    chance gives **0.234** of the time (Fisher exact, two-sided). What survives
    is the narrower point the comparison was good for: one of the two swaps
    measured is a band name, so the +11 % is measured on a mix rather than on
    classifier-confirmed payouts alone.

    The obvious next move is to let the gap between the last trade and the formal
    date price that bias, on the reading that the last close goes *stale*: a
    swap's value would go on moving with the acquirer while the target no longer
    trades, and the gap would then estimate the error on a name whose acquirer
    was never identified. It does not work, and the reason is worth recording so
    nobody buys it twice. The gap barely varies — 13 and 14 days across the two
    swaps against residuals of +9.9 % and +12.5 %, and **87 % of the 98
    payout-shaped names sit at 7-14 days** — because it is the settlement
    calendar rather than anything about the deal. And the mechanism cannot have
    run: the successor of every swap measured first trades on the day the target
    leaves, **zero sessions of overlap**, so there was no acquirer price to drift
    against. Both are holding-company conversions, which follows from the
    selection rather than being a coincidence — a swap stated 1:1 or as a flat
    share count is what a conversion looks like, while a third-party acquisition
    for stock is the case carrying the odd ratio excluded here. Across the seven
    the rank correlation with the gap is 0.51, and that is the cash deals
    settling in a day against the swaps' 13 and 14: the deal form reported under
    the gap's name. It was 0.80 on four deals and fell when three same-day cash
    settlements were added, which is what a correlation carried by two clusters
    does when one of them grows. The staleness account is untested rather than
    refuted, and these deals cannot test it.

    What survives that is the direction, and not the mechanism. Why a
    conversion's last close sits below what was paid is open: a liquidity
    discount on a name whose exit is already fixed, terms revised upward between
    announcement and effect, or two deals falling one way. Nothing in this
    package separates them at n=2, and none of the three is assumed anywhere in
    the code. Use the **+11 %** as a measured direction, not as a correction
    with a reason behind it — a correction would have to know which of the three
    it was undoing.

    So `terminal_value()` books on four bases, cut so each names a different
    piece of work. **`failed`** is zero. **`consideration`** is what was actually
    paid, for the 7 recorded, a swap priced on the panel at the delisting date.
    **`substituted`** is the last close standing in for a consideration nobody
    has looked up, carrying the bias above, and one filing closes each. It is
    the count that falls when a consideration is recorded, and the only one:
    nothing else moves.
    **`undecided`** is NaN and is the only NaN — the sign is what the band does
    not know, and a number there would be a guess at the direction rather than
    at the size. That distinction is what the column is for: the last two are
    both missing something, and it is not the same something, so a study that
    meets one has to pull a filing while a study that meets the other has to
    resolve the band or drop the name. Either way the count falls out of running
    the study instead of being estimated ahead of it.

    A hand-read filing outranks a price shape wherever one exists, so the
    labels settle the sign and the cuts fill the rest. That empties 28 of the 37
    band names, leaving exactly the **9** the single cut is registered against,
    and it overturns one verdict outside the band — 1613 books zero rather than
    its last close. The 98.7 % above is unchanged by this and should be: it is a
    fact about the cuts, and booking the value a label already settled does not
    make the cuts better. The counts a study meets are **41 `failed`, 7
    `consideration`, 107 `substituted`, 9 `undecided`**, and they are asserted
    rather than quoted: the previous pair of them was a name apart from what the
    code returned, and survived because the four numbers were only ever printed
    in a check's message and never compared to anything.

    **The filings are pulled, and this is how far they reach.**
    `mops_filings.py` collects 公開資訊觀測站 重大訊息 for every one of the 164,
    over the delisting ROC year and the two before it — **19,949 announcements**,
    the thinnest name carrying 31 and the median 103. Two hosts answer and they
    answer differently. `mopsov.twse.com.tw` serves 14 and refuses 150, 144 with
    「公開發行公司不繼續公開發行！」and 6 with 「上市公司已下市！」. The 2025 backend
    at `mops.twse.com.tw/mops/api` serves the 主旨 for all 164, which is why it is
    the host this package uses. Neither serves the 說明 for a company that has
    deregistered: the gate is on the company's registration today rather than on
    the filing, it does not move with `marketKind`, and it is the same on both
    hosts (probed 2026-08-24). So `mops_detail/` holds 2,555 filing bodies for the 14
    that stayed 公開發行公司, `mops_detail_refusals.csv` names the 150 that did
    not, and the reason for those is read off subject lines. A pull that reported
    only the 14 would be reporting the host's registration policy as a coverage
    figure.

    **What the subjects decide.** `mops_reason.py` anchors on the filing that
    announces the exit — the 終止上市/終止櫃檯買賣 notice nearest the delisting
    date, with bond notices excluded, since a company's convertible bond delists
    under almost the same sentence and 5346's would otherwise anchor the stock
    930 days early. An anchor is found for **134** of the 164, a median 40 days
    ahead of the exit and none earlier than 245, so the 540-day window the module
    reads is not binding on any name. Where the anchor names a mechanism it
    decides; where it does not, the window's subjects are counted; where the two
    sides tie, the answer is `unknown` and stays that way. The frame comes out
    **110 merger, 36 distress, 18 unknown**.

    Both marker sets are specified positively, and neither started that way. In
    Taiwanese accounting 合併 means *consolidated*: 合併負債, 合併現金流量表,
    合併及個體財務報告 and 合併自結獲利 are routine quarterly filings, and matching
    the bare word marked 24 subjects across 12 of the 116 unlabelled names as
    merger evidence. 淨值 alone is the monthly 每股淨值 disclosure and 逾期 alone
    the 逾期應收帳款 ageing table, both of which a watch-listed company files
    whether or not it is failing. Subtracting such phrases one at a time leaves
    whichever phrase was not thought of, so 合併 now counts only against a
    merger-specific word and 淨值 only against a negative one. 解散 is not a
    distress marker at all — a merger dissolves the company it absorbs.

    **Against the price shape.** The shape left **37** names undecided; the
    filings decide **30** of them, 19 as payouts and 11 as failures, and 7 stay
    unknown. On the 127 the shape did decide, the filings agree on 112, are
    silent on 11, and overturn **4** — all four in the same direction, a payout
    on the tape that was a removal in the filings. One is **1613 台一**, the miss
    this caveat names, recovered here without its label. Two more, **5305 敦南**
    and **8497 格威傳媒**, anchor on 「依證券交易所營業細則第五十三條之十七公告」,
    the provision under which a suspended company is delisted outright. The
    fourth, **3562 頂晶科技**, stopped trading at its own peak — a drawdown of
    1.00 — under 43 in-window notices of 關務署 penalties and 假扣押 seizures. So
    the error mode this caveat describes is not one name; it is four in 127, and
    all four are failures that never panicked the tape.

    **One asymmetry is left in, deliberately.** 營業細則第五十三條之十七 is the
    TWSE provision for delisting a suspended company and is a distress marker
    here; 證券商營業處所買賣有價證券業務規則, the TPEx notice that does the same
    job, is not. Adding it would move 6 names, 4 of which carry hand labels —
    which is to say it would be a second recalibration chosen after seeing what
    the first one scored, and the score would stop being a measurement. It is
    recorded as a gap rather than closed, and closing it needs labels this frame
    has not spent.

    **What it does not close.** The reason is not the amount. 說明 is refused for
    150 of the 164, so the consideration a holder actually received is still
    read one filing at a time. What changed is the sign: the band the single cut
    was registered against is no longer the only way to settle 30 of its 37
    names.

    **One table is not behind that gate, and it settles three of them.**
    公開收購申報資料彙總表 is filed by the *offeror* and served by period rather
    than by company, so a deregistered target has nothing to gate: 2325 矽品 and
    4180 安成藥業 both answer where their own 說明 does not (probed 2026-08-25).
    `tender_offers.py` takes the whole of it in one request — **89 offers** from
    ROC 105/11 (2016-11), the floor the query form states, each with the
    per-share 收購對價 in words, who was buying, and how much they got.
    **Fifteen** were made on a name in this frame.

    Three of those fifteen are booked as the consideration, and the rule that
    picks them is a date rather than a judgement. Taiwan's going-private order is
    to terminate the listing first and buy out whoever is left after, and
    公開收購管理辦法 §18 caps an offer at 50 days — so 4762 三汰-KY, 4965 商店街 and
    5304 鼎創達 each open their offer *on* the delisting date and close 49 days
    later, and nothing later can have been their exit because there was no market
    left for it to precede. The column the offeror files,
    被收購公司於收購後是否終止上市, does not decide this and is not used: it reads 是
    for two of the three and 不適用 for the third on identical facts.

    The other twelve stay out, and eight of them are the reason the amount is
    still open. Those were the first step of a two-step deal — a tender, then a
    股份轉換 or 合併 that ended the listing between 99 and 648 days later — and
    what a holder who did *not* tender received is the squeeze-out's price, which
    this table does not carry. Their tender prices sit from **−5.8 %** (3144
    新揚科) to **+11.1 %** (5820 日盛金) against the last close, so assuming the two
    steps priced alike would import a spread wider than the bias being measured.
    The remaining four are offers the table itself says did not end the listing:
    2823 中壽 was tendered twice, at NT$35 and NT$23.6, and left by a 股份轉換
    four years after the first.

    Where the two sources meet they agree. 4965's hand label already read
    「PChome bought in minorities at NT$44/share」 and the exchange's table says
    每股新台幣 44 元 — the same number from a filing read by hand and from a
    summary filed by the buyer. The other two are new: 4762's label recorded the
    tender and not its price, and 5304 carries no label at all.

    One label did not survive the filings, and is corrected here.
    `delisting_labels.csv` read 8420 明揚 as "suspended 6 months, compulsory
    termination". Its filings record the opposite: a one-day halt on 113/04/15
    for a press conference, trading resumed the next session, and on that same
    day two board resolutions — a 股份轉換 with 明安國際, and a 終止上櫃及停止公開
    發行 case put to the shareholders' meeting. The swap's base date moved twice
    and settled on 113/11/29; TPEx approved termination on exactly that date and
    金管會 the end of 公開發行 on it too. The frame's own `suspension_days` for
    the name is 9, not six months, a contradiction internal to the sheet and
    readable without any filing. The label is now `merger`. `form` stays blank:
    no subject states what 明安 paid, and 股份轉換 permits shares, cash or other
    property alike, so reading a form in would invent the fact that column
    exists to count. The correction leaves the 98.7 %, its miss list and the
    verdict count untouched, since a band name carries no verdict to score. It
    moves three other things, and all three in the same direction: the band's
    payout estimate from ~22 to ~24, the free reading a rule inside the band has
    to beat from 0.571 to 0.607, and with it the smallest readable held-out
    sample from 10 names to 11 — against the 9 that exist. A label correction
    that made the registered gate easier would be worth distrusting; this one
    put it further out of reach.

    **What the subject rule scores, and why that is not an independent number.**
    On the 42 names carrying both a hand label and a decided reason, the rule
    now agrees with all 42. It is worth exactly what its provenance allows: the
    rule parted from the labels on 8420, that parting is what sent the filings
    to be read, and the label rather than the rule was the side that moved. The
    number with provenance is **41 of 42 against the sheet as drawn**, followed
    by a corrected sheet that no longer disagrees — not a rule that scores
    perfectly. The other 41 were agreed before anyone went looking.
9. **Fundamentals are dated by fiscal period end, not by announcement.**
   `fin_is/`, `fin_bs/` and `fin_cf/` key on `date` = 2011-03-31, 2011-06-30, …
   — the quarter that closed, not the day the filing became public — and carry
   no column for the latter. Joining them to prices on `date` hands a trader
   figures weeks before they existed, which is look-ahead bias, not
   survivorship, and it reaches every fundamental signal built here.
   `month_rev/` has a `create_time` field that would carry the disclosure
   stamp, and for this window it does not — not because the column is
   meaningless, but because every value it holds falls outside the window.
   941 of the 43,779 rows in the first 200 files carry one, in 177 stocks, and
   they are two different things on either side. On the 2005-2010 backfill the
   stamp post-dates its own revenue month by 5,982 to 7,808 days, which is the
   vendor's ingest time for rows it rewrote in 2026 rather than a release date;
   on the 2026-03 to 2026-07 rows the lag is 1 to 51 days with a median of 10,
   which is what a release date looks like under Taiwan's 10th-of-the-month
   revenue deadline. **Not one stamped row is inside 2011-01-25..2024-12-31**,
   so the look-ahead limit here is a fact about the window rather than about the
   column — and it will not lift by the vendor stamping more, because the
   window's revenue months were ingested years after the fact and only what the
   vendor publishes now carries a release date. The other 42,838 rows are
   blank. `dividend/` is the exception that
   shows what the others lack: it carries `AnnouncementDate` and
   `AnnouncementTime`, so its events align point-in-time as delivered.

    `available_date.py` is the in-package correction, and it answers in two
    ways. The first is a **bound** rather than a date — the statutory filing
    deadline, i.e. the latest day by which the figure had to be public:

    ```python
    from finmind_data.available_date import with_available_date

    fin = with_available_date(pd.read_parquet(".../fin_is/2330.parquet"))
    rev = with_available_date(pd.read_parquet(".../month_rev/2330.parquet"),
                              kind="monthly_revenue")
    ```

    `date` is never overwritten — the fiscal period and the tradeable day are
    two separate facts — and `extra_days` shifts the bound as a research
    parameter, because whether a signal survives being read a fortnight later
    is a property of the signal worth measuring.

    The deadlines live in `filing_deadlines.csv`, one cited row per
    (`rule_type`, era, `entity_class`), because **the window spans a regime
    change**: the 2010-06-02 amendment to 證券交易法 §36 took effect
    自一百零一年一月一日 (2012-01-01) and cut the annual report from four months
    to three and the half-year report from a 75-day consolidated back-stop to
    45 days. FY2010 resolves to 2011-04-30 and FY2011 to 2012-03-31; H1 2011 to
    2011-09-13 and H1 2012 to 2012-08-14. A single constant is wrong for the
    window's first eleven months. Pre-2012 the quarterly deadlines used are the
    *consolidated* back-stops (45 and 75 days) rather than the parent-only one
    month and two months, because `fin_is/` carries consolidated line items and
    the back-stop is both the binding and the later date.

    `month_rev.date` is already the first of the month **after** the revenue
    month — 2011-02-01 carries `revenue_month` 1 of 2011, on all 281,009 rows
    — so its deadline is nine days on, not a month and nine.

    Two ways the bound stays loose, both deliberate. Shortened deadlines are
    not applied: a listed company with paid-in capital of NT$10bn or more files
    its annual report within 75 days from the FY2022 accounts, and
    financial-sector issuers file earlier still, but every such rule *shortens*
    the deadline, so the general one stays a valid upper bound and using it
    costs power rather than correctness (`entity_class` carries one value,
    `all`, so a sourced row can be added as data). That every variant shortens
    holds because `universe.parquet` is 上市/上櫃 only — the longer deadline an
    unlisted public company gets and the pre-2012 quarterly exemption for 興櫃
    companies reach nothing here, and a widened universe would need its own
    rows first. And a **late filer is not covered** — the deadline is what the
    law required, not what the company did, and a company that filed late, or
    one granted a 不可抗力 extension, published after the date computed here.
    Closing that needs the announcement dates, and the block below is where
    they were pulled from — not 公開資訊觀測站, which serves no such table, but
    TWSE's document server, which stamps every filed report with the second it
    was uploaded.

    **The announcement dates are pulled, and they close the one direction the
    deadline cannot bound.** `filing_dates.py` collects TWSE's document server —
    `doc.twse.com.tw/server-java/t57sb01`, which stamps every filed report with
    its 上傳日期 to the second — for all **2,230** companies that carry a
    statement tree: **255,795 documents**, consolidated to **163,991**
    company-quarters in `filing_dates.parquet`, one row per period with the
    earliest Chinese report that made it public. The server is not 公開資訊觀測站
    and carries none of its registration gate, so it answers for delisted and
    deregistered names alike — 158 of the 164 in-window delistings are dated
    here. A blank `year` returns a company's whole history, so this is one
    request per company rather than one per quarter.

    Of the **93,527** company-quarters inside the window, **6,138 — 6.56 %,
    across 1,421 companies — were published after the deadline this package
    computes**, a median of 15 days late, 234 at the 90th percentile and 1,665
    at the worst. That is the bias caveat 9 names, now measured rather than
    asserted: one company-quarter in fifteen, joined on the deadline, hands a
    trader a figure that did not yet exist. Where the deadline does hold it is
    tight — the on-time filings land a median of 3 days ahead of it — so it
    remains a good bound and a bad date.

    **`observed_date` is how a study joins on it.** Given a `stock_id` and the
    period end it returns the day that quarter's figures became tradable, and
    `with_observed_date` puts the column beside `date` the way
    `with_available_date` does:

    ```python
    from finmind_data.available_date import with_observed_date

    fin = with_observed_date(pd.read_parquet(".../fin_is/2330.parquet"))
    ```

    It is a **roll, not a truncation**, and that is where most of the exposure
    turns out to sit. TWSE's regular session closes at 13:30 and **74.9 %** of
    reports are uploaded after it, so a report filed on its deadline at 17:00
    cannot be acted on until the next session. Counting that, **13,710 —
    14.66 %** — of the window's company-quarters could not be traded on by the
    deadline this package computes, against the 6,138 that were filed after it.
    More than double, on the same frame and the same deadline, and 2330 is the
    case in miniature: it filed after its deadline exactly **once** in 56
    in-window quarters and is still a session late on **14** of them.

    **19 quarters come back `NaT`, and are left there.** Of the 94,772 in-window
    company-quarters `fin_is` holds, 94,753 carry an observed date. The 19 that
    do not fall over 18 companies, and 15 of them sit outside the span the
    document server holds for their company — an annual filed before the
    company listed or after it stopped filing, which the vendor kept and the
    server never carried; the remaining four are absent from inside a span the
    server does hold. They are not backfilled with the deadline. Substituting
    the bound there would put back exactly the look-ahead the column exists to
    remove, and it would be invisible while doing it, because the column would
    be full and the rows would trade — a `NaT` drops them from the join
    instead. `month_rev` has no observed date at all, the document server
    carrying 財務報告書 only, so its period ends are refused rather than returned
    as an all-`NaT` column that reads as missing data.

    **The filings also outrun a row of `filing_deadlines.csv`, and the document
    type says why.** The table puts the 45-day 第二季 rule in force from
    `2011-12-31`, so it scores FY2012's half-year against 45 days. That date is
    right as legislation — 證交法 §183 reads 「九十九年六月二日修正公布之第三十六
    條，自一百零一年一月一日施行」 — and the annual rule bites exactly there: the
    第四季 lag drops from 117 days to 89 at FY2011, where the three-month
    amendment lands. The 第二季 rule does not. Its median lag is 59, 59, 61, 61
    and 61 days for 2008 through 2012 and then 44 from 2013, and the filings
    name the reason instead of leaving it to be inferred: through FY2012 the
    mid-year document is `A01 母公司財報`, the 我國GAAP 半年度財務報告, and from
    FY2013 it is `AI1 IFRSs合併財報`. §36 I(2) governs a 第二季財務報告, and for
    these companies that report begins with IFRS adoption at 一百零二會計年度. The
    table is therefore applying a rule to a quarter the rule had not yet
    reached: 1,592 of the 1,621 FY2012 half-years come back late — 98.2 %, a
    table failing rather than a market failing — where a transitional line
    first applying it to FY2013 leaves 31, and takes the window's late count
    from 7,699 to the 6,138 quoted above.

    The row is left standing all the same. What it is missing is the instrument
    that governed the 一百零一會計年度 半年報 in the gap between the statute's
    start and the report type's — a citation this package has not found, not a
    number it can measure — and correcting sourced legislation against a
    measurement is the move this file exists to refuse. Recorded, asserted, and
    left for the citation.

    Two silent failures were caught in the collecting, both of which returned
    HTTP 200 and parsed to zero rows. The server throttles by serving
    「查詢過量，請稍後再查詢!」 in a 469-byte page — a burst allowance of about 14
    requests with a 16-second cooldown, measured — and reading that as an absence
    wrote empty histories for 89 companies that have one. A 金融控股公司 is served
    a subsidiary picker rather than its own filings, and needs the hidden
    `check2858=Y` the picker carries; without it the fifteen 金控 — 2880 through
    2892, 5820 and 5880, the whole sector — record nothing. Both are detected by
    the phrase now, and the collector ends non-zero if any company still lands an
    empty history, because twice the empty was the collector and not the company.

    Two smaller things the panel keeps and drops. **1,057 rows are filed under a
    six-digit 公開發行 registration number** rather than a ticker — a company that
    was publicly issued before it listed filed its first reports under that
    number, and the server returns them on the listed code's page; they are the
    same company, so they are kept under the listed code with the old one beside
    them in `filed_as`. **Thirteen filenames carry a period no calendar has** —
    192003, 291001, 283102 — and are dropped rather than clipped, all of them
    pre-2001 documents outside the window.

10. **The statement trees drop old delistings; the exchange's daily trees keep
    them.** The overlay puts every delisted name back in the universe and the
    rebuild gives each one an adjusted return series, but that completeness
    stops at the price. Of the **164** commons delisted inside the window,
    `fin_is/` carries rows for **63**, `fin_cf/` for 61, `fin_bs/` for 82 and
    `shares/` for 107. The rest are not short files, they are **empty** ones —
    zero rows before any clipping — so the gap is absence at the source rather
    than a window artifact: 90 of the missing names lived through eight or more
    in-window quarters and not one of them carries a single statement row.
    `download.py` asks for them on every pass and the endpoint returns nothing,
    which `download.log` records as `fin_is=ok(0)`.

    What the vendor retains is the **company**, not the listing. Twelve of the
    sixteen pre-break delistings that do carry statements are names that kept
    filing after they left the board — 5854 left in 2011 and its income
    statement runs to 2026-03-31 — and the other four sit within months of the
    break. The break itself is sharp and one-sided: every one of the **47**
    names delisted after **2020-11-20** has an income statement, against 16 of
    the 117 delisted on or before it. `fin_cf/` breaks on the same date,
    `shares/` three days earlier, `fin_bs/` on 2019-03-29, and `month_rev/` on
    2020-08-25 — where the loss is partial rather than total, since 139 of the
    164 keep a file but only 3 of the 117 pre-break names keep the full span
    against 29 of the 47 after it. The daily series the exchange publishes show
    no break at all: `per_pbr/` covers 162 of the 164 and `instflow/` 156.

    So **a fundamental signal on this panel is still survivorship-biased even
    though the price panel is not**, and the two are not separable by care in
    the join: the names that left are exactly the names whose statements are
    gone, so a value or quality sort formed before 2021 ranks survivors. This
    is not caveat 9 in another guise — that one is about when a figure became
    public, this one about whether it is here at all — and dating the data
    differently does not reach it. The bias runs the ordinary way for a
    fundamentals study: the failures are the missing rows.

    Whether the break is fixed or rolls forward with the pull date cannot be
    read off a single pull, and the difference decides whether a fresh clone
    reproduces this panel or a smaller one.
    `test_taiwan_statement_trees_drop_old_delistings` pins today's break so the
    next refresh answers it. The committed files are safe either way: a
    non-empty file is never emptied by a re-pull — `download.py` resumes from
    its last row and writes nothing when the fetch comes back empty — and an
    empty file is re-pulled whole, so the gap closes by itself if the vendor
    ever backfills.
11. **`open` is not inside `[min, max]` on 2.2 % of rows.** 125,114 traded rows
    across 669 stocks report an `open` above the session `max` or below the
    session `min`; `close` never does, on any row of the panel. The deviation
    beyond the bar is small on most of them — median 0.75 %, and 59 % sit within
    1 % — but 0.2 % of them exceed 10 % and the worst reaches 113 %. They are
    spread over every year of the window rather than clustered in any one
    regime, so
    this is a property of the `open` field, not of a period or a venue. A
    strategy that enters at the open therefore prices ~2 % of its fills off a
    number the same row contradicts, while the same strategy on `close` is
    unaffected. Screen with `open.between(min, max)` before using it; caveat 6's
    individually corrupt rows are a separate and much smaller set.

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
| `dividend/` | `TaiwanStockDividend` | Cash + stock dividends, at **declaration** level — the per-component split (`CashEarningsDistribution`, `StockEarningsDistribution`, `CashIncreaseSubscriptionRate`). Units differ per field: stock dividends are per NT$10 par, rights are 每仟股. Also carries `CashExDividendTradingDate`, a **declared ex-date usable as an independent second source** for `div_result`'s event date — the two agree on 19,722 of 19,730 comparable events (**99.96 %**; of 2,480 non-matches, 2,472 are outside that stock's `div_result` span and only 8 are real). Present for 1,846 of the 2,158 universe stocks, counting a stock as covered when any row carries a non-blank value (re-measured 2026-08-17). |
| `div_result/` | `TaiwanStockDividendResult` | 除權除息結果表 — the exchange's **published reference prices** per ex-event (`before_price`, `after_price`). 18,277 in-window events / 1,903 stocks. This, not `dividend/`, is what the adjusted series is built from. |
| `sec_lending/` | `TaiwanStockSecuritiesLending` | 借券/議借 — institutional short proxy |

Sponsor tier (level 3, since 2026-08-16):

| Subdir | Endpoint | Notes |
|---|---|---|
| `price_adj/` | `TaiwanStockPriceAdj` | 還原股價 — the back-adjusted OHLCV, **total-return convention** (see **Adjusted prices**). Gated above `register` until the tier was bought; the docs' "Free (with data_id)" line was wrong for every calling convention. Same schema as `ohlcv/`, and `Trading_Volume` is identical to it row for row — only the five price columns are adjusted. |

The tier reports itself at `api.web.finmindtrade.com/v2/user_info`:
`level: 3`, `level_title: "Sponsor"`, `api_request_limit_hour: 6000` — ten times
the register quota. The quota is spent per *request*, so the pace is
`3600/api_request_limit_hour` minus the round trip, measured at 0.27 s: about
5.7 s on the register tier and 0.33 s on the sponsor tier, against a `--sleep`
default of 6.5. Leave a margin — overshooting earns a 402, which
`download.py` answers by sleeping to the top of the hour and then failing the
stock after two of them, so a burst costs an hour and a gap rather than buying
throughput.

**Not in FinMind's enum:**

| Endpoint | Reason | Workaround |
|---|---|---|
| `TaiwanStockEPS` | Not a FinMind dataset | EPS lives inside `TaiwanStockFinancialStatements` as `type == 'EPS'` rows |
| `TaiwanStockShareholdingClassification` | Not a FinMind dataset | Use MOPS insider-holdings disclosures directly |

**Ungated by the tier, not downloaded.** Every endpoint the 2026-04-26 pass
recorded as paid-only answers HTTP 200 on the sponsor token (re-probed
2026-08-16); none is fetched here, because none feeds a current question. The
row below records that the gate is gone, not that the data is present or that
any particular `data_id` returns rows.

| Endpoint | Status |
|---|---|
| `TaiwanStockHoldingSharesPer` | Reachable — holder-size distribution, 68 rows for 2330 in Jan-2024 |
| `TaiwanStockConvertibleBondInfo` | Reachable — 7 rows in Jan-2024 |
| `TaiwanStockConvertibleBondDaily` / `…DailyOverview` / `…InstitutionalInvestors` | Reachable; the CB `data_id` convention was not explored |

Follow-up — delivered (top-level files, not in per-stock DATASETS):

| File | Endpoint | Notes |
|---|---|---|
| `delisted_universe.parquet` | `TaiwanStockDelisting` | Already in repo — the existing file *is* the `TaiwanStockDelisting` market-wide one-shot output (723 rows, 2001-2026). Refreshed 2026-08-17. Columns: `date`, `stock_id`, `stock_name`, `year` (year derived from date). No re-download needed. |
| `capital_reduction.parquet` | `TaiwanStockCapitalReductionReferencePrice` | Concatenated event log (sparse: most stocks have 0 events). 9 columns including `PostReductionReferencePrice`, `ExrightReferencePrice`, `ReasonforCapitalReduction`. Per-stock raw files in `cap_red/`; `consolidate_capred.py` merges them. **The endpoint's earliest row is 2011-01-25**, six years after the price series starts — see caveat 5. |

Not a FinMind endpoint at all — the exchange serves it free and without a key:

| File | Source | Notes |
|---|---|---|
| `exright_reference.parquet` | TWSE **TWT49U** 除權除息計算結果表, `www.twse.com.tw/rwd/zh/exRight/TWT49U?startDate=&endDate=&response=json` | 15,314 events / 1,269 stocks, 2005-01-11 → 2024-12-31. Whole-year queries are not truncated (2007 returns 538 rows either way), so `download_exright.py` needs 20 requests. Carries the same two reference prices as `div_result/` — they agree to 1e-6 on **99.99 %** of the 13,892 joined events, the single exception being 3454's malformed 2011-07-27 twin that the vendor audit also flags — plus the **權值 / 息值 split** `div_result` lacks, which resolves 143 fused events whose cash dividend was never declared. Schema narrows in 2009; see caveat 7. Probed 2026-08-01. |
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
That resume fills gaps and cannot move an end date: every file exists, so a
re-run with a later `--end` downloads nothing and reports a clean pass. Use
`--extend` for a later end — it resumes each file from its own last date and
appends. See "Extending the far end".

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
     2026-04-26). Re-pulled 2026-08-17 by `refresh_delisting.py`: the
     vendor backfills the table, 315 rows became 723, and five committed
     rows were retracted — so a refresh replaces the file rather than
     unioning onto it.
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
python -m finmind_data.consolidate_capred    # → capital_reduction.parquet
# (Delisting events are already in delisted_universe.parquet — no
# separate fetch needed; `TaiwanStockDelisting` produced this file.)

# Adjusted prices (~25 min at the sponsor 6000/hr quota)
nohup python download.py --datasets price_adj --sleep 0.4 \
  > nohup.price_adj.out 2>&1 &

# Validity mask — needs div_result/, capital_reduction.parquet and shares/
python -m finmind_data.detect_unpriced_actions --calibrate   # → unpriced_actions.parquet

# Exchange 除權息 report, independent of the above (~20 requests, no key)
python -m finmind_data.download_exright   # → exright_reference.parquet
```

Re-running any command is safe: `download.py` skips stock-subdir pairs
whose parquet file already exists — which is also why re-running one cannot
move `--end`. That is what `--extend` is for.

### Extending the far end

```bash
# Top every file up to a later end date. Each resumes from its own last date.
python download.py --extend --end <YYYY-MM-DD> --sleep 0.4
```

An empty file carries no last date to resume from, so it is re-pulled whole —
which also repairs files an earlier pull left empty when they should not have
been. A column set that differs between the two pulls is refused rather than
concatenated, since `pd.concat` would widen the frame and leave each pull's
rows NaN in the other's columns: the stock logs `schema-drift`, counts as a
failure, and its file is left as it was.

Extending the trees does not extend what this package answers for. The window
is `window.py`'s, every reader applies it (`window.clip`), and the figures
below are quoted on it — so an extension adds rows on disk and changes no
number here. Moving `COVERAGE_END` is a separate decision, and not this
package's alone: the study window it sits inside is shared across the
repository.