"""Derive halt, admin, and alert events from marcap daily snapshots.

This is the canonical kr_status source for three KRX classifications. The
underlying field in marcap is published daily by KRX; FDR's
``KRX-ADMINISTRATIVE`` snapshot and DART's 관리종목지정/해제 filings are
both downstream views of the same classification and have been retired.

Three signals are emitted:

- ``status='halt'`` — derived from `ChangeCode == '0'` (KRX's daily
  no-trade flag). Works for all years 2004–2026. Note: on KONEX, this is
  stricter than the prior `(Volume==0) AND (Open==0)` mask, which
  over-counted illiquid no-trade days as halts; on KOSPI/KOSDAQ the two
  approaches agree to within ~0.1%.
- ``status='admin'`` — derived from `Dept.str.contains("관리종목")`. Dept
  is first populated in 2011 and reliable for admin/alert from ~2014;
  earlier marcap rows have `Dept = NaN`.
- ``status='alert'`` — derived from `Dept.str.contains("투자주의환기")`
  (투자주의환기종목 designation). Same coverage as admin.

Consecutive flagged business days per ticker are consolidated into single
``(start_date, end_date)`` events. A gap of more than 7 calendar days breaks
a run (handles weekends + Chuseok/Seollal).

Output matches ``kr_status.schema.STATUS_COLUMNS`` and is written to
``kr_status/data/marcap_halt_events.parquet`` (path kept for backward
compatibility) so the downstream event-study consumer
(``kr_marcap.status.build_panel``) can read it via
``events_path("marcap_halt")``.

Cross-checking with DART is a separate, sample-based calibration pass; see
``kr_status/marcap_halt_dart_crosscheck.py``.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path

import pandas as pd

from kr_status.schema import STATUS_COLUMNS, events_path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
MARCAP_DIR = REPO_ROOT / "marcap" / "data"
RUN_GAP_DAYS = 7  # tolerate up to a week between flagged days (Chuseok/Seollal)


def _load_years(start_year: int, end_year: int) -> pd.DataFrame:
    frames = []
    for year in range(start_year, end_year + 1):
        path = MARCAP_DIR / f"marcap-{year}.parquet"
        if not path.exists():
            logger.warning("missing %s — skipping", path.name)
            continue
        df = pd.read_parquet(
            path, columns=["Code", "Name", "Date", "ChangeCode", "Dept"]
        )
        frames.append(df)
        logger.info("loaded %s (%d rows)", path.name, len(df))
    if not frames:
        raise RuntimeError(f"no marcap files found in {MARCAP_DIR}")
    return pd.concat(frames, ignore_index=True)


def _consolidate(df: pd.DataFrame) -> pd.DataFrame:
    """Group consecutive flagged days per ticker into (start_date, end_date) events.

    Input: rows pre-filtered to flagged days only, with columns Code, Name, Date.
    Output: one row per event with columns ticker, start_date, end_date, detail.
    """
    if df.empty:
        return pd.DataFrame(columns=["ticker", "start_date", "end_date", "detail"])

    df = df.sort_values(["Code", "Date"]).reset_index(drop=True)
    gap = df.groupby("Code")["Date"].diff().dt.days
    new_run = gap.isna() | (gap > RUN_GAP_DAYS)
    df = df.assign(run_id=new_run.cumsum())

    events = (
        df.groupby(["Code", "run_id"], sort=False)
        .agg(
            start_date=("Date", "min"),
            end_date=("Date", "max"),
            name=("Name", "first"),
        )
        .reset_index()
        .rename(columns={"Code": "ticker", "name": "detail"})
    )
    return events[["ticker", "start_date", "end_date", "detail"]]


def build(start_year: int, end_year: int) -> pd.DataFrame:
    df = _load_years(start_year, end_year)
    fetched_at = pd.Timestamp.now().floor("s")

    halt_mask = df["ChangeCode"] == "0"
    halt_events = _consolidate(df.loc[halt_mask, ["Code", "Name", "Date"]])
    halt_events["status"] = "halt"
    halt_events["source"] = "marcap_changecode"
    halt_events["fetched_at"] = fetched_at
    logger.info("halt events: %d (from %d flagged rows)", len(halt_events), halt_mask.sum())

    admin_mask = df["Dept"].fillna("").str.contains("관리종목")
    admin_events = _consolidate(df.loc[admin_mask, ["Code", "Name", "Date"]])
    admin_events["status"] = "admin"
    admin_events["source"] = "marcap_dept"
    admin_events["fetched_at"] = fetched_at
    logger.info("admin events: %d (from %d flagged rows)", len(admin_events), admin_mask.sum())

    alert_mask = df["Dept"].fillna("").str.contains("투자주의환기")
    alert_events = _consolidate(df.loc[alert_mask, ["Code", "Name", "Date"]])
    alert_events["status"] = "alert"
    alert_events["source"] = "marcap_dept"
    alert_events["fetched_at"] = fetched_at
    logger.info("alert events: %d (from %d flagged rows)", len(alert_events), alert_mask.sum())

    events = pd.concat([halt_events, admin_events, alert_events], ignore_index=True)
    return events[STATUS_COLUMNS]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start-year", type=int, default=2004)
    parser.add_argument("--end-year", type=int, default=dt.datetime.now().year)
    parser.add_argument("--output", type=Path, default=events_path("marcap_halt"))
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
    )

    events = build(args.start_year, args.end_year)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    events.to_parquet(args.output, index=False)
    logger.info("wrote %d events → %s", len(events), args.output)


if __name__ == "__main__":
    main()
