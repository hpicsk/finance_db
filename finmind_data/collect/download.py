"""Resumable per-stock downloader: one FinMind request per (stock, dataset).

Writes one parquet per stock under ``trees/<tree>/``, for every dataset in
``datasets.py``. Skips a file that exists. ``--extend`` tops each existing file
up to a later ``--end`` instead of skipping it: skip-existing is per *file*, so
it cannot move an end date — every file exists, so a plain re-run with a later
``--end`` downloads nothing and reports a clean pass. Under ``--extend`` a file's
own last date is what the next request starts from, and the pull is appended to
it. A back-adjusted file is re-pulled whole instead: its rows are anchored at the
day they were pulled, so an append would splice two anchors into one series.

The per-stock query answers only for names the universe already holds, so a
name absent from ``universe.parquet`` is never fetched and the hole it leaves is
invisible afterwards. ``collect/sweep.py`` asks date-keyed instead and has no
such dependence; this script remains the way to pull one stock's whole history.

    python -m finmind_data.collect.download --datasets price_adj --stocks 2330
    python -m finmind_data.collect.download --extend --end 2026-09-09
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from ..client import VendorRefused, get, log
from ..datasets import DATASETS
from ..paths import DATA, TREES

VENDOR = {d.tree: d.vendor for d in DATASETS}
# A back-adjusted series is anchored at the day it is pulled: an event after that
# rescales every row before it. Appending a later pull to one leaves the old rows
# at the old anchor, and the adjusted return jumps on the first appended session
# with no event under it. `--extend` re-pulls these whole.
BACK_ADJUSTED = {d.tree for d in DATASETS if d.back_adjusted}


def fetch(dataset: str, stock_id: str, start: str, end: str) -> pd.DataFrame | None:
    """One stock's rows over the span, or None where the vendor refused.

    An error the vendor names is not an answer. Returned empty, it would be
    written as a zero-row file or appended as nothing, and both read later as
    "the stock had no rows in the range".
    """
    try:
        return get(dataset, data_id=stock_id, start=start, end=end)
    except VendorRefused as e:
        log(f"  refused {stock_id} {dataset}: {e}")
        return None


def download_stock(stock_id: str, start: str, end: str,
                   datasets: dict[str, str], extend: bool = False) -> dict:
    """Download the given datasets for one stock.

    Skips existing files, or under `extend` requests only what each one is
    missing at its far end and appends that — except a back-adjusted file,
    which it re-pulls whole. Every dataset here carries a `date` column, so the
    resume point is read from the file rather than tracked separately.
    """
    result = {subdir: "skip" for subdir in datasets}
    for subdir, dataset in datasets.items():
        path = TREES / subdir / f"{stock_id}.parquet"
        whole = subdir in BACK_ADJUSTED
        old = None
        req_start = start
        if path.exists():
            if not extend:
                continue
            old = pd.read_parquet(path)
            if not len(old):
                # An empty file records that the stock had no rows in the range
                # pulled, which says nothing about a range it did not cover, so
                # it is re-pulled whole rather than treated as a resume point.
                old = None
            elif whole:
                # From the file's own first row where that is earlier, so a
                # `--start` chosen to bound the appends cannot cut its history.
                req_start = min(start, str(old["date"].min())[:10])
            else:
                last = pd.to_datetime(old["date"]).max()
                if last >= pd.Timestamp(end):
                    continue
                req_start = (last + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        df = fetch(dataset, stock_id, req_start, end)
        if df is None:
            result[subdir] = "fail"
            continue
        if whole and old is not None:
            held = set(old["date"].astype(str).str[:10])
            got = set(df["date"].astype(str).str[:10]) if len(df) else set()
            gone = sorted(held - got)
            if gone:
                # The vendor dropping some of the stock's history, or an `--end`
                # short of the file's last row: the file is kept whole at its
                # own anchor and the stock counts as a failure.
                log(f"  refused {stock_id} {dataset}: the whole re-pull lacks "
                    f"{len(gone)} of the {len(held)} dates the file holds, {gone[:3]}")
                result[subdir] = "fail"
                continue
            result[subdir] = f"whole({len(df)})"
        elif old is not None:
            if set(df.columns) != set(old.columns) and not df.empty:
                # A column added or dropped between pulls would be concatenated
                # into a ragged file whose new rows carry NaN for the old
                # columns and vice versa. Refuse and leave the file as it was.
                log(f"  schema-drift {stock_id} {dataset}: "
                    f"+{sorted(set(df.columns) - set(old.columns))} "
                    f"-{sorted(set(old.columns) - set(df.columns))}")
                result[subdir] = "fail"
                continue
            added = len(df)
            if added:
                df = (pd.concat([old, df], ignore_index=True)
                        .sort_values("date", kind="stable")
                        .reset_index(drop=True))
            else:
                df = old
            result[subdir] = f"+{added}"
            if not added:
                continue
        else:
            result[subdir] = f"ok({len(df)})"
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2005-01-01")
    # The session `window.COVERAGE_END` names, so a fresh clone pulls to where
    # coverage ends; `test_taiwan_coverage_does_not_outrun_the_data` keeps the
    # two equal.
    ap.add_argument("--end", default="2026-09-09")
    ap.add_argument("--extend", action="store_true",
                    help="top existing files up to --end instead of skipping "
                         "them; each file resumes from its own last date, and a "
                         "back-adjusted one is re-pulled whole")
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--stocks", nargs="*", default=None,
                    help="explicit stock_id list (overrides universe)")
    ap.add_argument("--datasets", nargs="*", default=None,
                    help="subset of the trees in datasets.py (e.g. price_adj "
                         "per_pbr); default = all")
    args = ap.parse_args()

    if args.datasets is None:
        active = dict(VENDOR)
    else:
        unknown = set(args.datasets) - set(VENDOR)
        if unknown:
            log(f"unknown --datasets keys: {sorted(unknown)}; valid: {sorted(VENDOR)}")
            return 2
        active = {k: VENDOR[k] for k in args.datasets}

    if args.stocks:
        stock_ids = args.stocks
    else:
        universe = pd.read_parquet(DATA / "universe.parquet")
        stock_ids = universe["stock_id"].tolist()

    stock_ids = stock_ids[args.offset:]
    if args.limit > 0:
        stock_ids = stock_ids[: args.limit]

    log(f"=== start: {len(stock_ids)} stocks, {args.start}..{args.end}, "
        f"datasets={list(active)}{', extend' if args.extend else ''} ===")

    ok_n = fail_n = skip_n = 0
    for i, sid in enumerate(stock_ids, 1):
        res = download_stock(sid, args.start, args.end, active, extend=args.extend)
        status = " ".join(f"{k}={v}" for k, v in res.items())
        log(f"{i}/{len(stock_ids)} {sid}: {status}")
        if any(v == "fail" for v in res.values()):
            fail_n += 1
        elif all(v == "skip" for v in res.values()):
            skip_n += 1
        else:
            ok_n += 1

    log(f"=== done: ok={ok_n} skip={skip_n} fail={fail_n} ===")
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
