"""Sector of every issue on a given date, from KRX's 업종분류현황 endpoint.

Takes one all-issues sector snapshot per date across a range. The endpoint
sits behind a free data.krx.co.kr account:

    export KRX_ID="your_id"
    export KRX_PW="your_password"

Columns
    ``date``        the date the snapshot is quoted as of (datetime)
    ``ticker``      6-digit issue code (e.g. 005930)
    ``name``        short issue name
    ``market``      KOSPI / KOSDAQ
    ``sector_krx``  the exchange's own sector name

**Delisted issues are covered without asking for them.** Each snapshot returns
only the issues listed on its own date, so stacking the dates into a series
carries a delisted name up to the date it left, and no survivorship overlay is
needed on top.

    # what output/sector_mapping.parquet was built with
    python collect_sector.py --start 20050101 --freq daily

    python collect_sector.py     # defaults: 2015 onward, month-end snapshots
    python collect_sector.py --start 20000104 --end 20260320 --freq monthly
"""

import argparse
import time
from pathlib import Path

import pandas as pd

from krx_utils import DEFAULT_DELAY, DEFAULT_END, setup_logging, trading_dates

logger = setup_logging()

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

MARKET_CODES = {
    "STK": "KOSPI",
    "KSQ": "KOSDAQ",
}


def fetch_sector_snapshot(date: str) -> pd.DataFrame:
    """
    One date's sector mapping for every issue, via pykrx's internal class.
    KOSPI and KOSDAQ are fetched separately and concatenated.
    """
    from pykrx.website.krx.market.core import 업종분류현황

    frames = []
    for mktId, market_name in MARKET_CODES.items():
        try:
            df = 업종분류현황().fetch(date, mktId)
        except Exception as e:
            logger.warning("업종분류현황 failed for %s %s: %s", date, market_name, e)
            continue

        if df is None or df.empty:
            logger.debug("Empty: %s %s", date, market_name)
            continue

        df = df.rename(columns={
            "ISU_SRT_CD": "ticker",
            "ISU_ABBRV":  "name",
            "IDX_IND_NM": "sector_krx",
        })
        df["date"]   = date
        df["market"] = market_name

        keep = [c for c in ["date","ticker","name","market","sector_krx"] if c in df.columns]
        frames.append(df[keep])

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    for c in ["date","ticker","name","market","sector_krx"]:
        if c not in out.columns:
            out[c] = None
    return out[["date","ticker","name","market","sector_krx"]]


def collect_sector_mapping(
    start: str = "20150101",
    end:   str = DEFAULT_END,
    freq:  str = "monthly",
    output_path: Path = OUTPUT_DIR / "sector_mapping.parquet",
    resume: bool = True,
    delay: float = DEFAULT_DELAY,
) -> pd.DataFrame:
    dates = trading_dates(start, end, freq)
    logger.info("dates to collect: %d  (%s..%s, freq=%s)", len(dates), dates[0], dates[-1], freq)

    existing = pd.DataFrame()
    if resume and output_path.exists():
        existing = pd.read_parquet(output_path)
        done = set(
            pd.to_datetime(existing["date"]).dt.strftime("%Y%m%d").unique()
        )
        dates = [d for d in dates if d not in done]
        logger.info("resuming: %d dates left (%d already done)", len(dates), len(done))

    frames = [existing] if not existing.empty else []
    save_every = 20

    for i, date in enumerate(dates, 1):
        logger.info("[%d/%d] %s", i, len(dates), date)
        df = fetch_sector_snapshot(date)

        if df.empty:
            logger.warning("empty result for %s — skipped", date)
            time.sleep(delay * 2)
            continue

        frames.append(df)
        logger.info("  -> %d issues", len(df))

        if i % save_every == 0:
            pd.concat(frames, ignore_index=True).to_parquet(output_path, index=False)
            logger.info("  [checkpoint written]")

        time.sleep(delay)

    if not frames:
        logger.error("nothing collected")
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result["date"] = pd.to_datetime(result["date"].astype(str), format="%Y%m%d", errors="coerce")
    result = result.sort_values(["date","market","ticker"]).reset_index(drop=True)
    # parquet only, without the csv mirror `save_with_csv` writes: a
    # business-daily sweep is ~12 million rows, so the mirror is a 584 MB
    # duplicate that nothing reads. The index_* collectors keep the mirror
    # because their output is small and the csv is tracked.
    result.to_parquet(output_path, index=False)
    logger.info("written: %s  (%d rows)", output_path, len(result))
    return result


def main():
    parser = argparse.ArgumentParser(description="KRX sector-mapping collector")
    parser.add_argument("--start",     default="20150101")
    parser.add_argument("--end",       default=DEFAULT_END)
    parser.add_argument("--freq",      default="monthly",
                        choices=["daily","weekly","monthly","yearly"])
    parser.add_argument("--delay",     default=DEFAULT_DELAY, type=float)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    collect_sector_mapping(
        start=args.start, end=args.end, freq=args.freq,
        output_path=OUTPUT_DIR / "sector_mapping.parquet",
        resume=not args.no_resume, delay=args.delay,
    )


if __name__ == "__main__":
    main()
