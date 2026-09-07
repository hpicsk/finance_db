"""DART harvest of 감사의견 (DS002/2020009) → audit_qualified event panel.

Endpoint: ``opendart.fss.or.kr/api/accnutAdtorNmNdAdtOpinion.json``
(wrapped by OpenDartReader.report('accnutAdtorNmNdAdtOpinion', ...) or by
the raw `fnltt_singl_acnt` API depending on OpenDartReader version).

**bsns_year ≥ 2015 only** — pre-2015 audit opinions live inside free-text
외부감사보고서 filings; structured extraction is not currently supported.

Iterates over (corp_code, year) pairs, skipping already-cached pairs.  Raw
opinion rows are persisted to ``data/dart_audit_opinions.parquet``; non-적정
opinions are projected to event rows in ``data/dart_audit_events.parquet``
with ``start_date = receipt_dt`` and ``end_date = next year's receipt_dt``
(or NaT for the most recent opinion).

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
import requests

from kr_status.schema import STATUS_COLUMNS, events_path
from kr_status.corp_code_map import (
    DATA_DIR, get_corp_code, flush_cache, flush_misses, open_dart,
)

OPINIONS_PATH = DATA_DIR / "dart_audit_opinions.parquet"
EVENTS_PATH   = events_path("dart_audit")

AUDIT_REPORT_CODE = "11011"   # 사업보고서 (annual)
MIN_YEAR = 2015               # DART structured endpoint floor

# An annual audit opinion is valid for one fiscal year.  When a qualified
# opinion has no subsequent filing in the cache (the most recent one), bound
# its window to one annual cycle instead of leaving end_date NaT — a NaT end
# is read as "+∞" by the query layer and would exclude the ticker on every
# future date forever.
AUDIT_OPINION_VALIDITY = pd.DateOffset(years=1)
_DART_AUDIT_URL = "https://opendart.fss.or.kr/api/accnutAdtorNmNdAdtOpinion.json"

# Non-적정 opinion labels DART returns.  Anything not in 적정 family is treated
# as `audit_qualified` for the tradable_universe filter.
QUALIFIED_OPINIONS = {"한정", "부적정", "의견거절"}


def _working_universe() -> pd.DataFrame:
    from _universe import load_working_universe
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
    return pd.DataFrame(columns=["ticker", "bsns_year", "opinion_code", "receipt_dt", "raw"])


def _save_cache(df: pd.DataFrame) -> None:
    OPINIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OPINIONS_PATH, index=False)


_LABELED_OPINION_RE = re.compile(r"감사의견\s*[:：]\s*(적정|한정|부적정|의견거절)")


def _classify(opinion_text: str) -> str:
    """Normalise free-text opinion to one of: 적정, 한정, 부적정, 의견거절.

    Prefer the explicit ``감사의견 : <verdict>`` label (the annual-audit line)
    when present, so a qualified 반기검토의견 (semi-annual review) on a line
    above doesn't mask a clean annual opinion — e.g. 066790 FY2018
    `반기검토의견 : 범위제한한정\n감사의견 : 적정` is a clean (적정) annual audit.
    Only the explicit labeled form short-circuits; long free-text disclaimers
    (which repeat "감사의견" in prose, e.g. "감사의견의 근거를…") fall through to
    the keyword scan so genuine 의견거절 are still caught.
    """
    s = str(opinion_text or "").strip()
    m = _LABELED_OPINION_RE.search(s)
    if m:
        return m.group(1)
    for k in ("의견거절", "부적정", "한정", "적정"):
        if k in s:
            return k
    return s or "unknown"


def _fetch_one(dart, corp_code: str, year: int) -> pd.DataFrame | None:
    """Return raw rows from accnutAdtorNmNdAdtOpinion for (corp_code, year).

    OpenDartReader does not wrap this endpoint, so we hit the raw JSON API.
    Returns None for genuine "no data" responses (status 013) and other
    non-success codes the caller can treat as terminal. Raises on quota/rate
    failures (020/021) so the harvester halts cleanly instead of marking
    every remaining pair as done.

    The response rows carry `rcept_no` (filing receipt no.) but no separate
    receipt-date field; we synthesise a `rcept_dt` column from the leading
    8 chars of `rcept_no` for downstream consumers.
    """
    api_key = os.environ.get("OPEN_DART_API_KEY")
    if not api_key:
        raise RuntimeError("OPEN_DART_API_KEY not set in env")
    r = requests.get(_DART_AUDIT_URL, params={
        "crtfc_key":  api_key,
        "corp_code":  corp_code,
        "bsns_year":  str(year),
        "reprt_code": AUDIT_REPORT_CODE,
    }, timeout=15)
    r.raise_for_status()
    payload = r.json()
    status = str(payload.get("status", ""))
    if status == "013":           # no data for this (corp, year)
        return None
    if status in ("020", "021"):  # quota / rate-limit — halt cleanly
        raise RuntimeError(
            f"DART quota/rate failure: status={status} msg={payload.get('message')}"
        )
    if status != "000":
        return None
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

    full = pd.concat([cache, pd.DataFrame(new_rows)], ignore_index=True).drop_duplicates(
        subset=["ticker", "bsns_year"]
    )
    _save_cache(full)
    flush_cache()
    flush_misses()

    events = build_events(full)
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    events.to_parquet(EVENTS_PATH, index=False)
    print(f"wrote {len(full)} opinions → {OPINIONS_PATH}", file=sys.stderr)
    print(f"wrote {len(events)} audit_qualified events → {EVENTS_PATH}", file=sys.stderr)
    return events


def build_events(opinions: pd.DataFrame) -> pd.DataFrame:
    """Project the opinions cache to an ``audit_qualified`` event panel.

    Reclassifies opinion_code from the cached raw text (so classifier fixes
    apply without re-harvesting DART) and orders each ticker's filings by
    ``receipt_dt`` — not ``bsns_year`` — so each qualified opinion's window is
    ``[receipt_dt, next filing's receipt_dt)``.  Sorting on bsns_year produced
    garbage windows when filings arrived out of chronological order (late /
    bulk re-filings): negative spans and multi-year stale flags.
    """
    full = opinions.copy()
    full["opinion_code"] = full["raw"].map(_classify)
    full["receipt_dt"] = pd.to_datetime(full["receipt_dt"])
    full = full.sort_values(["ticker", "receipt_dt", "bsns_year"])
    quals = full[full["opinion_code"].isin(QUALIFIED_OPINIONS)].copy()
    # Compute next_receipt on qualified-only rows so each qualified opinion's window
    # ends at the next qualified opinion (not any intervening non-qualified filing).
    quals["next_receipt"] = quals.groupby("ticker")["receipt_dt"].shift(-1)
    # Bound the open (most-recent) qualified opinion to one annual cycle so it
    # doesn't read as an indefinite exclusion (NaT → +∞) downstream.
    quals["end_date"] = quals["next_receipt"].fillna(
        quals["receipt_dt"] + AUDIT_OPINION_VALIDITY)
    fetched = pd.Timestamp.now()
    events = pd.DataFrame({
        "ticker":     quals["ticker"].values,
        "status":     "audit_qualified",
        "start_date": quals["receipt_dt"].values,
        "end_date":   quals["end_date"].values,
        "source":     [f"dart_audit:{y}" for y in quals["bsns_year"].values],
        "fetched_at": fetched,
        "detail":     [f"{c} ({r})" for c, r in zip(quals["opinion_code"], quals["raw"])],
    }, columns=STATUS_COLUMNS)
    return events.sort_values(["start_date", "ticker"]).reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--api-key",   default=None)
    ap.add_argument("--year-from", type=int, default=MIN_YEAR)
    ap.add_argument("--year-to",   type=int, default=None)
    ap.add_argument("--limit",     type=int, default=None,
                    help="limit number of tickers (test runs)")
    ap.add_argument("--tickers",   default=None)
    ap.add_argument("--restart",   action="store_true")
    ap.add_argument("--rebuild-events", action="store_true",
                    help="re-project events from the cached opinions parquet (no DART)")
    args = ap.parse_args(argv)
    if args.rebuild_events:
        cache = _load_cache()
        if cache.empty:
            raise SystemExit(f"no cached opinions at {OPINIONS_PATH} to rebuild from")
        events = build_events(cache)
        EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        events.to_parquet(EVENTS_PATH, index=False)
        print(f"rebuilt {len(events)} audit_qualified events → {EVENTS_PATH}", file=sys.stderr)
        return 0
    tickers = [t.strip() for t in args.tickers.split(",")] if args.tickers else None
    harvest(api_key=args.api_key, year_from=args.year_from, year_to=args.year_to,
            limit_tickers=args.limit, tickers=tickers, restart=args.restart)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
