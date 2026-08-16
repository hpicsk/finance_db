"""Grade every 除權息 in ``price_adj/`` against the reference prices the
exchange published for it, and write the result as the panel's fixed record.

Two conventions live in the adjusted panel and this file is where the boundary
between them is legible. FinMind builds its series by subtracting the *declared*
distribution from the prior close; ``adjust.py`` rebuilds the holes from the
exchange's *published reference price*. The two name the same number on 83 % of
events and land a cent apart on most of the rest — small, bounded, and not
cumulative, but a step at a vendor/rebuilt boundary looks like a bug to whoever
finds it next, and this table is the answer to that.

It also finds the events where the vendor is not a cent away but wrong, which is
what ``adjusted_loader`` patches:

``sign_flip``
    A 現金增資 subscribed above the market price raises the reference price —
    ``after > before``, 25 events in the panel — and on 6 of them the vendor
    applied the move in the opposite direction. The error is the full width of
    the reprice, up to 3.95 % of one session's return, and it sits in the
    factor for the stock's whole history behind that date.

``malformed_twin``
    A filing whose date also carries a ``div_result`` row with a non-positive
    reference leg. One in the panel: 3454 on 2011-07-27, filed as before 0.00 /
    after -2.30 beside the real 84.20 → 79.07. The vendor removed 7.42 = 5.12 +
    2.30, adding the two rows together.

Both are found by shape rather than by stock id, so a re-download that moves
them is graded, not matched against a list.

Writes ``vendor_event_audit.parquet``: one row per filed 除權息, whether or not
the vendor series covers it.

    python -m finmind_data.vendor_event_audit
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
OHLCV_DIR = ROOT / 'ohlcv'
PRICE_ADJ_DIR = ROOT / 'price_adj'
DIV_RESULT_DIR = ROOT / 'div_result'
OUT_PATH = ROOT / 'vendor_event_audit.parquet'

# The vendor's step for an event is read off two *adjacent* covered sessions
# bracketing it. Further apart than this and the ratio spans a gap that may
# hold other events, so the reading is not about this event alone and the row
# is recorded as unchecked rather than graded on a chain.
_MAX_BRACKET_DAYS = 10


def _vendor_factor(stock_id: str) -> pd.DataFrame | None:
    """Traded sessions the vendor covers, with its implied factor.

    ``adj_close / close`` on a traded session is the vendor's back-adjustment
    factor up to a constant, which is all a per-event ratio needs.
    """
    o = OHLCV_DIR / f'{stock_id}.parquet'
    a = PRICE_ADJ_DIR / f'{stock_id}.parquet'
    if not o.exists() or not a.exists():
        return None
    if not pq.ParquetFile(o).metadata.num_rows or not pq.ParquetFile(a).metadata.num_rows:
        return None
    raw = pd.read_parquet(o, columns=['date', 'close'])
    adj = pd.read_parquet(a, columns=['date', 'close']).rename(columns={'close': 'adj'})
    raw['date'] = pd.to_datetime(raw['date'])
    adj['date'] = pd.to_datetime(adj['date'])
    d = raw.merge(adj, on='date', how='inner').sort_values('date')
    d = d[d['close'] > 0]
    if len(d) < 2:
        return None
    d['f'] = d['adj'].to_numpy(dtype=float) / d['close'].to_numpy(dtype=float)
    return d.reset_index(drop=True)


def audit() -> pd.DataFrame:
    """One row per filed 除權息, graded against the exchange where possible."""
    rows = []
    for p in sorted(DIV_RESULT_DIR.glob('*.parquet')):
        if not pq.ParquetFile(p).metadata.num_rows:
            continue
        sid = p.stem
        e = pd.read_parquet(p)
        e['date'] = pd.to_datetime(e['date'])
        b = e['before_price'].astype(float).to_numpy()
        a = e['after_price'].astype(float).to_numpy()
        wellformed = (b > 0) & (a > 0)
        # A date carrying both a well-formed and a malformed row is the shape
        # the vendor adds together; flag the well-formed row, since that is the
        # one whose step the loader will replace.
        bad_dates = set(e['date'][~wellformed])
        px = _vendor_factor(sid)
        for j in range(len(e)):
            row = dict(stock_id=sid, date=e['date'].iloc[j],
                       kind=str(e['stock_or_cache_dividend'].iloc[j]),
                       before=b[j], after=a[j],
                       exchange_step=b[j] / a[j] if wellformed[j] else np.nan,
                       vendor_step=np.nan, rel=np.nan, checkable=False, defect='')
            if not wellformed[j]:
                row['defect'] = 'nonpositive_leg'
                rows.append(row)
                continue
            if e['date'].iloc[j] in bad_dates:
                row['defect'] = 'malformed_twin'
            if px is None:
                rows.append(row)
                continue
            dates = px['date'].to_numpy()
            i = int(np.searchsorted(dates, np.datetime64(e['date'].iloc[j]), 'left'))
            if i <= 0 or i >= len(dates):
                rows.append(row)
                continue
            if (dates[i] - dates[i - 1]) / np.timedelta64(1, 'D') > _MAX_BRACKET_DAYS:
                rows.append(row)
                continue
            f = px['f'].to_numpy()
            row['vendor_step'] = f[i] / f[i - 1]
            row['rel'] = abs(row['vendor_step'] / row['exchange_step'] - 1.0)
            row['checkable'] = True
            # The two steps sit on opposite sides of 1.0: the vendor scaled the
            # history the wrong way. A direction test, so it carries no
            # tolerance to choose — which is why "the vendor applied no step"
            # is not a class here. Its only candidate, 2867 on 2023-11-10, is a
            # one-cent reprice (5.05 → 5.04) whose declared distribution rounds
            # to zero; separating that from a genuinely missed event would take
            # a threshold with nothing to anchor it to.
            if (row['vendor_step'] - 1.0) * (row['exchange_step'] - 1.0) < 0:
                row['defect'] = 'sign_flip'
            rows.append(row)
    return pd.DataFrame(rows)


def defective_events(path: Path = OUT_PATH) -> pd.DataFrame:
    """The events ``adjusted_loader`` replaces the vendor's step on.

    Only the two defects that are wrong rather than differently derived. A
    ``nonpositive_leg`` row is not a step at all and is dropped, not patched;
    the cent-scale disagreements are the vendor's own methodology and stay.
    """
    if not path.exists():
        raise FileNotFoundError(
            f'{path} is missing — run `python -m finmind_data.vendor_event_audit` '
            f'first. Without it the vendor events that are wrong rather than '
            f'differently derived go through unpatched.')
    d = pd.read_parquet(path)
    return d[d['defect'].isin(('sign_flip', 'malformed_twin')) & d['checkable']].copy()


if __name__ == '__main__':
    d = audit()
    d.to_parquet(OUT_PATH, index=False)
    ck = d[d['checkable']]
    print(f'{len(d):,} filed 除權息; {len(ck):,} graded against the exchange')
    for tol in (1e-6, 1e-4, 1e-3, 1e-2):
        print(f'  vendor step == exchange within {tol:g}: {(ck["rel"] < tol).mean():8.4%}')
    print(f'  median {ck["rel"].median():.2e}  p99 {ck["rel"].quantile(.99):.2e}  '
          f'max {ck["rel"].max():.2e}')
    print(f'\ndefects: {d[d["defect"] != ""].groupby("defect").size().to_dict()}')
    print(d[d['defect'] != ''][['stock_id', 'date', 'kind', 'before', 'after',
                                'vendor_step', 'exchange_step', 'rel', 'defect']]
          .sort_values('rel', ascending=False).to_string(index=False))
