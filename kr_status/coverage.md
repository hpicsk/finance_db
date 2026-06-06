# kr_status — coverage and known gaps

Single source of truth for what each tradable-universe status flag covers,
which date range, from which source, and what its known limitations are.
Each project's `claim_survival.md` should link here rather than duplicate
these caveats.

## Coverage matrix

| Flag              | Date range covered                  | Primary source                | PIT? | Delisted firms? | Known gaps |
|-------------------|-------------------------------------|-------------------------------|------|-----------------|-----------|
| `admin`           | **2014–2026** (marcap.Dept first reliable in 2014) | `marcap_halt_infer.py` via `Dept~'관리종목'` on `../marcap/data/marcap-YYYY.parquet` | ✅ per-day flags consolidated to `(start_date, end_date)` events; gap > 7d breaks a run | ✅ marcap includes delisted firms up to their last trading day | Pre-2014 admin coverage absent (Dept is NaN). 2020–2024 KOSPI+KOSDAQ spot-check vs the retired FDR snapshot: 16/18 events matched with zero-day lag. |
| `audit_qualified` | (proxy) delisted-firm rows, 2005–latest delisting<br>(DART) **2015+ structured only** | (proxy) `kr_delisted/delisting_calendar.csv` audit-rejection rows via `fdr_collect --seed-historical`<br>(DART) `accnutAdtorNmNdAdtOpinion.json` (DS002/2020009) | (proxy) ⚠️ window = [delist−180d, delist]<br>(DART) ✅ receipt_dt anchored | (proxy) ✅ delisted-only (by construction)<br>(DART) ✅ | **No structured DART data pre-2015**; pre-2015 still-listed firms with non-적정 opinions are not flagged. Would require parsing 외부감사보고서 filing HTML/PDFs |
| `insincere`       | DART filing history (2005+) | `dart_insincere.py` → DART `list.json` title="불성실공시법인지정" | ✅ designation date | ✅ | Default release rule: `end_date = start_date + 12 months` (KRX standard); actual release filings vary |
| `halt`            | **2004–2026** (marcap snapshots) | `marcap_halt_infer.py` via `ChangeCode=='0'` on `../marcap/data/marcap-YYYY.parquet` | ✅ per-day flags consolidated to `(start_date, end_date)` events; gap > 7d breaks a run | ✅ marcap includes delisted firms up to their last trading day | False positives from permanently-illiquid preferreds, pre-merger SPACs, dead-shell tickers (~1.6% of events span > 252 days). DART cross-check on a 60-sample 2020–2024: 100% of 31–60d halts and 78% of 11–30d halts had a DART-substantiable causing event (회생절차, 감자결정, 조회공시요구, etc.) in ±14d. KIND scrape would be needed for canonical halt boundaries. |
| `alert`           | **2014–2026** (marcap.Dept first reliable in 2014) | `marcap_halt_infer.py` via `Dept~'투자주의환기'` on `../marcap/data/marcap-YYYY.parquet` | ✅ consolidated like `admin` | ✅ | Pre-2014 absent. KOSPI+KOSDAQ 2020–2024: 207 distinct tickers, 230 runs. |

## Hard known bounds

### 1. 감사의견 비적정, pre-2015
DART's structured audit-opinion endpoint (`accnutAdtorNmNdAdtOpinion.json`)
is only populated for `bsns_year ≥ 2015`. Pre-2015 audit opinions live
inside the free-text `외부감사보고서` filings, which would require HTML/PDF
parsing per filing per firm. **Result**: any backtest running pre-2015 will
have an `audit_qualified` filter that under-fires — false negatives for
firms with non-적정 opinions that have not subsequently delisted. The
Phase-A `historical_audit_events.parquet` partially mitigates this by
seeding from delisted-firm rows (which do reach KIND with audit-rejection
reasons), but does **not** catch firms that survived after a non-적정
opinion.

### 2. 거래정지, inference vs. canonical
`marcap_halt_infer.py` derives halts from `ChangeCode=='0'` on marcap
daily snapshots, giving full 2004–2026 coverage including delisted
firms. `ChangeCode=='0'` is KRX's daily no-trade flag (not a literal
거래정지 record); on KOSPI/KOSDAQ it matches the legacy
`(Volume==0)&(Open==0)` heuristic to within ~0.1%, and on KONEX it
correctly avoids classifying illiquid no-trade days as halts. Still an
inference, not a canonical KRX record:

- **False positives**: permanently illiquid preferred shares (e.g.
  `00341A 쌍용양회(4우B)` shows a multi-thousand-day "halt" — actually
  just never trades), pre-merger SPACs, dead-shell tickers post-suspension.
  A duration filter (`n_days ≤ 252`) removes most of these.
- **Boundary fuzz**: halt `start_date` / `end_date` are inferred from
  trading absence, not from the KRX 거래정지 시점. For an event-study
  regressor that needs exact halt timestamps, KIND scrape would be the
  upgrade path (DART does **not** carry halt filings — KRX files them
  into KIND).
- **Sample DART substantiation** (n=60, 2020–2024, 30 queryable):
  100% of 31–60d halts, 78% of 11–30d, 14% of 4–10d, 30% of 1–3d had a
  DART-filed causing event (회생절차, 감자결정, 조회공시요구, etc.) in a
  ±14d window. Short halts (1–10d) often have no DART trail — KRX
  manages 단기과열 operationally without a DART filing.

The direct KRX feed (`MDCSTAT08501`) was attempted and abandoned: KRX
repurposed the bld to ELW master, and the replacement bld for the
거래정지 list loads via an `mdiLoader`-injected JSP — capturable from
DevTools but not yet wired in. See `README.md § Deferred — direct KRX
halt feed` for notes if anyone wants to revisit.

### 3. 관리종목 pre-2014
`marcap.Dept` is the canonical source for 관리종목 (and 투자주의환기종목):
KRX publishes the classification daily, marcap captures both start and end
dates exactly, and coverage is full back to 2014. The retired FDR
snapshot / DART harvest pipelines added no information for the years
where marcap.Dept is populated.

The remaining gap is **pre-2014**: marcap rows from 2004–2013 have
`Dept = NaN`, so admin/alert events from that era are not recoverable
from marcap. DART does not store 관리종목 designations either (KRX
administrative action, not corporate-disclosure filing — `dart.list(corp=...)`
returns zero hits across every filing kind, verified 0/8 known admin firms).
The authoritative historical PIT source lives behind the `data.krx.co.kr`
403 geofence; recovery would require Korean-IP infra (AWS Seoul / GCP
`asia-northeast3` / paid proxy) or a paid feed (FnGuide, KOSCOM).
Backtests with universe-start dates before 2014 must accept the gap.

### 4. Insincere "active" window
KRX's official 불성실공시법인 designation lasts 1 year, but the de-facto
"don't hold this" period (the firm typically retains 관리종목 status and
auditor scrutiny longer) is closer to 18–24 months. The default
`insincere_lookback_months=6` in `TradableConfig` is **deliberately
conservative** — it excludes firms whose designation started within the
last 6 months even if the official 1-year window has elapsed. If a study
needs the strict 1-year KRX definition, set `insincere_lookback_months=0`
and the cube will use the literal `[start_date, end_date]` interval.

## How `claim_survival.md` should cite this

```markdown
## Survivorship-bias sensitivity

| Universe variant       | Sharpe | Verdict |
|-----------------------|--------|---------|
| Paper (FnGuide CL)    | 1.85   | as published |
| Bias-free, naive      | -0.38  | overturned (all commons incl. 동전주, 자본잠식) |
| Bias-free, tradable   | X.XX   | <SURVIVE / WEAKEN / OVERTURN> |

Coverage of the tradable filter is bounded by kr_status known gaps; see
[../../finance_db/kr_status/coverage.md](...). Headline limitation: pre-2015
audit-opinion data is absent for still-listed firms.
```
