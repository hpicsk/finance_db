"""Daily snapshots of KRX foreign ownership (외국인보유 비율, MDCSTAT03701).

Calls KRX's 외국인보유량(개별종목) all-issues endpoint, which returns the
foreign holding of every issue that traded on ``trdDd``. The endpoint sits
behind a login, so pykrx's authenticated session
(``pykrx.website.comm.auth``) is reused as-is — set ``KRX_ID`` and ``KRX_PW``.

Market codes
    ``STK`` 유가증권 (KOSPI), ``KSQ`` 코스닥 (KOSDAQ),
    ``KNX`` 코넥스 (KONEX, from 2013-07-01)

Output, partitioned by year and safe to re-run
    ``output/foreign_ownership_daily/year=YYYY/{YYYYMMDD}_{MKT}.parquet``

    One file is one (date, market) snapshot of every issue. An existing file is
    skipped, so an interrupted sweep resumes where it stopped. A non-trading day
    is written as a zero-row parquet, which is what stops it being retried on
    every later pass.

Columns
    ``ticker``, ``name``, ``shares_outstanding``, ``foreign_held``,
    ``foreign_pct``, ``foreign_limit_qty``, ``foreign_exhaustion_pct``,
    ``trade_date``, ``market``

    KRX_ID=… KRX_PW=… python -m krx_supplement.collect_foreign_ownership
    KRX_ID=… KRX_PW=… python -m krx_supplement.collect_foreign_ownership \
        --start 20200101 --end 20200131 --markets STK,KSQ
"""

import argparse
import time
from pathlib import Path

import pandas as pd
from pykrx.website.krx.market.core import 외국인보유량_전종목

from krx_utils import DEFAULT_DELAY, DEFAULT_END, setup_logging

logger = setup_logging()

OUTPUT_DIR = Path(__file__).parent / "output" / "foreign_ownership_daily"
DEFAULT_MARKETS = ("STK", "KSQ", "KNX")
KONEX_START = pd.Timestamp("2013-07-01")
DEFAULT_START = "20041001"

_RAW_TO_OUT = {
    "ISU_SRT_CD":        "ticker",
    "ISU_ABBRV":         "name",
    "LIST_SHRS":         "shares_outstanding",
    "FORN_HD_QTY":       "foreign_held",
    "FORN_SHR_RT":       "foreign_pct",
    "FORN_ORD_LMT_QTY":  "foreign_limit_qty",
    "FORN_LMT_EXHST_RT": "foreign_exhaustion_pct",
}
_NUMERIC_COLS = ("shares_outstanding", "foreign_held", "foreign_pct",
                 "foreign_limit_qty", "foreign_exhaustion_pct")
_EMPTY_SCHEMA = pd.DataFrame({
    "ticker":                 pd.Series(dtype="string"),
    "name":                   pd.Series(dtype="string"),
    "shares_outstanding":     pd.Series(dtype="Int64"),
    "foreign_held":           pd.Series(dtype="Int64"),
    "foreign_pct":            pd.Series(dtype="float64"),
    "foreign_limit_qty":      pd.Series(dtype="Int64"),
    "foreign_exhaustion_pct": pd.Series(dtype="float64"),
    "trade_date":             pd.Series(dtype="datetime64[ns]"),
    "market":                 pd.Series(dtype="string"),
})


def _output_path(date: pd.Timestamp, market: str) -> Path:
    return OUTPUT_DIR / f"year={date.year}" / f"{date.strftime('%Y%m%d')}_{market}.parquet"


def _normalise(raw: pd.DataFrame, date: pd.Timestamp, market: str) -> pd.DataFrame:
    df = raw.rename(columns=_RAW_TO_OUT).copy()
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    for c in _NUMERIC_COLS:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "", regex=False),
                              errors="coerce")
    df["shares_outstanding"] = df["shares_outstanding"].astype("Int64")
    df["foreign_held"]       = df["foreign_held"].astype("Int64")
    df["foreign_limit_qty"]  = df["foreign_limit_qty"].astype("Int64")
    df["trade_date"] = date
    df["market"] = market
    return df[list(_EMPTY_SCHEMA.columns)]


def _fetch(date: pd.Timestamp, market: str) -> pd.DataFrame | None:
    """Returns normalised frame, or None if the day was non-trading / empty."""
    dd = date.strftime("%Y%m%d")
    try:
        raw = 외국인보유량_전종목().fetch(trdDd=dd, mktId=market, isuLmtRto=0)
    except KeyError:
        # pykrx raises KeyError when the JSON `output` array is empty / shape changed
        return None
    if raw is None or len(raw) == 0:
        return None
    return _normalise(raw, date, market)


def collect(start: str, end: str, markets=DEFAULT_MARKETS, delay: float = 1.0) -> tuple[int, int, int]:
    dates = pd.bdate_range(pd.Timestamp(start), pd.Timestamp(end))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    n_written = n_empty = n_skipped = 0
    for i, date in enumerate(dates):
        for market in markets:
            if market == "KNX" and date < KONEX_START:
                continue
            out = _output_path(date, market)
            if out.exists():
                n_skipped += 1
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                df = _fetch(date, market)
            except Exception as e:
                logger.warning("fetch %s %s failed (%s) — retry after 5s",
                               date.date(), market, e)
                time.sleep(5)
                try:
                    df = _fetch(date, market)
                except Exception as e2:
                    logger.error("fetch %s %s failed twice: %s — skipping",
                                 date.date(), market, e2)
                    continue
            if df is None:
                _EMPTY_SCHEMA.to_parquet(out, index=False)
                n_empty += 1
            else:
                df.to_parquet(out, index=False)
                n_written += 1
            time.sleep(delay)
        if (i + 1) % 100 == 0:
            logger.info("progress: %s  written=%d empty=%d skipped=%d",
                        date.date(), n_written, n_empty, n_skipped)
    logger.info("done. written=%d empty=%d skipped=%d", n_written, n_empty, n_skipped)
    return n_written, n_empty, n_skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start",   default=DEFAULT_START, help="YYYYMMDD")
    ap.add_argument("--end",     default=DEFAULT_END,   help="YYYYMMDD")
    ap.add_argument("--markets", default=",".join(DEFAULT_MARKETS),
                    help="comma-separated subset of STK,KSQ,KNX")
    ap.add_argument("--delay",   default=DEFAULT_DELAY, type=float)
    args = ap.parse_args()
    markets = tuple(m.strip() for m in args.markets.split(",") if m.strip())
    collect(start=args.start, end=args.end, markets=markets, delay=args.delay)


if __name__ == "__main__":
    main()
