"""Resolve KRX 6-digit tickers to DART corp_codes — incl. delisted firms.

OpenDartReader's `find_corp_code(ticker)` returns None for many delisted
tickers (the DART corp-code directory drops some retired registrations).
This module layers a fallback:

  1. Try OpenDartReader.find_corp_code(ticker)
  2. If that fails, look up the ticker's name in
     ../kr_delisted/delisting_calendar.csv and fuzzy-match via DART's
     name-based corp directory.
  3. Cache misses to data/corp_code_misses.csv for manual triage.

Hits are memoised in data/corp_code_cache.parquet so re-runs of Phase B
collectors are cheap.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from kr_delisted.delisted_loader import CALENDAR

DATA_DIR = Path(__file__).resolve().parent / "data"
CACHE_PATH  = DATA_DIR / "corp_code_cache.parquet"
MISSES_PATH = DATA_DIR / "corp_code_misses.csv"
DELISTING_CSV = Path(CALENDAR)

_cache: dict[str, str | None] | None = None
_misses: set[tuple[str, str]] = set()


def _load_cache() -> dict[str, str | None]:
    global _cache
    if _cache is not None:
        return _cache
    if CACHE_PATH.exists():
        df = pd.read_parquet(CACHE_PATH)
        _cache = dict(zip(df["ticker"].astype(str), df["corp_code"].astype(object)))
    else:
        _cache = {}
    return _cache


def _save_cache() -> None:
    if _cache is None:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [{"ticker": t, "corp_code": c} for t, c in sorted(_cache.items())]
    )
    df.to_parquet(CACHE_PATH, index=False)


def _load_delisted_names() -> dict[str, str]:
    if not DELISTING_CSV.exists():
        return {}
    df = pd.read_csv(DELISTING_CSV, dtype={"ticker": str})
    df["ticker"] = df["ticker"].str.zfill(6)
    # if a ticker appears multiple times (rare; reuse), take the latest name
    return dict(df.drop_duplicates("ticker", keep="last")[["ticker", "name"]].values)


def get_corp_code(dart, ticker: str, name: str | None = None) -> str | None:
    """Return DART corp_code for `ticker`, or None if unresolvable.

    `dart` is an OpenDartReader instance.  `name` (optional) is used for the
    fuzzy fallback for delisted tickers.
    """
    ticker = str(ticker).zfill(6)
    cache = _load_cache()
    if ticker in cache:
        return cache[ticker]

    code: str | None = None
    try:
        code = dart.find_corp_code(ticker)
    except Exception:
        code = None

    if not code:
        # Delisted fallback: look up name from delisting calendar
        if name is None:
            name = _load_delisted_names().get(ticker)
        if name:
            try:
                hits = dart.company_by_name(name)
                if hits is not None and len(hits) > 0:
                    # Prefer exact-name match; otherwise take first.
                    exact = hits[hits["corp_name"] == name]
                    pick = exact.iloc[0] if len(exact) > 0 else hits.iloc[0]
                    code = str(pick["corp_code"])
            except Exception:
                pass

    cache[ticker] = code or None
    if not code:
        _misses.add((ticker, name or ""))
    return code or None


def flush_misses() -> Path | None:
    """Append accumulated misses to MISSES_PATH and clear the in-memory set."""
    if not _misses:
        return None
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    new_rows = pd.DataFrame(sorted(_misses), columns=["ticker", "name"])
    if MISSES_PATH.exists():
        existing = pd.read_csv(MISSES_PATH, dtype={"ticker": str})
        out = pd.concat([existing, new_rows], ignore_index=True).drop_duplicates()
    else:
        out = new_rows
    out.to_csv(MISSES_PATH, index=False)
    _misses.clear()
    return MISSES_PATH


def flush_cache() -> Path:
    """Persist the in-memory cache to disk."""
    _save_cache()
    return CACHE_PATH


def open_dart(api_key: str | None = None):
    """Convenience constructor; pulls key from env if not provided."""
    import OpenDartReader
    key = api_key or os.environ.get("OPEN_DART_API_KEY")
    if not key:
        raise RuntimeError("OPEN_DART_API_KEY not set (pass api_key= or export it)")
    return OpenDartReader(key)
