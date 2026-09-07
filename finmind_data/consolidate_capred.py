"""Merge per-stock cap_red parquets into a single capital_reduction.parquet.

cap_red/ holds one file per stock, but capital reductions are sparse: most
stocks have none. Empty files are written with 0 columns; filter them out
before concat. Output sorted by date.

Clipped to the window like every other read of the trees. The filings are what
the window's start is set by, so an unclipped merge cannot reach further back
than `COVERAGE_START` — but `download.py --extend` moves the far end, and a
filing after `COVERAGE_END` prices a session the panel does not contain. With
the clip, re-running this after an extension rewrites the same file.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from finmind_data.window import clip

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "cap_red"
OUT = ROOT / "capital_reduction.parquet"


def main() -> None:
    files = sorted(SRC.glob("*.parquet"))
    if not files:
        print(f"no parquets in {SRC}; aborting")
        return

    frames = []
    empty_n = 0
    for path in files:
        df = pd.read_parquet(path)
        if df.empty or df.shape[1] == 0:
            empty_n += 1
            continue
        frames.append(df)

    if not frames:
        print(f"all {len(files)} files empty; nothing to consolidate")
        return

    out = clip(pd.concat(frames, ignore_index=True))
    out = out.sort_values(["date", "stock_id"])
    out = out.reset_index(drop=True)
    out.to_parquet(OUT, index=False)

    print(f"files scanned:    {len(files)}")
    print(f"empty (0 events): {empty_n}")
    print(f"non-empty stocks: {len(frames)}")
    print(f"total events:     {len(out)}")
    print(f"date range:       {out['date'].min()} .. {out['date'].max()}")
    print(f"saved:            {OUT}")


if __name__ == "__main__":
    main()
