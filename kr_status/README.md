# kr_status

Point-in-time status flags for Korean equities — standalone data-gathering
scripts for the five KRX/DART signals that the
`kr_marcap.status.tradable_universe()` function consumes:

| Status            | Korean         | Meaning                            |
|-------------------|----------------|------------------------------------|
| `admin`           | 관리종목         | KRX administrative-issue flag      |
| `audit_qualified` | 감사의견 비적정  | 한정 / 부적정 / 의견거절 audit opinion |
| `insincere`       | 불성실공시법인    | KRX insincere-disclosure designee  |
| `halt`            | 거래정지         | KRX trading halt                    |
| `alert`           | 투자주의환기종목  | KRX investment-alert designation    |

This package is the **data layer** — pure collectors that write
event-format parquets under `data/`. The query API lives in sibling
package `kr_marcap.status`; it reads everything in `data/` and produces a
PIT tradable universe.

## Schema

Every `*_events.parquet` matches `kr_status.schema.STATUS_COLUMNS`:

```
ticker        str    6-char zero-padded ("001470")
status        str    one of {"admin","audit_qualified","insincere","halt","alert"}
start_date    Timestamp   designation / halt / qualified-opinion date
end_date      Timestamp   release date, or NaT if still active
source        str    provenance string (collector + source endpoint)
fetched_at    Timestamp   when the row was collected
detail        str    raw reason / opinion code / halt cause
```

Convention: `end_date = NaT` means **still active as of the most recent
`fetched_at`** (used by `_active_tickers` to fill with `+∞`).

## Collectors

### `marcap_halt_infer.py` — canonical source for `halt`, `admin`, `alert`

Full historical coverage 2004–2026 for halt and 2014–2026 for admin/alert;
no auth, no rate limits. Reads the marcap daily snapshots
(`../marcap/data/marcap-YYYY.parquet`) and emits three signals:

- `status='halt'` ← `ChangeCode == '0'` (KRX's daily no-trade flag).
  Works 2004–2026. On KOSPI/KOSDAQ this matches the legacy
  `(Volume==0) AND (Open==0)` heuristic to within ~0.1%; on KONEX the
  prior heuristic over-counted illiquid no-trade days as halts.
- `status='admin'` ← `Dept` column contains `관리종목`. The same KRX
  classification that drives FDR's `KRX-ADMINISTRATIVE` list and seeds
  DART's 관리종목지정 filings. Reliable **2014 onward** (pre-2014 marcap
  rows have `Dept = NaN`).
- `status='alert'` ← `Dept` column contains `투자주의환기` (투자주의환기
  종목 designation). Same coverage as admin.

Consecutive flagged business days per ticker are consolidated into single
`(start_date, end_date)` events; a gap > 7 calendar days breaks a run
(handles weekends + Chuseok / Seollal).

The previous FDR `KRX-ADMINISTRATIVE` snapshot/consolidate flow and the
per-corp DART `관리종목지정/해제` harvest (`dart_admin.py`) have been
retired — marcap.Dept supersedes both. On KOSPI+KOSDAQ 2020-2024, marcap
matched 16/18 FDR admin events with zero-day lag.

### `fdr_collect.py` — historical audit_qualified seed

Single remaining responsibility: walk `../kr_delisted/delisting_calendar.csv`
and emit one `audit_qualified` event per delisted ticker whose reason
mentions 감사의견거절 / 부적정 / 한정 etc. Window:
`[delisting_date − 180d, delisting_date]` (proxy; real 감사의견
publication date unknown from the KIND delisting feed).

```bash
python -m kr_status.fdr_collect --seed-historical  # delisting CSV → historical_audit_events.parquet
python -m kr_status.fdr_collect --check            # smoke test
```

Phase B (`dart_audit.py`) replaces these proxy windows with DART-receipt-
anchored events for `bsns_year ≥ 2015`.

### Phase B — DART collectors

Requires `OPEN_DART_API_KEY` (DART) — loaded from repo-root `.env`:

```bash
set -a; . ../.env; set +a            # exports OPEN_DART_API_KEY
python -m kr_status.dart_audit       # 감사의견 (2015+) via accnutAdtorNmNdAdtOpinion.json
python -m kr_status.dart_insincere   # 불성실공시 PIT history via DART list.json
```

Outputs (under `data/`):
- `dart_audit_opinions.parquet` — raw `(ticker, bsns_year, opinion_code, receipt_dt)`
- `dart_audit_events.parquet` — `audit_qualified` events (non-적정 → next-year-or-NaT)
- `dart_insincere_events.parquet` — `insincere` events

```bash
python -m kr_status.marcap_halt_infer    # writes data/marcap_halt_events.parquet
```

**Known false positives in `halt`** (acceptable for the exclusion-filter
use case, but problematic if halts are used as a regressor):

- Permanently illiquid preferred shares (e.g. `00341A 쌍용양회(4우B)` shows
  a multi-thousand-day "halt" — actually just never trades).
- SPACs pre-merger (e.g. `상상인이안제2호스팩`, `유안타제5호스팩`) — non-trading
  by design.
- Dead-shell tickers post-suspension that linger in marcap without volume.

A duration filter (`n_days ≤ 252`) drops most of these. For phase-1
exclusion-filter use, no filtering is required since those days have no
usable returns anyway.

**Boundary fuzz.** `start_date` / `end_date` for halt events are inferred
from trading absence, not from the KRX 거래정지 시점. For an event-study
regressor that needs exact halt timestamps, scrape KIND's 거래정지 category
directly — DART does **not** carry halt filings (KRX files them into KIND).
The cross-check tool `marcap_halt_dart_crosscheck.py` looks for *causes*
(회생절차, 감자결정, 조회공시요구, …) in the halt window and produces a
substantiation rate, not a confirmation rate.

#### Deferred — direct KRX halt feed

`marcap_halt_infer.py` is the canonical halt source. The direct KRX
feed was attempted and abandoned (file removed 2026-05-22). Notes for
anyone who wants to revisit it:

1. **Auth required.** `data.krx.co.kr/comm/bldAttendant/getJsonData.cmd`
   returns `400 LOGOUT` for unauthenticated POSTs. Working pattern:
   reuse `pykrx.website.comm.webio.get_session()` after exporting
   `KRX_ID` / `KRX_PW` (credentials in `../krx_supplement/krx_id`).
2. **`MDCSTAT08501` was repurposed.** The bld referenced in the
   original spec now returns the ELW warrant master (~2,907 rows of
   `KB증권 워런트증권 …`, fields `ELW_ULY_TP_NM`, `ELW_CONV_RTO`, etc.).
   `trdDd` is ignored — every date returns the same snapshot. The
   replacement bld for **매매거래정지종목 현황** is not captured here — the
   page loads via `MDC02020601` → `mdiLoader` → an inner JSP whose
   bld is set by client-side JS, not present in any server-rendered
   HTML. Browser DevTools Network tab is the fastest capture path if
   we want to upgrade later (canonical halt boundaries, vs. the
   `ChangeCode=='0'` flag).

### Shared utility

`corp_code_map.py` wraps `OpenDartReader.find_corp_code(ticker)` with a
persistent reverse map for delisted tickers; seeds from
`../kr_delisted/delisting_calendar.csv` names + `dart.company_by_name`
fuzzy match. Misses are logged to `data/corp_code_misses.csv` for triage.

## Endpoints used

| Source | URL | Notes |
|---|---|---|
| marcap snapshots | `../marcap/data/marcap-YYYY.parquet` | **canonical source for `halt`, `admin`, `alert`** (`marcap_halt_infer.py`): halt via `ChangeCode=='0'`, admin via `Dept~'관리종목'` (2014+), alert via `Dept~'투자주의환기'` (2014+) |
| DART `list.json` | `opendart.fss.or.kr/api/list.json` | paginated; filter `report_nm` for title keywords (used by `dart_insincere`) |
| DART audit-opinion | `opendart.fss.or.kr/api/accnutAdtorNmNdAdtOpinion.json` | DS002/2020009; **bsns_year ≥ 2015 only**. Not wrapped by OpenDartReader — `dart_audit._fetch_one` calls it via `requests.get` directly |
| KIND delisting feed | `kind.krx.co.kr/investwarn/delcompany.do` | already-wired in `../kr_delisted/build_delisting_calendar.py`; consumed by `fdr_collect --seed-historical` |

DART rate cap: ~10,000 req/day per API key. `dart_audit` for ~4,300 tickers
× ~10 years ≈ 43,000 req → batch across ~5 days (resumable via the
`dart_audit_opinions.parquet` cache).

## Rerun cadence

| Collector | Cadence | Why |
|---|---|---|
| `marcap_halt_infer`         | after each yearly marcap refresh | re-derives halt/admin/alert from updated marcap snapshots; idempotent rewrite |
| `dart_insincere`            | quarterly (or on-demand) | DART filings are historical; new ones added monthly |
| `dart_audit`                | annually (post-Mar audit-filing season) | annual cadence by nature |
| `fdr_collect --seed-historical` | when `delisting_calendar.csv` is refreshed | pre-2015 audit_qualified proxy seeds |

## Consumer

The query side lives in `kr_marcap/status/`:

- `kr_marcap.status.build_panel` — merges all `*_events.parquet` here into one
- `kr_marcap.status.tradable_universe(date, ...)` — applies status exclusions
  + price/marcap/ADV liquidity filters on top of `kr_marcap.universe(kind='common')`

`fn_shared.data.tradable_universe(date)` and `BiasFreeStore.tradable_universe(date)`
are thin shims around the kr_marcap function for use in fn_project research code.

## Coverage gaps

See [`coverage.md`](coverage.md) for the flag × date-range × source matrix,
the 2015+ audit-opinion bound, and other known limitations.
