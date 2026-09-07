# Delisted-ticker coverage in fnguide_data

**Verified 2026-05-28** (investor-flow + IFRS-C files);
**`fnguide_short-lending-float_20260615.xlsx` verified 2026-06-17.** The Excel
sheets in this directory (`raw/fnguide_investor_*`,
`raw/fnguide_financials_annual_20260219.xlsx`,
`raw/fnguide_short-lending-float_20260615.xlsx`) are **effectively
survivorship-bias-free for KOSPI/KOSDAQ common stocks**. With the common-stock
filter of `test_assertions.py::_is_common` (excludes ETFs, SPACs, preferred,
KONEX, REITs, ship/specialty funds) applied to the marcap universe:

- **Live universe:** 2,547 / 2,551 (**99.8 %**) marcap commons as of
  2026-02-20 have a column in `fnguide_investor_inst-buy_20260214`. The 4
  exceptions are infrastructure / real-estate / resource trusts (`088980`
  맥쿼리인프라, `415640` KB발해인프라, `094800` 맵스리얼티, `152550` 한국ANKOR유전). A stricter
  common-stock definition, one that drops those four trust-like issuers, gets
  **100 %** agreement with FnGuide's master table.
- **Delisted universe:** 570 / 625 (**91.2 %**) of common-kind
  genuine delistings have a column, rising to **99.2 %** for delistings
  in 2021 onward (118 / 119). The stricter definition no longer changes that
  figure:
  `152550` 한국ANKOR유전 was reclassified `is_genuine = N` by the 2026-08-23
  DART pass (투자회사 dissolution, not a business failure), so the resource
  trust never enters the genuine denominator in the first place. The single
  post-2021 miss (`038160` 팍스넷, delisted 2021-08-23, 감사의견 거절) is an
  ordinary FnGuide coverage hole, not a trust-like issuer. Older missing names
  are FnGuide's master-table purge, documented in [Caveat 2](#2-older-delisting-purge-60-common-names-missing-from-the-investor-flow) below.
- **`fnguide_short-lending-float_20260615.xlsx` (short-selling / lending /
  free-float):** **622 / 625 (99.5 %)** of genuine common KOSPI/KOSDAQ
  delistings have a column — higher than the investor-flow batch because this
  export used a longer FnGuide retention window (≥99 % in every year-bucket
  back to 2005, vs the investor-flow batch's gradual erosion). The 3 misses
  are all closed-end funds (`037500` 굿라이프5, `042950` 미래코리아1, `094520` 맵스베트남1).
  Universe: 1,284 KOSPI + 2,773 KOSDAQ = 4,041 tickers, split into per-market
  sheets.

- **`fnguide_price_adjclose_20260813.xlsx` (수정주가 + 수정주가(현금배당포함)):** **622 /
  625 (99.5 %)** of genuine common KOSPI/KOSDAQ delistings since 2005 carry
  real prices — the same retention window as
  `fnguide_short-lending-float_20260615.xlsx`, and **119 / 119 (100 %)** since
  2021. All 3 misses are closed-end funds (`037500` 굿라이프5, `042950` 미래코리아1,
  `094520` 맵스베트남1), not ordinary commons. Universe: 1,284 KOSPI + 2,785 KOSDAQ
  columns, of which 3,590 tickers carry prices in the 2005-01-03 – 2026-08-12
  window. The coverage figure is asserted in `test_assertions.py`
  (`test_fnguide_price_delisted_coverage`), because a re-pull under the
  "delisted excluded" (상폐제외) filter would drop every delisted name silently.

For most analyses that stay within these files, you do **not** need to
merge in an external delisted-data source.

The driver is the **DataGuide universe filter** chosen at export time:
this batch was pulled with "all codes" (전체 / 상폐 포함), which
retains delisted names for as long as FnGuide keeps them in the master
code table. A historical `raw/currently_listed/` sub-batch pulled with
the "delisted excluded" (상폐제외) filter had 0% delisted coverage and was
removed — see project history if you need that context. The two
`raw/0_*(상폐제외)` files still in the tree were pulled that way and carry
the same 0% by construction; see README.md §10. **If you
re-pull additional metrics from DataGuide, choose the "all codes"
filter.**

## Summary — what this package carries for delisted names

Dimensions this package does not carry at all are mapped in the repo root's
`README.md`, together with the coverage each of those sources verifies for
itself. Rates are not repeated here: they move when the source that owns them
is refreshed, and a second copy would go stale silently.

| Dimension | Source for delisted names | Delisted-common coverage |
|---|---|---:|
| Daily adjusted close, price + total return | `fnguide_data/raw/fnguide_price_adjclose_20260813.xlsx` (2005+) | 99.5 % |
| Investor-category daily flow | `fnguide_data/raw/fnguide_investor_*.xlsx` | 91.2 % (99.2 % since 2021) |
| Annual consolidated financials (IFRS-C) | `fnguide_data/raw/fnguide_financials_annual_20260219.xlsx` | 91.2 % (99.2 % since 2021) |
| Monthly market cap | **none — the 시가총액 sheet came back empty** (README.md §7) | 0 % |
| Daily short-sale balance / turnover | `fnguide_data/raw/fnguide_short-lending-float_20260615.xlsx` | 99.5 % (100 % since 2021) |
| Daily securities-lending balance | `fnguide_data/raw/fnguide_short-lending-float_20260615.xlsx` | 99.5 % (100 % since 2021) |
| Daily free-float ratio | `fnguide_data/raw/fnguide_short-lending-float_20260615.xlsx` | 99.5 % (100 % since 2021) |

Join key: `kr_delisted` 6-digit ticker ↔ `"A" + ticker` in fnguide
sheets (row 9 of the 14-row header).

## Evidence

Measured against the 1,018 genuine delistings in
`~/research/finance_db/kr_delisted/delisting_calendar.csv` (`is_genuine == "Y"`),
bucketed by security type — the common bucket is the one every figure above is
quoted on, and the one `test_assertions.py::_is_common` reproduces:

| Bucket | n | in `fnguide_investor_inst-buy_20260214` flow |
|---|---:|---:|
| Common KOSPI/KOSDAQ | 625 | 570 (**91.2 %**) |
| SPAC | 122 | 122 (100 %) |
| Preferred (code[-1] != '0') | 118 | 0 (0 %) |
| KONEX | 81 | 1 (1.2 %) |
| REIT (리츠 / REIT) | 7 | 0 (0 %) |
| Specialty fund (선박투자 / 호 / MF) | 65 | 2 (3.1 %) |

The investor-flow and IFRS-C files share the same 3,902-ticker universe
(exported together with the "all codes" filter). The non-common buckets
are excluded on methodological grounds (see Caveat 3) — not
data-availability ones.

### Common-KOSPI/KOSDAQ coverage by delisting year

After applying the common filter (which strips ETFs, KONEX, preferred,
SPAC, REIT, and specialty-fund buckets), the
remaining gap is a clean function of FnGuide's master-table retention
window — most recent delistings are covered, older ones gradually drop:

| Delisting year | Common KOSPI/KOSDAQ | In investor-flow |
|---|---:|---:|
| 2005–2010 | 254 | 230 (90.6 %) |
| 2011–2014 | 167 | 144 (86.2 %) |
| 2015–2020 | 85 | 78 (91.8 %) |
| 2021–2026 | 119 | 118 (**99.2 %**) |

### Post-2021 misses — the strict exclusion list is complete

Auditing the single missing name confirms no additional infrastructure /
real-estate / resource-trust commons need to be added to the strict
common-stock exclusion list:

| Ticker | Name | Delisted | Reason | Classification |
|---|---|---|---|---|
| `038160` | 팍스넷 | 2021-08-23 | 감사의견 거절 | genuine common — irreducible FnGuide hole |

Scanning all 55 fnguide-missing common delistings (pre- and post-2021)
for trust-like names (`인프라|리얼티|유전|선박|신탁|TRUST|자원|뮤추|REIT|맥쿼리|펀드|투자회사|투융자`)
now returns none. `152550` 한국ANKOR유전 used to be the one hit; the
2026-08-23 DART pass reclassified it `is_genuine = N` (투자회사 dissolution),
so it leaves the genuine denominator before the strict list is even consulted —
which is why the strict and default post-2021 figures are now the same
number. The 1 remaining miss is not structural.

### Sample data ranges (investor-flow, 기관 매수수량)

Column `A<ticker>` in `fnguide_investor_inst-buy_20260214.xlsx` / 매수수량(기관),
end date is the last trading day on or before the delisting date:

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

The 6-digit KRX code for a delisted company is eventually reassigned to a
later listing. `fnguide_financials_annual_20260219.xlsx` stores data under the
current occupant of each code, so querying a delisted ticker may return
financials from a completely different company that happens to share the code
today. Observed examples:

- `A066930 에스디` — delisted 2010-06-29, but
  `fnguide_financials_annual_20260219` returns 영업이익 values for years
  1999..2024.
- `A111820 지유온` — delisted 2021-09-30, 영업이익 values through 2024.

**Mitigation:** truncate each series at `delisting_date.year - 1`
before merging. Clean examples from the same sample:

- `A065410 지엔텍홀딩스` delisted 2010-05-05 → 영업이익 1999..2009 (clean).
- `A024810 이화전기` delisted 2025-09-10 → 영업이익 1999..2024 (clean).
- `A095300 엔에스브이` delisted 2017-09-12 → 영업이익 2002..2016 (clean).

This contamination **does not** affect daily data (investor-flow,
monthly market cap) because those series naturally end at the delisting
date. It is specific to annual financial statements.

### 2. Older-delisting purge (55 common names missing from the investor-flow)

FnGuide appears to retain delisted codes in its "all codes" export for
a few years, then drop them. Examples of common-stock delistings absent
from `fnguide_investor_inst-buy_20260214`:

| Ticker | Name | Delisted |
|---|---|---|
| 001310 | 풍림산업 | 2012-05-18 |
| 074000 | 엠텍비젼 | 2014-03-27 |
| 006440 | 한일건설 | 2013-04-16 |
| 068420 | 엔터미디어 | 2013-04-06 |
| 037640 | 지에스엔텍 | 2005-01-24 |

Coverage is near-complete for delistings from ~2021 onward (99.2 %),
gradually erodes for earlier years, and recovers slightly in the oldest
bucket (2005–2010: 90.6 %) because that window is disproportionately
KOSPI with long-retained codes. The FnGuide export cutoff is not
documented; treat the 55 missing names as irrecoverable without a
fresh export including delisted codes — 54 of them predate 2021.

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
from fnguide_data.test_assertions import _is_common

# 1. Delisted universe — restrict to common KOSPI/KOSDAQ only
cal = pd.read_csv("~/research/finance_db/kr_delisted/delisting_calendar.csv", dtype={"ticker": str})
cal = cal[(cal["is_genuine"] == "Y") & (cal["market"].isin(["KOSPI", "KOSDAQ"]))]
# Drop preferred / SPAC / REIT / fund. Preferred is keyed on the code's
# terminal digit, so a common whose name merely ends in 우 (대우 / 연우) is
# NOT dropped:
cal = cal[[_is_common(t, n, m)
           for t, n, m in zip(cal["ticker"], cal["name"], cal["market"])]].copy()
cal["fn_ticker"] = "A" + cal["ticker"]

# 2. Load investor-flow sheet (institutional buy volume example)
src = ("~/research/finance_db/fnguide_data/raw/"
       "fnguide_investor_inst-buy_20260214.xlsx")
meta = pd.read_excel(src, sheet_name="매수수량(기관)",
                     header=None, nrows=14)
flow = pd.read_excel(src, sheet_name="매수수량(기관)",
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

FNG = "/home/st/research/finance_db/fnguide_data/raw"
CAL = "/home/st/research/finance_db/kr_delisted/delisting_calendar.csv"

def universe(path, sheet):
    m = pd.read_excel(path, sheet_name=sheet, header=None, nrows=14)
    return set(m.iloc[8, 1:].tolist())

flow_u  = universe(f"{FNG}/fnguide_investor_inst-buy_20260214.xlsx",   "매수수량(기관)")
ifrsc_u = universe(f"{FNG}/fnguide_financials_annual_20260219.xlsx", "영업이익")

cal = pd.read_csv(CAL, dtype={"ticker": str})
cal["delisting_date"] = pd.to_datetime(cal["delisting_date"])
cal = cal[cal["is_genuine"] == "Y"].copy()
cal["fn_ticker"] = "A" + cal["ticker"]

from fnguide_data.test_assertions import _is_common
# Preferred is keyed on the code's terminal digit, so a common whose name
# merely ends in 우 (대우 / 연우) stays common.
cal["common"] = [_is_common(t, n, m)
                 for t, n, m in zip(cal["ticker"], cal["name"], cal["market"])]

cal["in_flow"]  = cal["fn_ticker"].isin(flow_u)
cal["in_ifrsc"] = cal["fn_ticker"].isin(ifrsc_u)

# Note: the `flow`/`ifrs_c` counts for KONEX (≈2) are 6-digit code
# collisions with KOSPI/KOSDAQ names, not real coverage of the
# KONEX-listed company.

print(cal.groupby("common").agg(
    n=("ticker", "size"),
    flow=("in_flow", "sum"),
    ifrs_c=("in_ifrsc", "sum"),
))
```

The common / non-common split is what every figure in this file rests on, and
`test_assertions.py::_is_common` is what reproduces it (625 common delistings,
99.8 % live-universe coverage) — it is the same filter
`test_fnguide_price_delisted_coverage` asserts against, so the figure here and
the one the suite checks cannot drift apart. The finer six-bucket breakdown
under Evidence was measured once with a full security-type classifier;
re-deriving that split needs one.

Drift in these numbers means either the underlying exports were
re-downloaded (FnGuide may extend the delisted-code retention window
in a newer pull) or the filter needs updating for new name patterns.
