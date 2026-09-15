# kr_status

DART collectors for Korean equities — standalone scripts, each writing one
parquet under `data/`:

| Collector | Output |
|---|---|
| `dart_audit.py` | `dart_audit_opinions.parquet` — 감사의견, one row per (ticker, bsns_year), FY2015+ |
| `dart_audit_first.py` | `dart_audit_first_filings.parquet` — the same rows, read from each 사업보고서's first filing |
| `dart_corp_actions.py` | `dart_corp_action_events.parquet` — the 증자 / 감자 / 합병 / 분할 / 주식교환 filings that move a share count |

All three call DART and need `OPEN_DART_API_KEY`, loaded from the repo-root `.env`:

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

The cache holds bsns_year 2015–2025. Each row is what the endpoint served for
that (ticker, year) at harvest time, and two things follow:

- **An amended report comes back as amended.** When a 사업보고서 was corrected
  (정정), the row usually carries the correction — its receipt date in
  `receipt_dt`, its opinion in `raw` — not what the market read first. 702 rows
  (2.7 %) are stamped more than a year after the 31 March filing deadline, and
  015540's rows for FY2019–2022 all carry receipt dates in 2023.
  `dart_audit_first_filings.parquet` holds the first filing of every row, and
  its section below counts how often the two differ.
- **`opinion_code` is read from `raw`, ignoring whitespace.** A
  `감사의견 : <verdict>` line wins; otherwise the first of 의견거절 / 부적정 /
  한정 / 적정 found in the text. A text with none of them but `거절` or the
  misspelling `겨절` is 의견거절. One stating fair presentation — `공정`,
  `공정하게 표시하고 있음`, the opinion paragraph itself — is 적정 unless it
  carries an exception (`제외`), a negation (`않`, `아니`) or `공정가치` (fair
  value): a qualified opinion adds "…을 제외하고는", and a review conclusion
  finds nothing "발견되지 아니함". 1,251 rows carry no opinion text
  (`unknown`), and 109 carry other text — a review conclusion such as 예외사항
  없음, an auditor's name, a footnote mark — which is kept as its own label.
  Both collectors re-derive the label from `raw` whenever they write, and
  `python -m kr_status.dart_audit --relabel` does it for the cache without
  calling DART.

### `dart_audit_first.py` — each opinion as first filed

```bash
python -m kr_status.dart_audit_first  # after dart_audit; list.json + document.xml
```

Writes `data/dart_audit_first_filings.parquet` — one row per row of the
opinions cache: `(ticker, bsns_year, rcept_no, receipt_dt, opinion_code, raw,
n_amendments)`, where `rcept_no` and `receipt_dt` (the 접수일자) belong to the
사업보고서's first filing and `raw` is its 당기 감사의견. `list.json` lists every
version of each report; `[첨부추가]` marks the original itself, and every other
bracket an amendment. A report never amended is the filing `dart_audit` read,
so its cached opinion is copied, unless the endpoint gave no opinion text. For
that report and for every amended one, the collector fetches the first filing
and reads its opinion table on the current-period row — the row labelled 당기,
else the highest 제N기, since some filers list the oldest year first. The
table's cells are tagged `OPN_CMTk` (`OPN_CMTk_A`, the 감사보고서 row, in the
form used since the FY2024 reports); older forms leave them untagged, and the
collector then takes the first table whose header cells are 사업연도 and
감사의견. Where no table has them, it accepts 감사(또는 검토)의견, 감사(검토)의견
or 감사 및 검토 의견 — headers that can also stand over a review conclusion, so
the exact 감사의견 wins — and the older spelling 사업년도. On 105 never-amended
filings sampled across 2015–2025 on 2026-09-15, the tagged cell matched the
structured endpoint's opinion every time. The untagged forms are mostly reports
the structured endpoint could not read either, so few have an endpoint opinion
to compare with.

Use this table, not the opinions cache, for what the market read and when:

- 6,060 of the 25,608 rows (23.7 %) were amended at least once. In 5,468 of
  them the opinions cache carries a receipt number dated after the first
  filing's: the endpoint served the correction.
- 120 rows read 한정 / 부적정 / 의견거절 in the first filing and 적정 as
  served — 015540's FY2020–2022 among them — and 13 go the other way.
- Of the 921 never-amended rows the endpoint gave no opinion text for, 809
  read one of 적정 / 한정 / 부적정 / 의견거절 in the document.
- 31 rows' first filings — 16 amended, 15 never amended — have no opinion
  table the collector reads, so their `opinion_code` is empty. Every row found
  its first filing in `list.json`.

### `dart_corp_actions.py` — corporate-action ground truth

`dart_corp_actions` harvests DART 주요사항보고서 events that move a share count
and splits them into two categories, which is what lets the price-adjustment
layer tell a corporate action apart from an entity change:

- **genuine** (유상증자 / 무상증자 / 유무상증자 / 감자) — price-affecting, and KRX's
  ChangesRatio already adjusts for it, so the share-count jump must *not* be
  read as a series break.
- **entity** (회사합병 / 회사분할 / 회사분할합병 / 주식교환) — the listing's economic
  identity may change, so the jump is a break candidate.

Reached through DART's 주요사항보고서 (DS005) endpoints, one call per (ticker,
event). Preferred shares have no `corp_code` of their own and resolve to the
parent common (`code[:5] + '0'`); 액면분할/병합 are absent from the event API and
are deliberately omitted, since a 액면 change always moves the price inversely
and is never misread as a break. DART's event API serves nothing filed before
2015; the earliest receipt here is 2015-01-07.

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

`corp_code_map.py` looks each ticker up in DART's corp-code directory
(`OpenDartReader.find_corp_code`) and memoises the answer in
`data/corp_code_cache.parquet`. A ticker the directory has no stock code for —
it drops some retired registrations — is a miss. Misses are logged to
`data/corp_code_misses.csv` for triage.

A DART error stops every collector here rather than reading as an empty
answer: `dart_audit` and `dart_audit_first` raise on every status but success
and no data (013, and 014 for a missing document), and `dart_corp_actions`
calls the event endpoints itself because OpenDartReader's `dart_event.event`
returns an empty frame on every error status. Each keeps what it fetched
before the stop, so the next run resumes; a `dart_corp_actions` ticker whose
events did not all answer is fetched again.

## Endpoints used

| Source | URL | Notes |
|---|---|---|
| DART audit-opinion | `opendart.fss.or.kr/api/accnutAdtorNmNdAdtOpinion.json` | DS002/2020009; **bsns_year ≥ 2015 only**. Not wrapped by OpenDartReader — `dart_audit._fetch_one` calls it via `requests.get` directly |
| DART 주요사항보고서 events | `opendart.fss.or.kr/api/{piicDecsn,fricDecsn,…}.json` (DS005) | 증자 / 감자 / 합병 / 분할 / 주식교환 per (ticker, event); used by `dart_corp_actions`, which reads the status itself. Nothing filed before 2015 |
| DART 공시검색 | `opendart.fss.or.kr/api/list.json` | every 사업보고서 of a corp_code, original and 정정 (`last_reprt_at=N`); used by `dart_audit_first` |
| DART 공시서류원본 | `opendart.fss.or.kr/api/document.xml` | the first filing's main document, read at the `OPN_CMT1` cell; used by `dart_audit_first` |

DART rate cap: 20,000 req/day per API key; `run_dart_audit_resume.sh` runs one
day's batch and logs to `runtime/`. `dart_audit` for ~4,300 tickers
× ~10 years ≈ 43,000 req → batch across ~3 days (resumable via the
`dart_audit_opinions.parquet` cache).

## Rerun cadence

| Collector | Cadence | Why |
|---|---|---|
| `dart_audit`                | annually (post-Mar audit-filing season) | annual cadence by nature |
| `dart_audit_first`          | after each `dart_audit` run | reads the rows `dart_audit` wrote; resume-safe |
| `dart_corp_actions`         | after a marcap refresh, once the candidate share-jump list has been rebuilt | new corporate actions land continuously; resume-safe, so a re-run only fetches what is new |
