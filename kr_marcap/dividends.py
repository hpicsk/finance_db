"""Cash-dividend collection from DART → total-return layer for kr_marcap.

marcap's ChangesRatio adjustment (``adjust.py``) is a *price* return: KRX 등락률
does not reset the 기준가 for ordinary cash dividends, so the adjusted series
omits them. This module crawls DART's structured 배당 report for the full
KOSPI+KOSDAQ common universe and caches per-(ticker, fiscal_year) cash-dividend
yield. ``adjust.load_adjusted(..., total_return=True)`` reinvests that yield at
each fiscal year-end to produce a total-return series (``adj_close_tr``).

Coverage: DART's structured 배당 endpoint is populated from ~fiscal 2014 only;
earlier years return no data and stay price-return-only. This is one of the
reasons total-return work should use post-2015 data — see the kr_marcap README
section "Use post-2015 data for Korean stocks".

Build once (after a marcap refresh / annually for the new fiscal year):

    export OPEN_DART_API_KEY=...          # or put it in finance_db/.env
    python -m kr_marcap.dividends build

Output: ``cache/dividends.parquet`` (code, fiscal_year, yield_pct, dps).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd

from kr_status.corp_code_map import open_dart, get_corp_code, flush_cache, flush_misses

CACHE_DIR = Path(__file__).resolve().parent / 'cache'
UNIVERSE_PANEL = CACHE_DIR / 'universe_panel.parquet'
DIVIDENDS_PATH = CACHE_DIR / 'dividends.parquet'

# Each DART 배당 report carries the year (thstrm) plus the two prior years
# (frmtrm, lwfr). These four windows therefore cover fiscal 2014-2025 with no
# gaps in 4 calls/ticker (~15k calls for the full universe, under DART's
# 20k/day cap). Fiscal ≤2013 is not in the structured endpoint.
REPORT_WINDOWS = [2016, 2019, 2022, 2025]
_MIN_FY, _MAX_FY = 2014, 2025
CHECKPOINT = 200


def _num(x):
    if x is None:
        return None
    s = str(x).replace(',', '').strip()
    if s in ('', '-', 'N/A'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _pick(df, item):
    sub = df[df['se'].astype(str).str.strip() == item]
    if sub.empty:
        return None
    com = sub[sub['stock_knd'].astype(str).str.strip() == '보통주']
    return (com if not com.empty else sub).iloc[0]


def yields_for(dart, corp, sleep_s=0.03):
    """Return {fiscal_year: (yield_pct, dps)} for one DART corp_code/ticker.

    A year seen in the report whose own fiscal year == that year (the `thstrm`
    column) is preferred over the same year read as a prior-year column.
    """
    out = {}  # year -> (yield_pct, dps, is_thstrm)
    for ry in REPORT_WINDOWS:
        try:
            df = dart.report(corp, '배당', ry)
        except Exception:
            df = None
        if not isinstance(df, pd.DataFrame) or len(df) == 0 or 'se' not in df.columns:
            continue
        yrow = _pick(df, '현금배당수익률(%)')
        drow = _pick(df, '주당 현금배당금(원)')
        for col, yr in {'thstrm': ry, 'frmtrm': ry - 1, 'lwfr': ry - 2}.items():
            if yr < _MIN_FY or yr > _MAX_FY:
                continue
            yv = _num(yrow[col]) if yrow is not None else None
            dv = _num(drow[col]) if drow is not None else None
            is_th = col == 'thstrm'
            if yr not in out or (is_th and not out[yr][2]):
                out[yr] = (yv, dv, is_th)
        time.sleep(sleep_s)
    return {y: (v[0], v[1]) for y, v in out.items()}


def _common_universe():
    panel = pd.read_parquet(UNIVERSE_PANEL)
    panel['code'] = panel['code'].astype(str).str.zfill(6)
    com = panel[(panel['kind'] == 'common') & (panel['code'].str.len() == 6)
                & (panel['market'].isin(['KOSPI', 'KOSDAQ']))]
    return com[['code', 'name']].drop_duplicates('code').reset_index(drop=True)


def build_dividends(restart: bool = False, limit: int | None = None) -> pd.DataFrame:
    """Crawl DART 배당 for the full common universe; cache to dividends.parquet."""
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    except ImportError:
        pass

    dart = open_dart()
    uni = _common_universe()
    if limit:
        uni = uni.head(limit)

    # Canary: a known payer must return a recent dividend, else key/quota is bad.
    canary = yields_for(dart, '005930')          # Samsung Electronics
    if not any(v[0] for v in canary.values()):
        raise RuntimeError(
            'DART canary failed (Samsung 005930 returned no dividend) — '
            'check OPEN_DART_API_KEY / daily quota'
        )

    existing = pd.DataFrame()
    done = set()
    if DIVIDENDS_PATH.exists() and not restart:
        existing = pd.read_parquet(DIVIDENDS_PATH)
        existing['code'] = existing['code'].astype(str).str.zfill(6)
        done = set(existing['code'])

    todo = uni[~uni['code'].isin(done)].reset_index(drop=True)
    print(f'dividends: {len(uni)} common tickers, {len(done)} cached, '
          f'{len(todo)} to crawl', file=sys.stderr, flush=True)

    rows = []
    n_hit = 0
    for i, r in todo.iterrows():
        y = yields_for(dart, get_corp_code(dart, r['code'], r['name']) or r['code'])
        if any(v[0] for v in y.values()):
            n_hit += 1
        for fy, (yv, dv) in y.items():
            rows.append((r['code'], fy, yv, dv))
        if (i + 1) % CHECKPOINT == 0 or (i + 1) == len(todo):
            part = pd.DataFrame(rows, columns=['code', 'fiscal_year', 'yield_pct', 'dps'])
            pd.concat([existing, part], ignore_index=True).to_parquet(DIVIDENDS_PATH, index=False)
            flush_cache()
            flush_misses()
            print(f'  {i+1}/{len(todo)} crawled, {n_hit} payers, '
                  f'{len(rows)} stock-years', file=sys.stderr, flush=True)

    # Guard against silent mid-run quota exhaustion (every ticker returning empty).
    if len(todo) > 50 and n_hit / len(todo) < 0.10:
        raise RuntimeError(
            f'implausibly low dividend hit-rate ({n_hit}/{len(todo)}) — '
            'likely DART quota exhausted mid-run; re-run to resume from checkpoint'
        )

    out = pd.read_parquet(DIVIDENDS_PATH)
    print(f'WROTE {DIVIDENDS_PATH}  {out.shape}  '
          f'({out["code"].nunique()} tickers, '
          f'fiscal {int(out["fiscal_year"].min())}-{int(out["fiscal_year"].max())})',
          file=sys.stderr, flush=True)
    return out


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == 'build':
        restart = '--restart' in sys.argv
        lim = next((int(a.split('=')[1]) for a in sys.argv if a.startswith('--limit=')), None)
        build_dividends(restart=restart, limit=lim)
    else:
        # Quick demo: Samsung's recent cash-dividend yields.
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parents[1] / '.env')
        except ImportError:
            pass
        d = open_dart()
        print('Samsung 005930 cash-dividend yields:', yields_for(d, '005930'))
