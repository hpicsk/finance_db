"""Add the rows a raw vintage carries and the trees lack.

A tree is a per-stock file written by the per-stock query, which answers only
for names the universe already held and, under ``--extend``, only for what
follows a file's last row. A vintage under ``raw/`` is what the date-keyed
query answered, every stock at once per date, so it carries rows the trees
cannot have: a name the per-stock query returns nothing for, a row the vendor
added behind a file's last row, a session a file skipped. ``repair/repull_fill.py``
and ``repair/date_keyed_fill.py`` did this once each against a per-stock
snapshot and a statement snapshot; this reads the dated vintage instead, for
every tree in ``datasets.py``, and is the fill that follows a sweep.

The rule is the one those two fixed. A row the tree holds is left as it is,
value for value, including where the vintage carries another value: a vendor
revision is not a correction (CAVEATS.md 13). A row the tree lacks under the
tree's key is added, for the universe's names inside the window, and for a tree
whose rows repeat under their key (``Dataset.repeats``) a date is added whole
or not at all. A back-adjusted tree takes no rows: its factor is anchored at
the day it was pulled, so a row from another day splices two anchors, and the
file is replaced whole or left alone (``ADJUSTED_PRICES.md``, "One pull per
adjusted file").

Only the years the vintage finished are compared, read off its manifest, so a
fill can run against a sweep still in progress and a session the sweep has not
reached is neither added nor reported missing. The comparison runs both ways:
``records/fill_<vintage>/<tree>.parquet`` holds every row added with where its
date sat against the span the file held, and ``unserved.parquet`` every
stock-date the tree holds and the vintage does not. Those rows stay: a row the
vendor stops serving is not a row shown to be wrong. A second run against the
same vintage finds nothing to add and would overwrite the record of the first
with an empty one, so the fill refuses to start while its record exists.

    python -m finmind_data.repair.fill_from_vintage --vintage 2026-09-13 --dry-run
    python -m finmind_data.repair.fill_from_vintage --vintage 2026-09-13 --trees ohlcv instflow
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd
import pyarrow.parquet as pq

from ..client import log
from ..datasets import BY_TREE, DATASETS
from ..paths import DATA, RECORDS, TREES
from ..raw_store import Vintage
from ..window import COVERAGE_END, COVERAGE_START


def _read(path) -> pd.DataFrame | None:
    """A per-stock file, or None where it is absent or holds no schema."""
    if not path.exists() or not pq.ParquetFile(path).metadata.num_rows:
        return None
    return pd.read_parquet(path)


def _keys(df: pd.DataFrame, key: list[str]) -> pd.Index:
    return pd.MultiIndex.from_frame(df[key]) if len(key) > 1 else pd.Index(df[key[0]])


def _place(dates: pd.Series, held: set[str] | None) -> list[str]:
    """Where each added date sits against the span the tree file held."""
    if not held:
        return ["empty"] * len(dates)
    first, last = min(held), max(held)
    return ["same-day" if d in held else
            "before" if d < first else
            "after" if d > last else "interior" for d in dates]


def _finished_years(vintage: Vintage, tree: str) -> list[int]:
    years = sorted(int(k.split("/")[1]) for k in vintage.manifest()
                   if k.startswith(f"{tree}/") and k.split("/")[1].isdigit())
    if not years and f"{tree}/all" in vintage.manifest():
        years = list(range(COVERAGE_START.year, COVERAGE_END.year + 1))
    return years


def plan(vintage: Vintage, tree: str, names: set[str]
         ) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame, list[int]]:
    """The rows to add per stock, the tree's columns, what the vintage lacks, the years compared."""
    ds = BY_TREE[tree]
    years = _finished_years(vintage, tree)
    if not years:
        raise SystemExit(f"{vintage.root / tree} holds no finished year; sweep it first")
    lo, hi = COVERAGE_START.strftime("%Y-%m-%d"), COVERAGE_END.strftime("%Y-%m-%d")
    now = vintage.read(tree)
    now = now[now["stock_id"].astype(str).isin(names) & now["date"].between(lo, hi)
              & now["date"].str[:4].astype(int).isin(years)]
    key = list(ds.key)
    if not ds.repeats and now.duplicated(["stock_id"] + key).any():
        raise SystemExit(f"{tree}: the vintage carries a {key} twice for one stock, "
                         f"so the key does not identify a row")
    adds, unserved = {}, []
    empty = now.iloc[:0].assign(place=pd.Series(dtype=object))
    by_stock = dict(tuple(now.groupby("stock_id", sort=True)))
    for sid in sorted(names):
        held = _read(TREES / tree / f"{sid}.parquet")
        new = by_stock.get(sid)
        if held is not None:
            mine = held[held["date"].between(lo, hi)
                        & held["date"].str[:4].astype(int).isin(years)]
            theirs = set(new["date"]) if new is not None else set()
            gone = mine.loc[~mine["date"].isin(theirs), "date"].value_counts()
            if len(gone):
                unserved.append(pd.DataFrame({"tree": tree, "stock_id": sid,
                                              "date": gone.index, "rows": gone.to_numpy()}))
        if new is None or not len(new):
            continue
        if held is None:
            add = new.assign(place="empty")
        else:
            if set(held.columns) != set(new.columns):
                raise SystemExit(f"{tree}/{sid}.parquet and the vintage differ in columns: "
                                 f"+{sorted(set(new.columns) - set(held.columns))} "
                                 f"-{sorted(set(held.columns) - set(new.columns))}")
            new = new[list(held.columns)]
            if not ds.repeats and held.duplicated(key).any():
                raise SystemExit(f"{tree}/{sid}.parquet repeats a {key}, so the key does "
                                 f"not identify a row")
            if ds.repeats:
                add = new[~new["date"].isin(set(held["date"]))]
            else:
                add = new[~_keys(new, key).isin(_keys(held, key))]
            add = add.assign(place=_place(add["date"], set(held["date"])))
        if len(add):
            adds[sid] = add.reset_index(drop=True)
    left = (pd.concat(unserved, ignore_index=True).sort_values(["stock_id", "date"])
            .reset_index(drop=True) if unserved else
            pd.DataFrame({"tree": pd.Series(dtype=object), "stock_id": pd.Series(dtype=object),
                          "date": pd.Series(dtype=object), "rows": pd.Series(dtype="int64")}))
    return adds, empty, left, years


def fill(vintage: Vintage, trees: list[str], dry_run: bool) -> None:
    record = RECORDS / f"fill_{vintage.name}"
    if record.exists():
        raise SystemExit(f"{record} exists: the fill has run against this vintage, and a "
                         f"second run would overwrite its record with an empty one")
    names = set(pd.read_parquet(DATA / "universe.parquet")["stock_id"].astype(str))
    plans, added, unserved = {}, {}, []
    for tree in trees:
        if BY_TREE[tree].back_adjusted:
            log(f"{tree}: back-adjusted, takes no rows from another anchor; skipped")
            continue
        adds, empty, left, years = plan(vintage, tree, names)
        plans[tree] = adds
        added[tree] = pd.concat(adds.values(), ignore_index=True) if adds else empty
        unserved.append(left)
        rec = added[tree]
        sd = rec[["stock_id", "date"]].drop_duplicates()
        log(f"{tree} ({years[0]}..{years[-1]}): add {len(rec):,} rows on {len(sd):,} "
            f"stock-dates of {sd['stock_id'].nunique()} names "
            f"{rec['place'].value_counts().to_dict()}; the vintage lacks "
            f"{len(left):,} stock-dates of {left['stock_id'].nunique()} names the tree holds")
    if dry_run or not plans:
        return
    record.mkdir(parents=True)
    for tree, rec in added.items():
        rec.to_parquet(record / f"{tree}.parquet", index=False)
    pd.concat(unserved, ignore_index=True).to_parquet(record / "unserved.parquet", index=False)
    written = 0
    for tree, adds in plans.items():
        for sid, add in adds.items():
            p = TREES / tree / f"{sid}.parquet"
            held = _read(p)
            add = add.drop(columns="place")
            if held is not None:
                for c in held.columns:
                    add[c] = add[c].astype(held[c].dtype)
                out = pd.concat([held, add], ignore_index=True)
            else:
                out = add
            p.parent.mkdir(parents=True, exist_ok=True)
            out.sort_values("date", kind="stable").reset_index(drop=True).to_parquet(p, index=False)
            written += 1
    log(f"wrote {written} files and {record}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vintage", required=True, help="a directory under raw/, YYYY-MM-DD")
    ap.add_argument("--trees", nargs="*", default=None,
                    help="trees to fill (default: every tree the vintage holds)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    vintage = Vintage(args.vintage)
    trees = args.trees or [d.tree for d in DATASETS if (vintage.root / d.tree).exists()]
    unknown = sorted(set(trees) - set(BY_TREE))
    if unknown:
        log(f"unknown trees {unknown}; valid: {list(BY_TREE)}")
        return 2
    fill(vintage, trees, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
