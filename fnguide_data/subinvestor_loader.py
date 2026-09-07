"""Sub-investor flow loader for KRX 기관계 decomposition.

The KRX discloses daily trading by 8 sub-types under the 기관계 aggregate:
연기금등 (pension), 보험 (insurance), 투신 (investment trust),
사모펀드 (PE funds), 금융투자 (proprietary), 기타금융 (other financial),
은행 (banks), 국가 (government). The standard ``investor_loader.load_investor_flow``
only exposes the aggregate. This module loads each sub-type as a separately-
identifiable series. It is the canonical home of the 8-type → (file, sheet)
mapping (companion to ``investor_loader``); downstream consumers should import
it from here rather than re-deriving the sheet map.

Source files (verified by openpyxl scan, FnGuide raw_dir):

  fnguide_investor_inst-sell-fin-ins-trust_20260214.xlsx :: 보험, 투신, 금융투자
  fnguide_investor_bank-otherfin_20260219.xlsx           :: 은행, 기타금융
  fnguide_investor_pension-corp-retail_20260219.xlsx     :: 연기금등
  fnguide_investor_foreign-pe_20260219.xlsx              :: 사모펀드
  fnguide_investor_govt-total_20260219.xlsx              :: 국가

A renamed or missing sheet raises inside ``load_fnguide_sheet`` (fail loud);
a sub-type that loads but has no nonzero flows in the window is simply absent
from the returned panel — consumers that require all 8 should check for missing
types and error rather than zero-fill.

All values are KRW (원). Returned ``net_buy_value = buy_value - sell_value``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fnguide_io import (
    cache_is_fresh,
    cache_path,
    load_fnguide_sheet,
    melt_fnguide_wide,
)


_INST_FILE    = 'fnguide_investor_inst-sell-fin-ins-trust_20260214.xlsx'
_BANK_FILE    = 'fnguide_investor_bank-otherfin_20260219.xlsx'
_PENSION_FILE = 'fnguide_investor_pension-corp-retail_20260219.xlsx'
_FOREIGN_FILE = 'fnguide_investor_foreign-pe_20260219.xlsx'
_GOVT_FILE    = 'fnguide_investor_govt-total_20260219.xlsx'

SUBINVESTOR_SOURCES: dict[str, tuple[str, str, str]] = {
    'pension':         (_PENSION_FILE, '매수대금(연기금등)', '매도대금(연기금등)'),
    'insurance':       (_INST_FILE,    '매수대금(보험)',     '매도대금(보험)'),
    'investment_trust':(_INST_FILE,    '매수대금(투신)',     '매도대금(투신)'),
    'pe_funds':        (_FOREIGN_FILE, '매수대금(사모펀드)', '매도대금(사모펀드)'),
    'financial_inv':   (_INST_FILE,    '매수대금(금융투자)', '매도대금(금융투자)'),
    'other_financial': (_BANK_FILE,    '매수대금(기타금융)', '매도대금(기타금융)'),
    'bank':            (_BANK_FILE,    '매수대금(은행)',     '매도대금(은행)'),
    'government':      (_GOVT_FILE,    '매수대금(국가)',     '매도대금(국가)'),
}


def _load_one_sub(raw_dir: Path,
                  fname: str,
                  sheet: str,
                  start: pd.Timestamp,
                  end: pd.Timestamp,
                  value_name: str) -> pd.DataFrame:
    print(f"  loading {fname} :: {sheet}", flush=True)
    wide = load_fnguide_sheet(str(raw_dir / fname), sheet)
    wide = wide.loc[(wide.index >= start) & (wide.index <= end)]
    long = melt_fnguide_wide(wide, value_name)
    return long[long[value_name] != 0]


def load_subinvestor_flow(
    start_date: str,
    end_date: str,
    *,
    raw_dir: str | Path,
    subinvestor_types: tuple[str, ...] = tuple(SUBINVESTOR_SOURCES),
    cache_dir: str | Path | None = None,
    cache_filename: str | None = None,
) -> pd.DataFrame:
    """Return a long ``(date, ticker, subinvestor_type, buy/sell/net)`` panel.

    Parameters
    ----------
    start_date, end_date : str
        Inclusive ``YYYY-MM-DD`` bounds.
    raw_dir : path-like
        Path to ``~/research/finance_db/fnguide_data/raw/``.
    subinvestor_types : tuple of str
        Subset of :data:`SUBINVESTOR_SOURCES` keys. Default: all 8.
    cache_dir, cache_filename : path-like, optional
        Parquet cache.

    Returns
    -------
    DataFrame with columns ``date`` (datetime64), ``ticker`` (str, A-prefixed),
    ``subinvestor_type`` (str, English key from ``SUBINVESTOR_SOURCES``),
    ``buy_value, sell_value, net_buy_value`` (KRW, float).
    """
    raw_dir = Path(raw_dir).expanduser()

    unknown = [t for t in subinvestor_types if t not in SUBINVESTOR_SOURCES]
    if unknown:
        raise ValueError(
            f"Unknown subinvestor_types {unknown!r}; valid: "
            f"{list(SUBINVESTOR_SOURCES)}")

    all_files = sorted({
        str(raw_dir / SUBINVESTOR_SOURCES[t][0])
        for t in subinvestor_types
    })

    cache = None
    if cache_dir is not None:
        if cache_filename is None:
            tag = '_'.join(sorted(subinvestor_types))
            cache_filename = f"subinvestor_flow_{start_date}_{end_date}_{tag}.parquet"
        cache = cache_path(cache_filename, cache_dir)
        if cache_is_fresh(cache, all_files):
            print(f"  [cache] loading sub-investor flow from {cache}", flush=True)
            return pd.read_parquet(cache)

    start, end = pd.Timestamp(start_date), pd.Timestamp(end_date)

    print(f"\n{'='*70}\n"
          f"LOADING SUB-INVESTOR FLOW ({start_date}..{end_date}, "
          f"{len(subinvestor_types)} types)\n{'='*70}", flush=True)

    pieces: list[pd.DataFrame] = []
    for t in subinvestor_types:
        fname, buy_sheet, sell_sheet = SUBINVESTOR_SOURCES[t]
        buy  = _load_one_sub(raw_dir, fname, buy_sheet,  start, end, 'buy_value')
        sell = _load_one_sub(raw_dir, fname, sell_sheet, start, end, 'sell_value')
        if buy.empty and sell.empty:
            print(f"  [{t}] no nonzero flows in window; skipping", flush=True)
            continue
        merged = buy.merge(sell, on=['date', 'ticker'], how='outer').fillna(0)
        merged['net_buy_value'] = merged['buy_value'] - merged['sell_value']
        merged['subinvestor_type'] = t
        pieces.append(merged[['date', 'ticker', 'subinvestor_type',
                              'buy_value', 'sell_value', 'net_buy_value']])

    if not pieces:
        return pd.DataFrame(columns=['date', 'ticker', 'subinvestor_type',
                                     'buy_value', 'sell_value', 'net_buy_value'])

    flow = pd.concat(pieces, ignore_index=True)
    flow = (flow.sort_values(['date', 'ticker', 'subinvestor_type'])
                .reset_index(drop=True))

    if cache:
        flow.to_parquet(cache, index=False)
        print(f"  [cache] wrote {cache}  ({len(flow):,} rows)", flush=True)

    return flow


def to_wide_net_sub(flow: pd.DataFrame) -> pd.DataFrame:
    """Pivot long sub-investor flow to wide net-buy. One column per sub-type.

    Returns ``(date, ticker, pension, insurance, investment_trust, pe_funds,
    financial_inv, other_financial, bank, government)`` with missing
    combinations filled with 0.
    """
    wide = flow.pivot_table(
        index=['date', 'ticker'],
        columns='subinvestor_type',
        values='net_buy_value',
        fill_value=0,
    ).reset_index()
    wide.columns.name = None
    return wide
