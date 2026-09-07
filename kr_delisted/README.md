# Korean delisted-equity universe

Point-in-time calendar and data loader for Korean stocks delisted between
2005-01-02 and the latest run date. Built for survivorship-bias-free
cross-sectional analysis.

## Sources

The calendar is stitched together from three sources, each addressing a
specific gap in the others:

| Source | What it provides | Coverage |
|---|---|---|
| **KIND** `kind.krx.co.kr/investwarn/delcompany.do` | Delisting events: 6-digit ticker, name, market, date, reason | Main shares, 2005-01-02 → present (1,268 events as of 2026-08-23) |
| **marcap** `~/research/finance_db/marcap/data/marcap-YYYY.parquet` | Last-trade dates and OHLCV history for preferred shares not in KIND | Preferred / 신주 / 전환 tickers (codes not ending in '0'), 2005+ |
| **DART** `opendart.fss.or.kr` (via `OpenDartReader`) | Corporate-action filings that disambiguate dissolutions | Post-2001 main-share filings + entity-type names |

Daily OHLCV / volume / marcap / shares for every ticker in the calendar
come from the marcap parquets — prices are **unadjusted** (matches KRX's
raw history). Adjust for splits / dividends only if you need a continuous
series (use returns, not levels).

## Scope

**Included (1,386 rows in the current canonical CSV):**
- All 1,268 KIND delisting events for KOSPI / KOSDAQ / KONEX, 2005-01-02 onward.
- 118 preferred-share / 신주 / 전환 tickers recovered from marcap
  (codes ending in a non-zero digit, last-appearance date as proxy
  delisting date).

**Excluded by design:**
- Pre-2005 main-share delistings — KIND does not publish them.
- Warrants / rights / ETNs / ETFs / funds (7–8 character codes) — these
  carry limited-life structure that confounds survival analysis and are
  not in marcap's daily snapshot. Filter on `len(ticker) == 6`.
- KONEX issues if your analysis targets KOSPI + KOSDAQ only — keep them
  filterable via `market == 'KONEX'` (196 rows).

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
                                   1,386 rows × 6 cols (ticker, name, market,
                                   delisting_date, reason, is_genuine)
delisting_calendar.kind.csv        intermediate KIND-only output of
                                   build_delisting_calendar.py --no-proxy;
                                   consumed by build_is_genuine_overrides.py
delisted_loader.py                 load_delisted(ticker) / universe() API
build_delisting_calendar.py        end-to-end regenerator (KIND + marcap + overrides)
build_is_genuine_overrides.py      DART + manual is_genuine refinement (run once;
                                   produces is_genuine_overrides.csv)
is_genuine_overrides.csv           85 override rows consumed by build_delisting_calendar.py
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
     override to N. 59 rows.
   - **REIT / SPC end-of-life** (Y → N): for each remaining `해산 사유 발생`
     row, fetch the DART entity name; if it matches
     `투자회사` / `리츠` / `REIT` / `기업구조조정`, the dissolution is a planned
     end of a special-purpose vehicle, not a business failure. 16 rows.
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

After steps 1-3, the regenerated calendar has `Y=1,018, N=368` (out of 1,386).

What each side holds, and why the split matters for return-based work:

- *Genuine* `Y` (1,018): bankruptcy, audit refusal, voluntary delisting,
  REIT/SPC ends — what survivorship analysis wants. Includes 118
  preferred-share proxy rows recovered from marcap.
- *Continuation* `N` (368): 107 exchange transfers (KOSPI↔KOSDAQ migration,
  the stock still trades) + 261 mergers / 주식교환 / SPC dissolutions (shares
  swapped into the acquirer — exclude these, since merger premia contaminate
  return-based analyses).

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
all 1,268 events at once, plus 18 round-trips to KIND's
`companysummary.do` to resolve foreign-issuer tickers and a marcap scan
(~9 s).  No DART calls here — DART is only used in
`build_is_genuine_overrides.py`.

`build_is_genuine_overrides.py` takes a few minutes — one DART query per
`해산 사유 발생` row. Re-run on each new KIND data refresh; the output is small
and stable.

**Run the three steps in order, or layer 2 silently skips the new rows.**
`build_is_genuine_overrides.py` reads `delisting_calendar.kind.csv`, not the
canonical CSV, so a KIND refresh that reaches the calendar while the
intermediate stays behind leaves the new `해산 사유 발생` rows holding the
keyword baseline's `Y` — and `Y` is the wrong default for a dissolution that
followed a merger, which puts continuations into
`universe(genuine_only=True)` as failures. Nothing about that is visible from
the output: every layer that ran, ran correctly.

```bash
python build_delisting_calendar.py --no-proxy        # → delisting_calendar.kind.csv
set -a; . ../.env; set +a
python build_is_genuine_overrides.py                 # → is_genuine_overrides.csv
python build_delisting_calendar.py --out delisting_calendar.csv
```

This went wrong once — the intermediate sat at 2025-10-23 while the calendar
ran to 2026-05-08, and five dissolutions (`006390`, `010620`, `042670`,
`138490`, `152550`) carried an unchecked `Y` until the 2026-08-23 refresh;
DART turned all five into `N`, four on a 회사합병 filing and one on the 투자회사
rule. `test_assertions.py::test_dissolution_rows_all_saw_the_dart_pass` now
fails while any dissolution row sits past the span the intermediate covers.

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

The tickers in this calendar can be joined to `~/research/finance_db/fnguide_data/`
on `"A" + ticker` — fnguide uses the A-prefix convention in row 9 of its
headers.

Two rules that belong to this calendar rather than to the sheet on the other
side of the join:

- **Truncate annual financials at `delisting_date.year - 1`.** The 6-digit KRX
  code freed by a delisting is reissued, and a code-keyed vendor series carries
  both occupants in one column. Without the truncation the later listing's
  financials bleed into the delisted company's history.
- **KONEX, preferred shares and specialty funds are the buckets a vendor is
  always short of** — filter them out with `kr_marcap.classify` before
  measuring a coverage rate, or the denominator answers a different question
  than the one asked. They are excluded on methodological grounds in most
  return / liquidity work anyway.

Which dimension is available for delisted names, at what rate, and against
which pull date is measured on the fnguide side and kept there, in
`~/research/finance_db/fnguide_data/DELISTED_COVERAGE.md`. Those figures move
whenever either the calendar or a vendor export is refreshed, so this file
points at them rather than holding a second copy.

## marcap coverage verification

**Re-measured 2026-08-23** against the full 1,386-row canonical CSV.
marcap includes delisted tickers (no survivorship bias). Every one of
the 1,268 KIND-sourced 6-digit tickers is present in marcap — that much is
asserted by `test_assertions.py::test_marcap_carries_every_kind_ticker`, so it
is checked on every run rather than dated. The end-of-trading pattern behind
it, taking each ticker's last marcap row *before* its `delisting_date`:

- 48 / 1,268 delist past the marcap right edge (2026-02-20), so the local
  clone cannot show their last session yet. Update lag, not a coverage gap —
  the figure moves with every marcap pull and is the one number here that is
  about the clone rather than the data.
- Of the 1,220 inside that span, **1,210 (99.2 %)** have a 1–7 day gap — the
  textbook pattern — of which 6 are Jan 2–3 delistings whose last trading row
  falls in `marcap-{year−1}.parquet` (Dec 28–30).
- 1 has an 8-day gap (`449020`, delisted 2025-10-10), a suspension before the
  formal delisting. None exceeds 30 days.

The 118 marcap-derived preferred-share proxy rows are present by
construction (their `delisting_date` IS the last-marcap-date for the
ticker).

Caveats: non-standard 7–8 digit codes (warrants, rights, fund
vehicles, bonds) were not verified here. Verification used
`marcap-{year}.parquet` files; behavior is assumed identical for the
upstream `.csv.gz` files.

```python
import pandas as pd
cal = pd.read_csv('~/research/finance_db/kr_delisted/delisting_calendar.csv', dtype={'ticker': str})
df  = pd.read_parquet('~/research/finance_db/marcap/data/marcap-2025.parquet')
# For any KIND-sourced row r in cal whose delisting_date is in 2025:
#   df[(df.Code.str.zfill(6) == r.ticker) & (df.Date < r.delisting_date)].Date.max()
# should equal r.delisting_date − 1 trading day.
```
