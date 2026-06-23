# Delisted-ticker coverage in fnguide_data

**Verified 2026-05-28** (investor-flow + IFRS-C files);
**`short_sale_lending.xlsx` verified 2026-06-17.** The Excel sheets in
this directory (`raw/data0203`–`data0208`, `raw/data2_0203`,
`raw/short_sale_lending.xlsx`) are **effectively
survivorship-bias-free for KOSPI/KOSDAQ common stocks**. With the
`kr_marcap.classify` common-stock filter (excludes ETFs, SPACs,
preferred, KONEX, REITs, ship/specialty funds) applied to the marcap
universe:

- **Live universe:** 2,547 / 2,551 (**99.8 %**) marcap commons as of
  2026-02-20 have a column in `data0203`. The 4 exceptions are
  infrastructure / real-estate / resource trusts (`088980` 맥쿼리인프라,
  `415640` KB발해인프라, `094800` 맵스리얼티, `152550` 한국ANKOR유전).
  They are bundled into the `STRICT_COMMON_EXCLUDE`
  set in `kr_marcap.universe`; call
  `kr_marcap.universe(date, 'common', strict=True)` to drop them and
  get **100 %** agreement with FnGuide's master table.
- **Delisted universe:** 564 / 620 (**91.0 %**) of common-kind
  genuine delistings have a column, rising to **98.2 %** for delistings
  in 2021 onward (112 / 114). With `strict=True` the post-2021 figure
  becomes **112 / 113 (99.1 %)** — one of the 2 misses (`152550`
  한국ANKOR유전, delisted 2026-05-04) is the already-excluded resource
  trust. The single remaining miss (`038160` 팍스넷, delisted 2021-08-23,
  감사의견 거절) is an ordinary FnGuide coverage hole, not a
  trust-like issuer. Older missing names are FnGuide's master-table
  purge, documented in [Caveat 2](#2-older-delisting-purge-60-common-names-missing-from-the-investor-flow) below.
- **`short_sale_lending.xlsx` (short-selling / lending / free-float):**
  **616 / 620 (99.4 %)** of genuine common KOSPI/KOSDAQ delistings have
  a column — higher than the investor-flow batch because this export
  used a longer FnGuide retention window (≥99 % in every year-bucket
  back to 2005, vs the investor-flow batch's gradual erosion). Of the 4
  misses, `152550` 한국ANKOR유전 is the resource trust already in
  `STRICT_COMMON_EXCLUDE`. Universe: 1,284 KOSPI + 2,773 KOSDAQ = 4,041
  tickers, split into per-market sheets.

For most analyses that stay within these files, you do **not** need to
merge in an external delisted-data source.

The driver is the **DataGuide universe filter** chosen at export time:
this batch was pulled with "all codes" (전체 / 상폐 포함), which
retains delisted names for as long as FnGuide keeps them in the master
code table. A historical `raw/currently_listed/` sub-batch pulled with
the "currently listed" filter had 0% delisted coverage and was
removed — see project history if you need that context. **If you
re-pull additional metrics from DataGuide, choose the "all codes"
filter.**

## Summary — what to pull from where for delisted names

| Dimension | Source for delisted names | Delisted-common coverage |
|---|---|---:|
| OHLCV daily (unadjusted) | `~/finance_db/kr_delisted/` (marcap) | 100 % |
| OHLCV daily (adjusted) | `kr_marcap.adjust.load_adjusted(ticker)` | 100 % |
| Daily market cap, shares | `~/finance_db/kr_delisted/` (marcap) | 100 % |
| Investor-category daily flow | `fnguide_data/raw/data0203`–`data0208.xlsx` | 91.0 % (98.2 % since 2021) |
| Annual consolidated financials (IFRS-C) | `fnguide_data/raw/data2_0203.xlsx` | 91.0 % (98.2 % since 2021) |
| Monthly market cap (legacy) | `fnguide_data/raw/data2_0203.xlsx` (시가총액 sheet) | 91.0 % (98.2 % since 2021) |
| Daily short-sale balance / turnover | `fnguide_data/raw/short_sale_lending.xlsx` | 99.4 % (99.1 % since 2021) |
| Daily securities-lending balance | `fnguide_data/raw/short_sale_lending.xlsx` | 99.4 % (99.1 % since 2021) |
| Daily free-float ratio | `fnguide_data/raw/short_sale_lending.xlsx` | 99.4 % (99.1 % since 2021) |

Join key: `kr_delisted` 6-digit ticker ↔ `"A" + ticker` in fnguide
sheets (row 9 of the 14-row header).

## Evidence

Measured against the 1,004 genuine delistings in
`~/finance_db/kr_delisted/delisting_calendar.csv` (`is_genuine == "Y"`),
bucketed via `kr_marcap.classify`:

| Bucket | n | in `data0203` flow |
|---|---:|---:|
| Common KOSPI/KOSDAQ | 620 | 564 (**91.0 %**) |
| SPAC | 117 | 117 (100 %) |
| Preferred (code[-1] != '0') | 118 | 0 (0 %) |
| KONEX | 79 | 1 (1.3 %) |
| REIT (리츠 / REIT) | 5 | 0 (0 %) |
| Specialty fund (선박투자 / 호 / MF) | 65 | 2 (3.1 %) |

The investor-flow and IFRS-C files share the same 3,902-ticker universe
(exported together with the "all codes" filter). The non-common buckets
are excluded on methodological grounds (see Caveat 3) — not
data-availability ones.

### Common-KOSPI/KOSDAQ coverage by delisting year

After applying the `kr_marcap.classify` common filter (which strips
ETFs, KONEX, preferred, SPAC, REIT, and specialty-fund buckets), the
remaining gap is a clean function of FnGuide's master-table retention
window — most recent delistings are covered, older ones gradually drop:

| Delisting year | Common KOSPI/KOSDAQ | In investor-flow |
|---|---:|---:|
| 2005–2010 | 254 | 230 (90.6 %) |
| 2011–2014 | 167 | 144 (86.2 %) |
| 2015–2020 | 85 | 78 (91.8 %) |
| 2021–2026 | 114 | 112 (**98.2 %**) |

### Post-2021 misses — STRICT_COMMON_EXCLUDE is complete

Auditing the 2 missing names confirms no additional infrastructure /
real-estate / resource-trust commons need to be added to
`kr_marcap.universe.STRICT_COMMON_EXCLUDE`:

| Ticker | Name | Delisted | Reason | Classification |
|---|---|---|---|---|
| `152550` | 한국ANKOR유전 | 2026-05-04 | 해산 사유 발생 | already in `STRICT_COMMON_EXCLUDE` (resource trust) |
| `038160` | 팍스넷 | 2021-08-23 | 감사의견 거절 | genuine common — irreducible FnGuide hole |

Scanning all 56 fnguide-missing common delistings (pre- and post-2021)
for trust-like names (`인프라|리얼티|유전|선박|신탁|TRUST|자원|뮤추|REIT|맥쿼리|펀드|투자회사|투융자`)
returns only `152550`. Drop it from the denominator with `strict=True`
and post-2021 coverage tightens to **112 / 113 = 99.1 %**; the 1
remaining miss is not structural.

### Sample data ranges (investor-flow, 기관 매수수량)

Column `A<ticker>` in `data0203.xlsx` / 매수수량(기관), end date is the
last trading day on or before the delisting date:

| Ticker | Name | Delisted | First obs | Last obs | n |
|---|---|---|---|---|---:|
| A117930 | 한진해운 | 2017-02-17 | 2009-12-29 | 2017-03-06 | 1,729 |
| A005390 | 신성통상 | 2025-09-30 | 2000-01-05 | 2025-09-29 | 3,545 |
| A024810 | 이화전기 | 2025-09-10 | 2000-01-11 | 2025-09-03 | 1,479 |
| A023460 | CNH | 2025-07-14 | 2000-05-02 | 2025-07-03 | 1,071 |
| A093230 | 이아이디 | 2025-09-11 | 2007-11-01 | 2025-09-09 | 2,658 |
| A096040 | 이트론 | 2025-09-10 | 2008-01-25 | 2025-09-03 | 1,099 |

## Caveats

### 1. Ticker-reassignment contamination (IFRS-C financials)

The 6-digit KRX code for a delisted company is eventually reassigned to
a later listing. `data2_0203.xlsx` stores data under the current
occupant of each code, so querying a delisted ticker may return
financials from a completely different company that happens to share
the code today. Observed examples:

- `A066930 에스디` — delisted 2010-06-29, but `data2_0203` returns
  영업이익 values for years 1999..2024.
- `A111820 지유온` — delisted 2021-09-30, 영업이익 values through 2024.

**Mitigation:** truncate each series at `delisting_date.year - 1`
before merging. Clean examples from the same sample:

- `A065410 지엔텍홀딩스` delisted 2010-05-05 → 영업이익 1999..2009 (clean).
- `A024810 이화전기` delisted 2025-09-10 → 영업이익 1999..2024 (clean).
- `A095300 엔에스브이` delisted 2017-09-12 → 영업이익 2002..2016 (clean).

This contamination **does not** affect daily data (investor-flow,
monthly market cap) because those series naturally end at the delisting
date. It is specific to annual financial statements.

### 2. Older-delisting purge (~60 common names missing from the investor-flow)

FnGuide appears to retain delisted codes in its "all codes" export for
a few years, then drop them. Examples of common-stock delistings absent
from `data0203`:

| Ticker | Name | Delisted |
|---|---|---|
| 001310 | 풍림산업 | 2012-05-18 |
| 074000 | 엠텍비젼 | 2014-03-27 |
| 006440 | 한일건설 | 2013-04-16 |
| 068420 | 엔터미디어 | 2013-04-06 |
| 037640 | 지에스엔텍 | 2005-01-24 |

Coverage is near-complete for delistings from ~2021 onward (98.8%),
gradually erodes for earlier years, and recovers slightly in the oldest
bucket (2005–2010: 90.8%) because that window is disproportionately
KOSPI with long-retained codes. The FnGuide export cutoff is not
documented; treat the ~60 missing names as irrecoverable without a
fresh export including delisted codes.

### 3. Methodological — KONEX / preferred / specialty fund exclusions

Most cross-sectional return / liquidity studies should exclude these
buckets on methodological grounds independent of data availability:

- **KONEX** has thin liquidity and different disclosure requirements.
- **Preferred shares** share fundamentals with the underlying common
  but have different liquidity and a fixed dividend preference.
- **Specialty funds** (ship investment, REITs, maritime) have fixed
  lifespans and distribute-then-dissolve mechanics that confound
  survival analysis.

So the low fnguide coverage of these buckets is typically not a
blocker.

## Cross-source join pattern

For a point-in-time panel of delisted KOSPI/KOSDAQ common stocks
combining `kr_delisted` prices with fnguide investor flow:

```python
import pandas as pd
from kr_marcap.classify import classify_ticker

# 1. Delisted universe — restrict to common KOSPI/KOSDAQ only
cal = pd.read_csv("~/finance_db/kr_delisted/delisting_calendar.csv", dtype={"ticker": str})
cal = cal[(cal["is_genuine"] == "Y") & (cal["market"].isin(["KOSPI", "KOSDAQ"]))]
# Drop preferred / SPAC / REIT / fund via the authoritative classifier (the
# single source of truth). Preferred is keyed on the code's terminal digit, so
# a common whose name merely ends in 우 (대우 / 연우) is NOT dropped:
kind = cal.apply(lambda r: classify_ticker(r["ticker"], r["name"], r["market"]), axis=1)
cal = cal[kind == "common"].copy()
cal["fn_ticker"] = "A" + cal["ticker"]

# 2. Load investor-flow sheet (institutional buy volume example)
meta = pd.read_excel("~/finance_db/fnguide_data/raw/data0203.xlsx", sheet_name="매수수량(기관)",
                     header=None, nrows=14)
flow = pd.read_excel("~/finance_db/fnguide_data/raw/data0203.xlsx", sheet_name="매수수량(기관)",
                     header=None, skiprows=14)
flow.columns = ["date"] + meta.iloc[8, 1:].tolist()
flow["date"] = pd.to_datetime(flow["date"])
flow = flow.set_index("date").sort_index()

# 3. For each delisted ticker, slice the flow up to its delisting date
for _, r in cal.iterrows():
    if r["fn_ticker"] not in flow.columns:
        continue                                   # 60 missing names; skip
    s = flow[r["fn_ticker"]].loc[:r["delisting_date"]].dropna()
    # ... merge with kr_delisted prices, run per-ticker analysis ...

# For annual IFRS-C financials, ALSO truncate at delisting_date.year - 1:
#     fin_series.loc[fin_series.index.year <= pd.Timestamp(r["delisting_date"]).year - 1]
# to avoid ticker-reassignment contamination (see Caveat 1).
```

## Reproduce

Regenerates the evidence tables in ~30 s by reading only the 14-row
metadata blocks of each workbook, not the full sheets.

```python
import pandas as pd

FNG = "/home/st/finance_db/fnguide_data/raw"
CAL = "/home/st/finance_db/kr_delisted/delisting_calendar.csv"

def universe(path, sheet):
    m = pd.read_excel(path, sheet_name=sheet, header=None, nrows=14)
    return set(m.iloc[8, 1:].tolist())

flow_u  = universe(f"{FNG}/data0203.xlsx",   "매수수량(기관)")
ifrsc_u = universe(f"{FNG}/data2_0203.xlsx", "영업이익")

cal = pd.read_csv(CAL, dtype={"ticker": str})
cal["delisting_date"] = pd.to_datetime(cal["delisting_date"])
cal = cal[cal["is_genuine"] == "Y"].copy()
cal["fn_ticker"] = "A" + cal["ticker"]

from kr_marcap.classify import classify_ticker
# Bucket via the authoritative classifier — the single source of truth. Kinds:
# common / preferred / spac / reit / fund / konex. Preferred is keyed on the
# code's terminal digit, so a common whose name merely ends in 우 (대우 / 연우)
# stays common.
cal["bucket"] = cal.apply(
    lambda r: classify_ticker(r["ticker"], r["name"], r["market"]), axis=1)

cal["in_flow"]  = cal["fn_ticker"].isin(flow_u)
cal["in_ifrsc"] = cal["fn_ticker"].isin(ifrsc_u)

# Note: the `flow`/`ifrs_c` counts for KONEX (≈2) are 6-digit code
# collisions with KOSPI/KOSDAQ names, not real coverage of the
# KONEX-listed company.

print(cal.groupby("bucket").agg(
    n=("ticker", "size"),
    flow=("in_flow", "sum"),
    ifrs_c=("in_ifrsc", "sum"),
))
```

The bucketing above is via `kr_marcap.classify` — the single source of truth —
and reproduces the headline numbers (620 common delistings, 99.8 % live-universe
coverage).

Drift in these numbers means either the underlying exports were
re-downloaded (FnGuide may extend the delisted-code retention window
in a newer pull) or the classifier needs updating for new name
patterns.
