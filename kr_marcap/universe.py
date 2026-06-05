"""Point-in-time Korean common-stock universe from marcap.

A ticker's [first_date, last_date] window in marcap defines its membership
window. The kind is the modal classification across all of the ticker's
marcap rows; if rows disagree (rare, mid-life rename), the conflict is
recorded in ``universe_conflicts.csv`` for manual review.

Build the panel once after a marcap refresh:

    from kr_marcap.universe import build_universe_panel
    build_universe_panel()

Then query point-in-time membership:

    from kr_marcap.universe import universe
    universe('2010-06-15', 'common')   # → ['005930', ...]
"""
from __future__ import annotations

import glob
import os
from collections import Counter
from functools import lru_cache
from pathlib import Path

import pandas as pd

from kr_marcap.classify import classify_ticker

MARCAP_DIR = Path(os.path.expanduser('~/finance_db/marcap/data'))
CACHE_DIR = Path(__file__).resolve().parent / 'cache'
PANEL_PATH = CACHE_DIR / 'universe_panel.parquet'
CONFLICTS_PATH = CACHE_DIR / 'universe_conflicts.csv'

# Infrastructure / real-estate / resource trusts that classify_ticker marks
# as 'common' (no 호 suffix, no 선박투자/리츠/REIT keyword) but are fund-like
# in substance. Opt-in exclusion via universe(..., strict=True). These are
# also the only live KOSPI/KOSDAQ commons missing from fnguide's master
# table, so strict=True yields a 100% fnguide-aligned set.
STRICT_COMMON_EXCLUDE = frozenset({
    '088980',   # 맥쿼리한국인프라투융자회사 (KOSPI 200 편입)
    '415640',   # KB발해인프라
    '094800',   # 맵스미래에셋맵스리얼티1
    '152550',   # 한국ANKOR유전
})


def _iter_marcap_years(marcap_dir: Path):
    for fp in sorted(glob.glob(str(marcap_dir / 'marcap-*.parquet'))):
        df = pd.read_parquet(fp, columns=['Code', 'Name', 'Market', 'Date'])
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        df['Date'] = pd.to_datetime(df['Date'])
        yield fp, df


def build_universe_panel(
    marcap_dir: Path = MARCAP_DIR,
    out_path: Path = PANEL_PATH,
    conflicts_path: Path = CONFLICTS_PATH,
) -> pd.DataFrame:
    """Scan all marcap parquets and emit a per-ticker membership table.

    Output schema: code, name, market, kind, first_date, last_date, n_days.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Collect every (code, date, name, market) seen across all years.
    seen_dates: dict[str, list] = {}    # code → [Timestamp, ...]
    kinds_per_code: dict[str, Counter] = {}
    # Most-recent (name, market) wins for the display row and the kind.
    latest_meta: dict[str, tuple[pd.Timestamp, str, str]] = {}

    for fp, df in _iter_marcap_years(marcap_dir):
        df = df.dropna(subset=['Code', 'Date'])
        for row in df.itertuples(index=False):
            code = row.Code
            name = row.Name if isinstance(row.Name, str) else ''
            market = row.Market if isinstance(row.Market, str) else ''
            date = row.Date

            seen_dates.setdefault(code, []).append(date)
            kind = classify_ticker(code, name, market)
            kinds_per_code.setdefault(code, Counter())[kind] += 1

            prev = latest_meta.get(code)
            if prev is None or date > prev[0]:
                latest_meta[code] = (date, name, market)

    rows = []
    conflicts = []
    for code, dates in seen_dates.items():
        first, last = min(dates), max(dates)
        n = len(dates)
        kinds = kinds_per_code[code]
        _, name, market = latest_meta[code]
        # Use the latest observation's classification: when a ticker migrates
        # (KONEX → KOSDAQ, REIT → operating company, etc.) the current type is
        # what callers querying "active on date D" expect, not the historical
        # modal type. The conflicts file still records the full distribution.
        latest_kind = classify_ticker(code, name, market)
        if len(kinds) > 1:
            conflicts.append({
                'code': code,
                'kinds': dict(kinds),
                'latest_kind': latest_kind,
                'name_latest': name,
                'market_latest': market,
            })
        rows.append({
            'code': code,
            'name': name,
            'market': market,
            'kind': latest_kind,
            'first_date': first,
            'last_date': last,
            'n_days': n,
        })

    panel = pd.DataFrame(rows).sort_values(['kind', 'code']).reset_index(drop=True)
    panel.to_parquet(out_path, index=False)

    if conflicts:
        pd.DataFrame(conflicts).to_csv(conflicts_path, index=False)
    elif conflicts_path.exists():
        conflicts_path.unlink()

    return panel


@lru_cache(maxsize=1)
def _load_panel(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df['first_date'] = pd.to_datetime(df['first_date'])
    df['last_date'] = pd.to_datetime(df['last_date'])
    return df


def universe(
    date: str | pd.Timestamp,
    kind: str = 'common',
    panel_path: Path | None = None,
    strict: bool = False,
) -> list[str]:
    """Return tickers active on *date* whose classification matches *kind*.

    strict=True (only meaningful for kind='common') additionally drops the
    handful of infrastructure / real-estate / resource trusts in
    STRICT_COMMON_EXCLUDE. Use it when you want the marcap commons set to
    match fnguide's master table exactly.
    """
    path = str(panel_path or PANEL_PATH)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f'universe panel not found at {path} — run build_universe_panel() first'
        )
    df = _load_panel(path)
    d = pd.to_datetime(date)
    mask = (df['kind'] == kind) & (df['first_date'] <= d) & (df['last_date'] >= d)
    codes = df.loc[mask, 'code'].tolist()
    if strict and kind == 'common':
        codes = [c for c in codes if c not in STRICT_COMMON_EXCLUDE]
    return codes


if __name__ == '__main__':
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == 'build':
        print(f'building universe panel from {MARCAP_DIR} ...')
        panel = build_universe_panel()
        print(f'  rows: {len(panel)}')
        print(f'  by kind: {panel["kind"].value_counts().to_dict()}')
        print(f'  written to: {PANEL_PATH}')
        if CONFLICTS_PATH.exists():
            print(f'  conflicts: see {CONFLICTS_PATH}')
    else:
        # quick query demo
        for d in ('2010-06-15', '2015-06-15', '2017-06-15', '2025-06-15'):
            tickers = universe(d, 'common')
            print(f'{d}  common: n={len(tickers)}  samples={tickers[:3]}')
