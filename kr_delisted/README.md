# Korean delisted-equity universe

Point-in-time calendar and data loader for Korean stocks delisted between
2005-01-02 and the latest run date. Built for survivorship-bias-free
cross-sectional analysis.

## Sources

The calendar is stitched together from three sources, each addressing a
specific gap in the others:

| Source | What it provides | Coverage |
|---|---|---|
| **KIND** `kind.krx.co.kr/investwarn/delcompany.do` | Delisting events: 6-digit ticker, name, market, date, reason | Main shares, 2005-01-02 → present (1,241 events as of 2026-05-11) |
| **marcap** `~/finance_db/marcap/data/marcap-YYYY.parquet` | Last-trade dates and OHLCV history for preferred shares not in KIND | Preferred / 신주 / 전환 tickers (codes not ending in '0'), 2005+ |
| **DART** `opendart.fss.or.kr` (via `OpenDartReader`) | Corporate-action filings that disambiguate dissolutions | Post-2001 main-share filings + entity-type names |

Daily OHLCV / volume / marcap / shares for every ticker in the calendar
come from the marcap parquets — prices are **unadjusted** (matches KRX's
raw history). Adjust for splits / dividends only if you need a continuous
series (use returns, not levels).

## Scope

**Included (1,359 rows in the current canonical CSV):**
- All 1,241 KIND delisting events for KOSPI / KOSDAQ / KONEX, 2005-01-02 onward.
- 118 preferred-share / 신주 / 전환 tickers recovered from marcap
  (codes ending in a non-zero digit, last-appearance date as proxy
  delisting date).

**Excluded by design:**
- Pre-2005 main-share delistings — KIND does not publish them.
- Warrants / rights / ETNs / ETFs / funds (7–8 character codes) — these
  carry limited-life structure that confounds survival analysis and are
  not in marcap's daily snapshot. Filter on `len(ticker) == 6`.
- KONEX issues if your analysis targets KOSPI + KOSDAQ only — keep them
  filterable via `market == 'KONEX'` (193 rows).

**Known unrecoverable gaps:**
- Pre-2005 preferred-share delistings. The regenerator's `start_date`
  filter excludes everything before 2005-01-01 to match KIND's coverage
  on the main-share side. A handful of 1997–2004 preferred-share rows
  (e.g. `032591 두일통신1신`, `033334 두림티앤씨전환`, both 1997-12-27) exist
  in older marcap parquets but are intentionally not included.

## Files

```
README.md                          (this file)
delisting_calendar.csv             canonical universe — output of build_delisting_calendar.py
                                   1,359 rows × 6 cols (ticker, name, market,
                                   delisting_date, reason, is_genuine)
delisting_calendar.kind.csv        intermediate KIND-only output of
                                   build_delisting_calendar.py --no-proxy;
                                   consumed by build_is_genuine_overrides.py
delisted_loader.py                 load_delisted(ticker) / universe() API
build_delisting_calendar.py        end-to-end regenerator (KIND + marcap + overrides)
build_is_genuine_overrides.py      DART + manual is_genuine refinement (run once;
                                   produces is_genuine_overrides.csv)
is_genuine_overrides.csv           80 override rows consumed by build_delisting_calendar.py
```

## Calendar schema

| Column | Meaning |
|---|---|
| `ticker` | 6-digit KRX code (zero-padded string) |
| `name` | Company name at delisting |
| `market` | `KOSPI` / `KOSDAQ` / `KONEX` |
| `delisting_date` | First day the stock no longer trades. For preferred-share proxies this is `last_date_in_marcap` (the previous trading day). |
| `reason` | KRX-reported delisting reason (Korean), verbatim from KIND. Preferred-share proxies carry `(not in KIND — proxy date from last-CSV-date)`. |
| `is_genuine` | `Y` for true delistings (bankruptcy, audit refusal, voluntary delisting, REIT maturity excluded — see below); `N` for exchange transfers and M&A absorptions. |

## `is_genuine` classification

Four layers, applied in order. See `build_is_genuine_overrides.py`'s
docstring for the rationale of each layer.

1. **Keyword baseline** (in `build_delisting_calendar.py`):
   - `N` if reason ∈ {`코스닥시장 이전상장`, `유가증권시장 상장`, `코스닥시장 상장`} (exchange transfer)
   - `N` if reason contains 피흡수합병 / 완전자회사화 / 완전자회사로 편입 / 스팩소멸합병 / 주식교환 (merger)
   - `Y` otherwise

2. **DART-driven overrides** (in `build_is_genuine_overrides.py`):
   - **Dissolution-after-merger** (Y → N): for each `해산 사유 발생` row,
     query DART 주요사항보고서 in the 9 months before delisting; if a
     filing matching `합병` / `주식의 포괄적 (교환|이전)` / `주식교환` exists,
     override to N. 55 rows.
   - **REIT / SPC end-of-life** (Y → N): for each remaining `해산 사유 발생`
     row, fetch the DART entity name; if it matches
     `투자회사` / `리츠` / `REIT` / `기업구조조정`, the dissolution is a planned
     end of a special-purpose vehicle, not a business failure. 15 rows.
   - **Holding-company restructuring** (N → Y): rule-based, no DART
     needed. Reason `지주회사의 완전자회사화(지주회사 신규상장)` is treated as
     a continuation under the newly-listed holding company. 9 rows.

3. **Manual overrides** (`MANUAL_OVERRIDES` dict in
   `build_is_genuine_overrides.py`): hard-coded entries with a verified
   citation for cases the three rules above cannot reach. Currently
   1 row:
   - `001370 FNC코오롱` 2009-08-17 (Y → N): merged into (주)코오롱;
     the 합병결정 was filed acquirer-side under 코오롱's `corp_code`, so
     an acquiree-side DART query returns nothing.

4. **Verified deviations from the legacy curated CSV (not corrected —
   regen is more accurate).** The current regenerator agrees with the
   legacy `delisting_calendar.curated.csv` on 1,111 / 1,116 overlap
   rows; the remaining 5 are all verified curated bugs left as-is
   because the regen's classification is correct (researched 2026-05-11):
   - `037150 CJ인터넷`, `056200 엠넷미디어` 2011-03-22 — both 피흡수합병
     into CJ E&M (130960); shareholders received CJ E&M shares, so this
     is M&A continuation → regen N is correct, curated Y is inconsistent
     with the project's merger=N convention.
   - `228180 티씨엠생명과학` 2020-08-07 — 주식의 포괄적 교환 into 넥스트BT
     (065170); same logic as above → regen N is correct.
   - `323350 다원넥스뷰` 2024-06-11 — KONEX → KOSDAQ transfer via
     스팩소멸합병 with 신한제9호스팩, relisted KOSDAQ same day under the
     same ticker → regen N is correct.
   - `117930 한진해운` 2017-03-07 — real bankruptcy (rehabilitation
     terminated 2017-02-02, declared bankrupt 2017-02-17, ~2 % of
     $10.5B owed recovered) → regen Y is correct, curated N is wrong.

After steps 1-3, the regenerated calendar has `Y=1,004, N=355` (out of 1,359).

## Regenerating the calendar

```bash
# One-time, with a DART API key (sourced from repo-root .env):
set -a; . ../.env; set +a            # exports OPEN_DART_API_KEY
python build_is_genuine_overrides.py    # writes is_genuine_overrides.csv

# Refresh whenever:
python build_delisting_calendar.py      # writes delisting_calendar.regen.csv
                                        # (or pass --out delisting_calendar.csv)
```

`build_delisting_calendar.py` takes ~20–30 s — a single KIND POST returns
all 1,241 events at once, plus 18 round-trips to KIND's
`companysummary.do` to resolve foreign-issuer tickers and a marcap scan
(~9 s).  No DART calls here — DART is only used in
`build_is_genuine_overrides.py`.

`build_is_genuine_overrides.py` takes a few minutes — one DART query per
`해산 사유 발생` row (currently 72 rows). Re-run on each new KIND data
refresh; the output is small and stable.

## Loader API

```python
from delisted_loader import load_delisted, universe

# Point-in-time analysis universe (genuine delistings only)
cal = universe(genuine_only=True)
# By market: KOSDAQ / KOSPI / KONEX

# One ticker's full history (unadjusted, ends on last trading day before delisting)
df = load_delisted('005390')          # 신성통상, delisted 2025-09-30
# cols: Date, Code, Name, Market, Open, High, Low, Close, Volume, Amount,
#       Marcap, Stocks, ChangeRate, Rank, Dept

# Rolling-window filter pattern
import pandas as pd
for D in pd.date_range('2020-01-01', '2025-10-23'):
    active = cal[pd.to_datetime(cal['delisting_date']) > D]
    # ... load prices for each ticker in `active`, run analysis ...
```

## Cross-source joins (for analyses needing more than OHLCV/marcap)

The tickers in this calendar can be joined to `~/finance_db/fnguide_data/`
on `"A" + ticker` (fnguide uses the A-prefix convention in row 9 of its
headers):

- **Investor-category daily flow** — `~/finance_db/fnguide_data/data0203`–`data0208.xlsx`.
  563/619 (91 %) of KOSPI/KOSDAQ common-kind delistings, rising to
  112/114 (98 %) for delistings in 2021 onward — and to 112/113 (99 %)
  once `kr_marcap.universe(..., strict=True)` drops the resource trust
  `152550` from the denominator. Each column ends on the delisting date.
- **Annual consolidated financials (IFRS-C) + monthly market cap** —
  `~/finance_db/fnguide_data/data2_0203.xlsx`. Same coverage.
  **Truncate at `delisting_date.year - 1`** before merging — the 6-digit
  KRX code may have been reassigned to a later listing whose financials
  will otherwise bleed in.
- **Main-entity financials (IFRS-M), adjusted prices, daily market cap,
  short-selling** — `~/finance_db/fnguide_data/currently_listed/` covers
  **0%** of delisted names. Use marcap for prices/marcap on delisted
  names; fall back to DART (`corp_code`) for IFRS-M. No fnguide source
  exists for delisted short-selling / lending history.
- **Always-missing in fnguide:** KONEX (~2.6%), preferred shares (~0.9%),
  specialty funds (선박투자/리츠/호, ~2.9%) — usually excluded on
  methodological grounds anyway.

Full breakdown with measured numbers: `~/finance_db/fnguide_data/DELISTED_COVERAGE.md`.

## marcap coverage verification

**Verified 2026-05-11** against the full 1,359-row canonical CSV.
marcap includes delisted tickers (no survivorship bias). Every one of
the 1,241 KIND-sourced 6-digit tickers is present in marcap, with the
expected end-of-trading pattern:

- 1,215 / 1,241 (97.9 %): last marcap row is 1–7 days before
  `delisting_date` in `marcap-{year-of-delisting}.parquet` — the
  textbook pattern.
- 7 / 1,241: 8–30 day gap (trading-suspension periods before formal
  delisting).
- 6 / 1,241: delisting_date is in the first trading days of a new year
  (Jan 2–3); the last trading row falls in `marcap-{year−1}.parquet`
  (Dec 28–30). Cross-year boundary, not a coverage gap.
- 13 / 1,241: recent 2026 delistings where the local marcap parquet
  only extends to 2026-02-20 — marcap update lag, not a coverage gap.

The 118 marcap-derived preferred-share proxy rows are present by
construction (their `delisting_date` IS the last-marcap-date for the
ticker).

Caveats: non-standard 7–8 digit codes (warrants, rights, fund
vehicles, bonds) were not verified here. Verification used
`marcap-{year}.parquet` files; behavior is assumed identical for the
upstream `.csv.gz` files.

```python
import pandas as pd
cal = pd.read_csv('~/finance_db/kr_delisted/delisting_calendar.csv', dtype={'ticker': str})
df  = pd.read_parquet('~/finance_db/marcap/data/marcap-2025.parquet')
# For any KIND-sourced row r in cal whose delisting_date is in 2025:
#   df[(df.Code.str.zfill(6) == r.ticker) & (df.Date < r.delisting_date)].Date.max()
# should equal r.delisting_date − 1 trading day.
```
