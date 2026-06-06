"""
krx_utils.py
------------
공통 유틸리티 — 4개 수집/재구성 스크립트가 공유하는 스캐폴딩.

- setup_logging  : 동일한 logging.basicConfig
- trading_dates  : start/end/freq → YYYYMMDD 문자열 리스트
- save_with_csv  : parquet + utf-8-sig csv 미러 동시 저장
- DEFAULT_DELAY  : KRX 요청 간 기본 sleep
- DEFAULT_END    : --end CLI 기본값 (의미 없는 drift 방지)
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
        dates = pd.date_range(s, e, freq="BY")
    else:
        raise ValueError(f"Unknown freq: {freq}")
    return [d.strftime("%Y%m%d") for d in dates]


def save_with_csv(df: pd.DataFrame, parquet_path: Path) -> None:
    df.to_parquet(parquet_path, index=False)
    df.to_csv(parquet_path.with_suffix(".csv"), index=False, encoding="utf-8-sig")
