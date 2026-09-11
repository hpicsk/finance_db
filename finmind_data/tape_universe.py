"""Rebuild the universe from the tape instead of from the vendor's registry,
and write what traded as `tape/{year}.parquet` plus the per-code summary
`tape_universe.parquet`.

`universe.parquet` is assembled from `taiwan_stock_info`, which is a list of
names the vendor still serves, patched with `delisted_universe.parquet` for the
ones it has dropped. Both are registries, and a registry is the artifact that
forgets: the 2026-08-17 refresh took the delisting table from 315 rows to 723
and retracted five committed ones, and every name the universe holds today
rests on the current state of those two files. Nothing in the package checks
them against a source that is not a registry.

The tape is that source. `TaiwanStockPrice` answers a `start_date` with no
`data_id` by returning every instrument that traded that session — 10,626 codes
in 2012, 50,688 in 2024 — so the union over the window is the set of codes that
*traded*, derived from execution records rather than from anyone's list of who
was listed. A name delisted in 2016 is in the 2015 sessions whatever the
registry says about it now.

Two limits decide what this can and cannot settle, and they are the reason the
output is a cross-check rather than a replacement universe.

**A code that traded is not a common stock.** The response mixes ETFs, warrants,
TDRs, preferreds and 興櫃 in with the commons, and nothing in a price row says
which is which. The 4-digit filter below is the same one `build_universe.py`
uses and it is not sufficient on its own — Taiwan numbers its ETFs `00xx` and
its depositary receipts `91xx` — so instrument type still has to come from the
registry. The tape can therefore show that a code is *missing* from the
universe; deciding whether it *belongs* there needs the registry back.

**A code is not a company.** 4415 and 2432 were reissued after their first
occupant delisted. The tape records trades under a code and cannot say the code
changed hands, which is the distinction `build_universe.py` matches on names to
make and `adjusted_loader` flags as `series_break`.

The sweep is one request per calendar day rather than per known session, so the
calendar comes out of the tape too. A day the market was closed returns zero
rows and costs one request; deriving the date list from `ohlcv/` instead would
have made the answer depend on the tree whose completeness is the question.
Sundays are dropped because the tree holds none in twenty years and the make-up
sessions the exchange does hold are Saturdays.

    python -m finmind_data.tape_universe

Resumable per year: a year whose file already reaches the end of what this
window asks for is skipped, so an interrupted sweep resumes at the year it
stopped in — and a year written short because coverage once ended inside it is
re-swept rather than skipped for existing.
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

from .auth import token
from .pit_universe import emerging_boundary
from .window import COVERAGE_START, COVERAGE_END

HERE = Path(__file__).resolve().parent
API = "https://api.finmindtrade.com/api/v4/data"
TAPE = HERE / "tape"
OUT = HERE / "tape_universe.parquet"

# The sponsor tier allows 6,000 requests/hour and the sweep needs ~4,890. Three
# workers hold the rate near 5,400/hr at the ~2 s round trip a recent session
# costs, which finishes inside the hour; a fourth would overshoot the quota and
# earn a 402, and fetch() answers that by sleeping to the reset.
WORKERS = 3

# The longest the exchange is shut inside a year. 農曆春節 closes it for up to
# nine sessions, so a year file whose last date falls short of the last day
# swept for by less than this is complete rather than truncated. A month is
# that with room: the case it has to separate is a year cut off in March, not
# one whose last session was the 28th.
_YEAR_END_SLACK = pd.Timedelta(days=31)

# Only 4-digit numeric codes are kept. This is `build_universe.py`'s filter, and
# keeping the tape to it drops the warrants that make a recent session 50,000
# rows wide while retaining every code the universe could be missing.
CODE = r"\d{4}"


def fetch_session(date: str) -> pd.DataFrame:
    """Every instrument that traded on `date`, narrowed to 4-digit codes.

    Returns an empty frame for a day the market was closed. Retries a rate
    limit by sleeping to the quota reset; anything else raises, because a
    session silently recorded as empty is a code list with a hole in it and
    the union would not show which day it came from.
    """
    params = {"dataset": "TaiwanStockPrice", "start_date": date,
              "end_date": date, "token": token()}
    for attempt in range(6):
        try:
            r = requests.get(API, params=params, timeout=180)
        except requests.RequestException as e:
            if attempt == 5:
                raise
            print(f"  net-err {date}: {e}; retry", flush=True)
            time.sleep(20)
            continue
        if r.status_code in (402, 429):
            sleep_s = 3600 - (time.time() % 3600) + 60
            print(f"  rate-limit {date}; sleep {sleep_s:.0f}s to quota reset",
                  flush=True)
            time.sleep(sleep_s)
            continue
        r.raise_for_status()
        payload = r.json()
        if payload.get("status") != 200:
            raise RuntimeError(f"{date}: {payload.get('msg')}")
        df = pd.DataFrame(payload.get("data") or [])
        if df.empty:
            return df
        # The endpoint keys on `start_date` and ignores `end_date`; assert it
        # rather than trust it, since a range response would silently attribute
        # other sessions' codes to this one.
        assert set(df["date"]) == {date}, f"{date}: response spans {set(df['date'])}"
        keep = df["stock_id"].str.fullmatch(CODE)
        return df.loc[keep, ["date", "stock_id", "Trading_Volume",
                             "Trading_money"]].reset_index(drop=True)
    raise RuntimeError(f"{date}: exhausted retries")


def sweep() -> None:
    """Pull every in-window session, one year per file."""
    TAPE.mkdir(exist_ok=True)
    days = pd.date_range(COVERAGE_START, COVERAGE_END, freq="D")
    days = days[days.dayofweek != 6]          # the exchange never trades Sunday
    for year, block in days.groupby(days.year).items():
        path = TAPE / f"{year}.parquet"
        if path.exists():
            # What the file holds, not that it exists. A year coverage ended
            # inside was written short, and skipping it for existing leaves the
            # rest of that year out of the calendar permanently — the calendar
            # `pit_universe` builds, so `universe_at` would raise on a session
            # the market held. `test_taiwan_tape_years_are_whole` is the check
            # that finds one already written.
            have = pd.to_datetime(pd.read_parquet(path, columns=["date"])["date"])
            reach = have.max() if len(have) else None
            if reach is not None and reach >= block.max() - _YEAR_END_SLACK:
                print(f"{year}: skip (covers to {reach.date()})", flush=True)
                continue
            print(f"{year}: re-sweep — file reaches "
                  f"{reach.date() if reach is not None else 'nothing'}, "
                  f"this window asks to {block.max().date()}", flush=True)
        dates = [d.strftime("%Y-%m-%d") for d in block]
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            frames = list(pool.map(fetch_session, dates))
        got = [f for f in frames if not f.empty]
        df = pd.concat(got, ignore_index=True)
        df.to_parquet(path, index=False)
        print(f"{year}: {len(dates)} days queried, {len(got)} sessions, "
              f"{len(df):,} 4-digit rows, {df['stock_id'].nunique()} codes "
              f"[{time.time() - t0:.0f}s]", flush=True)


def _registry() -> pd.DataFrame:
    """What `taiwan_stock_info` says each code is, as one row per code.

    Joined into the artifact rather than looked up when the check runs: the
    tape says a code traded and only the registry says whether it was a common
    stock, so a cross-check that fetches its own classification would compare a
    fixed tape against a registry that has moved. Stamped here, it is dated
    evidence like the rest of the file. Any of a code's rows carrying an
    excluded instrument type excludes the code, which is `build_universe.py`'s
    rule — dropping rows and deduplicating afterwards keeps a stock alive on
    whichever classification the response happened to list first.
    """
    raw = pd.DataFrame(requests.get(
        API, params={"dataset": "TaiwanStockInfo", "token": token()},
        timeout=180).json()["data"])
    excluded = {"ETF", "ETN", "受益證券", "存託憑證", "臺灣存託憑證",
                "創新版股票", "創新板股票"}
    g = raw.groupby("stock_id")
    out = pd.DataFrame({
        "registry_types": g["type"].apply(lambda s: "|".join(sorted(set(s)))),
        "registry_excluded": g["industry_category"].apply(
            lambda s: bool(set(s) & excluded)),
    })
    # `registry_types` is the union over a code's rows and says nothing about
    # when each applied, so a name that left 興櫃 after the window closed reads
    # as a listing that traded inside it. The registry dates its rows; the
    # boundary is joined in here so a check reading this file can tell the two
    # apart without a pull of its own.
    out["emerging_until"] = emerging_boundary(raw)
    return out.reset_index()


def summarise() -> pd.DataFrame:
    """One row per code the tape served, over the whole window."""
    df = pd.concat([pd.read_parquet(p) for p in sorted(TAPE.glob("*.parquet"))],
                   ignore_index=True)
    # A zero-volume row is FinMind's encoding for a session the stock did not
    # trade, so it says the code existed rather than that it changed hands; both
    # counts are kept because the first is what a universe is about and the
    # second is what a return series needs.
    traded = df[df["Trading_Volume"] > 0]
    out = pd.DataFrame({
        "sessions": df.groupby("stock_id").size(),
        "sessions_traded": traded.groupby("stock_id").size(),
        "first_date": df.groupby("stock_id")["date"].min(),
        "last_date": df.groupby("stock_id")["date"].max(),
        "first_traded": traded.groupby("stock_id")["date"].min(),
        "last_traded": traded.groupby("stock_id")["date"].max(),
        "money_total": traded.groupby("stock_id")["Trading_money"].sum(),
        "money_max": traded.groupby("stock_id")["Trading_money"].max(),
    })
    out["sessions_traded"] = out["sessions_traded"].fillna(0).astype(int)
    out = out.reset_index().merge(_registry(), on="stock_id", how="left")
    # A code the registry has no row for at all — it traded and the vendor's
    # list of instruments has since forgotten it. Kept as its own value rather
    # than folded into the exclusions, because it is the one bucket whose
    # instrument type nothing in the package can settle.
    out["registry_types"] = out["registry_types"].fillna("")
    out["registry_excluded"] = out["registry_excluded"].fillna(False).astype(bool)
    return out


def main() -> int:
    sweep()
    summary = summarise()
    summary.to_parquet(OUT, index=False)
    print(f"\n{len(summary)} four-digit codes traded in "
          f"{COVERAGE_START.date()}..{COVERAGE_END.date()} -> {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
