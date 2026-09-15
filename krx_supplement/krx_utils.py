"""Scaffolding the collectors and the reconstruction script share.

- ``setup_logging``  one ``logging.basicConfig`` for every script
- ``trading_dates``  start/end/freq -> a list of ``YYYYMMDD`` strings
- ``DEFAULT_DELAY``  seconds to sleep between KRX requests
- ``DEFAULT_END``    the ``--end`` default, pinned so two runs cover the same
  span; taking today's date instead would make the output drift with the day
  it was collected on.
"""

import logging
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
