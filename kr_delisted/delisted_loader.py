"""Loader for the delisted 6-digit Korean-equity universe (marcap-backed).

KOSPI + KOSDAQ + KONEX, 2005-01..present. Warrants/rights/funds (7-8 char
codes) are out of scope. Prices are unadjusted (matches KRX raw history).

Sources:
  - Prices/volume/marcap: marcap/data/marcap-YYYY.parquet
  - Delisting metadata:   kr_delisted/delisting_calendar.csv
                          (regenerable via build_delisting_calendar.py)
"""
import os
import glob
import warnings
import pandas as pd
from functools import lru_cache

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARCAP_DIR = os.path.join(_REPO_ROOT, 'marcap', 'data')
CALENDAR   = os.path.join(_REPO_ROOT, 'kr_delisted', 'delisting_calendar.csv')

# Columns returned to callers (from marcap's 18-col schema)
COMMON_COLS = ['Date','Code','Name','Market','Open','High','Low','Close',
               'Volume','Amount','Marcap','Stocks','ChangeRate','Rank','Dept']

@lru_cache(maxsize=1)
def calendar():
    """Return the full delisting calendar as a DataFrame."""
    return pd.read_csv(CALENDAR, dtype={'ticker': str})

@lru_cache(maxsize=1)
def _marcap_year_files():
    return sorted(glob.glob(os.path.join(MARCAP_DIR, 'marcap-*.parquet')))

def load_delisted(ticker, start=None, end=None):
    """Load one 6-digit delisted ticker's full history from marcap.

    Returns a Date-sorted DataFrame with COMMON_COLS. Empty if ticker not found.
    ChangeRate is returned in fractional form (0.033 = 3.3%) — matches FDR convention.
    """
    ticker = str(ticker).strip()
    if not (len(ticker) == 6 and ticker.isdigit()):
        raise ValueError(f"ticker must be a 6-digit code; got {ticker!r}")

    frames = []
    for fp in _marcap_year_files():
        df = pd.read_parquet(fp)
        df = df[df['Code'].astype(str).str.zfill(6) == ticker]
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=COMMON_COLS)
    df = pd.concat(frames, ignore_index=True)

    # Normalise the percent-change column name (marcap has typo 'ChagesRatio' in older years)
    if 'ChangesRatio' in df.columns:
        df = df.rename(columns={'ChangesRatio': 'ChangeRate'})
    elif 'ChagesRatio' in df.columns:
        df = df.rename(columns={'ChagesRatio': 'ChangeRate'})

    df['Date'] = pd.to_datetime(df['Date'])
    if 'ChangeRate' in df.columns:
        df['ChangeRate'] = pd.to_numeric(df['ChangeRate'], errors='coerce') / 100.0
    else:
        warnings.warn("ChangeRate column not found in delisted data", UserWarning)

    if start: df = df[df['Date'] >= pd.to_datetime(start)]
    if end:   df = df[df['Date'] <= pd.to_datetime(end)]
    df = df.sort_values('Date').reset_index(drop=True)

    keep = [c for c in COMMON_COLS if c in df.columns]
    return df[keep]

def universe(genuine_only=True, markets=('KOSPI','KOSDAQ','KONEX')):
    """Return the calendar filtered for point-in-time analysis use."""
    cal = calendar()
    if genuine_only:
        cal = cal[cal['is_genuine'] == 'Y']
    cal = cal[cal['market'].isin(markets)]
    return cal.reset_index(drop=True)

if __name__ == '__main__':
    print("== universe (genuine only, KOSPI/KOSDAQ/KONEX) ==")
    uni = universe()
    print(f"  rows: {len(uni)}")
    print(f"  by market: {uni['market'].value_counts().to_dict()}")

    print("\n== sample: 005390 신성통상 (delisted 2025-09-30) ==")
    df = load_delisted('005390')
    print(f"  rows={len(df)}  range=[{df['Date'].min().date()}..{df['Date'].max().date()}]")
    print(df.tail(3).to_string(index=False))
