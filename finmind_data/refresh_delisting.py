"""Re-pull `TaiwanStockDelisting` market-wide into `delisted_universe.parquet`.

The table is one market-wide request with no `data_id`, so a refresh is one
call rather than a per-stock sweep — `download.py` cannot serve it.

The vendor backfills this table. The first pull (2026-04-26) returned 315 rows;
the 2026-08-17 pull returns 723, of which 117 land inside the research window
and were absent before. It also *retracts*: five committed rows are gone from
the live response, one of them a name the exchange never actually delisted. A
refresh therefore has to be a replace, not a union — a union would preserve
exactly the vendor errors the backfill corrected — and the guard below is what
keeps a replace from being a silent truncation instead.

    python -m finmind_data.refresh_delisting
"""
from pathlib import Path

import pandas as pd
import requests

from .auth import token

HERE = Path(__file__).resolve().parent
API = "https://api.finmindtrade.com/api/v4/data"
OUT = HERE / "delisted_universe.parquet"

# A pull that returns fewer rows than this is a truncated response, not a
# vendor retraction: the table is cumulative and the count only grows. Set to
# the row count of the 2026-08-17 pull, which is what the committed file holds.
_MIN_ROWS = 723


def main() -> None:
    r = requests.get(API, params={"dataset": "TaiwanStockDelisting",
                                  "token": token()}, timeout=60)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") != 200:
        raise RuntimeError(f"FinMind returned {payload.get('status')}: "
                           f"{payload.get('msg')}")

    new = pd.DataFrame(payload["data"])
    if len(new) < _MIN_ROWS:
        raise RuntimeError(
            f"pull returned {len(new)} rows, fewer than the {_MIN_ROWS} already "
            f"committed — treat as a truncated response and do not overwrite")
    new["year"] = pd.to_datetime(new["date"]).dt.year
    new = new[["date", "stock_id", "stock_name", "year"]]

    old = pd.read_parquet(OUT)
    key = lambda d: set(zip(d["stock_id"].astype(str), d["date"].astype(str)))
    added, dropped = key(new) - key(old), key(old) - key(new)
    print(f"{len(old)} -> {len(new)} rows: +{len(added)} added, "
          f"-{len(dropped)} retracted")
    for sid, date in sorted(dropped):
        print(f"  retracted {sid} {date}")

    new.to_parquet(OUT, index=False)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
