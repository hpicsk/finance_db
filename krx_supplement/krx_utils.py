"""Scaffolding the collectors and the reconstruction script share.

- ``setup_logging``  one ``logging.basicConfig`` for every script
- ``trading_dates``  start/end/freq -> a list of ``YYYYMMDD`` strings
- ``save_with_csv``  parquet plus a utf-8-sig csv mirror, written together
- ``DEFAULT_DELAY``  seconds to sleep between KRX requests
- ``DEFAULT_END``    the ``--end`` default, pinned so two runs cover the same
  span; taking today's date instead would make the output drift with the day
  it was collected on.
"""

import logging
from pathlib import Path
from typing import List

import pandas as pd
from pandas.tseries.offsets import BMonthEnd

DEFAULT_DELAY: float = 0.6
DEFAULT_END: str = "20260427"


def setup_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger()


def trading_dates(start: str, end: str, freq: str) -> List[str]:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    if freq == "daily":
        dates = pd.bdate_range(s, e)
    elif freq == "weekly":
        dates = pd.date_range(s, e, freq="W-FRI")
    elif freq == "monthly":
        dates = pd.date_range(s, e, freq=BMonthEnd())
    elif freq == "yearly":
        dates = pd.date_range(s, e, freq="BYE")
    else:
        raise ValueError(f"Unknown freq: {freq}")
    return [d.strftime("%Y%m%d") for d in dates]


def save_with_csv(df: pd.DataFrame, parquet_path: Path) -> None:
    df.to_parquet(parquet_path, index=False)
    df.to_csv(parquet_path.with_suffix(".csv"), index=False, encoding="utf-8-sig")
