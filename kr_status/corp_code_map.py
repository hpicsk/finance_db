"""Resolve KRX 6-digit tickers to DART corp_codes.

`get_corp_code` looks a ticker up in DART's corp-code directory
(OpenDartReader's `find_corp_code`, a table OpenDartReader downloads when it
starts). The directory drops some retired registrations, so a ticker it has no
stock code for is a miss: cached as None and logged to data/corp_code_misses.csv
for triage. Hits and misses are memoised in data/corp_code_cache.parquet so
re-runs of the DART collectors are cheap.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
CACHE_PATH  = DATA_DIR / "corp_code_cache.parquet"
MISSES_PATH = DATA_DIR / "corp_code_misses.csv"

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


def get_corp_code(dart, ticker: str, name: str | None = None) -> str | None:
    """Return DART corp_code for `ticker`, or None if the directory has none.

    `dart` is an OpenDartReader instance; `name` (optional) is recorded beside a
    miss, for triage. The lookup reads OpenDartReader's local directory table,
    so an error in it is a real error and is raised, not read as a miss.
    """
    ticker = str(ticker).zfill(6)
    cache = _load_cache()
    if ticker in cache:
        return cache[ticker]
    code = dart.find_corp_code(ticker) or None
    cache[ticker] = code
    if not code:
        _misses.add((ticker, name or ""))
    return code


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
