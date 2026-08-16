# FnGuide DataGuide XLSX Dataset

## Overview

- **11 xlsx files** in `raw/`, ~6.5 GB total. Nine were pulled with the
  "all codes" universe filter; the two `0_*(상폐제외)` files were not — see
  ["Every sheet has its own pull date"](#️-every-sheet-has-its-own-pull-date)
- **Source:** FnGuide DataGuide (Korean financial data platform)
- **Not one snapshot.** The exports span 2026-02-14 to 2026-08-13 and each
  carries its own end date and its own ticker universe. Read the pull-date
  section before joining any two of them.
- **Layout:** Raw vendor exports live under `raw/`. Loader modules sit at
  the directory root: `price_loader.py` (adjusted close — the one research
  reads), plus `fnguide_io.py`, `investor_loader.py` and
  `subinvestor_loader.py`, flat and sys.path-imported for backward
  compatibility with older research projects. **Beyond the price panel,
  new projects should parse the sheets inline rather than depending on
  these helpers** — the layout is simple enough that centralizing the
  parsers earns little. All of them read xlsx through `engine="calamine"`.
- **Coverage:** ~3,900 Korean listed stocks (KOSPI / KOSDAQ) for
  investor trading & financials.
- **Adjusted prices live here; raw OHLCV does not.**
  `raw/Price data.xlsx` carries both conventions FnGuide publishes —
  수정주가 (price return) and 수정주가(현금배당포함) (total return) — for
  KOSPI + KOSDAQ including delisted names, 2005-01-03 to 2026-08-12.
  This is the price series research reads.
  `python -m fnguide_data.price_loader` parses it once into
  `cache/fnguide_price.parquet`; everything downstream reads the
  parquet, not the xlsx. It carries **adjusted close only** — no volume,
  market cap or share count, and no point-in-time market membership. For
  those use `kr_marcap`: `kr_marcap.market_loader.load_market_data` (raw
  OHLCV) and `kr_marcap.universe(date, kind='common')`.
  Adjusted **open / high / low** exist in `raw/0_KOSPI 주가(상폐제외).xlsx`
  and `raw/0_KOSDAQ 주가(상폐제외).xlsx`, but only for names listed on
  2026-03-20 — see §10 before reaching for them.
  `kr_marcap.adjusted_loader.load_adjusted_panel` builds the same two
  adjusted conventions from openly available sources — it is the
  *reconstruction* this file is the benchmark for, not a second source
  to mix in; see
  [`kr_marcap/CONSTRUCTION.md`](../kr_marcap/CONSTRUCTION.md).
- **Survivorship bias — not a problem for the "all codes" nine.** The
  `data0*`, `data2_0203`, `short_sale_lending` and `Price data` files were
  exported with DataGuide's **"all codes"
  (전체 / 상폐 포함)** filter and are **effectively
  survivorship-bias-free for KOSPI/KOSDAQ common stocks** — paired with
  `kr_marcap.universe(date, 'common', strict=True)`, the live universe
  matches 100 %, and 99.1 % of common-stock delistings since 2021 are
  present (only 1 irreducible fnguide hole remains; 98.2 % under the
  default `strict=False`). Each delisted ticker's column carries data
  through its delisting date and goes NaN after. For most analyses that
  stay within these files, no external delisted-data merge is needed.
  See `DELISTED_COVERAGE.md` for the full breakdown.
- **The two `0_*(상폐제외)` files are the exception** — pulled with
  "delisted excluded", so they carry no delisted names at all and their
  live-column count only ever rises. They add adjusted open/high/low and
  1999--2004 history that no other file here has; both come with that
  survivorship bias attached. See §10.
- **If you re-pull additional metrics from DataGuide,** choose the
  "all codes" (전체 / 상폐 포함) filter to preserve delisted coverage.
  A previous `raw/currently_listed/` sub-batch pulled with the
  "delisted excluded" filter had 0% delisted coverage by construction
  and was removed.
- **Ticker-reassignment caveat — every code-keyed series, not just
  financials.** A 6-digit KRX code freed by a delisting is reissued, and
  FnGuide serves one column per *code*, so both occupants share it with a
  multi-year NaN gap between them. `data2_0203.xlsx` annual financials may
  return values from the later listing — truncate each series at
  `delisting_date.year - 1`. The price panel splices the same way — 58 codes —
  but there it is handled: `price_loader.py` emits a `segment` column and
  research differences within `['ticker', 'segment']` (§9).
- **Always-missing buckets:** preferred shares (우/우B/1우/MF, ~0.9%),
  KONEX (~2.6%), and specialty funds (선박투자/리츠/호, ~2.9%). These
  are usually excluded on methodological grounds anyway.
- **Data domains in this directory:**
  - **Daily investor trading flow** (6 files: data0203--data0208) —
    buy/sell volume & amount by investor type, 2000-01-04 to Feb 2026
  - **Annual financial statements + monthly market cap** (1 file:
    data2\_0203) — balance sheet, income statement items (IFRS
    consolidated), 1999--2025
  - **Short-selling / securities-lending / free-float** (1 file:
    short_sale_lending) — daily short-sale balance & turnover, lending
    balance, and free-float ratio, split KOSPI/KOSDAQ, 2002--2026
  - **Adjusted close, both conventions** (1 file: Price data) — daily
    수정주가 (price return) and 수정주가(현금배당포함) (total return),
    split KOSPI/KOSDAQ, 2005--2026
  - **Adjusted OHLC, price-return convention only** (2 files:
    0_KOSPI / 0_KOSDAQ 주가(상폐제외)) — daily 수정시가/고가/저가/주가,
    1999--2026-03, currently-listed names only

## ⚠️ Every sheet has its own pull date

**The files in `raw/` are not one snapshot.** Each was exported in a separate
DataGuide session, months apart in places, and DataGuide serves whatever the
master table held on the day of the export. Row 8 (`Term` / `기간`) records the
vendor's own stamp as `Current(YYYYMMDD)` / `최근일자(YYYYMMDD)`; that end date,
the ticker-column count, and the universe behind them all differ file to file.

This table is `vintages.csv` in prose; the file is the source of truth, and
"ticker columns" there counts non-empty codes on the Symbol row.

| File | Data through | Downloaded | Ticker columns |
|---|---|---|---:|
| `data0203.xlsx` | 2026-02-03 | 2026-02-14 | 3,902 |
| `data0204.xlsx` | 2026-02-06 | 2026-02-14 | 3,902 |
| `data0205.xlsx` | 2026-02-09 | 2026-02-19 | 3,902 |
| `data0206.xlsx` | 2026-02-09 | 2026-02-19 | 3,902 |
| `data0207.xlsx` | 2026-02-11 | 2026-02-19 | **3,904** |
| `data0208.xlsx` | 2026-02-12 | 2026-02-19 | **3,904** |
| `data2_0203.xlsx` | 2026-02-02 annual/monthly, 2026-02-03 시가총액 | 2026-02-19 | 3,902 |
| `0_KOSPI 주가(상폐제외).xlsx` | 2026-03-20 | 2026-03-23 | 2,311 |
| `0_KOSDAQ 주가(상폐제외).xlsx` | 2026-03-20 | 2026-03-23 | 1,815 / **1,813** |
| `short_sale_lending.xlsx` | 2026-06-12, **2026-06-15** on three sheets | 2026-06-15 | 1,284 KOSPI / 2,773 KOSDAQ |
| `Price data.xlsx` | **2026-08-12** | 2026-08-13 | 1,284 KOSPI / 2,785 KOSDAQ (3,590 priced) |

**"Downloaded" is the vendor's build stamp, not the file's mtime.** The
Korean-locale exports carry it on row 1 as `Refresh | Last Updated:
YYYY-MM-DD HH:MM:SS` — the moment DataGuide assembled that *sheet*. Where the
two disagree the Refresh row wins: the 상폐제외 pair was built on 2026-03-23 and
did not land on this disk until 2026-06-07, and `short_sale_lending.xlsx` was
built on 2026-06-15 and copied here on 2026-06-18. The English-locale
`data0*` exports have no Refresh row at all, so for those the mtime is the only
evidence there is.

Five consequences, in the order they bite:

1. **A join truncates to the earliest file in it, not the latest.** Investor
   flow ends 2026-02-12 and adjusted close runs to 2026-08-12; a panel built
   from both is six months shorter than the price file suggests. Date the
   joined panel by the *minimum* end date of its inputs.
2. **The universe is not constant across files.** 3,902 columns against 3,904
   is not a formatting difference — it is two tickers that listed between the
   14th and the 19th of February. A name that delisted between two pulls is
   live in the earlier file and terminated in the later one; a name that listed
   after a pull is absent from that file entirely and present in the next.
   Left-joining on the wider file silently manufactures all-NaN columns.
3. **Coverage figures are pinned to the pull that measured them.** "99.8 % of
   live commons" was measured against a marcap vintage of 2026-02-20 and
   describes the February batch. It is not a property of `Price data.xlsx`,
   which was pulled six months later against a different live universe — that
   file has its own figure (99.4 % of genuine common delistings since 2005) in
   `DELISTED_COVERAGE.md`. Quote the figure with the pull it came from.
4. **A re-pull of one file re-dates only that file.** Refreshing
   `Price data.xlsx` does not extend the investor-flow window, and nothing in
   the loaders detects the mismatch — the parse succeeds and the panel is just
   short. `price_loader.py` asserts the item code on row 12 so a *swapped item*
   raises at build time, but no check compares end dates across files.
5. **It is per *sheet*, not per file — one file is not one snapshot either.**
   DataGuide builds a workbook one sheet at a time, and the Refresh stamps show
   the gaps: `short_sale_lending.xlsx` was assembled between 11:54 and 17:40 on
   2026-06-15, and its last three sheets crossed that afternoon's 15:30 close —
   their `기간` stamp reads 2026-06-15 where the other seven read 2026-06-12.
   The same metric splits across markets there: `KOSDAQ_유동주식비율` (built
   15:24) is stamped 2026-06-12, `KOSPI_유동주식비율` (17:18) 2026-06-15. Worse,
   the universe
   can move inside one file: `KOSDAQ_수정주가` in the 상폐제외 pair was built 29
   minutes after `KOSDAQ_수정저가` and came back with **two fewer columns**
   (§10). So align sheets on the row-9 code, never on column position, and take
   a file's end date from the sheet you actually read.

The same asymmetry crosses the repo boundary: `kr_marcap`'s benchmark against
this export is bounded on the marcap side (2026-02-20), not the FnGuide side
(2026-08-12), so the comparison runs only to February. See
[`kr_marcap/CONSTRUCTION.md`](../kr_marcap/CONSTRUCTION.md).

### What to do about it

**Not** re-pull everything into one session. That alignment survives exactly
until the next single-file refresh, costs a day, and re-anchors every
back-adjusted level on the way — a name that split since the old pull comes back
at a different price for its whole history, so every cached result built on the
old vintage silently stops matching (§10 measures this: 24 of 2,577 shared
tickers, at ratios of ×10, ×5, ×0.5, ×0.2). Re-pull a file when you need data
past its end date, not to make the dates agree.

What is worth fixing is that the vintage was invisible. It now lives in
**`vintages.csv`** — one row per sheet, with the build stamp, the `기간` range,
and the ticker count — committed, and regenerated by `python -m
fnguide_data.vintages` whenever an export is replaced:

```python
from fnguide_data.vintages import end_date
end_date('Price data.xlsx')                             # Timestamp('2026-08-12')
min(end_date(f) for f in ('data0203.xlsx', 'Price data.xlsx'))   # date the join
```

Reading one header out of a 1.4 GB export costs a full sheet parse, so the scan
takes ~15 minutes and the CSV exists to make the answer free at the point where
someone is about to join two files. Three rules follow, and the manifest is what
makes the first two checkable:

1. **Date a joined panel by `min(end_date(...))` of its inputs, explicitly.**
   Never let it be inferred from whichever frame happened to be on the left.
2. **Quote a coverage figure with the pull that measured it** — see consequence
   3 above.
3. **One export per price series.** Never splice two pulls of the same series:
   they disagree on levels wherever a corporate action fell between them, and on
   returns by ₩1 rounding everywhere else (§10).

`test_assertions.py` compares the manifest against `raw/` on every run, so a
re-pull cannot land without the manifest — and the figures it dates — being
revisited in the same commit.

### The 상폐제외 pair uses the other universe filter

Nine of the eleven files in `raw/` were pulled with DataGuide's **"all codes"
(전체 / 상폐 포함)** filter. The two `0_*(상폐제외)` files were pulled with
**"delisted excluded"**, so they carry no delisted names at all — measured, not
assumed: of their 4,126 codes, 107 appear in `kr_delisted/delisting_calendar.csv`
with a date before the pull, and every one of those is a code still occupied on
the pull date (§10). Keep the two filters in separate panels; a union of them is
survivorship-biased wherever the 상폐제외 side is the only source.

A previous `raw/currently_listed/` sub-batch pulled under the same
"delisted excluded" filter carried a hard defect worth knowing about before
anyone re-pulls that way: its ticker count dropped from ~3,253 (Fri 2023-10-20)
to ~1,843 (Mon 2023-10-23) in a single session and then climbed back via IPOs.
~1,400 currently-listed common stocks silently disappear from the export from
late-Oct-2023 onward and **only 10 of them are genuine delistings**, so a
`kr_delisted/` overlay cannot recover them — the export had been pulled in two
phases under different universe filters and concatenated horizontally. That
batch has been removed (see the historical note in `integrity_report.md`); for
OHLCV / market cap / shares use `marcap/` via `kr_marcap`, which covers every
ticker that traded on every date.

## Data Summary

| Domain | Files | Granularity | Coverage |
|--------|-------|-------------|----------|
| **Investor Trading (12 types, buy+sell, volume+amount)** | data0203--data0208 | Daily | ~3,902 stocks, 2000--2026 |
| **Financials (consolidated)** | data2_0203 | Annual + Monthly (시가총액) | IFRS(C): balance sheet, operating profit, total assets, market cap |
| **Short-selling / lending / free-float** | short_sale_lending | Daily | ~4,041 stocks (KOSPI+KOSDAQ split), 2002--2026 |
| **Adjusted close (price return + total return)** | Price data | Daily | 3,590 stocks (KOSPI+KOSDAQ split), 2005--2026 |
| **Adjusted OHLC (price return only)** | 0_KOSPI / 0_KOSDAQ 주가(상폐제외) | Daily | 4,126 codes incl. ETF/ETN, listed-on-2026-03-20 only, 1999--2026-03 |

**NOT available in this dataset:** volume / market cap / shares (use
`kr_marcap/` and `kr_delisted/`); adjusted open/high/low for *delisted*
names — the only OHL here is the currently-listed 상폐제외 pair; main-entity
(IFRS-M) financials, L2 order book / tick data, bid-ask spread,
analyst coverage / consensus estimates, CB/BW/mezzanine event
calendar, index composition & rebalancing events, tick size /
institutional rules calendar, broker-level / account-level data.

## Common File Structure (Header Rows 1--14)

All sheets share the same FnGuide DataGuide export format:

| Row | Field | Description |
|-----|-------|-------------|
| 1 | Refresh | `Last Updated: YYYY-MM-DD HH:MM:SS` — when DataGuide built *this sheet*. Present in the Korean-locale exports (`Price data`, `short_sale_lending`, the 상폐제외 pair), blank in the `data0*` batch |
| 2 | Calendar Basis | Calendar system used |
| 3 | Portfolio | Currency unit (원 = KRW) |
| 4 | Item | Spacer |
| 5 | Frequency | Data frequency (일간=Daily / 월간=Monthly / 연간=Annual), currency code |
| 6 | Non-Trading Day | Handling rule (Exclusive = skip non-trading days) |
| 7 | Include Weekend | "ALL" |
| 8 | Term / 기간 | Date range: start (e.g. 20000101) to end (e.g. `Current(20260203)`, or `최근일자(20260320)` in the Korean-locale exports) |
| 9 | **Symbol** | Stock ticker codes (e.g. A005930, A000660) |
| 10 | **Symbol Name** | Company names in Korean (e.g. 삼성전자, SK하이닉스) |
| 11 | Kind | Data category: CIA (investor trading), NFS-IFRS(C) (consolidated financials), SSC (stock stats) |
| 12 | **Item** | FnGuide item code (e.g. CI20001010, 6000903007) |
| 13 | **Item Name** | Full metric name in Korean |
| 14 | Frequency | DAILY / MONTHLY / ANNUAL |

**Data starts at row 15.** Column A = date (datetime), columns B
onward = one column per stock (~3,902--3,904 stocks).

**The row numbers above are the `pd.read_excel` view, and only that view.**
The English-locale exports have a genuinely *blank* first row where the
Korean-locale ones have `Refresh`. `pd.read_excel` keeps it as a NaN row, so
row 9 is `Symbol` in both — which is why `fnguide_io.py` and `price_loader.py`
can use fixed indices. `python_calamine.CalamineWorkbook.to_python()` **trims**
it, so under that reader the English files sit one row higher than the Korean
ones and a fixed index silently returns 코드명 where 코드 was meant. Read
headers with pandas, or locate rows by their column-A label as
`vintages.py` does.

## Stock Universe

- ~3,902--3,904 Korean listed stocks across KOSPI and KOSDAQ
- Identified by ticker codes with "A" prefix + 6 digits (e.g. A005930
  = Samsung Electronics)
- Columns are ordered approximately by market cap
- Stocks not yet listed on a given date have `None`/NaN values
- Column counts differ between files (3,902 vs 3,904) because each was
  pulled on its own date against its own live universe — this changes which
  tickers exist, not just how many. See
  ["Every sheet has its own pull date"](#️-every-sheet-has-its-own-pull-date)
- **Not every column is a stock.** The 상폐제외 pair carries 388 `Q…` ETN
  codes and 241 six-character alphanumeric codes alongside the plain 6-digit
  equity codes, and its plain 6-digit set includes ETFs. Intersect with
  `kr_marcap.universe(date, kind='common')` rather than pattern-matching the
  code (§10).
- **Survivorship-bias status:** the nine "all codes" (전체 / 상폐 포함) files
  are effectively survivorship-bias-free — ~90% of genuine delistings
  present, ~99% from 2021 onward. See `DELISTED_COVERAGE.md` for the
  full breakdown. The two 상폐제외 files have zero delisted coverage by
  construction (§10).

## Python Loading Example

**Every xlsx read in this directory goes through `engine="calamine"`**
(python-calamine, a Rust reader). It is ~10× faster than openpyxl on these
exports and a fraction of the memory — `Price data.xlsx` reads in ~4 s a
sheet against ~45 s — and it is a prerequisite of this package, not an
optional accelerator. Install with `pip install python-calamine`; the repo's
dependency list is in `../CLAUDE.md`.

Helper modules ship in this directory for the common cases. The flat ones
have no package boilerplate — put `~/research/finance_db/fnguide_data/` on
`sys.path` and import them by module name. **These exist for backward
compat with current research projects; new projects should prefer
inline parsing using the documented 14-row layout.**

- `fnguide_io.py` — `load_fnguide_sheet(filepath, sheet_name)` returns
  a date-indexed wide DataFrame; `melt_fnguide_wide(df, value_name)`
  pivots it long.
- `price_loader.py` — `load_price_panel()` returns the long
  `(date, ticker, market, adj_close_pr, adj_close_tr, segment)`
  adjusted-price panel (both conventions, 2005+, delisted included) from
  `raw/Price data.xlsx`, building `cache/fnguide_price.parquet` on first
  call. `segment` numbers each code's listing spells, so returns are
  differenced within `['ticker', 'segment']`. This is the package's
  research price input; see §9 below.
- `investor_loader.py` —
  `load_investor_flow(start, end, *, raw_dir, investor_types=('기관','개인','외국인'), foreign_definition='등록외국인', cache_dir=None)`
  returns a long
  `(date, ticker, investor_type, buy_value, sell_value, net_buy_value)`
  panel (KRW) for any date range, derived from
  `raw/data0203/0204/0206/0207.xlsx`. `foreign_definition='등록외국인'`
  (Smart Money, default) restricts 외국인 to registered foreigners;
  `'외국인계'` adds 기타외국인. Sibling helper `to_wide_net(flow)`
  pivots to wide `(date, ticker, institutional, individual, foreign)`
  net columns. Design rationale and an integrity report (vs the
  legacy `qf_next/investor_data/` data1229/data1230 export) live in
  `docs/investor/`.
- `subinvestor_loader.py` —
  `load_subinvestor_flow(start, end, *, raw_dir, subinvestor_types=<all 8>, cache_dir=None)`
  returns a long `(date, ticker, subinvestor_type, buy_value, sell_value,
  net_buy_value)` panel (KRW) decomposing the 기관계 aggregate into its 8 KRX
  sub-types (pension/연기금등, insurance/보험, investment_trust/투신,
  pe_funds/사모펀드, financial_inv/금융투자, other_financial/기타금융,
  bank/은행, government/국가) from `raw/data0204/0205/0206/0207/0208.xlsx`.
  `SUBINVESTOR_SOURCES` is the canonical 8-type → (file, sheet) map; sibling
  `to_wide_net_sub(flow)` pivots to one net column per sub-type. A missing/
  renamed sheet raises (fail loud); consumers requiring all 8 (e.g. qf_paper's
  Capacity-Bound = pension + insurance) should error on an absent type rather
  than zero-fill.

For OHLCV / market cap / listed shares, see `kr_marcap` in this repo —
`kr_marcap.market_loader.load_market_data` (`date, ticker, open, high,
low, close, volume, amount, market_cap, listed_shares`),
`kr_marcap.adjust.load_adjusted(ticker)` (split-adjusted single-ticker
series), and `kr_marcap.universe(date, kind='common')` (point-in-time
common-stock membership). Both are survivorship-bias-free.

`kr_marcap` also has its own adjusted-price loader,
`kr_marcap.adjusted_loader.load_adjusted_panel()`, reconstructing both
conventions from open sources. It is a separate project with a separate
input chain — read it to study the reconstruction, not to source prices
for research. Don't merge its output into a panel built on this one.

For ad-hoc reads, the underlying xlsx layout is documented above —
column codes on row 9, names on row 10, item codes on row 12, data
starts row 15.

```python
import pandas as pd

# Read a single sheet (skip first 14 header rows, use row 9 as column names).
# engine="calamine" is not optional on files this size — see the note above.

# Step 1: Read metadata rows to get stock symbols and item info
meta = pd.read_excel("raw/data0203.xlsx", sheet_name="매수수량(기관)", header=None,
                     nrows=14, engine="calamine")
symbols = meta.iloc[8, 1:]       # Row 9: ticker codes (A005930, ...)
names = meta.iloc[9, 1:]         # Row 10: company names (삼성전자, ...)
item_code = meta.iloc[11, 1]     # Row 12: FnGuide item code
item_name = meta.iloc[12, 1]     # Row 13: metric name in Korean

# Step 2: Read the time series data
df = pd.read_excel("raw/data0203.xlsx", sheet_name="매수수량(기관)",
                   header=None, skiprows=14, engine="calamine")
df.columns = ["date"] + list(symbols)
df["date"] = pd.to_datetime(df["date"])
df = df.set_index("date")
```

---

## File-by-File Documentation

### 1. `raw/data0203.xlsx` (220 MB)

**Content:** Institutional investors (aggregate) -- **buy** side only

| Sheet Name | English | Item Code | Unit |
|---|---|---|---|
| 매수수량(기관) | Institutional Buy Volume (total) | CI20001010 | Shares (주) |
| 매수대금(기관) | Institutional Buy Amount (total) | CI20001020 | KRW (원) |

- **Sheets:** 2
- **Rows per sheet:** ~6,446 (trading days)
- **Columns:** 3,903 (1 date + ~3,902 stocks)
- **Frequency:** Daily
- **Date range:** 2000-01-04 to ~2026-02-03
- **Kind:** CIA
- **Notes:** Aggregate institutional buy data. The sell side for aggregate institutional is in data0204.

---

### 2. `raw/data0204.xlsx` (1.4 GB)

**Content:** Institutional investors (aggregate sell) + breakdown by sub-type: Securities firms, Insurance companies, Asset management/Mutual funds

| Sheet Name | English | Item Code | Unit |
|---|---|---|---|
| 매도수량(기관계) | Institutional Sell Volume (total) | CI20002010 | Shares |
| 매도대금(기관계) | Institutional Sell Amount (total) | CI20002020 | KRW |
| 매수수량(금융투자) | Securities Firm Buy Volume | CI20011010 | Shares |
| 매수대금(금융투자) | Securities Firm Buy Amount | CI20011020 | KRW |
| 매도수량(금융투자) | Securities Firm Sell Volume | CI20012010 | Shares |
| 매도대금(금융투자) | Securities Firm Sell Amount | CI20012020 | KRW |
| 매수수량(보험) | Insurance Co. Buy Volume | CI20021010 | Shares |
| 매수대금(보험) | Insurance Co. Buy Amount | CI20021020 | KRW |
| 매도수량(보험) | Insurance Co. Sell Volume | CI20022010 | Shares |
| 매도대금(보험) | Insurance Co. Sell Amount | CI20022020 | KRW |
| 매수수량(투신) | Asset Mgmt (Mutual Fund) Buy Volume | CI20031010 | Shares |
| 매수대금(투신) | Asset Mgmt (Mutual Fund) Buy Amount | CI20031020 | KRW |
| 매도수량(투신) | Asset Mgmt (Mutual Fund) Sell Volume | CI20032010 | Shares |
| 매도대금(투신) | Asset Mgmt (Mutual Fund) Sell Amount | CI20032020 | KRW |
| Sheet16 | (empty) | -- | -- |

- **Sheets:** 15 (14 data + 1 empty)
- **Rows per sheet:** ~6,449
- **Columns:** 3,903
- **Frequency:** Daily
- **Date range:** 2000-01-04 to ~2026-02-06
- **Kind:** CIA
- **Notes:** Largest file. Contains the aggregate institutional sell side (counterpart to data0203 buy side) plus full buy/sell breakdown for three institutional sub-types. Ignore Sheet16 (empty).

---

### 3. `raw/data0205.xlsx` (666 MB)

**Content:** Institutional sub-types continued: Banks, Other Financial Institutions

| Sheet Name | English | Item Code | Unit |
|---|---|---|---|
| 매수수량(은행) | Bank Buy Volume | CI20041010 | Shares |
| 매수대금(은행) | Bank Buy Amount | CI20041020 | KRW |
| 매도수량(은행) | Bank Sell Volume | CI20042010 | Shares |
| 매도대금(은행) | Bank Sell Amount | CI20042020 | KRW |
| 매수수량(기타금융) | Other Financial Buy Volume | CI20051010 | Shares |
| 매수대금(기타금융) | Other Financial Buy Amount | CI20051020 | KRW |
| 매도수량(기타금융) | Other Financial Sell Volume | CI20052010 | Shares |
| 매도대금(기타금융) | Other Financial Sell Amount | CI20052020 | KRW |

- **Sheets:** 8
- **Rows per sheet:** ~6,450
- **Columns:** 3,903
- **Frequency:** Daily
- **Date range:** 2000-01-04 to ~2026-02-09
- **Kind:** CIA
- **Notes:** Sheet tabs were corrected from truncated forms (기타 -> 기타금융).

---

### 4. `raw/data0206.xlsx` (1.4 GB)

**Content:** Pension Funds, Other Corporations, Individuals

| Sheet Name | English | Item Code | Unit |
|---|---|---|---|
| 매수수량(연기금등) | Pension Fund Buy Volume | CI20061010 | Shares |
| 매수대금(연기금등) | Pension Fund Buy Amount | CI20061020 | KRW |
| 매도수량(연기금등) | Pension Fund Sell Volume | CI20062010 | Shares |
| 매도대금(연기금등) | Pension Fund Sell Amount | CI20062020 | KRW |
| 매수수량(기타법인) | Other Corporation Buy Volume | CI20071010 | Shares |
| 매수대금(기타법인) | Other Corporation Buy Amount | CI20071020 | KRW |
| 매도수량(기타법인) | Other Corporation Sell Volume | CI20072010 | Shares |
| 매도대금(기타법인) | Other Corporation Sell Amount | CI20072020 | KRW |
| 매수수량(개인) | Individual Buy Volume | CI20081010 | Shares |
| 매수대금(개인) | Individual Buy Amount | CI20081020 | KRW |
| 매도수량(개인) | Individual Sell Volume | CI20082010 | Shares |
| 매도대금(개인) | Individual Sell Amount | CI20082020 | KRW |

- **Sheets:** 12
- **Rows per sheet:** ~6,450
- **Columns:** 3,903
- **Frequency:** Daily
- **Date range:** 2000-01-04 to ~2026-02-09
- **Kind:** CIA
- **Notes:** Sheet 8 tab was corrected from truncated "매도대금" to "매도대금(기타법인)".

---

### 5. `raw/data0207.xlsx` (1.3 GB)

**Content:** Registered Foreigners, Other Foreigners, Private Funds

| Sheet Name | English | Item Code | Unit |
|---|---|---|---|
| 매수수량(등록외국인) | Registered Foreign Buy Volume | CI20091010 | Shares |
| 매수대금(등록외국인) | Registered Foreign Buy Amount | CI20091020 | KRW |
| 매도수량(등록외국인) | Registered Foreign Sell Volume | CI20092010 | Shares |
| 매도대금(등록외국인) | Registered Foreign Sell Amount | CI20092020 | KRW |
| 매수수량(기타외국인) | Other Foreign Buy Volume | CI20101010 | Shares |
| 매수대금(기타외국인) | Other Foreign Buy Amount | CI20101020 | KRW |
| 매도수량(기타외국인) | Other Foreign Sell Volume | CI20102010 | Shares |
| 매도대금(기타외국인) | Other Foreign Sell Amount | CI20102020 | KRW |
| 매수수량(사모펀드) | Private Fund Buy Volume | CI20311010 | Shares |
| 매수대금(사모펀드) | Private Fund Buy Amount | CI20311020 | KRW |
| 매도수량(사모펀드) | Private Fund Sell Volume | CI20312010 | Shares |
| 매도대금(사모펀드) | Private Fund Sell Amount | CI20312020 | KRW |

- **Sheets:** 12
- **Rows per sheet:** ~6,452
- **Columns:** 3,905
- **Frequency:** Daily
- **Date range:** 2000-01-04 to ~2026-02-11
- **Kind:** CIA
- **Notes:** Sheet tabs were corrected (typos and truncations fixed). **기타외국인 data is NULL before 2003-12-01** and **사모펀드 is NULL before 2008-06-23** -- see "Investor Type Introduction Dates" section for details.

---

### 6. `raw/data0208.xlsx` (616 MB)

**Content:** Government/National entities, Total (all investors aggregate)

| Sheet Name | English | Item Code | Unit |
|---|---|---|---|
| 매수수량(국가) | Government Buy Volume | CI20321010 | Shares |
| 매수대금(국가) | Government Buy Amount | CI20321020 | KRW |
| 매도수량(국가) | Government Sell Volume | CI20322010 | Shares |
| 매도대금(국가) | Government Sell Amount | CI20322020 | KRW |
| 매수수량(전체) | Total (All Investors) Buy Volume | CI20991010 | Shares |
| 매도수량(전체) | Total (All Investors) Sell Volume | CI20992010 | Shares |

- **Sheets:** 6
- **Rows per sheet:** ~6,453
- **Columns:** 3,905
- **Frequency:** Daily
- **Date range:** 2000-01-04 to ~2026-02-12
- **Kind:** CIA
- **Notes:** Sheet tabs were corrected: truncated names restored, and sheets 5--6 renamed from misleading "국가" to "전체" to match their actual content (Total/All Investors).

---

### 7. `raw/data2_0203.xlsx` (11 MB)

**Content:** Annual financial statements (IFRS consolidated) + Monthly market capitalization

| Sheet Name | English | Item Code | Kind | Frequency |
|---|---|---|---|---|
| 보통주자본금 | Common Stock Capital | 6000903007 | NFS-IFRS(C) | Annual |
| 자본잉여금 | Capital Surplus | 6000903012 | NFS-IFRS(C) | Annual |
| 이익잉여금 | Retained Earnings | 6000903016 | NFS-IFRS(C) | Annual |
| 이연법인세부채 | Deferred Tax Liabilities | 6000911019 | NFS-IFRS(C) | Annual |
| 자기주식 | Treasury Stock | 6000903019 | NFS-IFRS(C) | Annual |
| 자기주식 처분손실 | Loss on Disposal of Treasury Stock | 6000991046 | NFS-IFRS(C) | Annual |
| 영업이익 | Operating Profit | 6000906001 | NFS-IFRS(C) | Annual |
| 총자산 | Total Assets | 6000901001 | NFS-IFRS(C) | Annual |
| 시가총액 | Market Capitalization (millions KRW) | S410001250 | SSC | Monthly |
| Sheet13 | (empty) | -- | -- | -- |

- **Sheets:** 10 (8 annual financials + 1 monthly market cap + 1 empty)
- **Rows:** 42 (annual sheets, 28 entries = 27 fiscal years 1999--2025 + one 2026-02-02 current-snapshot row) / 340 (시가총액, monthly: 326 entries, ~27 years)
- **Columns:** 3,903
- **Date range:** 1999-12-31 to 2025-12-31 (annual; trailing 2026-02-02 current-snapshot row); 1999-01-31 to 2026-01-31 (monthly; trailing 2026-02-02 current-snapshot row)
- **Kind:** NFS-IFRS(C) for financial statements, SSC for market cap
- **Notes:** This is the only file with non-daily data. Annual dates are fiscal year-end dates (typically 12-31). Market cap is in millions of KRW. Ignore Sheet13 (empty). For daily market cap on currently-listed names, prefer `kr_marcap.market_loader.load_market_data` (column `market_cap`).

---

### 8. `raw/short_sale_lending.xlsx` (876 MB)

**Content:** Short-selling, securities-lending, and free-float series.
This is the **only** short-selling/lending source in the repo — the
investor-flow and financials files carry none of it.

| Sheet (per KOSPI + KOSDAQ) | English | Item Code | Unit | First obs |
|---|---|---|---|---|
| 대차잔고 | Securities-lending balance | S410100400 | Shares | 2002-01-04 |
| 차입공매도금액 | Covered short-sale turnover (daily) | S410000920 | KRW | 2008-01-03 |
| 공매도잔고금액 | Short-sale balance (value) | S410000994 | mn KRW | 2008-08-07 |
| 공매도잔고 | Short-sale balance (shares) | S410000992 | Shares | 2016-06-30 |
| 유동주식비율 | Free-float ratio | S420005150 | % | 2003-01-02 |

- **Sheets:** 10 — each metric has a **separate KOSPI and KOSDAQ sheet**.
  Unlike the investor-flow files, tickers are NOT pooled across markets:
  read the market sheet you need, or concatenate both.
- **Tickers:** 1,284 KOSPI + 2,773 KOSDAQ = 4,041 unique
- **Frequency:** Daily
- **Kind:** SSC
- **Date axis:** padded back to a 1979-12-24 placeholder; real data
  begins per-metric as in the table above and runs to 2026-06-10/12.
- **Notes:** Short-sale *balance in shares* begins 2016-06-30, matching
  KRX's public short-sale-balance disclosure start; the value series
  (백만원) carries earlier dates. Tabs are named `KOSPI_<metric>` /
  `KOSDAQ_<metric>` (e.g. `KOSDAQ_대차잔고`); the vendor's original
  full-width `ＫＯＳＰＩ＿` / `ＫＯＳＤＡＱ＿` prefixes were normalized to
  plain ASCII. Row 13 (Item Name) and row 11 (Kind) remain authoritative.
  Survivorship-bias-free: 99.4% of genuine common KOSPI/KOSDAQ
  delistings present (better than the investor-flow files) — see
  `DELISTED_COVERAGE.md`.

---

### 9. `raw/Price data.xlsx` (220 MB)

**Content:** Both adjusted-price conventions FnGuide publishes, KOSPI and
KOSDAQ in separate sheets.

| Sheet Name | English | Item Code | Unit |
|---|---|---|---|
| 수정주가_KOSPI | Adjusted close, price return (KOSPI) | S410000700 | KRW (원) |
| 수정주가_KOSDAQ | Adjusted close, price return (KOSDAQ) | S410000700 | KRW (원) |
| 수정주가(현금배당포함)__KOSPI | Adjusted close, total return (KOSPI) | S410007700 | KRW (원) |
| 수정주가(현금배당포함)_KOSDAQ | Adjusted close, total return (KOSDAQ) | S410007700 | KRW (원) |

- **Sheets:** 4 (the doubled underscore in the third tab is the vendor's)
- **Columns:** 1,284 KOSPI + 2,785 KOSDAQ; **3,590 tickers actually carry
  prices** in-window (1,025 KOSPI, 2,551 KOSDAQ, 14 in both). The rest are
  master-table columns for names that delisted before the window opens.
- **Rows:** 5,332 sessions, **2005-01-03 to 2026-08-12**
- **Kind:** SSC
- **Observations:** 10,802,289 per convention — the two cover *exactly* the
  same (session, ticker) cells, so a price-return figure always has its
  total-return twin.
- **Adjusted close only.** No volume, market cap or share count, and no
  point-in-time market label. Adjusted open/high/low exists only in the
  currently-listed 상폐제외 pair (§10), never for a delisted name.
- **Values are rounded to the won.** Because both series are back-adjusted,
  a name that later split carries single-digit adjusted prices early in its
  history, where ₩1 quantisation is a percent-scale effect on the daily
  return. This is the dominant source of small disagreement against any
  independently built series.
- **A code is not a company: 58 columns hand over to a second occupant.** KRX
  reissues a 6-digit code once its first occupant is delisted and FnGuide keys a
  series by code, so both companies arrive in one column with a NaN gap between
  them. Differencing straight through the gap produces a median return of
  **+1,802 %**, topping out at +8,136,485 % — 54 of the 58 inside the
  2005--2024 window.
  `price_loader.py` marks the handovers in a **`segment`** column; difference
  within `['ticker', 'segment']`, never within `ticker` alone.
- **The extreme returns that survive segmenting are real KRX prints, not
  defects.** 52 one-session returns exceed **+100 %**, which KRX's ±30 % daily
  limit makes impossible for ordinary trading. Every one is a session the limit
  did not govern, and they come in two kinds:
  - **A halt priced at a nominal constant, then released.** `008080`
    에스와이코퍼레이션 sits at ₩1 on zero volume for twelve sessions and reopens at
    ₩67,000; `058550` 네오리소스 sits at ₩100 for a week and reopens at ₩320 on a
    12.5:1 감자 (`marcap` shows shares 68,996,138 → 5,519,691 that morning).
    Four rows go further and carry an outright **`0`** (`009280`, `013090`,
    `036840`, `038710`, all 2023) — the vendor writing a halt as a price rather
    than as NaN.
  - **정리매매**, where no price limit applies: `004230` 세신 runs
    ₩360 → ₩25 → ₩5 → ₩30 in six sessions before delisting the next day.

  Spot-checked against `marcap/`, FnGuide's adjusted value equals the raw close
  **exactly** in every case above — the series is faithful. What it cannot
  express is that a print was not tradeable, because it carries no volume and no
  halt flag. That is what `kr_marcap` (`Volume`, `ChangeCode`) and
  `kr_marcap.status.tradable_universe(date)` are for. Mask there; do not patch
  the prices.
- **Market transfers appear twice.** 14 tickers that moved KOSDAQ → KOSPI
  (신세계푸드, KTF, 신세계건설, …) are served their *whole* history under both
  market sheets at identical prices; `price_loader.py` collapses them
  and marks them `market == 'BOTH'`.
- **Survivorship-bias status:** **616 / 620 (99.4 %)** of genuine common
  KOSPI/KOSDAQ delistings since 2005 carry real prices — matching
  `short_sale_lending.xlsx`, and better than the investor-flow batch. All
  4 misses are closed-end funds or resource trusts (`037500` 굿라이프5,
  `042950` 미래코리아1, `094520` 맵스베트남1, `152550` 한국ANKOR유전), not
  ordinary commons; the last is already in
  `kr_marcap.universe.STRICT_COMMON_EXCLUDE`.

Loading:

```python
from fnguide_data.price_loader import load_price_panel
px = load_price_panel()      # date, ticker, market, adj_close_pr, adj_close_tr, segment

# `segment` numbers a code's listing spells — differencing across the boundary
# would compare two different companies that shared the 6-digit code.
px["ret"] = px.groupby(["ticker", "segment"])["adj_close_tr"].pct_change()
```

---

### 10. `raw/0_KOSPI 주가(상폐제외).xlsx` (292 MB) + `raw/0_KOSDAQ 주가(상폐제외).xlsx` (238 MB)

**Content:** adjusted **open / high / low / close**, one sheet per field, one
file per market. These are the only files in the package that carry adjusted
open, high or low — everything else here is close-only.

| Sheet | Item Code | Item Name |
|---|---|---|
| `KOSPI_수정시가` / `KOSDAQ_수정시가` | S410000650 | 수정시가(원) |
| `KOSPI_수정고가` / `KOSDAQ_수정고가` | S410000660 | 수정고가(원) |
| `KOSPI_수정저가` / `KOSDAQ_수정저가` | S410000670 | 수정저가(원) |
| `KOSPI_수정주가` / `KOSDAQ_수정주가` | S410000700 | 수정주가(원) |

- **Sheets:** 4 each. **Kind:** SSC. **Unit:** KRW, rounded to the won.
- **Rows:** **1998-12-28 to 2026-03-20** (`기간` = 19990101 →
  최근일자(20260320)) — six years deeper than `Price data.xlsx`, which starts
  2005-01-03. 1,002 codes carry a pre-2005 price, 1.19 M cells over 1,477
  extra sessions.
- **Columns:** 2,311 KOSPI; 1,815 KOSDAQ on the OHL sheets and **1,813** on
  `KOSDAQ_수정주가`.
- **Built 2026-03-23**, 13:27:06 → 15:06:51, one DataGuide session per sheet
  (row 1 `Refresh`). The 2026-06-07 mtime is when the copy landed here.
- **Universe filter: 상폐제외 (delisted excluded)** — the opposite of the "all
  codes" filter behind the other nine files, and the only two files in `raw/`
  pulled under it. Nothing in this package reads them; `price_loader.py` reads
  `Price data.xlsx`.

**Not every column is a stock — least of all in the KOSPI file.** Of its 2,311
codes, 1,716 are plain 6-digit KRX equity codes, **388 are `Q…` ETNs**, and 207
are 6-character alphanumeric new-format codes carrying both ETFs (`0043B0`
TIGER 머니마켓액티브) and ordinary companies (`0126Z0` 삼성에피스홀딩스). KOSDAQ is
1,779 plain + 34 alphanumeric, no ETNs. Code shape does not separate stock from
fund: of the 906 plain 6-digit codes that appear here and *not* in
`Price data.xlsx`, only **4** are in `kr_marcap.universe(kind='common')` — the
other 902 are ETFs and funds holding plain 6-digit codes. Filter against the
marcap universe, not against the code.

**The 상폐제외 filter holds, and the exceptions are code reuse.** 119 of the
4,126 codes appear in `kr_delisted/delisting_calendar.csv`: 12 delisted *after*
2026-03-20 (correctly live at pull time) and 107 before it. Of those 107, 102
are `is_genuine == 'N'` — the code survived a holdco conversion, market transfer
or rename (`035420` NHN → NAVER, `032640` LG텔레콤 → LG유플러스) — and 5 are
genuine delistings whose code was later reassigned to a different company
(`013890` 지누스, `037030` 파워넷, `101970` 우양에이치씨, `036220` 인포피아 →
오상헬스케어, `198940` 한주금속 → 한주라이트메탈). No column continues past its
occupant's delisting.

The live-column count climbs from 583 at end-1998 to 4,124 at the pull and its
largest single-session drop is −3 columns. That shape *is* the survivorship
bias: a survivorship-free panel sheds columns at every delisting, and this one
effectively never does. It
also rules out the `currently_listed/` cliff — 2023-10-20 → 2023-10-23 holds at
3,253 columns here, the same count the defective batch had immediately before it
lost ~1,400.

**Two sheets in the KOSDAQ file disagree about the universe.**
`KOSDAQ_수정주가` (built 15:06) is missing `000250` 삼천당제약 and `043090`
더테크놀로지, both present on the three OHL sheets built 14:37–14:57 and both
still listed — they are in `Price data.xlsx` five months later. `000250` is the
**first** data column of the OHL sheets, so stacking the four sheets by column
position shifts the entire KOSDAQ frame by one. Join on the row-9 code.

**Against `Price data.xlsx`, where the two pulls overlap** — 2,625 shared codes,
2005-01-03 to 2026-03-20, 8.87 M cells present in both; on the 2,577 with more
than 100 shared observations:

| | tickers | what it means |
|---|---:|---|
| identical to the won | 2,296 | the two pulls agree exactly |
| one exact constant ratio ≠ 1 | 24 | ×10, ×5, ×0.5, ×0.2 — a corporate action between 2026-03-20 and 2026-08-12 rescaled the whole back-adjusted history. Levels differ, returns do not. |
| ratio not constant | 257 | ₩1 rounding at two different anchors |

7.10 % of daily returns differ, but by a median of **0.56 bp** (p99 16.3 bp), and
the p99 falls with the price level — 15.9 bp for prices in ₩100–1,000 against
1.75 bp above ₩10,000, the ₩1-quantisation signature described in §9. So:
**pick one export and use it end to end.** Back-adjusted *levels* from different
pulls are not comparable for any name with an action in between, and splicing
two pulls injects rounding noise into every early session of a heavily split
name.

**Use them for** adjusted OHL, and for 1999–2004 adjusted close if a
survivor-only sample is acceptable. **Do not use them for** anything that needs
delisted names, or as a second opinion on `Price data.xlsx` — it is the same
vendor series at a different anchor, not an independent source.

---

## Investor Type Code Reference (CI20 prefix)

| Code Prefix | Korean | English | Files |
|---|---|---|---|
| CI2000 | 기관계 | Institutional Total | data0203 (buy), data0204 (sell) |
| CI2001 | 금융투자 | Securities/Brokerage Firms | data0204 |
| CI2002 | 보험 | Insurance Companies | data0204 |
| CI2003 | 투신 | Asset Mgmt / Mutual Funds | data0204 |
| CI2004 | 은행 | Banks | data0205 |
| CI2005 | 기타금융 | Other Financial Institutions | data0205 |
| CI2006 | 연기금등 | Pension Funds | data0206 |
| CI2007 | 기타법인 | Other Corporations | data0206 |
| CI2008 | 개인 | Individuals (Retail) | data0206 |
| CI2009 | 등록외국인 | Registered Foreigners | data0207 |
| CI2010 | 기타외국인 | Other Foreigners | data0207 |
| CI2031 | 사모펀드 | Private Funds | data0207 |
| CI2032 | 국가 | Government / National | data0208 |
| CI2099 | 전체 | Total (All Investors) | data0208 |

**Item code pattern:** `CI20[investor_group][1=buy, 2=sell][010=volume(shares), 020=amount(KRW)]`

## Missing Aggregates (Download Omissions)

Two aggregate items were not included in the download batch but **can be computed** from existing data:

### 전체 매수대금/매도대금 (Total Trading Amount)

Item codes `CI20991020` (전체 매수대금) and `CI20992020` (전체 매도대금) were not downloaded. Only 전체 수량 (volume) is present in data0208.

**Formula (canonical KRX classification):**
```
전체 = 기관계 + 개인 + 외국인계 + 기타법인
```
Where:
- **기관계** (data0203/0204) already includes: 금융투자, 보험, 투신, 은행, 기타금융, 연기금, 사모펀드, 국가
- **외국인계** = 등록외국인 + 기타외국인

**Important:** Do NOT add 국가 or 사모펀드 separately -- they are already included in the 기관계 aggregate.

### 외국인계 (All Foreigners Aggregate)

The pre-computed 외국인계 aggregate was not downloaded. It can be computed:
```
외국인계 = 등록외국인 + 기타외국인
```

**Note:** 기타외국인 data is NULL before 2003-12-01 (see "Investor Type Introduction Dates" below). For those periods, 외국인계 = 등록외국인 (since 기타외국인 did not exist as a category).

### Verification

Both formulas were verified by cross-checking against `qf_next/investor_data/` (which has pre-computed 전체 and 외국인계 from a separate FnGuide download covering 2020-01-02 to 2025-12-26, 5 stocks × 1,472 dates):
- All non-zero diffs were **exact multiples of 10,000원** — purely 만원 rounding artifacts from the reference data (stored in 만원 units)
- The fnguide component sums (all in 원) are the **more precise** values
- **Conclusion: manual summation is correct**

See `integrity_report.md` for full details.

## Investor Type Introduction Dates

Not all investor categories existed from the start of the dataset. The KRX introduced new classifications over time, so earlier dates have NULL values for categories that did not yet exist.

| Investor Type | First Data Date | Notes |
|---|---|---|
| 기관계, 금융투자, 보험, 투신, 은행, 기타금융, 기타법인, 개인, 등록외국인, 국가 | **2000-01-04** | Available from dataset start |
| 연기금등 | **2000-01-05** | Essentially from the start |
| **기타외국인 (Other Foreigners)** | **2003-12-01** | KRX introduced this classification on Dec 1, 2003 |
| **사모펀드 (Private Funds)** | **2008-06-23** | KRX introduced this classification in mid-2008 |

### 기타외국인 (Other Foreigners) -- introduced 2003-12-01

Before December 1, 2003, the KRX grouped all foreign investors under a single classification (code `9000`, "외국인"). On that date, per the amendment to Article 67 of the Enforcement Rules of the Market Operations Regulation (passed September 26, 2003), the KRX subdivided foreign investors into:

- **등록외국인 (Registered Foreigners, code `9000`):** Foreign investors with a formal foreign investment registration ID
- **기타외국인 (Other Foreigners, code `9001`):** Unregistered foreigners, foreign corporations without an ID, or other foreign entities

**Implications for data processing:**
- For dates **before 2003-12-01**: 기타외국인 values are NULL. Treat 등록외국인 as the total foreign investor figure (외국인계 = 등록외국인).
- For dates **from 2003-12-01 onward**: 외국인계 = 등록외국인 + 기타외국인.

### 사모펀드 (Private Funds) -- introduced 2008-06-23

사모펀드 was separated out from 기관계 as a distinct reporting category in mid-2008. Values are NULL before this date. Note that 사모펀드 is included in the 기관계 aggregate, so its introduction does not affect the 기관계 total -- only the granularity of the breakdown.

## Known Data Quality Notes

1. **Sheet tab names corrected:** Truncated, misspelled, and misleading sheet tab names have been fixed in-place. Row 13 (Item Name) remains the authoritative source.
2. **Empty sheets:** data0204/Sheet16, data2\_0203/Sheet13 are empty -- skip these.
3. **NULL values:** Stocks not yet listed have None/NaN. Delisted stocks present in the universe (e.g. A117930 한진해운) carry values up to their delisting date and NaN afterward. 기타외국인 and 사모펀드 are NULL before their respective introduction dates (see above).
4. **Survivorship bias:** all files were pulled with DataGuide's "all codes" filter — **effectively survivorship-bias-free** for KOSPI/KOSDAQ common stocks (~90% of genuine delistings present, ~99% from 2021+). Each delisted ticker carries data through its delisting date and goes NaN after. See `DELISTED_COVERAGE.md` for the full breakdown.
5. **Slight column count differences:** Files downloaded on different dates have slightly different stock counts (3,903 vs 3,905).
6. **Date column differences:** Row counts vary slightly (6,446--6,453) across investor trading files due to different download end dates (Feb 3--12, 2026).

## Verification

- Open each file with `pd.read_excel(..., sheet_name=None, nrows=15)` to confirm header structure
- Verify row 9 (Symbol) contains stock tickers starting with "A"
- Verify row 13 (Item Name) matches the documented metric names
- Spot-check numeric values are reasonable (e.g., Samsung trading volumes in hundreds of thousands)
