"""Write the vendor's current volume, value and trade count over the rows the
trees still hold at its first answer.

The vendor raised these counts on 12 of the 14 make-up Saturdays after
`ohlcv/` was downloaded. `download.py` never reads a written row again, so
`ohlcv/` kept the first answer on 5,925 rows. Both raw endpoints serve the
raised count now: the tape, the re-pull in `ohlcv_repull.parquet` and a fresh
date-keyed read agree on it.

The rows are found, not listed. The sessions are the ones on which some
`ohlcv/` row's volume or value differs from the tape. Each session is read back
from the date-keyed endpoint, and a row is rewritten where its counts differ
from what the endpoint serves now. Its prices must equal the endpoint's, or the
run stops: a raw price has no vintage, so a moved price means the row is not
the kind this repair is for.

`price_adj/` takes its three counts from the repaired `ohlcv/`, on every
in-window row where the two differ. Only its prices are adjusted, so its counts
are the raw ones. Its own endpoint would not repair them: read on 2026-09-11,
it served a count other than the raw endpoint's for 243 of the 1,945 stocks it
answers for on 2018-12-22.

Every value replaced is kept in `volume_repair.parquet`, and the run refuses to
start while that record exists.

    python -m finmind_data.volume_repair --dry-run
    python -m finmind_data.volume_repair
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .backfill_make_up_sessions import fetch
from .window import COVERAGE_START, COVERAGE_END

HERE = Path(__file__).resolve().parent
LOG = HERE / "volume_repair.parquet"
COUNTS = ["Trading_Volume", "Trading_money", "Trading_turnover"]
PRICES = ["open", "max", "min", "close", "spread"]
LO, HI = str(COVERAGE_START.date()), str(COVERAGE_END.date())


def _read(path: Path) -> pd.DataFrame | None:
    """A tree file, or None for the zero-row files that carry no schema."""
    if pq.ParquetFile(path).metadata.num_rows == 0:
        return None
    return pd.read_parquet(path)


def _stale_dates() -> list[str]:
    """In-window sessions on which some `ohlcv/` row's volume or value is not
    the tape's."""
    tape = pd.concat([pd.read_parquet(p) for p in sorted((HERE / "tape").glob("*.parquet"))],
                     ignore_index=True)
    tree = []
    for p in sorted((HERE / "ohlcv").glob("*.parquet")):
        if pq.ParquetFile(p).metadata.num_rows == 0:
            continue
        f = pd.read_parquet(p, columns=["date", "stock_id", "Trading_Volume",
                                        "Trading_money"])
        tree.append(f[(f["date"] >= LO) & (f["date"] <= HI)])
    m = pd.concat(tree, ignore_index=True).merge(
        tape, on=["date", "stock_id"], suffixes=("", "_tape"))
    off = (m["Trading_Volume"] != m["Trading_Volume_tape"]) | (
        m["Trading_money"] != m["Trading_money_tape"])
    return sorted(set(m.loc[off, "date"]))


def _entries(tree: str, rows: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    out = rows[["stock_id", "date"]].reset_index(drop=True).assign(tree=tree)
    for c in COUNTS:
        out[f"{c}_old"] = rows[c].astype("int64").to_numpy()
        out[f"{c}_new"] = new[c].astype("int64").to_numpy()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if LOG.exists():
        raise SystemExit(f"{LOG.name} exists: the repair has run, and that file "
                         f"is the only record of the values it replaced")

    dates = _stale_dates()
    print(f"sessions where ohlcv/ is not the tape's: {len(dates)} {dates}")
    snap = pd.concat([fetch("TaiwanStockPrice", d) for d in dates], ignore_index=True)
    assert not snap.duplicated(["date", "stock_id"]).any(), "endpoint repeats a row"
    served = dict(tuple(snap.groupby("stock_id")))

    log, fixed, written = [], {}, []
    for p in sorted((HERE / "ohlcv").glob("*.parquet")):
        f = _read(p)
        if f is None:
            continue
        on = f.index[f["date"].isin(dates)]
        if not len(on):
            continue
        now = f.loc[on, ["date", "stock_id"]].merge(
            served.get(p.stem, snap.iloc[:0]), how="left", on=["date", "stock_id"])
        now.index = on
        gone = now["close"].isna()
        assert not gone.any(), (
            f"{p.stem}: the endpoint no longer serves {sorted(now.loc[gone, 'date'])}")
        moved = (f.loc[on, COUNTS] != now[COUNTS]).any(axis=1)
        if not moved.any():
            continue
        rows = moved.index[moved]
        a, b = f.loc[rows, PRICES], now.loc[rows, PRICES]
        priced = ((a != b) & ~(a.isna() & b.isna())).any(axis=1)
        assert not priced.any(), (
            f"{p.stem}: a price moved on {sorted(f.loc[rows[priced], 'date'])}, "
            f"so these are not first-answer counts")
        log.append(_entries("ohlcv", f.loc[rows], now.loc[rows]))
        for c in COUNTS:
            f.loc[rows, c] = now.loc[rows, c].astype(f[c].dtype)
        fixed[p.stem] = f
        written.append(p)

    for p in sorted((HERE / "price_adj").glob("*.parquet")):
        q = HERE / "ohlcv" / p.name
        a = _read(p)
        if a is None or not q.exists():
            continue
        o = fixed.get(p.stem)
        if o is None:
            o = _read(q)
        if o is None:
            continue
        win = a.index[(a["date"] >= LO) & (a["date"] <= HI)]
        raw = a.loc[win, ["date"]].merge(o[["date"] + COUNTS], how="left", on="date")
        raw.index = win
        raw = raw.dropna(subset=["Trading_Volume"])
        moved = (a.loc[raw.index, COUNTS] != raw[COUNTS]).any(axis=1)
        if not moved.any():
            continue
        rows = moved.index[moved]
        log.append(_entries("price_adj", a.loc[rows], raw.loc[rows]))
        for c in COUNTS:
            a.loc[rows, c] = raw.loc[rows, c].astype(a[c].dtype)
        fixed[f"price_adj/{p.stem}"] = a
        written.append(p)

    log = pd.concat(log, ignore_index=True)
    summary = log.groupby("tree").agg(rows=("date", "size"), stocks=("stock_id", "nunique"),
                                      sessions=("date", "nunique"))
    print(summary.to_string())
    if args.dry_run:
        return 0
    for p in written:
        key = p.stem if p.parent.name == "ohlcv" else f"price_adj/{p.stem}"
        fixed[key].to_parquet(p, index=False)
    log.to_parquet(LOG, index=False)
    print(f"wrote {len(written)} files and {LOG.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
