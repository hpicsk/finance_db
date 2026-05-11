# Delisted-ticker coverage in marcap

**Verified 2026-04-22:** marcap **includes delisted tickers** (no survivorship bias).
Each delisted ticker is present in its year file with rows up to the last trading
day before the official delisting date.

## Evidence

Compared against `~/finance_db/kr_delisted/delisting_calendar.csv` (KIND-sourced delisting
dates for KOSPI + KOSDAQ, 2005–2025, 1768 rows).

- **11 targeted samples** — all present, last `Date` = delisting_date − 1 trading day:
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

## Caveats

- Only 6-digit common-stock-style codes were tested. Non-standard 7–8 digit codes
  in the delisting calendar (preferreds, rights, funds, bonds) were not verified
  here.
- Verification used `marcap-{year}.parquet` files; behavior is assumed identical
  for the upstream `.csv.gz` files in `data/`.

## Reproduce

```python
import pandas as pd
cal = pd.read_csv('~/finance_db/kr_delisted/delisting_calendar.csv', dtype={'ticker': str})
df  = pd.read_parquet('~/finance_db/marcap/data/marcap-2025.parquet')
# For any row r in cal: df[df.Code.str.zfill(6) == r.ticker].Date.max()
# should equal r.delisting_date − 1 trading day.
```
