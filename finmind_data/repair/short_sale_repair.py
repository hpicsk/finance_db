"""Exchange `margin_short`'s two short-sale flow columns where the row's own balances say they are crossed.

A short sale raises the short balance and buying the position back lowers it, so
a row's balance identity is

    ShortSaleTodayBalance
      == ShortSaleYesterdayBalance + ShortSaleSell - ShortSaleBuy
         - ShortSaleCashRepayment

and the margin side carries the same identity with the buy and the sell the
other way round. The margin identity holds on every in-window row of the tree.
The short identity fails on 761,472 of them, in 750 names, every one dated
2011-2024 — the rows `download.py` wrote in the 2026-04-27 build, against none
of the rows it appended on 2026-09-10. Exchanging the two values repairs every
one. The whole re-pull of 2026-09-13 serves the two that way round on each of
the 759,918 it carries, and satisfies the identity on all 5,743,035 of its
in-window rows.

`repair` exchanges the two values on every in-window row of a universe name
whose short identity fails, and stops on a row the exchange does not repair: the
premise is that the pair is crossed, and a row failing for another reason is not
one this repair is for. It also stops on a row the re-pull carries with the two
values as the tree has them, which would contradict the reading above.

`short_sale_repair.parquet` keeps every row exchanged, with the values as the
tree held them and whether the re-pull confirmed the exchange, and the run
refuses to start while that record exists.

    python -m finmind_data.repair.short_sale_repair --snapshot DIR --dry-run
    python -m finmind_data.repair.short_sale_repair --snapshot DIR
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from ..window import COVERAGE_END, COVERAGE_START
from ..paths import DATA, RECORDS, TREES

RECORD = RECORDS / "short_sale_repair.parquet"
TREE = "margin_short"
BUY, SELL = "ShortSaleBuy", "ShortSaleSell"


def crossed(df: pd.DataFrame) -> pd.Series:
    """Each row whose short-sale flows contradict the balances beside them."""
    return (df["ShortSaleTodayBalance"]
            != df["ShortSaleYesterdayBalance"] + df[SELL] - df[BUY]
            - df["ShortSaleCashRepayment"])


def repair(snapshot: Path, dry_run: bool) -> pd.DataFrame:
    if RECORD.exists():
        raise SystemExit(f"{RECORD.name} exists: the repair has run, and a second run "
                         f"would overwrite its record with an empty one")
    lo, hi = COVERAGE_START.strftime("%Y-%m-%d"), COVERAGE_END.strftime("%Y-%m-%d")
    names = sorted(pd.read_parquet(DATA / "universe.parquet")["stock_id"].astype(str))
    rows, writes = [], {}
    for sid in names:
        p = TREES / TREE / f"{sid}.parquet"
        if not pq.ParquetFile(p).metadata.num_rows:
            continue
        held = pd.read_parquet(p)
        bad = crossed(held) & held["date"].between(lo, hi)
        if not bad.any():
            continue
        out = held.copy()
        out.loc[bad, [BUY, SELL]] = held.loc[bad, [SELL, BUY]].to_numpy()
        left = crossed(out.loc[bad])
        if left.any():
            d = out.loc[bad][left]
            raise SystemExit(f"{TREE}/{sid}.parquet: exchanging the two values leaves "
                             f"{len(d)} rows contradicting their balances, {list(d['date'][:3])}")
        rec = held.loc[bad, ["stock_id", "date", BUY, SELL]].copy()
        pulled = snapshot / TREE / f"{sid}.parquet"
        if not pulled.exists():
            raise SystemExit(f"{pulled} is not in the snapshot")
        now = (pd.read_parquet(pulled, columns=["date", BUY, SELL])
               if pq.ParquetFile(pulled).metadata.num_rows else None)
        if now is None:
            rec["repull"] = "absent"
        else:
            if now.duplicated("date").any():
                raise SystemExit(f"{pulled} repeats a date, so a row of it is not one row")
            m = rec.merge(now, on="date", how="left", suffixes=("", "_now"))
            same = (m[f"{BUY}_now"] == m[BUY]) & (m[f"{SELL}_now"] == m[SELL])
            if same.any():
                raise SystemExit(f"{TREE}/{sid}.parquet: the re-pull serves the two values "
                                 f"as the tree holds them on {int(same.sum())} rows the "
                                 f"balances call crossed, {list(m.loc[same, 'date'][:3])}")
            swapped = (m[f"{BUY}_now"] == m[SELL]) & (m[f"{SELL}_now"] == m[BUY])
            rec["repull"] = np.where(swapped, "exchanged",
                                     np.where(m[f"{BUY}_now"].notna(), "revised", "absent"))
        rows.append(rec)
        writes[sid] = out
    log = pd.concat(rows, ignore_index=True)
    print(f"{TREE}: {len(log)} rows in {log['stock_id'].nunique()} names, "
          f"{log['date'].min()}..{log['date'].max()}; "
          f"{log['repull'].value_counts().to_dict()}")
    if dry_run:
        return log
    log.to_parquet(RECORD, index=False)
    for sid, out in writes.items():
        out.to_parquet(TREES / TREE / f"{sid}.parquet", index=False)
    return log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path, required=True,
                    help="a whole re-pull of the daily trees, <tree>/<stock_id>.parquet")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    repair(args.snapshot, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
