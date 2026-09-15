# kr_status

DART collectors for Korean equities — standalone scripts, each writing one
parquet under `data/`:

| Collector | Output |
|---|---|
| `dart_audit.py` | `dart_audit_opinions.parquet` — 감사의견, one row per (ticker, bsns_year), FY2015+ |
| `dart_corp_actions.py` | `dart_corp_action_events.parquet` — the 증자 / 감자 / 합병 / 분할 / 주식교환 filings that move a share count |

Both call DART and need `OPEN_DART_API_KEY`, loaded from the repo-root `.env`:

```bash
set -a; . .env; set +a               # exports OPEN_DART_API_KEY; run from the repo root
```

## Collectors

### `dart_audit.py` — 감사의견

```bash
python -m kr_status.dart_audit       # 감사의견 (2015+) via accnutAdtorNmNdAdtOpinion.json
```

Writes `data/dart_audit_opinions.parquet` — raw `(ticker, bsns_year,
opinion_code, receipt_dt, raw)`. DART's structured endpoint is populated for
`bsns_year ≥ 2015` only; earlier opinions live inside free-text 외부감사보고서
filings, which this collector does not parse.

### `dart_corp_actions.py` — corporate-action ground truth

`dart_corp_actions` harvests DART 주요사항보고서 events that move a share count
and splits them into two categories, which is what lets the price-adjustment
layer tell a corporate action apart from an entity change:

- **genuine** (유상증자 / 무상증자 / 유무상증자 / 감자) — price-affecting, and KRX's
  ChangesRatio already adjusts for it, so the share-count jump must *not* be
  read as a series break.
- **entity** (회사합병 / 회사분할 / 회사분할합병 / 주식교환) — the listing's economic
  identity may change, so the jump is a break candidate.

Reached through `OpenDartReader.dart_event.event`, one call per (ticker,
event). Preferred shares have no `corp_code` of their own and resolve to the
parent common (`code[:5] + '0'`); 액면분할/병합 are absent from the event API and
are deliberately omitted, since a 액면 change always moves the price inversely
and is never misread as a break. DART's structured coverage is reliable from
~2015; earlier events are sparse and fall to the manual-override path.

```bash
set -a; . .env; set +a
python -m kr_status.dart_corp_actions            # writes data/dart_corp_action_events.parquet
```

Output columns: `ticker, parent, corp_code, event, category, rcept_dt,
rcept_no`. Resume-safe — tickers already in the cache are skipped unless
`--restart`.

One thing to know before running it: the default ticker list is the share-jump
candidate set, which only exists once the price-adjustment build has written
it, so this collector runs *after* a seeding build, not before (`--tickers` /
`--all-universe` override).

### Shared utility

`corp_code_map.py` wraps `OpenDartReader.find_corp_code(ticker)` with a
persistent reverse map for delisted tickers; seeds from
`../kr_delisted/data/delisting_calendar.csv` names + `dart.company_by_name`
fuzzy match. Misses are logged to `data/corp_code_misses.csv` for triage.

## Endpoints used

| Source | URL | Notes |
|---|---|---|
| DART audit-opinion | `opendart.fss.or.kr/api/accnutAdtorNmNdAdtOpinion.json` | DS002/2020009; **bsns_year ≥ 2015 only**. Not wrapped by OpenDartReader — `dart_audit._fetch_one` calls it via `requests.get` directly |
| DART 주요사항보고서 events | `OpenDartReader.dart_event.event` | 증자 / 감자 / 합병 / 분할 / 주식교환 per (ticker, event); used by `dart_corp_actions`. Reliable from ~2015 |

DART rate cap: ~10,000 req/day per API key; `run_dart_audit_resume.sh` runs one
day's batch and logs to `runtime/`. `dart_audit` for ~4,300 tickers
× ~10 years ≈ 43,000 req → batch across ~5 days (resumable via the
`dart_audit_opinions.parquet` cache).

## Rerun cadence

| Collector | Cadence | Why |
|---|---|---|
| `dart_audit`                | annually (post-Mar audit-filing season) | annual cadence by nature |
| `dart_corp_actions`         | after a marcap refresh, once the candidate share-jump list has been rebuilt | new corporate actions land continuously; resume-safe, so a re-run only fetches what is new |
