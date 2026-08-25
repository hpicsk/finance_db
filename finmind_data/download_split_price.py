"""Download the exchange's 分割／面額變更 reference prices as a third event chain.

``adjust.py`` rebuilds a total-return factor from two chains of the exchange's
own reference prices — ``div_result/`` for 除權息 and ``capital_reduction.parquet``
for 減資. A third action reprices a share the same mechanical way and was in
neither: 面額變更, the flexible-par-value change the FSC opened to listed
companies, together with the 分割 / 反分割 it is filed alongside. A par value cut
from NT$10 to NT$1 multiplies the share count by ten and divides the quoted
price by ten, and the exchange publishes the pre- and post-change reference
prices for it exactly as it does for a 減資.

Without this file the rebuilt factor steps straight across the change and
carries the whole division as a return: on the twelve in-window events it is
wrong by 49 to 99 percentage points, reading 6548's 2019-09-09 ten-for-one as a
−89.0 % day. ``detect_unpriced_actions`` cannot cover for that, because it looks
for share-count *drops* — a cancellation — and this action is a share-count
*multiplication*. The two blind spots line up, which is why the class was
invisible from inside the package.

**The endpoint's first row is not a publication floor.** ``TaiwanStockSplitPrice``
begins on 2019-09-09, well inside the window, so the natural worry is caveat 5
again — a chain that starts after the prices do and hides its own early events.
It is not: an independent scan of ``shares/`` × ``ohlcv/`` for the signature of
this action — the share count multiplying while the close divides by the
matching ratio — finds eleven candidates across the whole window and every one
of them is already in the endpoint, the earliest on the endpoint's own first
date. Nothing precedes it because the flexible-par regime produced no listed
change before it, not because the table was trimmed.

The one event the scan does not reproduce is 8476's 2024-11-11, whose share
count updates two sessions after the reprice; that is the endpoints disagreeing
on a date, which is the same lag ``detect_unpriced_actions._EXPLAINED_WINDOW_DAYS``
exists to absorb, not a missing event.

``TaiwanStockParValueChange`` covers the same actions under different column
names and is a strict subset — every one of its 15 rows is already keyed in
``TaiwanStockSplitPrice`` — so only the wider table is taken.

    python -m finmind_data.download_split_price
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from .window import COVERAGE_START, COVERAGE_END

ROOT = Path(__file__).resolve().parent
API = "https://api.finmindtrade.com/api/v4/data"
DATASET = "TaiwanStockSplitPrice"
TOKEN_FILE = ROOT / ".token"
OUT = ROOT / "split_reference.parquet"

# The columns adjust.py reads, under the endpoint's own names. `type` is kept
# because it names which action repriced the share (面額變更 / 分割 / 反分割) and
# the step is the same formula for all three; the intraday reference bounds the
# endpoint also returns are not read by anything and are not stored.
COLUMNS = ["date", "stock_id", "type", "before_price", "after_price"]


def fetch() -> pd.DataFrame:
    """The whole table. It is market-wide and takes no data_id."""
    token = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""
    r = requests.get(API, params={"dataset": DATASET, "token": token}, timeout=120)
    r.raise_for_status()
    payload = r.json()
    rows = payload.get("data")
    if not rows:
        raise RuntimeError(f"{DATASET} returned no rows: {payload.get('msg')!r}")
    df = pd.DataFrame(rows)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError(f"{DATASET} is missing {missing}; got {list(df.columns)}")
    df = df[COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["stock_id"] = df["stock_id"].astype(str)
    df[["before_price", "after_price"]] = (
        df[["before_price", "after_price"]].astype(float))
    return df.sort_values(["date", "stock_id"]).reset_index(drop=True)


def main() -> None:
    df = fetch()
    df.to_parquet(OUT, index=False)
    # Stored whole and reported twice. The table runs past COVERAGE_END and a
    # later refresh will extend it further, so the count that matters to
    # `adjust.py` is the in-window one. It is 13, one more than the 12 caveat 5
    # quotes and `test_taiwan_par_value_changes_are_priced` pins: the odd one is
    # in the window but not in `universe.parquet`, and the check scores on
    # universe names because those are the ones a study prices.
    inwin = df["date"].between(COVERAGE_START, COVERAGE_END)
    print(f"{len(df):,} events / {df['stock_id'].nunique():,} stocks "
          f"({df['date'].min().date()} .. {df['date'].max().date()}) → {OUT}")
    print(f"{int(inwin.sum()):,} of them inside "
          f"{COVERAGE_START.date()}..{COVERAGE_END.date()}")
    print(df["type"].value_counts().to_string())


if __name__ == "__main__":
    main()
