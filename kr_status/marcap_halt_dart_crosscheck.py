"""Sample-based DART cross-check for marcap-inferred halt events.

Reads ``kr_status/data/marcap_halt_events.parquet`` (output of
``marcap_halt_infer.py``), takes a stratified random sample of halt events
in the 2020–2024 window, and queries DART OpenAPI's ``list.json`` endpoint
for each sampled ticker over the halt window (± 14 days). A halt is
"DART-confirmed" if at least one filing's ``report_nm`` matches one of
the halt-related Korean keywords.

Output: a short report printed to stdout summarising the confirmation
rate, broken down by halt duration bucket. This is **not** a replacement
for a full DART harvest — it's a calibration tool to decide whether the
marcap inference is good enough as the canonical halt source (it almost
certainly is not, but it tells us where the gaps are).

Requires the ``OPEN_DART_API_KEY`` environment variable. Uses raw HTTP via
``requests`` so no OpenDartReader dependency is needed.

Usage::

    export OPEN_DART_API_KEY=...
    python -m kr_status.marcap_halt_dart_crosscheck            # default sample=30
    python -m kr_status.marcap_halt_dart_crosscheck --sample 60
    python -m kr_status.marcap_halt_dart_crosscheck --seed 42
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import time
from pathlib import Path

import pandas as pd
import requests

from kr_status.schema import events_path

logger = logging.getLogger(__name__)

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
CORP_CACHE_PATH = Path(__file__).resolve().parent / "data" / "corp_code_cache.parquet"

HALT_KEYWORDS = re.compile(
    # Direct halt mentions
    r"(매매\s*거래\s*정지|거래\s*정지|정리매매|상장폐지|관리종목"
    # Common halt CAUSES (the literal "거래정지" is filed by KRX into KIND, not DART;
    # DART carries the underlying triggering events). Match these to count a halt
    # as "DART-substantiated" — i.e. there's an event in the window that plausibly
    # caused the halt, even if no filing literally says 거래정지.
    r"|조회공시요구|불성실공시|풍문\s*또는\s*보도|회생절차|감자\s*결정"
    r"|단기\s*과열|투자\s*주의\s*환기|주식\s*분할|주식\s*병합|영업정지"
    r"|상장적격성|횡령|배임|감사의견|최대주주\s*변경)"
)
DEFAULT_SAMPLE = 30
WINDOW_DAYS = 14  # ± window around halt event to search DART


def _load_corp_codes() -> dict[str, str]:
    if not CORP_CACHE_PATH.exists():
        raise RuntimeError(f"corp_code cache missing at {CORP_CACHE_PATH}")
    cc = pd.read_parquet(CORP_CACHE_PATH)
    cc = cc.dropna(subset=["corp_code"])
    return dict(zip(cc["ticker"].astype(str), cc["corp_code"].astype(str)))


def _sample_halts(seed: int, n: int) -> pd.DataFrame:
    ev = pd.read_parquet(events_path("marcap_halt"))
    halts = ev[ev.status == "halt"].copy()
    halts["n_days"] = (halts["end_date"] - halts["start_date"]).dt.days + 1
    # Restrict to plausible-duration halts (1–60 bdays) in 2020–2024
    window = halts[
        (halts.start_date >= "2020-01-01")
        & (halts.start_date <= "2024-12-31")
        & (halts.n_days.between(1, 60))
    ]
    logger.info("eligible halts in sample frame: %d", len(window))
    return window.sample(n=min(n, len(window)), random_state=seed).sort_values("start_date")


def _query_dart(api_key: str, corp_code: str, bgn: str, end: str) -> list[dict]:
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bgn_de": bgn,
        "end_de": end,
        "page_count": 100,
    }
    r = requests.get(DART_LIST_URL, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    status = data.get("status")
    if status == "013":  # no data
        return []
    if status != "000":
        logger.warning("DART status=%s msg=%s corp=%s", status, data.get("message"), corp_code)
        return []
    return data.get("list", []) or []


def crosscheck(api_key: str, sample_n: int, seed: int, sleep_s: float = 0.4) -> pd.DataFrame:
    corp_map = _load_corp_codes()
    sample = _sample_halts(seed=seed, n=sample_n)

    rows: list[dict] = []
    n_no_corp = 0
    for i, row in enumerate(sample.itertuples(index=False), 1):
        ticker = str(row.ticker).zfill(6)
        corp_code = corp_map.get(ticker)
        if not corp_code:
            n_no_corp += 1
            rows.append({
                "ticker": ticker,
                "start_date": row.start_date,
                "end_date": row.end_date,
                "n_days": row.n_days,
                "detail": row.detail,
                "confirmed": False,
                "n_filings_in_window": 0,
                "first_match_report": "",
                "note": "no corp_code in cache",
            })
            continue

        bgn = (row.start_date - pd.Timedelta(days=WINDOW_DAYS)).strftime("%Y%m%d")
        end = (row.end_date + pd.Timedelta(days=WINDOW_DAYS)).strftime("%Y%m%d")
        try:
            filings = _query_dart(api_key, corp_code, bgn, end)
        except Exception as e:
            logger.warning("[%s] DART query failed: %s", ticker, e)
            filings = []

        matches = [f for f in filings if HALT_KEYWORDS.search(f.get("report_nm", ""))]
        rows.append({
            "ticker": ticker,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "n_days": row.n_days,
            "detail": row.detail,
            "confirmed": len(matches) > 0,
            "n_filings_in_window": len(filings),
            "first_match_report": matches[0]["report_nm"] if matches else "",
            "note": "",
        })
        time.sleep(sleep_s)

        if i % 5 == 0 or i == len(sample):
            n_conf = sum(1 for r in rows if r["confirmed"])
            logger.info("  [%d/%d] confirmed=%d", i, len(sample), n_conf)

    out = pd.DataFrame(rows)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE)
    parser.add_argument("--seed", type=int, default=20260522)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "data" / "marcap_halt_dart_crosscheck.parquet",
    )
    parser.add_argument("--api-key", default=os.environ.get("OPEN_DART_API_KEY"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")

    if not args.api_key:
        raise SystemExit("OPEN_DART_API_KEY not set (export it or pass --api-key)")

    df = crosscheck(api_key=args.api_key, sample_n=args.sample, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.output, index=False)

    n = len(df)
    # Exclude no-corp-code rows from the rate denominator — we never queried DART for them
    queryable = df[df.note == ""]
    n_q = len(queryable)
    n_q_conf = queryable.confirmed.sum()
    print(f"\n=== marcap halt → DART cross-check ({n} samples, seed={args.seed}) ===")
    print(f"queryable (corp_code in cache):  {n_q} / {n}")
    if n_q > 0:
        print(f"DART-substantiated (cause filings in ±14d window):  {n_q_conf} / {n_q}  ({n_q_conf/n_q:.1%})")
    else:
        print("DART-substantiated (cause filings in ±14d window):  0 / 0  (N/A)")
    print()
    print("By halt duration bucket (queryable only):")
    queryable = queryable.copy()
    queryable["bucket"] = pd.cut(queryable.n_days, bins=[0, 3, 10, 30, 60], labels=["1-3d", "4-10d", "11-30d", "31-60d"])
    bucket_stats = queryable.groupby("bucket", observed=True).agg(
        n=("confirmed", "size"),
        confirmed=("confirmed", "sum"),
    )
    bucket_stats["rate"] = (bucket_stats["confirmed"] / bucket_stats["n"]).map("{:.1%}".format)
    print(bucket_stats.to_string())
    print()
    print("Unconfirmed sample (first 10):")
    print(df[~df.confirmed].head(10)[["ticker", "start_date", "end_date", "n_days", "n_filings_in_window", "detail", "note"]].to_string(index=False))
    print(f"\nfull report written to: {args.output}")


if __name__ == "__main__":
    main()
