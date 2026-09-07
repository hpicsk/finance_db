"""Put the make-up sessions the trees never downloaded back into `ohlcv/` and
`price_adj/`, reading them from the date-keyed endpoint.

`adjusted_loader` used to reconstruct the sessions `price_adj/` carries and
`ohlcv/` does not — 303 rows in 96 stocks, every one a 補行交易日. That count is
a set difference between two local trees, so it can only see a session at least
one of them holds. `tape_universe.py` measures the same hole against the vendor
instead, and the hole is **1,941 rows in 507 stocks**: the 303 the loader could
reach, and 1,638 that neither tree has and nothing therefore reports. The damage
is the one the loader already named — an absent session makes the *next*
session's return span two sessions, and 1,940 of them are clustered on 14
holiday-adjacent Saturdays rather than scattered, which is the shape a study
reads as an effect.

The endpoint serves them today: a `data_id` request for 1338 on 2012-02-04
returns the row `ohlcv/1338.parquet` lacks. So the trees are behind a backfill
rather than the endpoint being short, which is the same thing the delisting
table did between the 315-row and 723-row pulls.

**Raw rows are safe to insert and adjusted rows are not.** A back-adjustment
factor is anchored at the present, so a row fetched today carries every event
since the tree was downloaded and a row in the file does not. Across four dates
the trees already cover, `ohlcv/` reproduces the endpoint exactly on every one
of ~1,500 comparisons, while `price_adj/` differs on 38 stocks by up to 32 % —
those are re-anchorings, not errors, and inserting one into a file at the older
anchor would splice two vintages inside a single series. Ten of the 38 are in
this repair set.

So the adjusted insert is gated per stock, at no extra request: a stock missing
some of the 15 dates almost always holds others, and those are the comparison.
A stock whose committed values agree with the endpoint is at the same anchor and
is repaired; one that disagrees needs its whole file re-downloaded rather than a
row added, and is reported instead of touched. The rows are inserted, never
overwritten — an existing row is left exactly as committed.

    python -m finmind_data.backfill_make_up_sessions --dry-run
    python -m finmind_data.backfill_make_up_sessions

Not folded into `download.py`: that script resumes each file from its own last
date, which moves the far end and cannot reach an interior hole.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

from .auth import token
from .window import COVERAGE_START, COVERAGE_END

HERE = Path(__file__).resolve().parent
API = "https://api.finmindtrade.com/api/v4/data"
TAPE = HERE / "tape"

TREES = {"ohlcv": "TaiwanStockPrice", "price_adj": "TaiwanStockPriceAdj"}

# Two committed closes for one session are the same number or they are two
# different factor vintages; the endpoint quotes to the cent and the trees carry
# the vendor's own rounding, which `adjusted_loader` measures at 5.9e-6 across
# the shared panel. Anything above that is a re-anchoring, not a rounding.
_VINTAGE_TOL = 1e-5


def _candidate_dates() -> list[str]:
    """Dates `ohlcv/` is missing interior rows on, measured against the tape.

    This only decides *where to look*. What actually gets inserted into a tree
    is decided per tree by what that tree's own endpoint serves on the date —
    the adjusted endpoint answers for ~1,500 stocks a session where the raw one
    answers for ~9,200, so a plan drawn from the raw tape would ask the adjusted
    tree for rows that do not exist and count them as failures.
    """
    plan = _sessions_missing_from("ohlcv")
    return sorted(plan["date"].unique())


def _sessions_missing_from(tree: str) -> pd.DataFrame:
    """(stock_id, date) the tape holds and this tree's file does not."""
    tape = pd.concat([pd.read_parquet(p) for p in sorted(TAPE.glob("*.parquet"))],
                     ignore_index=True)
    lo, hi = tape["date"].min(), tape["date"].max()
    by_code: dict[str, set[str]] = {}
    for c, d in zip(tape["stock_id"], tape["date"]):
        by_code.setdefault(c, set()).add(d)

    rows = []
    for p in sorted((HERE / tree).glob("*.parquet")):
        sid = p.stem
        if sid not in by_code:
            continue
        try:
            have = pd.read_parquet(p, columns=["date"])["date"].astype(str)
        except Exception:
            continue                      # a zero-row file has no date column
        have = {d[:10] for d in have if lo <= d[:10] <= hi}
        if not have:
            # The file covers nothing in the window — a delisting the vendor
            # serves no adjusted series for, or a listing outside it. Adding a
            # session to one would invent coverage rather than restore it.
            continue
        # Only sessions *interior* to what the file already spans are holes. A
        # date before its first row is the other condition entirely: the
        # vendor's adjusted series opens one session after the raw one for ~500
        # stocks, which `adjusted_loader` handles by carrying the adjacent
        # factor across (`adj_source == "vendor_carried"`). Repairing that here
        # would overwrite a handled edge with a second answer, and a date past
        # the last row would extend a series rather than fill it.
        first, last = min(have), max(have)
        rows += [(sid, d) for d in by_code[sid] - have if first < d < last]
    return pd.DataFrame(rows, columns=["stock_id", "date"])


def fetch(dataset: str, date: str) -> pd.DataFrame:
    params = {"dataset": dataset, "start_date": date, "end_date": date,
              "token": token()}
    for _ in range(6):
        r = requests.get(API, params=params, timeout=180)
        if r.status_code in (402, 429):
            time.sleep(3600 - (time.time() % 3600) + 60)
            continue
        r.raise_for_status()
        payload = r.json()
        if payload.get("status") != 200:
            raise RuntimeError(f"{dataset} {date}: {payload.get('msg')}")
        df = pd.DataFrame(payload.get("data") or [])
        if len(df):
            assert set(df["date"]) == {date}, f"{date}: response spans dates"
        return df
    raise RuntimeError(f"{dataset} {date}: exhausted retries")


def _vintage_verdict(sid: str, committed: pd.DataFrame,
                     snaps: dict[str, pd.DataFrame], dates: list[str]) -> str:
    """Whether `committed` is at the same factor anchor as today's endpoint.

    Compares every date the file and the snapshots share, which costs no extra
    request: a stock missing some of the dates almost always holds others.

    ``"same"``       every shared close agrees, so a fetched row can be inserted
    ``"stale"``      one disagrees, so the file needs re-downloading whole
    ``"unverified"`` nothing is shared, so the anchor cannot be established
    """
    checks = agreed = 0
    for d in dates:
        if not len(snaps[d]) or sid not in snaps[d].index:
            continue
        mine = committed.loc[committed["date"] == d, "close"]
        if not len(mine):
            continue
        a, b = float(mine.iloc[0]), float(snaps[d].loc[sid, "close"])
        scale = max(abs(a), abs(b))
        if scale == 0:
            continue
        checks += 1
        agreed += abs(a - b) / scale <= _VINTAGE_TOL
    if checks == 0:
        return "unverified"
    return "same" if agreed == checks else "stale"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    dates = _candidate_dates()
    print(f"candidate dates (interior gaps in ohlcv/ vs the tape): {len(dates)}")
    print("  " + ", ".join(f"{d} {pd.Timestamp(d).day_name()[:3]}" for d in dates))

    for tree, dataset in TREES.items():
        # A back-adjusted close is anchored at the present, so a row fetched now
        # carries every event since the file was written. A raw print carries no
        # factor and so has no vintage — measured, not assumed: across four
        # dates the trees already cover, `ohlcv/` reproduces the endpoint exactly
        # on every one of ~1,500 closes while `price_adj/` differs on 38 stocks
        # by up to 32 %.
        adjusted = dataset.endswith("Adj")
        snaps = {}
        for d in dates:
            s = fetch(dataset, d)
            snaps[d] = s.set_index("stock_id") if len(s) else s

        inserted = stale = unverified = 0
        stale_ids, unverified_ids = [], []
        n_planned = 0
        for path in sorted((HERE / tree).glob("*.parquet")):
            sid = path.stem
            try:
                f = pd.read_parquet(path)
            except Exception:
                continue
            if not len(f):
                continue
            f["date"] = f["date"].astype(str)
            span = f["date"][(f["date"] >= str(COVERAGE_START.date()))
                             & (f["date"] <= str(COVERAGE_END.date()))]
            if not len(span):
                continue
            first, last = span.min(), span.max()
            have = set(f["date"])
            # Interior only: a date before the file's first row is the vendor's
            # series-head edge, which `adjusted_loader` handles by carrying the
            # adjacent factor (`adj_source == "vendor_carried"`).
            want = [d for d in dates
                    if first < d < last and d not in have
                    and len(snaps[d]) and sid in snaps[d].index]
            if not want:
                continue
            n_planned += len(want)

            if adjusted:
                verdict = _vintage_verdict(sid, f, snaps, dates)
                if verdict == "unverified":
                    unverified += len(want)
                    unverified_ids.append(sid)
                    continue
                if verdict == "stale":
                    stale += len(want)
                    stale_ids.append(sid)
                    continue

            new = pd.concat([snaps[d].loc[[sid]].reset_index() for d in want],
                            ignore_index=True)[f.columns.tolist()]
            for c in f.columns:
                new[c] = new[c].astype(f[c].dtype)
            if not args.dry_run:
                out = (pd.concat([f, new], ignore_index=True)
                         .sort_values("date", kind="stable")
                         .reset_index(drop=True))
                assert out["date"].is_unique, f"{sid}: duplicate date after insert"
                assert len(out) == len(f) + len(new), f"{sid}: row count"
                out.to_parquet(path, index=False)
            inserted += len(new)

        print(f"\n=== {tree} ({dataset}) ===")
        print(f"  rows the endpoint serves and the file lacks : {n_planned:,}")
        print(f"  inserted                                    : {inserted:,}")
        if adjusted:
            print(f"  refused, file at an older factor vintage     : {stale} "
                  f"({len(stale_ids)} stocks) {sorted(stale_ids)}")
            print(f"  refused, no shared session to verify         : {unverified} "
                  f"({len(unverified_ids)} stocks) {sorted(unverified_ids)}")
            if stale_ids:
                print(f"  -> these need the whole file, not a row: python download.py "
                      f"--datasets {tree} --stocks {' '.join(sorted(stale_ids))}")
        assert inserted + stale + unverified == n_planned, (
            f"{tree}: {n_planned} planned but {inserted}+{stale}+{unverified} "
            f"accounted for — rows went missing silently")
    return 0


if __name__ == "__main__":
    sys.exit(main())
