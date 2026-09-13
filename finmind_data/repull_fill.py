"""Add the rows FinMind's per-stock query serves and the daily trees lack.

`download.py --extend` asks a file only for what follows its last row, so a row
the vendor published before that row never reaches the tree. The six daily trees
were pulled again whole on 2026-09-13, one request per stock over the range
`download.py` asks for, and the pull carries rows in three places the tree has
none: before its first row, inside its span, and on a session it holds under
another key.

`fill` adds every row the pull carries under a key the tree holds no row of, for
the universe's names inside the window. The key is the date on the five trees
that carry one row a session, and the date with the investor category on
`instflow/`, which carries one row per category. A row the tree holds is left as
it is, value for value, including where the pull carries another value:
`fin_bs_vintage.py` found a vendor revision is not a correction. A row the pull
no longer carries stays as well.

Every added row is written to `repull_fill/<tree>.parquet` before any tree is
written, one file per tree the snapshot holds, empty where the fill found
nothing. Each carries a `place` beside the row: where its date sat against the
span the tree file held, which the filled file no longer shows. The comparison
runs the other way too, and `repull_fill/unserved.parquet` holds every stock-date
the tree carries rows on and the pull carries none for. Those rows stay: a row
the vendor stops serving is not a row shown to be wrong. `fill` refuses to start
while the directory exists, because a second run finds nothing to add and would
overwrite the record of the first with an empty one.

    python -m finmind_data.repull_fill --snapshot DIR --dry-run
    python -m finmind_data.repull_fill --snapshot DIR
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .window import COVERAGE_END, COVERAGE_START

HERE = Path(__file__).resolve().parent
RECORD = HERE / "repull_fill"
KEY = {"ohlcv": ["date"], "instflow": ["date", "name"], "margin_short": ["date"],
       "shares": ["date"], "per_pbr": ["date"], "sec_lending": ["date"]}
# `sec_lending/` is keyed on its date alone, and its rows are not unique under
# that key: the tree carries 86,002 rows twice (README caveat 12), and nothing
# here can tell a repeated load from two identical transactions. A date the tree
# holds no row of takes every row the pull carries for it; a date it holds keeps
# the rows it has.
REPEATS = {"sec_lending"}


def _read(path: Path) -> pd.DataFrame | None:
    """A per-stock file, or None for the zero-row files that carry no schema."""
    return pd.read_parquet(path) if pq.ParquetFile(path).metadata.num_rows else None


def _keys(df: pd.DataFrame, key: list[str]) -> pd.Index:
    return pd.MultiIndex.from_frame(df[key]) if len(key) > 1 else pd.Index(df[key[0]])


def _place(dates: pd.Series, held: set[str] | None) -> list[str]:
    """Where each added date sits against the span the tree file held."""
    if held is None:
        return ["empty"] * len(dates)
    first, last = min(held), max(held)
    return ["same-day" if d in held else
            "before" if d < first else
            "after" if d > last else "interior" for d in dates]


def _plan(tree: str, snapshot: Path, names: list[str]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    """The rows to add to each of one tree's files, its columns, and what the pull lacks."""
    lo, hi = COVERAGE_START.strftime("%Y-%m-%d"), COVERAGE_END.strftime("%Y-%m-%d")
    key = KEY[tree]
    plan, empty, unserved = {}, None, []
    for sid in names:
        pulled = snapshot / tree / f"{sid}.parquet"
        if not pulled.exists():
            raise SystemExit(f"{pulled} is not in the snapshot")
        now = _read(pulled)
        held_all = _read(HERE / tree / f"{sid}.parquet")
        if held_all is not None:
            mine = held_all[held_all["date"].between(lo, hi)]
            theirs = set(now["date"]) if now is not None else set()
            gone = mine.loc[~mine["date"].isin(theirs), "date"].value_counts()
            if len(gone):
                unserved.append(pd.DataFrame({"tree": tree, "stock_id": sid,
                                              "date": gone.index, "rows": gone.to_numpy()}))
        if now is None:
            continue
        if empty is None:
            empty = now.iloc[:0].assign(place=pd.Series(dtype=object))
        now = now[now["date"].between(lo, hi)]
        if not len(now):
            continue
        held = held_all
        if held is None:
            add = now.assign(place="empty")
        else:
            if list(held.columns) != list(now.columns) or (held.dtypes != now.dtypes).any():
                raise SystemExit(f"{tree}/{sid}.parquet and the pull differ in schema: "
                                 f"{dict(held.dtypes)} against {dict(now.dtypes)}")
            if tree not in REPEATS:
                for side, df in (("tree", held), ("pull", now)):
                    if df.duplicated(key).any():
                        raise SystemExit(f"{tree}/{sid}.parquet: the {side} repeats a {key}, "
                                         f"so the key does not identify a row")
            add = now[~_keys(now, key).isin(_keys(held, key))]
            add = add.assign(place=_place(add["date"], set(held["date"])))
        if len(add):
            plan[sid] = add
    if empty is None:
        raise SystemExit(f"every {tree} file in {snapshot} is empty")
    left = (pd.concat(unserved, ignore_index=True).sort_values(["stock_id", "date"])
            .reset_index(drop=True) if unserved else
            pd.DataFrame({"tree": [], "stock_id": [], "date": [], "rows": []}))
    return plan, empty, left


def fill(snapshot: Path, dry_run: bool) -> dict[str, pd.DataFrame]:
    if RECORD.exists():
        raise SystemExit(f"{RECORD.name}/ exists: the fill has run, and a second run "
                         f"would overwrite its record with an empty one")
    trees = sorted(d.name for d in snapshot.iterdir() if d.is_dir())
    unknown = [t for t in trees if t not in KEY]
    if unknown:
        raise SystemExit(f"{snapshot} holds {unknown}, which this fill has no key for")
    names = sorted(pd.read_parquet(HERE / "universe.parquet")["stock_id"].astype(str))
    plans, added, unserved = {}, {}, []
    for tree in trees:
        plan, empty, left = _plan(tree, snapshot, names)
        plans[tree] = plan
        added[tree] = pd.concat(plan.values(), ignore_index=True) if plan else empty
        unserved.append(left)
    unserved = pd.concat(unserved, ignore_index=True)
    for tree, rec in added.items():
        sd = rec[["stock_id", "date"]].drop_duplicates()
        u = unserved[unserved["tree"] == tree]
        print(f"{tree}: {len(sd)} stock-dates of {sd['stock_id'].nunique()} names, "
              f"{len(rec)} rows, {rec['place'].value_counts().to_dict()}; "
              f"the pull lacks {len(u)} stock-dates of {u['stock_id'].nunique()} names, "
              f"{int(u['rows'].sum())} rows")
    if dry_run:
        return added
    RECORD.mkdir()
    for tree, rec in added.items():
        rec.to_parquet(RECORD / f"{tree}.parquet", index=False)
    unserved.to_parquet(RECORD / "unserved.parquet", index=False)
    for tree, plan in plans.items():
        for sid, add in plan.items():
            p = HERE / tree / f"{sid}.parquet"
            held = _read(p)
            add = add.drop(columns="place")
            out = pd.concat([held, add], ignore_index=True) if held is not None else add
            out.sort_values("date", kind="stable").reset_index(drop=True).to_parquet(p, index=False)
    return added


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path, required=True,
                    help="a whole re-pull of the daily trees, <tree>/<stock_id>.parquet")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    fill(args.snapshot, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
