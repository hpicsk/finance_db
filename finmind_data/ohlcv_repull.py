"""Pull `TaiwanStockPrice` again for a sample of stocks, and keep what came back.

`download.py` writes each row once and never asks the vendor for it again. A
row the vendor revises afterwards keeps its first value in `ohlcv/`, and no
check sees the revision. This pull is the second reading of those rows, and
`test_taiwan_repull_returns_the_stored_prices` holds it against `ohlcv/` row by
row.

The sample is 60 universe stocks, drawn at random from two strata. 40 come
from the stocks whose window holds a traded row with `open` outside
`[min, max]` (README caveat 11), because a correction of that defect would
show in them. 20 come from the rest, where a revision unrelated to the defect
would show. `SEED` fixes the draw, and the check draws it again.

The endpoint needs the sponsor tier, which lapses on 2026-09-16. The script
cannot run after that, so `ohlcv_repull.parquet` is the record of what the
vendor served, and it is committed.

    python -m finmind_data.ohlcv_repull
"""
from __future__ import annotations

import random
import time
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import requests

from .auth import token
from .window import COVERAGE_START, COVERAGE_END, clip

HERE = Path(__file__).resolve().parent
API = "https://api.finmindtrade.com/api/v4/data"
OUT = HERE / "ohlcv_repull.parquet"

# CHOSEN. Any fixed seed reproduces the draw; this one is the date of the pull.
SEED = 20260911
# CHOSEN. 60 requests, two thirds of them where a correction of caveat 11's
# defect would show.
N_ANOMALOUS = 40
N_CLEAN = 20
# Seconds between requests. The sponsor quota is 6,000 an hour, one per 0.6 s.
PACE = 0.7


def strata() -> tuple[list[str], list[str]]:
    """The universe stocks with a traded window row whose `open` is outside
    `[min, max]`, and the stocks with traded window rows and none such."""
    anomalous, clean = [], []
    u = pd.read_parquet(HERE / "universe.parquet")
    for sid in sorted(u["stock_id"].astype(str)):
        p = HERE / f"ohlcv/{sid}.parquet"
        # A zero-row file carries no schema, so a column-projected read fails.
        if pq.ParquetFile(p).metadata.num_rows == 0:
            continue
        r = pd.read_parquet(p, columns=["date", "open", "max", "min", "close"])
        r["date"] = pd.to_datetime(r["date"])
        r = clip(r)
        r = r[r["close"] > 0]
        if len(r):
            out = (r["open"] > r["max"]) | (r["open"] < r["min"])
            (anomalous if out.any() else clean).append(sid)
    return anomalous, clean


def draw(anomalous: list[str], clean: list[str]) -> list[str]:
    rng = random.Random(SEED)
    return rng.sample(anomalous, N_ANOMALOUS) + rng.sample(clean, N_CLEAN)


def pull(sid: str) -> pd.DataFrame:
    r = requests.get(API, params={
        "dataset": "TaiwanStockPrice", "data_id": sid,
        "start_date": str(COVERAGE_START.date()),
        "end_date": str(COVERAGE_END.date()), "token": token()}, timeout=180)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") != 200:
        raise RuntimeError(f"{sid}: {payload.get('msg')}")
    return pd.DataFrame(payload["data"])


def main() -> None:
    ids = draw(*strata())
    frames = []
    for sid in ids:
        frames.append(pull(sid))
        time.sleep(PACE)
    pd.concat(frames, ignore_index=True).to_parquet(OUT, index=False)
    print(f"{len(ids)} stocks -> {OUT.name}")


if __name__ == "__main__":
    main()
