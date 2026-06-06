# Delisted-ticker coverage in fnguide_data

**Verified 2026-05-28.** The Excel sheets in this directory
(`raw/data0203`–`data0208`, `raw/data2_0203`) are **effectively
survivorship-bias-free for KOSPI/KOSDAQ common stocks**. With the
`kr_marcap.classify` common-stock filter (excludes ETFs, SPACs,
preferred, KONEX, REITs, ship/specialty funds) applied to the marcap
universe:

- **Live universe:** 2,544 / 2,548 (**99.8 %**) marcap commons as of
  2026-02-20 have a column in `data0203`. The 4 exceptions are
  infrastructure / real-estate / resource trusts (`088980` 맥쿼리한국
  인프라투융자회사, `415640` KB발해인프라, `094800` 맵스미래에셋맵스리얼티1,
  `152550` 한국ANKOR유전). They are bundled into the `STRICT_COMMON_EXCLUDE`
  set in `kr_marcap.universe`; call
  `kr_marcap.universe(date, 'common', strict=True)` to drop them and
  get **100 %** agreement with FnGuide's master table.
- **Delisted universe:** 563 / 619 (**91.0 %**) of common-kind
  genuine delistings have a column, rising to **98.2 %** for delistings
  in 2021 onward (112 / 114). With `strict=True` the post-2021 figure
  becomes **112 / 113 (99.1 %)** — one of the 2 misses (`152550`
  한국ANKOR유전, delisted 2026-05-04) is the already-excluded resource
  trust. The single remaining miss (`038160` 팍스넷, delisted 2021-08-23,
  감사의견 거절) is an ordinary FnGuide coverage hole, not a
  trust-like issuer. Older missing names are FnGuide's master-table
  purge, documented in [Caveat 2](#2-older-delisting-purge-60-common-names-missing-from-the-investor-flow) below.

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

Join key: `kr_delisted` 6-digit ticker ↔ `"A" + ticker` in fnguide
sheets (row 9 of the 14-row header).

## Evidence

Measured against the 1,004 genuine delistings in
`~/finance_db/kr_delisted/delisting_calendar.csv` (`is_genuine == "Y"`),
bucketed via `kr_marcap.classify`:

| Bucket | n | in `data0203` flow |
|---|---:|---:|
| Common KOSPI/KOSDAQ | 619 | 563 (**91.0 %**) |
| SPAC | 117 | 117 (100 %) |
| Preferred (우/우B/1우/MF + non-zero last digit) | 120 | 1 (0.8 %) |
| KONEX | 79 | 1 (1.3 %) |
| REIT (리츠 / REIT) | 5 | 0 (0 %) |
| Specialty fund (선박투자 / 호) | 64 | 2 (3.1 %) |

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
| 2005–2010 | 253 | 229 (90.5 %) |
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

# 1. Delisted universe — restrict to common KOSPI/KOSDAQ only
cal = pd.read_csv("~/finance_db/kr_delisted/delisting_calendar.csv", dtype={"ticker": str})
cal = cal[(cal["is_genuine"] == "Y") & (cal["market"].isin(["KOSPI", "KOSDAQ"]))]
# Drop preferred, SPAC, specialty funds by name suffix:
is_pref      = cal["name"].str.endswith(("우", "우B", "1우", "2우", "MF"))
is_spac      = cal["name"].str.contains("스팩|SPAC", case=False, na=False)
is_fund      = cal["name"].str.endswith("호") | cal["name"].str.contains("선박투자|리츠")
cal = cal[~(is_pref | is_spac | is_fund)].copy()
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

def bucket(row):
    nm, mkt = str(row["name"]), row["market"]
    if mkt == "KONEX": return "KONEX"
    if "스팩" in nm or "SPAC" in nm.upper(): return "SPAC"
    if nm.endswith(("우", "우B", "1우", "2우", "MF")): return "Preferred/Fund"
    if nm.endswith("호") or "선박투자" in nm or "리츠" in nm: return "Specialty fund"
    return "Common"
cal["bucket"] = cal.apply(bucket, axis=1)

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

Expected output uses the simple inline bucketing above and will give
slightly different counts than `kr_marcap.classify` (which catches more
preferreds via the `code[-1] != '0'` rule and treats REITs as a
separate kind). For the canonical headline numbers — 619 common
delistings, 99.8 % live-universe coverage — use `kr_marcap.classify`
directly:

```python
import sys, pandas as pd
sys.path.insert(0, '/home/st/finance_db/kr_marcap')
from classify import classify_ticker
cal = pd.read_csv('/home/st/finance_db/kr_delisted/delisting_calendar.csv',
                  dtype={'ticker': str})
cal['kind'] = cal.apply(
    lambda r: classify_ticker(r['ticker'], r['name'], r['market']), axis=1)
```

Drift in these numbers means either the underlying exports were
re-downloaded (FnGuide may extend the delisted-code retention window
in a newer pull) or the classifier needs updating for new name
patterns.
