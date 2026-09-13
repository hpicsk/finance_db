"""Sweep FinMind date-keyed, every stock at once per date, into a dated vintage.

``download.py`` asks per stock, so it can only ask about names it already holds,
and a name the universe lacks leaves a hole nothing reports. A date-keyed query
names no stock: it returns every instrument the vendor has rows for on that
date, delisted or not, so the set of names is an output of the sweep rather than
an input to it. It is also what an extension costs: one request per new session
per dataset, against one per file per dataset for the per-stock route.

Dates asked, by the cadence ``datasets.py`` gives each dataset:

    day       every calendar day in the span
    session   every date this vintage's own ``ohlcv`` answered rows for, so
              ``ohlcv`` is swept first and the calendar is read off the tape
              rather than off a file whose completeness is the question
    month     the first of each month
    quarter   the four quarter ends
    range     one request, start to end

Rows are narrowed to ``datasets.CODE``, the scope every tree already has; a
price session carries ten times as many warrant rows as stock rows and nothing
here reads them. Each response is checked to carry only the date asked for,
since a range answer silently attributed to one date is a calendar with a hole
in it.

Resumable per (dataset, year): a year whose manifest entry records the last
date this run asks for is skipped, so an interrupted sweep resumes where it
stopped and a later run with a further ``--end`` re-sweeps the last year only.
Files are written whole, to a temporary name first, so a crash leaves no
half-year behind.

    python -m finmind_data.collect.sweep --end 2026-09-12
    python -m finmind_data.collect.sweep --end 2026-09-12 --datasets fin_is fin_bs
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..client import get, log
from ..datasets import BY_TREE, CODE, DATASETS
from ..raw_store import Vintage
from ..window import COVERAGE_END, COVERAGE_START

# Three in flight keeps the pacer's slots filled at the ~1 s a price session
# takes to answer; the pacer, not the worker count, bounds the hourly total.
WORKERS = 3

# `ohlcv` first, because every `session` dataset takes its dates from it.
ORDER = ["ohlcv"] + [d.tree for d in DATASETS if d.cadence == "session"] + \
        [d.tree for d in DATASETS if d.cadence not in ("session",) and d.tree != "ohlcv"]


def _dates(cadence: str, start: pd.Timestamp, end: pd.Timestamp,
           vintage: Vintage) -> list[str]:
    if cadence == "day":
        days = pd.date_range(start, end, freq="D")
    elif cadence == "session":
        days = pd.to_datetime(vintage.dates("ohlcv"))
        days = days[(days >= start) & (days <= end)]
    elif cadence == "month":
        days = pd.date_range(start.replace(day=1), end, freq="MS")
    elif cadence == "quarter":
        days = pd.date_range(start, end, freq="QE")
    else:
        raise ValueError(cadence)
    return [d.strftime("%Y-%m-%d") for d in days]


def _fetch(vendor: str, date: str) -> pd.DataFrame:
    df = get(vendor, start=date, end=date)
    if len(df):
        got = set(df["date"])
        assert got == {date}, f"{vendor} {date}: response spans {sorted(got)[:3]}"
        df = df[df["stock_id"].astype(str).str.fullmatch(CODE)].reset_index(drop=True)
    return df


def _write(path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def sweep_one(tree: str, vintage: Vintage, start: pd.Timestamp, end: pd.Timestamp,
              workers: int) -> None:
    ds = BY_TREE[tree]
    if ds.cadence == "range":
        key = f"{tree}/all"
        done = vintage.manifest().get(key)
        if done and done["asked_through"] >= end.strftime("%Y-%m-%d"):
            log(f"{tree}: skip (asked through {done['asked_through']})")
            return
        t0 = time.time()
        df = get(ds.vendor, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
        df = df[df["stock_id"].astype(str).str.fullmatch(CODE)].reset_index(drop=True)
        _write(vintage.path(tree, "all"), df)
        vintage.record(key, {"asked_from": start.strftime("%Y-%m-%d"),
                             "asked_through": end.strftime("%Y-%m-%d"), "requests": 1,
                             "rows": int(len(df)), "codes": int(df["stock_id"].nunique()) if len(df) else 0,
                             "seconds": round(time.time() - t0, 1),
                             "finished": dt.datetime.now().isoformat(timespec="seconds")})
        log(f"{tree}: {len(df):,} rows in one range request")
        return

    dates = _dates(ds.cadence, start, end, vintage)
    by_year: dict[int, list[str]] = {}
    for d in dates:
        by_year.setdefault(int(d[:4]), []).append(d)
    for year, asked in by_year.items():
        key = f"{tree}/{year}"
        done = vintage.manifest().get(key)
        if done and done["asked_through"] >= asked[-1] and vintage.path(tree, year).exists():
            log(f"{tree} {year}: skip (asked through {done['asked_through']})")
            continue
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            frames = list(pool.map(lambda d: _fetch(ds.vendor, d), asked))
        got = [f for f in frames if len(f)]
        df = pd.concat(got, ignore_index=True) if got else pd.DataFrame()
        _write(vintage.path(tree, year), df)
        vintage.record(key, {"asked_from": asked[0], "asked_through": asked[-1],
                             "requests": len(asked), "answered": len(got),
                             "rows": int(len(df)),
                             "codes": int(df["stock_id"].nunique()) if len(df) else 0,
                             "seconds": round(time.time() - t0, 1),
                             "finished": dt.datetime.now().isoformat(timespec="seconds")})
        log(f"{tree} {year}: {len(asked)} dates asked, {len(got)} answered, "
            f"{len(df):,} rows, {df['stock_id'].nunique() if len(df) else 0} codes "
            f"[{time.time() - t0:.0f}s]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=str(COVERAGE_START.date()))
    ap.add_argument("--end", default=str(COVERAGE_END.date()))
    ap.add_argument("--vintage", default=dt.date.today().isoformat(),
                    help="the day the sweep started; the directory under raw/")
    ap.add_argument("--datasets", nargs="*", default=None,
                    help="trees to sweep (default all), in datasets.py's names")
    ap.add_argument("--workers", type=int, default=WORKERS)
    args = ap.parse_args()

    trees = ORDER if args.datasets is None else args.datasets
    unknown = sorted(set(trees) - set(BY_TREE))
    if unknown:
        log(f"unknown datasets {unknown}; valid: {list(BY_TREE)}")
        return 2
    trees = [t for t in ORDER if t in trees]
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)
    vintage = Vintage(args.vintage)
    log(f"=== sweep {vintage.name}: {start.date()}..{end.date()}, {trees}, "
        f"{args.workers} workers ===")
    for tree in trees:
        sweep_one(tree, vintage, start, end, args.workers)
    log("=== sweep done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
