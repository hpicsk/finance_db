"""Total-return factors rebuilt from the exchange's own reference prices.

This is not a second adjusted series. ``price_adj/`` is the panel;
``adjusted_loader`` is the only caller and the only public entry point. What
this module supplies is the part of that panel the vendor does not serve — the
38 stocks with raw prices and an empty adjusted file, every one a 2005-2007
delisting dropped from FinMind's live registry, which is exactly the
survivorship overlay the universe was patched to keep.

The rebuild is possible because ``ohlcv/close`` is raw: it equals the exchange's
published pre-event ``before_price`` on 99.82 % of 除權息 events, so nothing has
been removed from it and the reference prices can be applied directly. Both
event chains are the exchange's own numbers rather than a redistribution of a
declared dividend — ``div_result/`` for 除權息 and ``capital_reduction.parquet``
for 減資 — and they never share a ``(stock_id, date)``: 0 overlaps across 22,370
and 627 filings, so the two chains multiply without double counting.
``_assert_disjoint`` re-checks it per stock rather than trusting that.

**Only total return is built.** A price-return convention needs the cash leg of
each event named separately, and the exchange publishes one *fused* reference
price per 除權息 covering cash, 無償配股 and 現增 together. There is no
price-return series to check such a split against at any vendor tier, so the
machinery is not carried.

A 現金減資 needs no special handling here, which is worth stating because it
looks like it should. The company cancels a fraction ``r`` of the shares and
refunds par for them, ``C = 10r`` per share, and the exchange prices
``after = (before - C)/(1 - r)``. That reference price is value-conserving
*including the refund* — ``(1 - r) * after + C == before`` holds to 2.8e-14 on
all 275 filings where both legs are published — so the step below leaves the
adjusted series flat across the event, which is what reinvesting the refund
means. Taking the refund out again is a price-return operation, not a
total-return one.

Convention. Each event contributes ``step = before / after``, placed on the
event row, accumulated with ``cumprod`` and normalised so the factor is 1.0 on
the last row. For 除權息 the reference price falls, so step > 1 and history is
scaled down; for 減資 it rises, so step < 1. Same formula, opposite direction,
no special case.

The step is taken at the ex price rather than the cum one, which is not a
cosmetic choice: back-adjustment factors compose multiplicatively and only the
ex form telescopes. A cum-price form ``1 + D/before`` understates each step by
``(D/before)**2`` — a median 21.5 bp per event and q95 159 bp, because Taiwan's
steps are large (median 4.6 % of the cum price, q95 12.6 %) where they carry a
share-count change as well as cash — compounding to a median 3.7 % and a q99
30.5 % over a stock's full history.

Coverage limit. ``capital_reduction.parquet`` starts on 2011-01-25 while prices
and 除權息 start in 2005, so a reduction filed in the first six years is
invisible to both chains and its mechanical price jump survives adjustment in
full. Nothing this account can reach repairs that window — the reference prices
were never published to it — so it is marked rather than guessed:
``detect_unpriced_actions`` reports the share cancellations no filing explains
and ``adjusted_loader`` turns them into ``is_valid``.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OHLCV_DIR = ROOT / 'ohlcv'
DIV_RESULT_DIR = ROOT / 'div_result'
CAP_RED_PATH = ROOT / 'capital_reduction.parquet'

# 除權息 columns: the exchange's official pre- and post-event reference prices.
_DIV_BEFORE, _DIV_AFTER = 'before_price', 'after_price'
# 減資 columns: same pair under the capital-reduction endpoint's own names.
# ExrightReferencePrice is -1.0 / 0.0 across the file and is not a price.
_RED_BEFORE, _RED_AFTER = 'ClosingPriceonTheLastTradingDay', 'PostReductionReferencePrice'

# The exchange publishes before_price to two decimals, so agreement with a close
# is agreement at the published precision. Not a fitted cut: the one filing this
# rejects misses by 3.95, and every tolerance from 1e-6 to 0.5 rejects the same
# one filing and no other.
_TOL_BEFORE_PRICE = 1e-2
# A filing repeated under both its suspension and its resumption date sits days
# apart, never years. Two filings carrying identical reference prices further
# apart than this are separate actions that happen to have repriced alike — 28
# of the 31 such pairs in the panel — and both are real.
_TWIN_WINDOW_DAYS = 30


def _read_events(stock_id: str, px: pd.DataFrame) -> pd.DataFrame:
    """Both event chains for one stock as (date, step, kind), earliest first.

    ``px`` is this stock's own (date, close) series, sorted. Both filters below
    need it: which dates it traded, and what it closed at.
    """
    out = []
    p = DIV_RESULT_DIR / f'{stock_id}.parquet'
    if p.exists():
        # Stocks the endpoint returned nothing for are written as zero-row files
        # with no schema, so a column projection cannot be pushed down.
        d = pd.read_parquet(p)
        if len(d):
            out.append(d[['date', _DIV_BEFORE, _DIV_AFTER]]
                       .rename(columns={_DIV_BEFORE: 'before', _DIV_AFTER: 'after'})
                       .assign(kind='除權息'))
    if CAP_RED_PATH.exists():
        c = pd.read_parquet(CAP_RED_PATH)
        c = c[c['stock_id'].astype(str) == str(stock_id)]
        if len(c):
            out.append(c[['date', _RED_BEFORE, _RED_AFTER]]
                       .rename(columns={_RED_BEFORE: 'before', _RED_AFTER: 'after'})
                       .assign(kind='減資'))
    if not out:
        return pd.DataFrame(columns=['date', 'step', 'kind'])

    ev = pd.concat(out, ignore_index=True)
    ev['date'] = pd.to_datetime(ev['date'])
    ev[['before', 'after']] = ev[['before', 'after']].astype(float)
    # A non-positive leg is a missing disclosure, not a price. Dropping is the
    # only safe reading — a zero would make the chain infinite or zero — and it
    # is not hypothetical: 3454 carries a row reading before 0.00 / after -2.30
    # alongside its real 2011-07-27 filing, and the vendor series applies both,
    # removing 7.42 where the exchange removed 5.13.
    ev = ev[(ev['before'] > 0) & (ev['after'] > 0)].reset_index(drop=True)

    # The same action is occasionally filed twice, once under a date the stock
    # did not trade. 2327 and 3018 each carry their 減資 under both the date
    # trading was suspended and the date it resumed, with one pair of reference
    # prices between them. Exact-date placement discarded the stray copy for
    # free; placing on the next session instead would apply the step twice. So
    # where a filing has an identical twin that fell on a session, keep the copy
    # the exchange actually priced. A filing whose only copy missed a session is
    # untouched — that is the typhoon case, and it is the one to postpone.
    #
    # "Twin" needs the date bound as well as the prices: a stock can reprice to
    # the same pair twice, years apart, and then both filings are real. Without
    # the bound a coincidence landing on a closure would silently delete a
    # genuine postponement instead of moving it.
    if len(ev) > 1:
        traded = ev['date'].isin(set(px['date'])).to_numpy()
        window = np.timedelta64(_TWIN_WINDOW_DAYS, 'D')
        superseded = np.zeros(len(ev), dtype=bool)
        for _, g in ev.groupby(['kind', 'before', 'after'], sort=False):
            if len(g) < 2:
                continue
            pos, dates = g.index.to_numpy(), g['date'].to_numpy()
            for k, i in enumerate(pos):
                if not traded[i]:
                    superseded[i] = bool(((np.abs(dates - dates[k]) <= window)
                                          & traded[pos]).any())
        ev = ev[~superseded]

    # That leaves the copy whose stray twin also fell on a session, which the
    # calendar alone cannot tell apart. The reference price is computed off the
    # last close before the event, so a filing whose predecessor closed at some
    # other price is not describing this series: 6109 files its 2018 現金減資
    # again under 2020-09-25, a date it traded straight through. The identity
    # holds for 22,952 of the 22,953 filings that have a prior close to check
    # against, so it rejects that one and leaves every other alone. A prior
    # close of zero is a stale FinMind row rather than a price and anchors
    # nothing, so those 41 pass unexamined.
    ev = ev.sort_values('date')
    prior = pd.merge_asof(ev[['date']], px, on='date', direction='backward',
                          allow_exact_matches=False)['close'].to_numpy()
    ev = ev[~(prior > 0)
            | (np.abs(ev['before'].to_numpy() - prior) <= _TOL_BEFORE_PRICE)]

    ev['step'] = ev['before'] / ev['after']
    return ev[['date', 'step', 'kind']].reset_index(drop=True)


def _assert_disjoint(ev: pd.DataFrame, stock_id: str) -> None:
    """除權息 and 減資 must not land on the same session, or the step double counts."""
    dup = ev[ev.duplicated('date', keep=False)]
    if len(dup) and dup['kind'].nunique() > 1:
        clash = dup.groupby('date')['kind'].nunique()
        clash = clash[clash > 1]
        if len(clash):
            raise ValueError(
                f'{stock_id}: 除權息 and 減資 share {len(clash)} session(s) '
                f'({", ".join(str(d.date()) for d in clash.index[:3])}) — the two '
                f'reference-price chains would double count. Reconcile the '
                f'endpoints before adjusting.')


def _raw_event_count(stock_id: str) -> int:
    """Events as filed, before any filter, so `events_dropped` is real."""
    n = 0
    p = DIV_RESULT_DIR / f'{stock_id}.parquet'
    if p.exists():
        n += len(pd.read_parquet(p))
    if CAP_RED_PATH.exists():
        c = pd.read_parquet(CAP_RED_PATH, columns=['stock_id'])
        n += int((c['stock_id'].astype(str) == str(stock_id)).sum())
    return n


def rebuild_tr_factor(stock_id: str, px: pd.DataFrame) -> tuple[np.ndarray, dict]:
    """Back-adjustment factor for one stock, 1.0 on the last row of ``px``.

    ``px`` is that stock's raw (date, close) series, sorted, with no-trade
    sessions still carrying ``close == 0`` — the calendar is the caller's, so
    the factor lines up row for row with the frame it will be multiplied into.

    Returns the factor and a diagnostics dict: ``events_placed``,
    ``events_postponed`` (the disclosed date was not a session, so the step sits
    on the next one — see the placement comment), ``events_unplaced`` (no
    session on or after the event date, so nothing is left to adjust) and
    ``events_dropped`` (a non-positive reference leg, or a duplicate filing
    superseded by the copy the exchange priced).

    The factor is defined on every row including the no-trade ones, because the
    chain is a property of the events and not of any one session; the caller
    decides which rows carry a price.
    """
    ev = _read_events(str(stock_id), px[['date', 'close']])
    _assert_disjoint(ev, str(stock_id))

    steps = np.ones(len(px))
    # First session ON OR AFTER the event date, not the exact date. A disclosed
    # event date is usually a session and this resolves to it, but 274 of the
    # 22,997 filed events fall on a day the stock did not trade, and 271 of those
    # are one of 21 dates when nothing traded at all — the exchange was shut,
    # almost always for a typhoon. TWSE 順延s such an event to the next session,
    # and the data says so: ``before_price`` equals the close of the session
    # before the closure, and the next session's realised return matches the
    # reference-price step to a mean 1 bp. So the step is right and only its date
    # is stale; placing it on the resumption session is what removes the move,
    # and skipping it would leave the full step inside a return. The remaining
    # three are 減資 suspensions, where trading stops for 12 to 18 days to
    # exchange certificates and the same reasoning applies to the resumption.
    dates = px['date'].to_numpy()
    idx = (np.searchsorted(dates, ev['date'].to_numpy(), 'left')
           if len(ev) else np.array([], int))
    postponed = 0
    for i, ev_date, step in zip(idx, ev['date'].to_numpy(), ev['step'].to_numpy()):
        # 0 == at or before the first row, where a step has no history to scale
        # and cancels in the normalisation; len(px) == no session on or after the
        # event date, so there is nothing left to adjust.
        if i <= 0 or i >= len(px):
            continue
        postponed += dates[i] != ev_date
        steps[i] *= step

    f = np.cumprod(steps)
    if not np.all(np.isfinite(f)) or np.any(f <= 0):
        raise ValueError(f'{stock_id}: non-finite or non-positive adjustment chain')
    diag = {
        'events_placed': int(((idx > 0) & (idx < len(px))).sum()),
        'events_unplaced': int(((idx <= 0) | (idx >= len(px))).sum()),
        'events_postponed': int(postponed),
        'events_dropped': int(_raw_event_count(str(stock_id)) - len(ev)),
    }
    return f / f[-1], diag


if __name__ == '__main__':
    # Three of the 38 the vendor does not serve: one with a factor chain, one
    # with no action in window, one whose history sits behind an unpriced
    # cancellation.
    for sid in ('2822', '1204', '1207'):
        px = pd.read_parquet(OHLCV_DIR / f'{sid}.parquet')
        px['date'] = pd.to_datetime(px['date'])
        px = px.sort_values('date').reset_index(drop=True)
        f, diag = rebuild_tr_factor(sid, px)
        print(f'{sid}: {len(px):,} sessions '
              f'{px["date"].min().date()}..{px["date"].max().date()}  '
              f'factor {f.min():.4f}..{f.max():.4f}  {diag}')
