"""DART harvest of 감사의견 (DS002/2020009) → one opinion row per (ticker, bsns_year).

Endpoint: ``opendart.fss.or.kr/api/accnutAdtorNmNdAdtOpinion.json``
(wrapped by OpenDartReader.report('accnutAdtorNmNdAdtOpinion', ...) or by
the raw `fnltt_singl_acnt` API depending on OpenDartReader version).

**bsns_year ≥ 2015 only** — pre-2015 audit opinions live inside free-text
외부감사보고서 filings; structured extraction is not currently supported.

Iterates over (corp_code, year) pairs, skipping already-cached pairs.  Raw
opinion rows are persisted to ``data/dart_audit_opinions.parquet``.

Usage:
    export OPEN_DART_API_KEY=...
    python -m kr_status.dart_audit                       # full harvest, resume from cache
    python -m kr_status.dart_audit --year-from 2015 --year-to 2024
    python -m kr_status.dart_audit --restart             # ignore cache, re-fetch all
    python -m kr_status.dart_audit --tickers 005930      # specific tickers only
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

import pandas as pd

from kr_status.corp_code_map import (
    DATA_DIR, get_corp_code, flush_cache, flush_misses, open_dart,
)
from kr_status.dart_request import dart_get

OPINIONS_PATH = DATA_DIR / "dart_audit_opinions.parquet"
_COLUMNS = ["ticker", "bsns_year", "opinion_code", "receipt_dt", "raw"]

AUDIT_REPORT_CODE = "11011"   # 사업보고서 (annual)
MIN_YEAR = 2015               # DART structured endpoint floor

_DART_AUDIT_URL = "https://opendart.fss.or.kr/api/accnutAdtorNmNdAdtOpinion.json"


def _working_universe() -> pd.DataFrame:
    from kr_status._universe import load_working_universe
    return load_working_universe(include_dates=True)


def _years_for_ticker(row: dict, year_from: int, year_to: int) -> list[int]:
    """Years where this ticker was likely active and a sa-eop filing exists."""
    yf, yt = year_from, year_to
    if pd.notna(row.get("first_date")):
        yf = max(yf, pd.Timestamp(row["first_date"]).year)
    if pd.notna(row.get("last_date")):
        yt = min(yt, pd.Timestamp(row["last_date"]).year)
    return list(range(yf, yt + 1))


def _load_cache() -> pd.DataFrame:
    if OPINIONS_PATH.exists():
        return pd.read_parquet(OPINIONS_PATH)
    return pd.DataFrame(columns=_COLUMNS)


def _save_cache(df: pd.DataFrame) -> None:
    """Write the cache with opinion_code re-derived from `raw`, so a classifier
    change reaches every row, not only the rows fetched after it."""
    OPINIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.assign(opinion_code=df["raw"].map(_classify)).to_parquet(OPINIONS_PATH, index=False)


_LABELED_OPINION_RE = re.compile(r"감사의견[:：](적정|한정|부적정|의견거절)")


def _classify(opinion_text: str) -> str:
    """Normalise free-text opinion to one of: 적정, 한정, 부적정, 의견거절.

    Matching ignores whitespace, since filers space the words ("적 정",
    "의견 거절"). Prefer the explicit ``감사의견 : <verdict>`` label (the
    annual-audit line) when present, so a qualified 반기검토의견 (semi-annual
    review) on a line above doesn't mask a clean annual opinion — e.g. 066790
    FY2018 `반기검토의견 : 범위제한한정\n감사의견 : 적정` is a clean (적정) annual
    audit. Only the explicit labeled form short-circuits; long free-text
    disclaimers (which repeat "감사의견" in prose, e.g. "감사의견의 근거를…") fall
    through to the keyword scan so genuine 의견거절 are still caught. A text with
    none of the four words but "거절" or the misspelling "겨절" is a disclaimer, and
    one stating fair presentation ("공정", "공정하게 표시하고 있음", the opinion
    paragraph itself) with no exception, negation or "공정가치" (fair value) is 적정.
    No text ("", "nan", "-") is ``unknown``; any other text is returned as its own
    label.
    """
    text = str(opinion_text or "").strip()
    s = re.sub(r"\s+", "", text)
    if s in ("", "nan", "-"):
        return "unknown"
    m = _LABELED_OPINION_RE.search(s)
    if m:
        return m.group(1)
    for k in ("의견거절", "부적정", "한정", "적정"):
        if k in s:
            return k
    if "거절" in s or "겨절" in s:       # "의결거절", "의겨거절", "의견겨절"
        return "의견거절"
    # The unqualified opinion says the statements present fairly (공정하게 표시하고
    # 있습니다); a qualified one adds "…을 제외하고는", an adverse one negates it, and
    # a review conclusion finds no misstatement "발견되지 아니함" — hence the exclusions.
    if "공정" in s and not re.search(r"제외|않|아니|공정가치", s):
        return "적정"
    return text


def _fetch_one(dart, corp_code: str, year: int) -> pd.DataFrame | None:
    """Return raw rows from accnutAdtorNmNdAdtOpinion for (corp_code, year).

    OpenDartReader does not wrap this endpoint, so we hit the raw JSON API.
    Returns None for a genuine "no data" response (status 013). Raises on every
    other non-success status — a quota stop (020/021), maintenance, a key error
    — so the harvester halts instead of reading the pair as empty.

    The response rows carry `rcept_no` (filing receipt no.) but no separate
    receipt-date field; we synthesise a `rcept_dt` column from the leading
    8 chars of `rcept_no` for downstream consumers.
    """
    api_key = os.environ.get("OPEN_DART_API_KEY")
    if not api_key:
        raise RuntimeError("OPEN_DART_API_KEY not set in env")
    r = dart_get(_DART_AUDIT_URL, {
        "crtfc_key":  api_key,
        "corp_code":  corp_code,
        "bsns_year":  str(year),
        "reprt_code": AUDIT_REPORT_CODE,
    }, timeout=15)
    payload = r.json()
    status = str(payload.get("status", ""))
    if status == "013":           # no data for this (corp, year)
        return None
    if status in ("020", "021"):  # quota / rate-limit — halt cleanly
        raise RuntimeError(
            f"DART quota/rate failure: status={status} msg={payload.get('message')}"
        )
    if status != "000":           # maintenance, a key error: not an empty year
        raise RuntimeError(
            f"DART answered status={status} msg={payload.get('message')} "
            f"for corp_code {corp_code} bsns_year {year}"
        )
    rows = payload.get("list") or []
    if not rows:
        return None
    df = pd.DataFrame(rows)
    if "rcept_no" in df.columns:
        df["rcept_dt"] = pd.to_datetime(
            df["rcept_no"].astype(str).str.slice(0, 8),
            format="%Y%m%d", errors="coerce",
        )
    return df


def harvest(api_key: str | None = None,
            year_from: int = MIN_YEAR,
            year_to: int | None = None,
            limit_tickers: int | None = None,
            tickers: list[str] | None = None,
            restart: bool = False,
            sleep_s: float = 0.05) -> pd.DataFrame:
    if year_from < MIN_YEAR:
        raise ValueError(f"DART structured audit-opinion endpoint requires year ≥ {MIN_YEAR}")
    if year_to is None:
        year_to = pd.Timestamp.today().year - 1   # most recent fully-reported year

    dart = open_dart(api_key)
    universe = _working_universe()
    if tickers:
        wanted = {str(t).zfill(6) for t in tickers}
        universe = universe[universe["ticker"].isin(wanted)]

    cache = pd.DataFrame() if restart else _load_cache()
    done_pairs: set[tuple[str, int]] = set()
    if not cache.empty:
        done_pairs = set(zip(cache["ticker"].astype(str), cache["bsns_year"].astype(int)))

    new_rows: list[dict] = []
    n_tickers = min(limit_tickers, len(universe)) if limit_tickers else len(universe)
    print(f"harvest 감사의견 {year_from}..{year_to}: {n_tickers} tickers", file=sys.stderr)

    processed = 0
    try:
        for _, row in universe.head(n_tickers).iterrows():
            ticker = row["ticker"]
            name = row["name"]
            years = _years_for_ticker(row, year_from, year_to)
            years = [y for y in years if (ticker, y) not in done_pairs]
            if not years:
                continue
            corp_code = get_corp_code(dart, ticker, name)
            if not corp_code:
                continue

            for y in years:
                df = _fetch_one(dart, corp_code, y)
                if df is None or len(df) == 0:
                    done_pairs.add((ticker, y))
                    time.sleep(sleep_s)
                    continue
                # The endpoint returns one row per (auditor, opinion); for our
                # purposes the consolidated-statement (CFS) opinion suffices.
                # Take the first row's opinion text.
                opinion_text = str(df.iloc[0].get("adt_opinion", "")
                                   or df.iloc[0].get("opinion", "")
                                   or "")
                receipt_dt = df.iloc[0].get("rcept_dt")
                if receipt_dt is None:
                    print(f"  rcept_dt missing for ticker {ticker} year {y}, skipping", file=sys.stderr)
                    continue
                new_rows.append({
                    "ticker":      ticker,
                    "bsns_year":   y,
                    "opinion_code": _classify(opinion_text),
                    "receipt_dt":  pd.to_datetime(receipt_dt) if receipt_dt else pd.NaT,
                    "raw":         opinion_text,
                })
                done_pairs.add((ticker, y))
                time.sleep(sleep_s)

            processed += 1
            if processed % 50 == 0:
                print(f"  processed {processed}/{n_tickers} tickers", file=sys.stderr)
                # Flush cache periodically so a Ctrl-C doesn't lose hours of work
                partial = pd.concat([cache, pd.DataFrame(new_rows)], ignore_index=True)
                _save_cache(partial)
                flush_cache()
    finally:            # a DART error stops the run; what it fetched is kept
        full = pd.concat([cache, pd.DataFrame(new_rows, columns=_COLUMNS)],
                         ignore_index=True).drop_duplicates(subset=["ticker", "bsns_year"])
        if new_rows:
            _save_cache(full)
        flush_cache()
        flush_misses()
    print(f"{len(full)} opinions in {OPINIONS_PATH} ({len(new_rows)} new)", file=sys.stderr)
    return full


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--api-key",   default=None)
    ap.add_argument("--year-from", type=int, default=MIN_YEAR)
    ap.add_argument("--year-to",   type=int, default=None)
    ap.add_argument("--limit",     type=int, default=None,
                    help="limit number of tickers (test runs)")
    ap.add_argument("--tickers",   default=None)
    ap.add_argument("--restart",   action="store_true")
    ap.add_argument("--relabel",   action="store_true",
                    help="re-derive opinion_code from the cached raw text (no DART)")
    args = ap.parse_args(argv)
    if args.relabel:
        cache = _load_cache()
        if cache.empty:
            raise SystemExit(f"no cached opinions at {OPINIONS_PATH} to relabel")
        _save_cache(cache)
        print(f"relabelled {len(cache)} opinions → {OPINIONS_PATH}", file=sys.stderr)
        return 0
    tickers = [t.strip() for t in args.tickers.split(",")] if args.tickers else None
    harvest(api_key=args.api_key, year_from=args.year_from, year_to=args.year_to,
            limit_tickers=args.limit, tickers=tickers, restart=args.restart)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
