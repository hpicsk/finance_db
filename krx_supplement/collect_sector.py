"""
collect_sector.py
-----------------
전 종목 일별 업종 맵핑 수집기
================================
KRX [업종분류현황] API → 특정 날짜의 전 종목 업종 스냅샷을 날짜 범위에 걸쳐 수집.

## 필수 조건
    환경변수 KRX_ID, KRX_PW 설정 필요 (data.krx.co.kr 무료 계정)
    export KRX_ID="your_id"
    export KRX_PW="your_password"

## 제공 컬럼
    date        : 조회 기준일 (datetime)
    ticker      : 6자리 종목코드 (e.g. 005930)
    name        : 종목약칭
    market      : KOSPI / KOSDAQ
    sector_krx  : KRX 거래소 업종명

## 상장폐지 포함 방식
    날짜별 스냅샷 = 해당 날짜 상장 종목만 반환
    → 시계열로 쌓으면 폐지 전 날짜까지의 데이터가 자연스럽게 포함됨

## 사용법
    # 권장: 2005~ 영업일별 (현재 output/sector_mapping.parquet 와 동일 설정)
    python collect_sector.py --start 20050101 --freq daily

    # 기타 옵션
    python collect_sector.py                                              # 인자 기본값 (2015~, 월말 스냅샷)
    python collect_sector.py --start 20000104 --end 20260320 --freq monthly
"""

import argparse
import time
from pathlib import Path

import pandas as pd

from krx_utils import DEFAULT_DELAY, DEFAULT_END, save_with_csv, setup_logging, trading_dates

logger = setup_logging()

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

MARKET_CODES = {
    "STK": "KOSPI",
    "KSQ": "KOSDAQ",
}


def fetch_sector_snapshot(date: str) -> pd.DataFrame:
    """
    pykrx 내부 클래스를 사용해 특정 날짜의 전 종목 업종 맵핑 조회.
    KOSPI + KOSDAQ 합산.
    """
    from pykrx.website.krx.market.core import 업종분류현황

    frames = []
    for mktId, market_name in MARKET_CODES.items():
        try:
            df = 업종분류현황().fetch(date, mktId)
        except Exception as e:
            logger.warning("업종분류현황 오류 %s %s: %s", date, market_name, e)
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
    logger.info("대상 날짜: %d개  (%s ~ %s, freq=%s)", len(dates), dates[0], dates[-1], freq)

    existing = pd.DataFrame()
    if resume and output_path.exists():
        existing = pd.read_parquet(output_path)
        done = set(
            pd.to_datetime(existing["date"]).dt.strftime("%Y%m%d").unique()
        )
        dates = [d for d in dates if d not in done]
        logger.info("이어서 수집: %d개 남음 (완료 %d개)", len(dates), len(done))

    frames = [existing] if not existing.empty else []
    save_every = 20

    for i, date in enumerate(dates, 1):
        logger.info("[%d/%d] %s", i, len(dates), date)
        df = fetch_sector_snapshot(date)

        if df.empty:
            logger.warning("빈 결과: %s — 스킵", date)
            time.sleep(delay * 2)
            continue

        frames.append(df)
        logger.info("  → %d 종목", len(df))

        if i % save_every == 0:
            pd.concat(frames, ignore_index=True).to_parquet(output_path, index=False)
            logger.info("  [체크포인트 저장]")

        time.sleep(delay)

    if not frames:
        logger.error("수집된 데이터 없음")
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result["date"] = pd.to_datetime(result["date"].astype(str), format="%Y%m%d", errors="coerce")
    result = result.sort_values(["date","market","ticker"]).reset_index(drop=True)
    save_with_csv(result, output_path)
    logger.info("저장 완료: %s  (%d 행)", output_path, len(result))
    return result


def main():
    parser = argparse.ArgumentParser(description="KRX 업종 맵핑 수집기")
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
