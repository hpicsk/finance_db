"""Add the company-periods FinMind serves date-keyed and the per-stock trees lack.

FinMind answers a query naming no stock, every stock for one date, from other
coverage than a query naming one. The date-keyed answer holds two kinds of
company-period the trees lack. The first belongs to a delisted name the
per-stock query returns nothing for: `download.py` asks for it on every pass
and writes an empty file, or a series that stops early. The second is a row the
vendor added after the tree was pulled: `download.py --extend` asks only for
what follows a file's last row, so a row added before it never reaches the
tree.

`fill` reads one date-keyed pull per period end of `fin_is`, `fin_bs`, `fin_cf`
and `month_rev`, each named `<tree>_<period>.parquet`. It adds every
company-period the pull carries and the tree holds no row of, for the
universe's names inside the window the package answers for. A company-period
the tree holds is left as it is, including any row the pull carries and the
tree lacks. Such a row is a revision, and `fin_bs_vintage.py` found a revision
is not a correction. Every added row is written to
`date_keyed_fill/<tree>.parquet` before any tree is written. `fill` refuses to
start while that directory exists, because a second run finds nothing to add
and would overwrite the record of the first with an empty one.

    python -m finmind_data.date_keyed_fill --snapshot DIR [DIR ...] --dry-run
    python -m finmind_data.date_keyed_fill --snapshot DIR [DIR ...]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .window import COVERAGE_END, COVERAGE_START

HERE = Path(__file__).resolve().parent
RECORD = HERE / "date_keyed_fill"
TREES = ("fin_is", "fin_bs", "fin_cf", "month_rev")


def _pull(tree: str, snapshots: list[Path]) -> pd.DataFrame:
    """Every row the date-keyed pulls of one tree carry."""
    files = [p for s in snapshots for p in sorted(s.glob(f"{tree}_*.parquet"))]
    periods = [p.stem[len(tree) + 1:] for p in files]
    if not files:
        raise SystemExit(f"no {tree}_<period>.parquet in {[str(s) for s in snapshots]}")
    twice = sorted({d for d in periods if periods.count(d) > 1})
    if twice:
        raise SystemExit(f"{tree}: {twice[:3]} are pulled in more than one snapshot")
    parts = []
    for p, d in zip(files, periods):
        if not pq.ParquetFile(p).metadata.num_rows:
            continue
        f = pd.read_parquet(p)
        if (f["date"] != d).any():
            raise SystemExit(f"{p} carries rows dated other than {d}")
        parts.append(f)
    return pd.concat(parts, ignore_index=True)


def _plan(tree: str, snapshots: list[Path], names: set[str]) -> dict[str, pd.DataFrame]:
    """The rows to add to each of one tree's files, by stock."""
    lo, hi = COVERAGE_START.strftime("%Y-%m-%d"), COVERAGE_END.strftime("%Y-%m-%d")
    now = _pull(tree, snapshots)
    now = now[now["stock_id"].isin(names) & now["date"].between(lo, hi)]
    key = ["date", "stock_id"] + (["type"] if "type" in now.columns else [])
    if now.duplicated(key).any():
        raise SystemExit(f"{tree}: the pull carries a {key} twice")
    plan = {}
    for sid, new in now.groupby("stock_id", sort=True):
        f = pd.read_parquet(HERE / tree / f"{sid}.parquet")
        if len(f) and (list(f.columns) != list(new.columns)
                       or (f.dtypes != new.dtypes).any()):
            raise SystemExit(f"{tree}/{sid}.parquet and the pull differ in schema: "
                             f"{dict(f.dtypes)} against {dict(new.dtypes)}")
        add = new[~new["date"].isin(set(f["date"]) if len(f) else set())]
        if len(add):
            plan[sid] = add
    return plan


def fill(snapshots: list[Path], dry_run: bool) -> dict[str, pd.DataFrame]:
    if RECORD.exists():
        raise SystemExit(f"{RECORD.name}/ exists: the fill has run, and a second run "
                         f"would overwrite its record with an empty one")
    names = set(pd.read_parquet(HERE / "universe.parquet")["stock_id"].astype(str))
    plans = {tree: _plan(tree, snapshots, names) for tree in TREES}
    added = {tree: pd.concat(plan.values(), ignore_index=True) for tree, plan in plans.items()}
    for tree, rec in added.items():
        cps = rec[["stock_id", "date"]].drop_duplicates()
        print(f"{tree}: {len(cps)} company-periods of {cps['stock_id'].nunique()} "
              f"names, {len(rec)} rows")
    if dry_run:
        return added
    RECORD.mkdir()
    for tree, rec in added.items():
        rec.to_parquet(RECORD / f"{tree}.parquet", index=False)
    for tree, plan in plans.items():
        for sid, add in plan.items():
            p = HERE / tree / f"{sid}.parquet"
            f = pd.read_parquet(p)
            out = pd.concat([f, add], ignore_index=True) if len(f) else add
            out.sort_values("date", kind="stable").reset_index(drop=True).to_parquet(p, index=False)
    return added


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path, nargs="+", required=True,
                    help="directories of date-keyed pulls, <tree>_<period>.parquet")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    fill(args.snapshot, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
