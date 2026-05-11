# Korean delisted-equity universe

Point-in-time calendar and data loader for Korean stocks delisted between
2005-01-02 and 2025-10-23. Built for survivorship-bias-free cross-sectional
analysis.

## Canonical sources

| Data | Source | Path |
|---|---|---|
| Daily OHLCV, Volume, Amount, Marcap, Stocks | marcap (KRX 시가총액) | `~/finance_db/marcap/data/marcap-YYYY.parquet` |
| Delisting date, reason, market | KIND `investwarn/delcompany.do` | embedded in `delisting_calendar.csv` |

Prices are **unadjusted** — matches KRX's raw historical storage. Adjust for
splits/dividends only when you need a continuous series (use returns, not levels).

## Cross-source joins (for analyses needing more than OHLCV/marcap)

The tickers in this calendar can be joined to `~/finance_db/fnguide_data/` on
`"A" + ticker` (fnguide uses the A-prefix convention in row 9 of its headers):

- **Investor-category daily flow** — `~/finance_db/fnguide_data/data0203`–`data0208.xlsx`.
  ~90% coverage of KOSPI/KOSDAQ common delistings in this calendar (536/592).
  Each column ends on the delisting date.
- **Annual consolidated financials (IFRS-C)** + monthly market cap —
  `~/finance_db/fnguide_data/data2_0203.xlsx`. Same ~90% coverage. **Truncate at
  `delisting_date.year - 1`** before merging — the 6-digit KRX code may have
  been reassigned to a later listing whose financials will otherwise bleed in.
- **Main-entity financials (IFRS-M), adjusted prices, daily market cap,
  short-selling** — `~/finance_db/fnguide_data/currently_listed/` batch covers **0%** of delisted
  names. For prices / marcap use this directory. For IFRS-M financials on
  delisted names, fall back to DART (`corp_code`). No fnguide source exists
  for delisted short-selling / lending history.
- **Always-missing in fnguide:** KONEX (~2.6%), preferred shares (~0.9%), and
  specialty funds (선박투자/리츠/호, ~2.9%) — usually excluded on
  methodological grounds anyway.

Full breakdown with measured numbers: `~/finance_db/fnguide_data/DELISTED_COVERAGE.md`.

## Files

```
delisting_calendar.csv      Canonical universe: 1,118 tickers × 6 cols
                            (ticker, name, market, delisting_date, reason, is_genuine)
delisted_loader.py          load_delisted(ticker) / universe() API
```

## Usage

```python
from delisted_loader import load_delisted, universe

# Point-in-time analysis universe (genuine delistings only)
cal = universe(genuine_only=True)                 # 948 rows
# By market: KOSDAQ 592, KOSPI 280, KONEX 76

# One ticker's full history (unadjusted, ends on last trading day before delisting)
df = load_delisted('005390')                      # 신성통상, delisted 2025-09-30
# cols: Date, Code, Name, Market, Open, High, Low, Close, Volume, Amount,
#       Marcap, Stocks, ChangeRate, Rank, Dept

# Rolling-window filter pattern
import pandas as pd
for D in pd.date_range('2020-01-01', '2025-10-23'):
    active = cal[pd.to_datetime(cal['delisting_date']) > D]
    # ... load prices for each ticker in `active`, run analysis ...
```

## Calendar schema

| Column | Meaning |
|---|---|
| `ticker` | 6-digit KRX code (zero-padded string) |
| `name` | Company name at delisting |
| `market` | KOSPI / KOSDAQ / KONEX |
| `delisting_date` | Official delisting date (first day the stock no longer trades) |
| `reason` | KRX-reported delisting reason (Korean) |
| `is_genuine` | `Y` for true delistings, `N` for exchange transfers and M&A absorptions |

## marcap coverage verification

**Verified 2026-04-22:** marcap **includes delisted tickers** (no survivorship
bias). Each delisted ticker is present in its year file with rows up to the last
trading day before the official delisting date. **1,118/1,118 (100%)** of
6-digit delisted tickers in this calendar were found.

### Evidence

Compared against `delisting_calendar.csv` (KIND-sourced delisting dates for
KOSPI + KOSDAQ, 2005–2025, 1,768 rows).

- **11 targeted samples** — all present, last `Date` = delisting_date − 1
  trading day:

  | ticker | name | delisted | last Date in marcap |
  |---|---|---|---|
  | 005600 | 중앙제지 | 2005-01-06 | 2005-01-05 |
  | 035780 | 그로웰텔레콤 | 2005-01-11 | 2005-01-10 |
  | 009220 | 그로웰전자 | 2005-01-19 | 2005-01-18 |
  | 007910 | 세원화성 | 2005-02-24 | 2005-02-23 |
  | 019590 | 에스유앤피 | 2025-09-08 | 2025-09-05 |
  | 024810 | 이화전기 | 2025-09-10 | 2025-09-09 |
  | 096040 | 이트론 | 2025-09-10 | 2025-09-09 |
  | 093230 | 이아이디 | 2025-09-11 | 2025-09-10 |
  | 010420 | 한솔피엔에스 | 2025-09-25 | 2025-09-24 |
  | 005390 | 신성통상 | 2025-09-30 | 2025-09-29 |

- **Stratified random sample of 152** 6-digit delisted tickers across 5-year
  buckets from 2005–2025 → **152/152 (100%) found** in the year-of-delisting
  parquet.

### Caveats

- Only 6-digit common-stock-style codes were tested. Non-standard 7–8 digit
  codes in the delisting calendar (preferreds, rights, funds, bonds) were not
  verified here.
- Verification used `marcap-{year}.parquet` files; behavior is assumed
  identical for the upstream `.csv.gz` files in `data/`.

### Reproduce

```python
import pandas as pd
cal = pd.read_csv('~/finance_db/kr_delisted/delisting_calendar.csv', dtype={'ticker': str})
df  = pd.read_parquet('~/finance_db/marcap/data/marcap-2025.parquet')
# For any row r in cal: df[df.Code.str.zfill(6) == r.ticker].Date.max()
# should equal r.delisting_date − 1 trading day.
```

## Methodology notes

1. **Three-way classification of KIND's 1,181 delisting events:**
   - *Transfer* (100): KOSDAQ↔KOSPI migration — stock still trades, excluded via `is_genuine=N`
   - *Merger/absorption* (~170 inc. 완전자회사화): shares swapped into acquirer —
     excluded via `is_genuine=N` (merger premia would contaminate avalanche analysis)
   - *Genuine* (948 in 6-digit universe): bankruptcy, audit refusal, voluntary delisting,
     etc. — this is what you want.

2. **Scope exclusions:**
   - Warrants / rights / ETN / funds (7-8 char codes) — dropped from universe because
     (a) marcap doesn't carry them, (b) their limited-life structure confounds survival
     analysis, (c) they trade on underlying behavior, not their own fundamentals.
   - 184 KONEX delistings are kept (market=`KONEX`) but filter them out if your
     analysis targets KOSPI+KOSDAQ only.
   - 2 pre-2006 bankruptcies (`013890 지누스`, `037030 파워넷`) unrecoverable — neither
     FDR's KRX-DELISTING nor pykrx's archive reaches them.

3. **Why not DART?** DART's `corpCode.xml` doesn't distinguish delisted from never-
   listed, and its disclosure search is noisier than KIND's clean delisting-event
   table. DART remains the right tool for fundamentals, shareholder changes, and
   corporate-action flags — just not for building this calendar.

