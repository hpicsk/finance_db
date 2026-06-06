"""
collect_index_members.py
------------------------
KOSPI200 / KOSDAQ150 일별 구성종목 수집기
==========================================
KRX [지수구성종목] API → 특정 날짜의 인덱스 구성종목 리스트 수집.

## 필수 조건
    export KRX_ID="your_id"
    export KRX_PW="your_password"

## 제공 컬럼
    date    : 기준일 (datetime)
    index   : 인덱스명 (코스피 200 / 코스닥 150)
    ticker  : 6자리 종목코드
    name    : 종목약칭

## 인덱스 코드 (KRX 내부)
    코스피 200  : group_id='1', ind_idx2='028'
    코스닥 150  : group_id='2', ind_idx2='203'
    코스피 100  : group_id='1', ind_idx2='034'
    코스피 50   : group_id='1', ind_idx2='035'
    KRX 300     : group_id='4', ind_idx2='106'

## 출시일 참고
    KOSPI200  : 1994-06-15
    KOSDAQ150 : 2015-07-07

## 사용법
    python collect_index_members.py                    # 월말, 2001~현재
    python collect_index_members.py --freq weekly      # 주별
    python collect_index_members.py --freq daily       # 일별 (느림)
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
# 인덱스 정의: { 표시명: (group_id, ind_idx2) }
# -----------------------------------------------------------------------
INDEX_TARGETS: Dict[str, Tuple[str, str]] = {
    "코스피 200": ("1", "028"),
    "코스닥 150": ("2", "203"),
    # 필요 시 추가:
    # "코스피 100": ("1", "034"),
    # "코스피 50":  ("1", "035"),
    # "KRX 300":    ("4", "106"),
}


def fetch_index_members(
    date: str, index_name: str, group_id: str, ind_idx2: str
) -> pd.DataFrame:
    """
    특정 날짜의 인덱스 구성종목 조회.
    pykrx 지수구성종목 내부 클래스 사용.
    """
    from pykrx.website.krx.market.core import 지수구성종목

    try:
        df = 지수구성종목().fetch(date, ind_idx2, group_id)
    except Exception as e:
        logger.warning("지수구성종목 오류 %s %s: %s", index_name, date, e)
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns={
        "ISU_SRT_CD": "ticker",
        "ISU_ABBRV":  "name",
        "ISU_NM":     "name",
    })

    if "ticker" not in df.columns:
        logger.warning("ticker 컬럼 없음: %s %s, cols=%s",
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
    end:   str = "20260320",
    freq:  str = "monthly",
    targets: Dict[str, Tuple[str, str]] = None,
    output_path: Path = OUTPUT_DIR / "index_members.parquet",
    resume: bool = True,
    delay: float = DEFAULT_DELAY,
) -> pd.DataFrame:
    if targets is None:
        targets = INDEX_TARGETS

    dates = trading_dates(start, end, freq)
    logger.info("대상 날짜: %d개  (%s ~ %s, freq=%s)", len(dates), dates[0], dates[-1], freq)

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
        logger.info("이어서: 완료 %d (date,index) 조합", len(done_keys))

    frames   = [existing] if not existing.empty else []
    save_every = 30
    total    = len(dates) * len(targets)
    count    = 0

    for date in dates:
        for idx_name, (group_id, ind_idx2) in targets.items():
            count += 1
            if (date, idx_name) in done_keys:
                continue

            logger.info("[%d/%d] %s %s", count, total, idx_name, date)
            df = fetch_index_members(date, idx_name, group_id, ind_idx2)

            if df.empty:
                logger.debug("  → 빈 결과 (미출시 또는 데이터 없음)")
            else:
                logger.info("  → %d 종목", len(df))
                frames.append(df)

            time.sleep(delay)

        if count % (save_every * len(targets)) < len(targets) and frames:
            pd.concat(frames, ignore_index=True).to_parquet(output_path, index=False)
            logger.info("  [체크포인트 저장]")

    if not frames:
        logger.error("수집된 데이터 없음")
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result["date"] = pd.to_datetime(result["date"].astype(str),
                                    format="%Y%m%d", errors="coerce")
    result = result.sort_values(["index","date","ticker"]).reset_index(drop=True)

    save_with_csv(result, output_path)
    logger.info("저장 완료: %s  (%d 행)", output_path, len(result))
    return result


def main():
    parser = argparse.ArgumentParser(description="KOSPI200/KOSDAQ150 구성종목 수집기")
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
