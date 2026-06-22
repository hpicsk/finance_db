"""FnGuide DataGuide XLSX I/O helpers.

All FnGuide DataGuide export files share a 14-row metadata header
(symbol codes on row 9, symbol names on row 10, item codes on row 12).
Data starts at row 15. Column A is the date; columns B onward are one
per ticker.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import pandas as pd


def load_fnguide_sheet(
    filepath: str,
    sheet_name: str,
    *,
    return_names: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, dict[str, str]]:
    """Load a FnGuide DataGuide sheet as a date-indexed wide DataFrame.

    Returns a DataFrame whose index is the trading date and whose columns
    are ticker codes (e.g. ``A005930``). Values are coerced to numeric where
    possible.

    If ``return_names`` is True, also return a ``{ticker: name}`` mapping
    drawn from row 10 of the metadata header.
    """
    # engine="calamine" (python-calamine, Rust) — substantially faster than the
    # default openpyxl reader on these large DataGuide exports.
    meta = pd.read_excel(filepath, sheet_name=sheet_name, header=None, nrows=14,
                         engine="calamine")
    tickers = list(meta.iloc[8, 1:].values)

    df = pd.read_excel(filepath, sheet_name=sheet_name, header=None, skiprows=14,
                       engine="calamine")
    df.columns = ['date'] + tickers
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date').sort_index()

    if not return_names:
        return df

    names = meta.iloc[9, 1:].values
    name_map = {
        code: name
        for code, name in zip(tickers, names)
        if pd.notna(code) and pd.notna(name)
    }
    return df, name_map


def melt_fnguide_wide(df: pd.DataFrame, value_name: str) -> pd.DataFrame:
    """Convert a wide (date × ticker) FnGuide frame to long (date, ticker, value)."""
    long = df.reset_index().melt(id_vars='date', var_name='ticker', value_name=value_name)
    long = long.dropna(subset=[value_name])
    return long


def cache_path(name: str, cache_dir) -> str:
    """Resolve a cache filename under *cache_dir*, creating the dir if needed."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return str(cache_dir / name)


def cache_is_fresh(cache: str, sources: Iterable[str | os.PathLike]) -> bool:
    """Return True iff *cache* exists and is newer than every source file.

    If any source is missing, treat the cache as stale (the caller will then
    read the source directly and fail loud with a clear error).
    """
    if not os.path.exists(cache):
        return False
    cache_mtime = os.path.getmtime(cache)
    for s in sources:
        s = str(s)
        if not os.path.exists(s):
            return False
        if os.path.getmtime(s) > cache_mtime:
            return False
    return True
