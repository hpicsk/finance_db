"""Share-count changes no filed event explains. `python -m finmind_data.detect_unpriced_actions`

``capital_reduction.parquet`` starts on 2011-01-25; ``ohlcv/`` and ``div_result/``
start in 2005. The six missing years are a limit of FinMind's endpoint, not of the
download, and nothing in the reference-price chain can see past it — a 減資 filed
before 2011 leaves its full mechanical price jump inside the adjusted series with
``is_cap_red`` reading False.

FinMind's own ``TaiwanStockPriceAdj`` inherits the same limit — 2357's 85 %
reduction on 2010-06-24 has a vendor factor step of 1.0000 — so buying the
adjusted series does not retire this detector.

``shares/NumberOfSharesIssued`` is a third source, from a different endpoint, and it
covers 2005 onward. A share cancellation shows up there as a one-step drop, so it
can say *that* an action happened in the window where the event file cannot. It
cannot say by how much the exchange repriced: the reference prices simply are not
published anywhere this account can reach. So this script detects and reports; it
never synthesises a factor. ``adjusted_loader.py`` marks the history behind each
detection ``is_valid = False`` rather than guessing a step for it.

Parameters (see CLAUDE.md §6.1):
  MEASURED  none — no parameter here is fitted to a target.
  CHOSEN    ``_MIN_SHARE_DROP`` 5 % — a materiality floor, so ordinary buyback
            cancellations and rounding in the share count do not register.
  CHOSEN    ``_MIN_SUSPENSION_DAYS`` 5 — a Taiwanese capital reduction suspends
            trading for 12 to 18 days to exchange certificates, so the drop is
            straddled by a hole in the calendar. This is what separates a
            cancellation the exchange repriced from one it did not.
  CHOSEN    ``_EXPLAINED_WINDOW_DAYS`` 30 — the share count and the filing are
            dated by different endpoints and disagree by days, not weeks.

Calibrated against the years where ``capital_reduction.parquet`` *is* the ground
truth (2011-01-25 onward): 92.7 % of detections match a filed event and 91.9 % of
filed events are detected. ``--calibrate`` reprints that table. Precision is flat
at ~92 % across drop thresholds once the suspension condition is on, so the 5 %
floor sets recall, not the pass mark.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from finmind_data.adjusted_loader import OHLCV_DIR, UNPRICED_PATH

ROOT = Path(__file__).resolve().parent
SHARES_DIR = ROOT / 'shares'
# The two filed-event chains, read here only as the explainer set: a detected
# share drop within _EXPLAINED_WINDOW_DAYS of a filing is one the exchange priced.
DIV_RESULT_DIR = ROOT / 'div_result'
CAP_RED_PATH = ROOT / 'capital_reduction.parquet'

_MIN_SHARE_DROP = 0.05
_MIN_SUSPENSION_DAYS = 5
_EXPLAINED_WINDOW_DAYS = 30
# capital_reduction.parquet's own first row. Detections at or after it are the
# calibration set; detections before it are the window the chain cannot see.
_CAP_RED_COVERAGE_START = pd.Timestamp('2011-01-25')


def _filed_events() -> pd.DataFrame:
    """Every event either chain filed, as (stock_id, date). The explainer set."""
    f = []
    for p in sorted(DIV_RESULT_DIR.glob('*.parquet')):
        d = pd.read_parquet(p)
        if len(d):
            f.append(d[['stock_id', 'date']])
    c = pd.read_parquet(CAP_RED_PATH, columns=['stock_id', 'date'])
    f.append(c)
    ev = pd.concat(f, ignore_index=True)
    ev['stock_id'] = ev['stock_id'].astype(str)
    ev['date'] = pd.to_datetime(ev['date'])
    return ev


def detect() -> pd.DataFrame:
    """Material share-count drops, each tagged with whether a filing explains it.

    Columns: ``stock_id``, ``date`` (the session the reduced count first appears
    on), ``share_drop`` (the fraction cancelled), ``suspension_days`` (the calendar
    hole the drop sits in) and ``explained`` (a filing within
    ``_EXPLAINED_WINDOW_DAYS``).
    """
    filed = _filed_events()
    by_stock = {k: v['date'].to_numpy() for k, v in filed.groupby('stock_id')}
    window = np.timedelta64(_EXPLAINED_WINDOW_DAYS, 'D')

    hits = []
    for p in sorted(SHARES_DIR.glob('*.parquet')):
        s = pd.read_parquet(p)
        # Stocks the endpoint returned nothing for are written as zero-row files
        # with no schema, so the column projection cannot be pushed down.
        if s.empty or 'NumberOfSharesIssued' not in s.columns:
            continue
        sid = p.stem
        s['date'] = pd.to_datetime(s['date'])
        s = s.sort_values('date')
        s = s[s['NumberOfSharesIssued'] > 0]
        if len(s) < 2:
            continue
        n = s['NumberOfSharesIssued'].to_numpy(dtype=float)
        sd = s['date'].to_numpy()
        drop = 1.0 - n[1:] / n[:-1]
        material = np.nonzero(drop >= _MIN_SHARE_DROP)[0]
        if not len(material):
            continue

        px = pd.read_parquet(OHLCV_DIR / f'{sid}.parquet')
        if not len(px):
            continue
        pdt = pd.to_datetime(px['date']).sort_values().to_numpy()
        known = by_stock.get(sid, np.empty(0, dtype='datetime64[ns]'))
        for i in material:
            d = sd[i + 1]
            # The suspension is a hole in the *price* calendar straddling the
            # drop: the session before it and the session at or after it.
            j = int(np.searchsorted(pdt, d, 'left'))
            if j <= 0 or j >= len(pdt):
                continue
            susp = int((pdt[j] - pdt[j - 1]) / np.timedelta64(1, 'D'))
            if susp < _MIN_SUSPENSION_DAYS:
                continue
            hits.append(dict(
                stock_id=sid, date=pd.Timestamp(pdt[j]),
                share_drop=float(drop[i]), suspension_days=susp,
                explained=bool(len(known) and
                               np.abs(known - d).min() <= window)))
    return pd.DataFrame(hits, columns=['stock_id', 'date', 'share_drop',
                                       'suspension_days', 'explained'])


def calibrate(hits: pd.DataFrame) -> None:
    """Precision and recall where capital_reduction.parquet is ground truth."""
    cr = pd.read_parquet(CAP_RED_PATH, columns=['stock_id', 'date'])
    cr['stock_id'] = cr['stock_id'].astype(str)
    cr['date'] = pd.to_datetime(cr['date'])
    post = hits[hits['date'] >= _CAP_RED_COVERAGE_START]
    found = {k: v['date'].to_numpy() for k, v in post.groupby('stock_id')}
    window = np.timedelta64(_EXPLAINED_WINDOW_DAYS, 'D')
    rec = sum(1 for sid, d in zip(cr['stock_id'], cr['date'].to_numpy())
              if sid in found and np.abs(found[sid] - d).min() <= window)
    print(f'\ncalibration on {_CAP_RED_COVERAGE_START.date()}..2024, where the '
          f'filed events are the ground truth')
    print(f'  detections {len(post):,}   of them explained by a filing '
          f'{100 * post["explained"].mean():.1f}%   (precision)')
    print(f'  filed 減資 {len(cr):,}   of them detected '
          f'{100 * rec / max(len(cr), 1):.1f}%   (recall)')


def main() -> None:
    hits = detect()
    hits.to_parquet(UNPRICED_PATH, index=False)
    un = hits[~hits['explained']]
    pre = un[un['date'] < _CAP_RED_COVERAGE_START]
    print(f'share-count drops >= {_MIN_SHARE_DROP:.0%} straddling a '
          f'>= {_MIN_SUSPENSION_DAYS}-day suspension: {len(hits):,} '
          f'in {hits["stock_id"].nunique():,} stocks')
    print(f'  no filing explains them: {len(un):,} in '
          f'{un["stock_id"].nunique():,} stocks')
    print(f'  of those, before {_CAP_RED_COVERAGE_START.date()} (the window the '
          f'event file does not cover): {len(pre):,} in '
          f'{pre["stock_id"].nunique():,} stocks')
    print(f'  → {UNPRICED_PATH}')
    if '--calibrate' in sys.argv:
        calibrate(hits)


if __name__ == '__main__':
    main()
