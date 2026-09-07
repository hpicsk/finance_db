"""Index membership on a given date, from KRX's 지수구성종목 endpoint.

Collects the constituent list of KOSPI200 / KOSDAQ150 for each date in a range.
The endpoint sits behind a free data.krx.co.kr account:

    export KRX_ID="your_id"
    export KRX_PW="your_password"

Columns
    ``date``    the date the membership is quoted as of (datetime)
    ``index``   the index name (코스피 200 / 코스닥 150)
    ``ticker``  6-digit issue code
    ``name``    short issue name

Index codes, which are KRX-internal and not published as a table
    코스피 200  ``group_id='1'``, ``ind_idx2='028'``
    코스닥 150  ``group_id='2'``, ``ind_idx2='203'``
    코스피 100  ``group_id='1'``, ``ind_idx2='034'``
    코스피 50   ``group_id='1'``, ``ind_idx2='035'``
    KRX 300     ``group_id='4'``, ``ind_idx2='106'``

Launch dates, before which a query returns nothing rather than failing
    KOSPI200 1994-06-15, KOSDAQ150 2015-07-07

    python collect_index_members.py                 # month-end, 2001 to now
    python collect_index_members.py --freq weekly
    python collect_index_members.py --freq daily    # slow
"""

import argparse
import time
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

from krx_utils import DEFAULT_DELAY, DEFAULT_END, save_with_csv, setup_logging, trading_dates

logger = setup_logging()

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# -----------------------------------------------------------------------
# { display name: (group_id, ind_idx2) }
# -----------------------------------------------------------------------
INDEX_TARGETS: Dict[str, Tuple[str, str]] = {
    "코스피 200": ("1", "028"),
    "코스닥 150": ("2", "203"),
    # add as needed:
    # "코스피 100": ("1", "034"),
    # "코스피 50":  ("1", "035"),
    # "KRX 300":    ("4", "106"),
}


def fetch_index_members(
    date: str, index_name: str, group_id: str, ind_idx2: str
) -> pd.DataFrame:
    """
    One date's constituent list for one index.
    Uses pykrx's internal 지수구성종목 class.
    """
    from pykrx.website.krx.market.core import 지수구성종목

    try:
        df = 지수구성종목().fetch(date, ind_idx2, group_id)
    except Exception as e:
        logger.warning("지수구성종목 failed for %s %s: %s", index_name, date, e)
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns={
        "ISU_SRT_CD": "ticker",
        "ISU_ABBRV":  "name",
    })

    if "ticker" not in df.columns:
        logger.warning("no ticker column: %s %s, cols=%s",
                       index_name, date, df.columns.tolist())
        return pd.DataFrame()

    df["date"]  = date
    df["index"] = index_name

    keep = ["date", "index", "ticker"]
    if "name" in df.columns:
        keep.append("name")
    return df[keep].copy()


def collect_index_members(
    start: str = "19940615",
    end:   str = DEFAULT_END,
    freq:  str = "monthly",
    targets: Dict[str, Tuple[str, str]] = None,
    output_path: Path = OUTPUT_DIR / "index_members.parquet",
    resume: bool = True,
    delay: float = DEFAULT_DELAY,
) -> pd.DataFrame:
    if targets is None:
        targets = INDEX_TARGETS

    dates = trading_dates(start, end, freq)
    logger.info("dates to collect: %d  (%s..%s, freq=%s)", len(dates), dates[0], dates[-1], freq)

    existing = pd.DataFrame()
    done_keys: set = set()
    if resume and output_path.exists():
        existing = pd.read_parquet(output_path)
        _dates = (
            pd.to_datetime(existing["date"]).dt.strftime("%Y%m%d")
            if pd.api.types.is_datetime64_any_dtype(existing["date"])
            else existing["date"].astype(str)
        )
        done_keys = set(zip(_dates, existing["index"]))
        logger.info("resuming: %d (date, index) pairs already done", len(done_keys))

    frames   = [existing] if not existing.empty else []
    save_every = 30
    total    = len(dates) * len(targets)
    count    = 0
    date_count = 0

    for date in dates:
        date_count += 1
        for idx_name, (group_id, ind_idx2) in targets.items():
            count += 1
            if (date, idx_name) in done_keys:
                continue

            logger.info("[%d/%d] %s %s", count, total, idx_name, date)
            df = fetch_index_members(date, idx_name, group_id, ind_idx2)

            if df.empty:
                logger.debug("  -> empty (index not launched yet, or no data)")
            else:
                logger.info("  -> %d issues", len(df))
                frames.append(df)

            time.sleep(delay)

        if date_count % save_every == 0 and frames:
            pd.concat(frames, ignore_index=True).to_parquet(output_path, index=False)
            logger.info("  [checkpoint written]")

    if not frames:
        logger.error("nothing collected")
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result["date"] = pd.to_datetime(result["date"].astype(str),
                                    format="%Y%m%d", errors="coerce")
    result = result.sort_values(["index","date","ticker"]).reset_index(drop=True)

    save_with_csv(result, output_path)
    logger.info("written: %s  (%d rows)", output_path, len(result))
    return result


def main():
    parser = argparse.ArgumentParser(description="KOSPI200/KOSDAQ150 constituent collector")
    parser.add_argument("--start",     default="19940615")
    parser.add_argument("--end",       default=DEFAULT_END)
    parser.add_argument("--freq",      default="monthly",
                        choices=["daily","weekly","monthly","yearly"])
    parser.add_argument("--delay",     default=DEFAULT_DELAY, type=float)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    collect_index_members(
        start=args.start, end=args.end, freq=args.freq,
        output_path=OUTPUT_DIR / "index_members.parquet",
        resume=not args.no_resume, delay=args.delay,
    )


if __name__ == "__main__":
    main()
