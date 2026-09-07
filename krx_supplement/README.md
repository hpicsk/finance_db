# KRX Supplement Data Pipeline

Collects **sector mappings** and **KOSPI200 / KOSDAQ150 membership** from KRX's
own APIs, for the two series the FnGuide DataGuide export does not carry:

| What is needed | Source | Note |
|---|---|---|
| Daily sector mapping, all issues | KRX 업종분류현황 API | delisted names included by construction |
| Daily KOSPI200 / KOSDAQ150 membership | KRX 지수구성종목 API | carries the rebalancing history |

> **The delisted universe comes from `kr_delisted/`** instead — the KIND-based
> pipeline, which needs no credentials and carries marcap's unadjusted OHLCV
> alongside. A `data.krx.co.kr` delisting-master collector once lived here and
> was removed: it earned an IP block, and ISIN enrichment was the only thing it
> did that the KIND pipeline does not.

---

## Prerequisite: a KRX account

Since 2024 the `data.krx.co.kr` API answers only inside a **logged-in session**;
an anonymous request returns `LOGOUT (400)`.

1. Open [https://data.krx.co.kr](https://data.krx.co.kr) and register — 회원가입,
   top right. The account is free.
2. Put the credentials in the environment:

```bash
# in ~/.bashrc or ~/.zshrc
export KRX_ID="your_krx_id"
export KRX_PW="your_krx_password"
```

or inline, per run:

```bash
KRX_ID="id" KRX_PW="pw" python collect_sector.py --start 20240101 --end 20260320
```

---

## Install

```bash
pip install pykrx finance-datareader requests tqdm pandas pyarrow
```

---

## Quick start

Each script runs on its own; there is no end-to-end wrapper.

```bash
# 1) sector mapping (business-daily snapshots, needs KRX_ID/PW)
python collect_sector.py --start 20050101 --freq daily

# 2) index membership (KOSPI200 + KOSDAQ150, monthly snapshots, needs KRX_ID/PW)
python collect_index_members.py --start 19940615 --end 20260320 --freq monthly

# 3) index entry/exit event log (whole history in one call, no login)
python collect_index_changes.py

# 4) combine 2 + 3 into the daily index panel
python reconstruct_index_panel.py

# 5) foreign ownership (daily all-issue snapshots, needs KRX_ID/PW)
python collect_foreign_ownership.py --start 20050101
```

Rough timings:

- A quick test — the last two years, monthly (`--start 20240101`, steps 1–2): ~5 min
- Index membership, 2000 to now, monthly: 1–2 hours
- Sector mapping, 2005 to now, business-daily: 2–3 hours (~5,500 sessions)

### The minimum path to the daily index panel

`reconstruct_index_panel.py` collects nothing — it is a **pure transform**. It
reads `output/index_members.parquet` and `output/index_changes.parquet`, so both
have to exist first.

```bash
# 1) month-end snapshots (ground truth) — needs KRX_ID/KRX_PW
python collect_index_members.py --start 20000101 --freq monthly

# 2) the entry/exit event log (exact change dates) — no login
python collect_index_changes.py

# 3) 1 + 2 -> output/index_panel_daily.parquet
python reconstruct_index_panel.py
```

**Why both inputs.** KRX's event log is *incomplete*: a name removed
automatically on a delisting or merger often has no `REMOVE` event at all. So
the month-end snapshots are the ground truth, and the event log contributes only
the exact date a change took effect. `RECONSTRUCT.md` carries the algorithm.

> **Sector is not part of this.** `reconstruct_index_panel.py` handles index
> membership only. Run `collect_sector.py` separately for sector — KRX publishes
> no change-event log for sector, so there is nothing to reconstruct from.

---

## Output layout

```
output/
├── sector_mapping.parquet                  # sector mapping (business-daily snapshots)
├── index_members.parquet / .csv            # index membership (monthly snapshots)
├── index_changes.parquet / .csv            # index entry/exit event log
├── index_membership_intervals.parquet/.csv # per-ticker membership spells
├── index_panel_daily.parquet               # the reconstructed business-daily panel
├── index_reconstruction_sanity.csv         # reconstruction agreement report (audit)
├── index_reconstruction_synthetic.csv      # the injected events (audit)
└── foreign_ownership_daily/                # foreign ownership, partitioned by year
    └── year=YYYY/{YYYYMMDD}_{STK|KSQ|KNX}.parquet
```

> `foreign_ownership_daily/` is gitignored for its size (613 MB across 14.6k
> files) and is rebuilt by `collect_foreign_ownership.py`. Every other output
> file is tracked. `sector_mapping` is written as parquet only: the
> business-daily snapshot's csv mirror is a 584 MB duplicate that nothing reads.

> **Cadence per file:**
> - `sector_mapping.parquet` — **business-daily snapshots** (`--freq daily`;
>   the current build covers 2005-01-03..2026-04-27, 5,561 sessions).
> - `index_members.parquet` — **month-end snapshots** (`--freq monthly`), so a
>   change is seen up to a month after it happened.
> - `index_changes.parquet` — KRX's **exact change events**, whole history.
> - `index_panel_daily.parquet` — the month-end snapshots (ground truth) and the
>   event log **reconstructed to business-daily**.
> - `foreign_ownership_daily/` — one all-issue snapshot per (date, market).
>   Resume is per file, so an interrupted sweep continues where it stopped.

### sector_mapping.parquet
| Column | Type | Meaning |
|---|---|---|
| `date` | datetime | the date the snapshot is quoted as of |
| `ticker` | str | 6-digit issue code (`005930`) |
| `name` | str | short issue name |
| `market` | str | `KOSPI` / `KOSDAQ` |
| `sector_krx` | str | the exchange's own sector name (전기전자, 서비스업, …) |

### index_members.parquet
| Column | Type | Meaning |
|---|---|---|
| `date` | datetime | snapshot date (month-end) |
| `index` | str | `코스피 200` / `코스닥 150` |
| `ticker` | str | 6-digit issue code |
| `name` | str | short issue name |

### index_changes.parquet
The **exact entry and exit dates**, from KRX's 구성종목변경내역 page on
`index.krx.co.kr`. An effective date carrying both an ADD and a REMOVE becomes
two rows.

| Column | Type | Meaning |
|---|---|---|
| `date` | datetime | effective date (`appl_dd`) |
| `index` | str | `코스피 200` / `코스닥 150` |
| `action` | str | `ADD` / `REMOVE` |
| `isin` | str | 12-character ISIN |
| `ticker` | str | 6-digit issue code |
| `name` | str | short issue name |

### index_membership_intervals.parquet
One row per (index, ticker) spell of membership. `in_source` / `out_source` is
one of `log` (from the event log), `synthetic` (imputed from a snapshot
difference), `initial` (already a member at the first snapshot), or `None`
(still a member).

| Column | Type | Meaning |
|---|---|---|
| `index` | str | `코스피 200` / `코스닥 150` |
| `ticker` | str | 6-digit issue code |
| `name` | str | short issue name |
| `in_date` | datetime | entry date; NaT means already in at the first snapshot |
| `in_source` | str | `log` / `synthetic` / `initial` |
| `out_date` | datetime | exit date; NaT means still a member |
| `out_source` | str | `log` / `synthetic` / `None` |

### foreign_ownership_daily/year=YYYY/{YYYYMMDD}_{MKT}.parquet
Daily snapshots from KRX's 외국인보유량(개별종목) all-issues endpoint
(`MDCSTAT03701`). One file is one (date, market) covering every issue. Market
codes are `STK` (KOSPI), `KSQ` (KOSDAQ) and `KNX` (KONEX, from 2013-07-01).

| Column | Meaning |
|---|---|
| `ticker` / `name` | 6-digit issue code / short issue name |
| `shares_outstanding` | shares outstanding (상장주식수) |
| `foreign_held` | shares held by foreign investors |
| `foreign_pct` | foreign holding as a share of those outstanding |
| `foreign_limit_qty` | the foreign ownership ceiling, in shares |
| `foreign_exhaustion_pct` | how much of that ceiling is used |
| `trade_date` / `market` | the date quoted / market code |

> **A non-trading day and a failed fetch look the same.** `_fetch` writes a
> zero-row parquet in both cases, and the `out.exists()` resume check then skips
> it on every later run. A span whose response schema changed has to be deleted
> before it can be re-fetched — see limitation 6 below.

### index_panel_daily.parquet
Long-format membership, forward-filled to business days. KOSPI200 starts
1999-01-04, where the event log starts, and is a complete 200 names every day
from 2005; KOSDAQ150 starts 2015-07-07. `RECONSTRUCT.md`'s Limits section has
the detail.

| Column | Type | Meaning |
|---|---|---|
| `date` | datetime | business day |
| `index` | str | `코스피 200` / `코스닥 150` |
| `ticker` | str | 6-digit issue code |

---

## Using it from Python

```python
import pandas as pd

# ─────────────────────────────────────────────────────────────────
# 1. Sector mapping
# ─────────────────────────────────────────────────────────────────
sector = pd.read_parquet("output/sector_mapping.parquet")
sector["date"] = pd.to_datetime(sector["date"])

# one date's mapping
snap = sector[sector["date"] == "2024-01-31"]
print(snap.groupby("sector_krx")["ticker"].count().sort_values(ascending=False))

# one ticker's sector history
samsung = sector[sector["ticker"] == "005930"][["date", "sector_krx"]]
print(samsung.drop_duplicates())

# ─────────────────────────────────────────────────────────────────
# 2. Index membership
# ─────────────────────────────────────────────────────────────────
members = pd.read_parquet("output/index_members.parquet")

kospi200 = members[
    (members["date"] == "2024-01-31") &
    (members["index"] == "코스피 200")
]["ticker"].tolist()
print(f"KOSPI200 constituents: {len(kospi200)}")

# when one name was in the index
ticker = "000660"  # SK하이닉스
history = members[
    (members["ticker"] == ticker) &
    (members["index"] == "코스피 200")
]["date"].sort_values()
print(f"{ticker} in KOSPI200: {history.iloc[0]}..{history.iloc[-1]}")

# ─────────────────────────────────────────────────────────────────
# 3. A survivorship-bias-free universe
# ─────────────────────────────────────────────────────────────────
# Delisted names come from the KIND pipeline in kr_delisted/.
# from kr_delisted.delisted_loader import universe
# delisted_tickers = set(universe()["ticker"])

live_tickers = set(sector["ticker"].unique())
# full_universe = live_tickers | delisted_tickers

# ─────────────────────────────────────────────────────────────────
# 4. Joining sector onto a price panel
# ─────────────────────────────────────────────────────────────────
# price_long: columns = [date, ticker, close]

def join_sector(price_df: pd.DataFrame, sector_df: pd.DataFrame,
                method: str = "asof") -> pd.DataFrame:
    """Attach sector to a price frame.

    method='asof' takes the nearest snapshot at or before each date.
    """
    sector_dates = sector_df["date"].unique()
    sector_sorted = sector_df.sort_values("date")

    result = pd.merge_asof(
        price_df.sort_values("date"),
        sector_sorted[["date", "ticker", "sector_krx", "market"]].rename(columns={"date": "sector_date"}),
        left_on="date", right_on="sector_date",
        by="ticker",
        direction="backward",
    )
    return result
```

---

## Choosing a snapshot frequency

| Frequency | Requests (2000–2026) | Time | Suits |
|---|---|---|---|
| `daily` | ~6,500 | 2–4 h | precise rebalancing backtests |
| `weekly` | ~1,350 | 30–45 min | weekly factor models |
| `monthly` | ~312 | 5–10 min | **the default** — monthly factor / index work |
| `yearly` | ~26 | <1 min | a quick check |

Monthly snapshots can see a sector change up to a month late, which most
academic work tolerates.

---

## How delisted names are covered

The 업종분류현황 API returns **only the issues listed on the date asked for**, so
stacking snapshots into a series carries a name up to the date it left:

```
2020-01-31 snapshot: ticker A present (listed at the time)
2021-06-30 snapshot: ticker A absent  (delisted in 2021-03)
-> sector_mapping holds ticker A through January 2020
```

For the survivorship gap in the FnGuide dataset itself, use the KIND pipeline in
`kr_delisted/` (`delisting_calendar.csv`, `delisted_loader.py`), which ships
marcap's unadjusted OHLCV alongside, so no separate price backfill is needed.

---

## The KRX OpenAPI alternative (auth key)

[KRX Open API](https://openapi.krx.co.kr) issues an `AUTH_KEY` instead of
requiring an account. Its 업종분류현황 / 지수구성종목 endpoints are narrower than
the logged-in ones, which is why the account route is used here.

```python
import requests
headers = {"AUTH_KEY": "your_auth_key"}
r = requests.get(
    "https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES001_S1.cmd",
    headers=headers, params={"bld": "...", "trdDd": "20260422"}
)
```

---

## Known limitations

1. **Sector taxonomy.** Only KRX's own classification is available; WICS and
   GICS are FnGuide-only. Work needing GICS has to substitute the KRX
   classification or build a [mapping](https://www.msci.com/gics) separately.

2. **Same-day data.** KRX publishes a session's data after the close. A query
   during trading hours can return the previous day.

3. **Request rate.** KRX blocks sustained bursts. Keep the default delay
   (0.5–0.7 s).

4. **Session expiry.** A KRX session expires after an hour; re-login is handled
   automatically.

5. **KOSDAQ150 launch.** 2015-07-07. Earlier dates return an empty response.

6. **A failed fetch becomes a data gap, recorded only in the log.**
   `fetch_sector_snapshot` and `fetch_index_members` catch `Exception`, warn, and
   skip that (date, market). The row is simply absent from the output, so "no
   data existed that day" and "the fetch failed" are indistinguishable in the
   file. Read the log after collecting.

   `collect_foreign_ownership` is worse. `_fetch` maps `KeyError` to `None`,
   folding *a non-trading day* and *a changed response schema* into one value,
   and `None` writes an `_EMPTY_SCHEMA` parquet. The resume check
   (`out.exists()`) then skips that file forever, so a span collected while the
   schema differed stays empty no matter how often the collector is re-run.
   Delete those files to re-fetch them.

---

## Files

```
krx_supplement/
├── README.md                     this file
├── RECONSTRUCT.md                the daily-panel reconstruction algorithm
├── collect_sector.py             sector mapping (business-daily snapshots, pykrx)
├── collect_index_members.py      index membership (monthly snapshots, pykrx)
├── collect_index_changes.py      index entry/exit event log (no login)
├── collect_foreign_ownership.py  foreign ownership (daily all-issue snapshots)
├── reconstruct_index_panel.py    month-end snapshots + event log -> daily panel
├── krx_utils.py                  scaffolding the scripts share (logging /
│                                 business-day lists / parquet+csv writing /
│                                 the default request delay)
├── test_assertions.py            executable checks behind this file's claims
├── populations.json              the population size each check last read
├── sector_mapping.parquet        ⚠️ an old 2020-2025 monthly build. No collector
│                                 writes here — `collect_sector.py` writes only
│                                 to output/. Always read the output/ copy
└── output/                       collected data
    ├── sector_mapping.parquet
    ├── index_members.parquet / .csv
    ├── index_changes.parquet / .csv
    ├── index_membership_intervals.parquet / .csv
    ├── index_panel_daily.parquet
    ├── index_reconstruction_sanity.csv
    ├── index_reconstruction_synthetic.csv
    └── foreign_ownership_daily/year=YYYY/*.parquet
```

`pykrx` 1.2.x handles the KRX login internally, so there is no HTTP utility here
— `krx_utils.py` is logging, dates and writing, not HTTP. `KRX_ID` / `KRX_PW`
are needed by `collect_sector.py`, `collect_index_members.py` and
`collect_foreign_ownership.py`. `collect_index_changes.py` uses the public
`index.krx.co.kr` endpoint and needs no login.
