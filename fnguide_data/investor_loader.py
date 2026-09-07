"""Unified investor flow loader for FnGuide DataGuide xlsx exports.

Reads buy/sell amounts directly from the ``raw/fnguide_investor_*`` exports
carrying 기관 / 개인 / 외국인 and returns a long
``(date, ticker, investor_type, buy/sell/net)`` panel for any date range.
All values are KRW (원).

Foreign definition
------------------
- ``'등록외국인'`` (default, Smart Money): 외국인 = 등록외국인 only.
- ``'외국인계'`` (Total): 외국인 = 등록외국인 + 기타외국인.

Pre-2003-12-01: 기타외국인 is NULL before this date. With
``foreign_definition='외국인계'`` the missing 기타외국인 contributes 0,
so 외국인계 = 등록외국인 for early dates (matches the KRX historical
single-classification regime — see parent README "Investor Type
Introduction Dates").
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd

from fnguide_io import (
    cache_is_fresh,
    cache_path,
    load_fnguide_sheet,
    melt_fnguide_wide,
)


# The trailing date on each export is the pull it came from — the exports are
# not one snapshot, and vintages.csv is where the dates are read from. A re-pull
# arrives under its own date and these constants move to it.
_INST_BUY_FILE  = 'fnguide_investor_inst-buy_20260214.xlsx'
_INST_SELL_FILE = 'fnguide_investor_inst-sell-fin-ins-trust_20260214.xlsx'
_RETAIL_FILE    = 'fnguide_investor_pension-corp-retail_20260219.xlsx'
_FOREIGN_FILE   = 'fnguide_investor_foreign-pe_20260219.xlsx'

# (file, sheet) sources per investor type and side. Multiple sources are summed.
_BASE_SOURCES: dict[str, dict[str, list[tuple[str, str]]]] = {
    '기관': {
        'buy':  [(_INST_BUY_FILE,  '매수대금(기관)')],
        'sell': [(_INST_SELL_FILE, '매도대금(기관계)')],
    },
    '개인': {
        'buy':  [(_RETAIL_FILE, '매수대금(개인)')],
        'sell': [(_RETAIL_FILE, '매도대금(개인)')],
    },
}

_FOREIGN_SOURCES: dict[str, dict[str, list[tuple[str, str]]]] = {
    '등록외국인': {
        'buy':  [(_FOREIGN_FILE, '매수대금(등록외국인)')],
        'sell': [(_FOREIGN_FILE, '매도대금(등록외국인)')],
    },
    '외국인계': {
        'buy':  [(_FOREIGN_FILE, '매수대금(등록외국인)'),
                 (_FOREIGN_FILE, '매수대금(기타외국인)')],
        'sell': [(_FOREIGN_FILE, '매도대금(등록외국인)'),
                 (_FOREIGN_FILE, '매도대금(기타외국인)')],
    },
}

_KR_TO_EN = {'기관': 'institutional', '개인': 'individual', '외국인': 'foreign'}


def _load_sum_long(raw_dir: Path,
                   sources: list[tuple[str, str]],
                   start: pd.Timestamp,
                   end: pd.Timestamp,
                   value_name: str) -> pd.DataFrame:
    """Load one or more sheets, filter to [start, end], and sum across sheets."""
    parts = []
    for fname, sheet in sources:
        print(f"  loading {fname} :: {sheet}", flush=True)
        wide = load_fnguide_sheet(str(raw_dir / fname), sheet)
        wide = wide.loc[(wide.index >= start) & (wide.index <= end)]
        long = melt_fnguide_wide(wide, value_name)
        long = long[long[value_name] != 0]  # drop zero-trade rows
        parts.append(long)
    if len(parts) == 1:
        return parts[0]
    return (pd.concat(parts, ignore_index=True)
              .groupby(['date', 'ticker'], as_index=False)[value_name].sum())


def load_investor_flow(
    start_date: str,
    end_date: str,
    *,
    raw_dir: str | Path,
    investor_types: tuple[str, ...] = ('기관', '개인', '외국인'),
    foreign_definition: Literal['등록외국인', '외국인계'] = '등록외국인',
    cache_dir: str | Path | None = None,
    cache_filename: str | None = None,
) -> pd.DataFrame:
    """Return a long ``(date, ticker, investor_type, buy/sell/net)`` panel.

    Parameters
    ----------
    start_date, end_date : str
        Inclusive ``YYYY-MM-DD`` window bounds.
    raw_dir : path-like
        Path to ``~/research/finance_db/fnguide_data/raw/``.
    investor_types : tuple
        Subset of ``('기관', '개인', '외국인')``.
    foreign_definition : ``'등록외국인'`` or ``'외국인계'``
        See module docstring.
    cache_dir, cache_filename : path-like, optional
        Enable parquet caching. ``cache_filename`` defaults to a name derived
        from the query parameters.

    Returns
    -------
    DataFrame
        Columns: ``date`` (datetime64), ``ticker`` (str),
        ``investor_type`` (str, Korean: ``기관``/``개인``/``외국인``),
        ``buy_value``, ``sell_value``, ``net_buy_value`` (all KRW, float).
        Sorted by ``(date, ticker, investor_type)``.
    """
    raw_dir = Path(raw_dir).expanduser()

    valid_types = ('기관', '개인', '외국인')
    bad = [t for t in investor_types if t not in valid_types]
    if bad:
        raise ValueError(f"Unknown investor_types {bad!r}; valid: {valid_types}")

    if foreign_definition not in _FOREIGN_SOURCES:
        raise ValueError(
            f"foreign_definition must be one of {list(_FOREIGN_SOURCES)}; "
            f"got {foreign_definition!r}.")

    sources_by_type: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for t in investor_types:
        sources_by_type[t] = (_FOREIGN_SOURCES[foreign_definition]
                              if t == '외국인' else _BASE_SOURCES[t])

    all_files = sorted({
        str(raw_dir / fname)
        for sources in sources_by_type.values()
        for side in sources.values()
        for fname, _ in side
    })

    cache = None
    if cache_dir is not None:
        if cache_filename is None:
            tag = '_'.join(sorted(investor_types))
            cache_filename = (
                f"investor_flow_{start_date}_{end_date}_"
                f"{foreign_definition}_{tag}.parquet"
            )
        cache = cache_path(cache_filename, cache_dir)
        if cache_is_fresh(cache, all_files):
            print(f"  [cache] loading investor flow from {cache}", flush=True)
            return pd.read_parquet(cache)

    start, end = pd.Timestamp(start_date), pd.Timestamp(end_date)

    print(f"\n{'='*70}\n"
          f"LOADING INVESTOR FLOW ({start_date}..{end_date}, "
          f"foreign={foreign_definition})\n{'='*70}", flush=True)

    pieces: list[pd.DataFrame] = []
    for t, sides in sources_by_type.items():
        buy  = _load_sum_long(raw_dir, sides['buy'],  start, end, 'buy_value')
        sell = _load_sum_long(raw_dir, sides['sell'], start, end, 'sell_value')
        merged = buy.merge(sell, on=['date', 'ticker'], how='outer').fillna(0)
        merged['net_buy_value'] = merged['buy_value'] - merged['sell_value']
        merged['investor_type'] = t
        pieces.append(merged[['date', 'ticker', 'investor_type',
                              'buy_value', 'sell_value', 'net_buy_value']])

    flow = pd.concat(pieces, ignore_index=True)
    flow = (flow.sort_values(['date', 'ticker', 'investor_type'])
                .reset_index(drop=True))

    if cache:
        flow.to_parquet(cache, index=False)
        print(f"  [cache] wrote {cache}  ({len(flow):,} rows)", flush=True)

    return flow


def to_wide_net(flow: pd.DataFrame) -> pd.DataFrame:
    """Pivot long flow to wide net-buy (one column per investor type, English).

    Returns columns ``date, ticker, institutional, individual, foreign``;
    missing combinations are filled with 0. Convenience wrapper for callers
    that want the ``build_pre2020_flow`` shape.
    """
    wide = flow.pivot_table(
        index=['date', 'ticker'],
        columns='investor_type',
        values='net_buy_value',
        fill_value=0,
    ).reset_index()
    wide.columns.name = None
    return wide.rename(columns=_KR_TO_EN)
