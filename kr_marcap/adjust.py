"""ChangesRatio price adjustment for marcap.

Price adjustment
----------------
For each ticker the back-adjusted close is built by compounding the exchange's
official daily return ``ChangesRatio`` (등락률): ``adj_close[t] / adj_close[t-1]
== 1 + ChangesRatio[t]/100``, anchored so the last day's adj_close equals its
raw close. ChangesRatio is computed by KRX against the corporate-action 기준가,
so it already absorbs splits, free/paid rights offerings (무상/유상증자), and
capital reductions (감자) correctly — including cases a shares-outstanding ratio
misses (e.g. 감자/액면병합 where the Stocks update and the price reset fall on
different days). ``cum_factor = adj_close / raw_close`` is stored for loaders.

Entity-change detection
-----------------------
The Stocks (shares outstanding) ratio is no longer used for adjustment, only to
detect *entity changes* — SPAC mergers, reverse listings, ticker reuse — where
the share count jumps without an inverse price move. A big Stocks ratio whose
same-day price move does not corroborate it (see ``_CORROBORATION_TOL``) is a
series break: the pre-break history belongs to a different entity (e.g. the
pre-merger shell) and is marked ``valid=False`` so loaders drop it.

Known limitation
----------------
ChangesRatio is rounded to 0.01%, so compounded price *levels* carry a tiny
drift; daily and h-day *returns* (the pipeline's actual inputs) are unaffected
beyond ~1e-4 since the anchor cancels. Rare ChangesRatio data errors on
relisting first days remain — they affect only the local window, not the rest
of the series.

Build once:

    from kr_marcap.adjust import build_adjustment_factors
    build_adjustment_factors()

Then load one ticker:

    from kr_marcap.adjust import load_adjusted
    df = load_adjusted('005930')
"""
from __future__ import annotations

import glob
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

MARCAP_DIR = Path(os.path.expanduser('~/finance_db/marcap/data'))
CACHE_DIR = Path(__file__).resolve().parent / 'cache'
FACTORS_PATH = CACHE_DIR / 'adj_factors.parquet'
ANOMALIES_PATH = CACHE_DIR / 'adjust_anomalies.csv'

# Stocks ratio outside this band flags a possible entity change for review.
_RATIO_FLAG_LOW = 0.1
_RATIO_FLAG_HIGH = 10.0
# An anomalous Stocks ratio (outside the flag band) is a GENUINE corporate
# action (split / free-issue) only if the same-day price moved inversely to the
# share count, i.e. the residual adjusted return it would inject is near zero.
# Empirically (2026-06 diagnosis) genuine actions leave |residual| <= 0.495
# while entity changes (SPAC mergers, reverse listings, ticker reuse, data
# errors) leave |residual| >= 0.522, so 0.5 cleanly separates the two.
_CORROBORATION_TOL = 0.5


def _load_all_marcap(marcap_dir: Path) -> pd.DataFrame:
    """Read every marcap year, keep only OHLCV+Stocks+ChangesRatio+Code+Date."""
    cols = ['Date', 'Code', 'Open', 'High', 'Low', 'Close',
            'Volume', 'Amount', 'Marcap', 'Stocks', 'ChangesRatio']
    frames = []
    for fp in sorted(glob.glob(str(marcap_dir / 'marcap-*.parquet'))):
        df = pd.read_parquet(fp, columns=cols)
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        df['Date'] = pd.to_datetime(df['Date'])
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(['Code', 'Date']).reset_index(drop=True)
    return out


def build_adjustment_factors(
    marcap_dir: Path = MARCAP_DIR,
    out_path: Path = FACTORS_PATH,
    anomalies_path: Path = ANOMALIES_PATH,
) -> pd.DataFrame:
    """Compute back-adjusted factors from exchange ChangesRatio.

    adj_close is built by compounding ChangesRatio (corporate-action-correct);
    the Stocks ratio is used only to flag entity-change series breaks.

    Output schema: date, code, raw_close, stocks, ratio, cum_factor, adj_close,
    valid (False before a ticker's last series break — pre-relisting history).
    ``ratio`` is the diagnostic Stocks ratio, not the adjustment factor.
    Writes anomalies (Stocks ratio outside [0.1, 10] or missing Stocks, with the
    corroboration verdict in ``raw_ret``/``adj_ret``/``is_break``) to a sidecar.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = _load_all_marcap(marcap_dir)

    df['stocks_prev'] = df.groupby('Code', sort=False)['Stocks'].shift(1)
    # ratio[t] = Stocks[t-1] / Stocks[t]  (back-adjusted: applied to history)
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio = np.where(
            (df['Stocks'] > 0) & (df['stocks_prev'] > 0),
            df['stocks_prev'] / df['Stocks'],
            np.nan,
        )
    df['ratio'] = ratio

    # Same-day raw price move, used to corroborate that an anomalous Stocks
    # jump is a real split (price moves inversely) vs an entity change.
    close_prev = df.groupby('Code', sort=False)['Close'].shift(1)
    df['raw_ret'] = df['Close'] / close_prev - 1.0

    # Anomaly capture: missing/zero Stocks OR ratio outside [low, high].
    missing = df['stocks_prev'].notna() & (
        (df['Stocks'] <= 0) | (df['stocks_prev'] <= 0)
    )
    big_jump = df['ratio'].notna() & (
        (df['ratio'] < _RATIO_FLAG_LOW) | (df['ratio'] > _RATIO_FLAG_HIGH)
    )
    # Residual return a big-jump ratio would inject after adjustment: ~0 means
    # the price moved inversely to shares (real split); large means the share
    # count changed without a matching price move (entity change / relisting).
    adj_ret = (1.0 + df['raw_ret']) / df['ratio'] - 1.0
    corroborated = (
        big_jump & df['raw_ret'].notna() & (adj_ret.abs() < _CORROBORATION_TOL)
    )
    # A non-corroborated big jump is a series break: the listing changed hands
    # (e.g. a SPAC merger), so its pre-break history belongs to a different
    # entity and must be neither adjusted nor carried forward.
    is_break = big_jump & ~corroborated

    anomalies = df.loc[
        missing | big_jump,
        ['Date', 'Code', 'stocks_prev', 'Stocks', 'ratio', 'Close'],
    ].copy()
    anomalies['raw_ret'] = df.loc[anomalies.index, 'raw_ret']
    anomalies['adj_ret'] = adj_ret.loc[anomalies.index]
    anomalies['is_break'] = is_break.loc[anomalies.index]
    if not anomalies.empty:
        anomalies.to_csv(anomalies_path, index=False)
    elif anomalies_path.exists():
        anomalies_path.unlink()

    # Daily gross return from the exchange's official ChangesRatio (등락률).
    # NaN (first row), non-positive/garbage, no-trade (Close<=0), and
    # entity-change break days do not compound: a break day's move is across two
    # different entities and its pre-break history is dropped anyway.
    gross = 1.0 + df['ChangesRatio'].to_numpy() / 100.0
    gross = np.where(
        np.isnan(gross) | (gross <= 0.0) | is_break.to_numpy()
        | (df['Close'].to_numpy() <= 0.0),
        1.0, gross,
    )
    df['gross'] = gross

    # Back-adjusted close: compound ChangesRatio per ticker, anchored so the
    # last *traded* day's adj_close == its raw close. The anchor cancels in any
    # return (adj_close[t]/adj_close[t-h] == product of the intervening
    # grosses), so daily and h-day returns carry no rounding accumulation.
    def _adj_close(group: pd.DataFrame) -> pd.Series:
        px = group['Close'].to_numpy()
        g = np.cumprod(group['gross'].to_numpy())
        traded = px > 0.0
        if not traded.any():
            return pd.Series(np.nan, index=group.index)
        anchor = np.where(traded)[0][-1]  # last positive-close (traded) row
        return pd.Series(px[anchor] * g / g[anchor], index=group.index)

    df['adj_close'] = (
        df.groupby('Code', sort=False, group_keys=False).apply(_adj_close)
    )
    # cum_factor is undefined on no-trade rows (raw close 0); loaders drop them.
    df['cum_factor'] = df['adj_close'] / df['Close']
    df.loc[df['Close'] <= 0.0, 'cum_factor'] = np.nan

    # valid=False for every row strictly before a ticker's LAST series break:
    # that history belongs to the pre-merger shell / a prior listing and is
    # dropped at load time (kr_marcap.market_loader).
    df['is_break'] = is_break.to_numpy()
    last_break = df.loc[df['is_break']].groupby('Code', sort=False)['Date'].max()
    lb = df['Code'].map(last_break)
    df['valid'] = lb.isna() | (df['Date'] >= lb)

    out = df[['Date', 'Code', 'Close', 'Stocks', 'ratio',
              'cum_factor', 'adj_close', 'valid']].copy()
    out.columns = ['date', 'code', 'raw_close', 'stocks', 'ratio',
                   'cum_factor', 'adj_close', 'valid']
    out.to_parquet(out_path, index=False)
    return out


@lru_cache(maxsize=1)
def _load_factors(path: str) -> pd.DataFrame:
    f = pd.read_parquet(path)
    f['date'] = pd.to_datetime(f['date'])
    return f


def load_adjusted(
    ticker: str,
    factors_path: Path | None = None,
    marcap_dir: Path = MARCAP_DIR,
) -> pd.DataFrame:
    """Return a single ticker's full OHLCV history with adjusted columns.

    Columns: date, open, high, low, close, volume, amount, market_cap, stocks,
             cum_factor, adj_open, adj_high, adj_low, adj_close, adj_volume.

    Volume is also adjusted (multiplied by 1/cum_factor → shares scaled to
    today's share-count basis) so adj_close × adj_volume ≈ raw_close × raw_volume.
    """
    path = str(factors_path or FACTORS_PATH)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f'factors not found at {path} — run build_adjustment_factors() first'
        )
    ticker = str(ticker).zfill(6)
    factors = _load_factors(path)
    f = factors.loc[factors['code'] == ticker, ['date', 'cum_factor', 'valid']]
    if f.empty:
        return pd.DataFrame()

    # Pull raw OHLCV from marcap.
    frames = []
    for fp in sorted(glob.glob(str(marcap_dir / 'marcap-*.parquet'))):
        df = pd.read_parquet(fp, columns=['Date', 'Code', 'Open', 'High', 'Low',
                                          'Close', 'Volume', 'Amount', 'Marcap',
                                          'Stocks'])
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        df = df[df['Code'] == ticker]
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True)
    raw['Date'] = pd.to_datetime(raw['Date'])
    raw = raw.sort_values('Date').reset_index(drop=True)

    merged = raw.merge(f, left_on='Date', right_on='date', how='left')
    # Drop pre-relisting history flagged valid=False (see build_adjustment_factors).
    merged = merged[merged['valid'].fillna(True)].reset_index(drop=True)
    cf = merged['cum_factor'].fillna(1.0).to_numpy()
    out = pd.DataFrame({
        'date': merged['Date'],
        'open': merged['Open'],
        'high': merged['High'],
        'low': merged['Low'],
        'close': merged['Close'],
        'volume': merged['Volume'],
        'amount': merged['Amount'],
        'market_cap': merged['Marcap'],
        'stocks': merged['Stocks'],
        'cum_factor': cf,
        'adj_open': merged['Open'] * cf,
        'adj_high': merged['High'] * cf,
        'adj_low': merged['Low'] * cf,
        'adj_close': merged['Close'] * cf,
        'adj_volume': merged['Volume'] / cf,
    })
    return out


if __name__ == '__main__':
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == 'build':
        print(f'building adjustment factors from {MARCAP_DIR} ...')
        out = build_adjustment_factors()
        print(f'  rows: {len(out):,}')
        print(f'  unique tickers: {out["code"].nunique():,}')
        print(f'  written to: {FACTORS_PATH}')
        if ANOMALIES_PATH.exists():
            n = sum(1 for _ in open(ANOMALIES_PATH)) - 1
            print(f'  anomalies: {n} rows — see {ANOMALIES_PATH}')
    else:
        # Samsung 005930 split 50:1 on 2018-05-04.
        df = load_adjusted('005930')
        print(f'005930 rows: {len(df)}  range [{df["date"].min().date()}..{df["date"].max().date()}]')
        around_split = df[(df['date'] >= '2018-04-25') & (df['date'] <= '2018-05-10')]
        print('Samsung around 2018-05-04 split:')
        print(around_split[['date', 'close', 'stocks', 'cum_factor', 'adj_close']].to_string(index=False))
