"""Concat per-source kr_status event tables into a single events panel.

Read every ``kr_status/data/*_events.parquet`` matching the STATUS_COLUMNS
schema and write a unified ``kr_marcap/status/events.parquet``.  The cube
projection (date × ticker × status) is computed lazily at query time in
``query.py`` rather than materialised here — at Phase A volumes (~400 events,
~6000 backtest dates) the interval-scan is fast enough.

Phase B: add a daily_cube.parquet materialisation if per-query latency
becomes a bottleneck.

Usage:
    python -m kr_marcap.status.build_panel
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from kr_status.schema import STATUS_COLUMNS, DATA_DIR as KR_STATUS_DATA

EVENTS_PATH = Path(__file__).resolve().parent / "events.parquet"


def build_events_panel(in_dir: Path = KR_STATUS_DATA,
                       out_path: Path = EVENTS_PATH) -> pd.DataFrame:
    """Concat all per-source event parquets into one sorted table."""
    files = sorted(in_dir.glob("*_events.parquet"))
    if not files:
        raise RuntimeError(f"no *_events.parquet found in {in_dir} — run kr_status collectors first")

    frames = []
    for f in files:
        df = pd.read_parquet(f)
        missing = set(STATUS_COLUMNS) - set(df.columns)
        if missing:
            raise RuntimeError(f"{f.name} missing required columns: {missing}")
        frames.append(df[STATUS_COLUMNS])

    out = pd.concat(frames, ignore_index=True)
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    out["start_date"] = pd.to_datetime(out["start_date"])
    out["end_date"]   = pd.to_datetime(out["end_date"])
    out = out.sort_values(["status", "start_date", "ticker"]).reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)
    return out


def main() -> int:
    out = build_events_panel()
    print(f"wrote {len(out)} status events → {EVENTS_PATH}", file=sys.stderr)
    by_status = out["status"].value_counts().to_dict()
    print(f"  by status: {by_status}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
