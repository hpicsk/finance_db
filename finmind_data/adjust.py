"""Taiwan back-adjusted, dividend-inclusive price series from exchange reference prices.

FinMind's ``TaiwanStockPrice.close`` is **raw** — verified against the exchange's
own pre-event ``before_price`` at 99.87 % on the 7,441 events inside 2020-2024
(99.81 % on 22,105 events since 2005), at both 1e-6 and the exchange's own
2-decimal precision. Nothing in ``ohlcv/`` is adjusted for anything, so a
close-to-close return spanning a 除權息 or 減資 session is contaminated by the
full reference-price step, not merely by a cash dividend.

The adjustment is therefore built here rather than downloaded:
``TaiwanStockPriceAdj`` is gated above this account's ``register`` tier, and the
per-event reference prices are both free and strictly better than a pre-built
series, because they are the exchange's own numbers.

**Both conventions are exposed**, so this side matches ``kr_marcap``: a
price-return ``adj_close_pr`` (structural actions only, the cash drop left in as
a real return, the usual vendor "adjusted close") and a total-return
``adj_close_tr`` (cash removed too).

Splitting the two is not obvious, because TWSE/TPEx publish **one fused
reference price** per 除權息 event covering cash dividends, 無償配股 and 現增
together, and that number does not decompose by recomputing its components:
``dividend/`` is declaration-level and its declared 配股率 omits 員工配股 and
董監酬勞 dilution, so the TWSE formula reproduces the published ``after_price``
for only 77.8 % of mixed events. The split used here needs no 配股率 at all.
``stock_or_cache_dividend`` already labels each event 息 (cash), 權 (stock) or
權息 (both), which settles 79.8 % of events outright — a cash-only event has
``pr_step = 1``, a stock-only event has ``pr_step = step``. Only the 20.2 % that
are mixed need arithmetic, and there

    pr_step = step * (1 - D / before)

strips the cash leg out of the exact published ratio using the declared cash
dividend ``D`` alone. ``D`` is verified independently on the 15,449 cash-only
events, where 配股率 is zero by construction and the identity reduces to
``after == before - D`` — it holds for 99.99 % of them. See
ADJUSTED_PRICE_VERIFICATION.md.

Chain composition. 除權息 (``div_result/``) and 減資 (``capital_reduction.parquet``)
never share a ``(stock_id, date)`` pair across the whole 2005-2024 history — 0
overlaps on 22,370 and 627 events — so the two factor chains multiply without
double counting. ``_assert_disjoint`` re-checks this per stock rather than
trusting the global result.

Convention. Each event contributes ``step = before / after``, placed on the
event row, accumulated with ``cumprod`` and normalised so the factor is 1.0 on
the last row — ``adj_close_tr[today] == close[today]``. This is the exact
reference-price ratio, matching kr_marcap's ``1 + dps/close_ex`` in taking the
step at the ex price rather than the cum one. Both are back-adjustment factors,
which compose multiplicatively, and only the ex price telescopes correctly there.
Taiwan's step is large — median 4.6 % of the cum price, q95 12.6 %, because it
carries share-count changes as well as cash — so a cum-price form would be
understated by ``x**2``, a median 22.6 bp per event compounding to a median 3.7 %
and a q99 30.5 % over a stock's full history.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OHLCV_DIR = ROOT / 'ohlcv'
DIV_RESULT_DIR = ROOT / 'div_result'
DIVIDEND_DIR = ROOT / 'dividend'
CAP_RED_PATH = ROOT / 'capital_reduction.parquet'

# Cash legs of a distribution, TWD per share. Their sum is the `D` that the
# price-return split subtracts; validated at 99.99 % on cash-only events.
_CASH_LEGS = ['CashEarningsDistribution', 'CashStatutorySurplus']
# The declaration discloses its own cash ex-date, which agrees with div_result's
# event date on 99.96 % of comparable rows (validate_adjust check [3]).
_DECLARED_EX = 'CashExDividendTradingDate'
# The exchange publishes before_price to two decimals, so agreement with a close
# is agreement at the published precision. Not a fitted cut: the one filing this
# rejects misses by 3.95, and every tolerance from 1e-6 to 0.5 rejects the same
# one filing and no other.
_TOL_BEFORE_PRICE = 1e-2

# 除權息 columns: the exchange's official pre- and post-event reference prices.
_DIV_BEFORE, _DIV_AFTER = 'before_price', 'after_price'
# 減資 columns: same pair under the capital-reduction endpoint's own names.
# ExrightReferencePrice is -1.0 / 0.0 across the file and is not a price.
_RED_BEFORE, _RED_AFTER = 'ClosingPriceonTheLastTradingDay', 'PostReductionReferencePrice'


def _cash_dps(stock_id: str) -> pd.Series:
    """Declared cash dividend per share, keyed by its own disclosed ex-date.

    Only the mixed 權息 events consult this; a cash-only event needs no ``D``
    (its price-return step is 1) and neither does a stock-only one.
    """
    p = DIVIDEND_DIR / f'{stock_id}.parquet'
    if not p.exists():
        return pd.Series(dtype=float)
    d = pd.read_parquet(p)
    if not len(d) or _DECLARED_EX not in d.columns:
        return pd.Series(dtype=float)
    d = d[d[_DECLARED_EX].astype(str).str.len() == 10]
    if not len(d):
        return pd.Series(dtype=float)
    # A stock may declare several distributions onto one ex-date; the price
    # steps off their sum, so summing here is the matching aggregation.
    return (d.assign(D=d[_CASH_LEGS].sum(axis=1))
             .groupby(pd.to_datetime(d[_DECLARED_EX]))['D'].sum())


def _read_events(stock_id: str, px: pd.DataFrame) -> pd.DataFrame:
    """Both event chains for one stock as (date, before, step, pr_step, kind).

    Earliest first.

    ``step = before / after`` for both endpoints. For 除權息 the reference price
    falls, so step > 1 and history is scaled down; for 減資 it rises, so step < 1
    and history is scaled up. Same formula, opposite direction, no special case.

    ``pr_step`` is the same step with the cash leg taken back out, so that a cash
    dividend stays in the return series as a real price drop. 減資 and stock-only
    除權 carry no cash and pass through unchanged; a cash-only 除息 is entirely
    cash, so its ``pr_step`` is 1; only a mixed 權息 needs ``D``, and its
    ``pr_step`` is NaN when the declaration is missing rather than silently 1.

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
            k = d['stock_or_cache_dividend'].astype(str)
            # The 除 prefix is a vintage marker, not a kind; 息/權 are the kind.
            out.append(d[['date', _DIV_BEFORE, _DIV_AFTER]]
                       .rename(columns={_DIV_BEFORE: 'before', _DIV_AFTER: 'after'})
                       .assign(kind='除權息',
                               has_cash=k.str.contains('息').to_numpy(),
                               has_stock=k.str.contains('權').to_numpy()))
    if CAP_RED_PATH.exists():
        c = pd.read_parquet(CAP_RED_PATH)
        c = c[c['stock_id'].astype(str) == str(stock_id)]
        if len(c):
            out.append(c[['date', _RED_BEFORE, _RED_AFTER]]
                       .rename(columns={_RED_BEFORE: 'before', _RED_AFTER: 'after'})
                       .assign(kind='減資', has_cash=False, has_stock=True))
    if not out:
        return pd.DataFrame(columns=['date', 'before', 'step', 'pr_step', 'kind'])

    ev = pd.concat(out, ignore_index=True)
    ev['date'] = pd.to_datetime(ev['date'])
    ev[['before', 'after']] = ev[['before', 'after']].astype(float)
    # A non-positive leg is a missing disclosure, not a price. Dropping is the
    # only safe reading -- a zero would make the chain infinite or zero -- so it
    # is dropped here and counted by the caller into `events_dropped`.
    ev = ev[(ev['before'] > 0) & (ev['after'] > 0)].copy()

    # The same action is occasionally filed twice, once under a date the stock
    # did not trade. 2327 and 3018 each carry their 減資 under both the date
    # trading was suspended and the date it resumed, with one pair of reference
    # prices between them. Exact-date placement discarded the stray copy for
    # free; placing on the next session instead would apply the step twice. So
    # where a filing has an identical twin that fell on a session, keep the copy
    # the exchange actually priced. A filing whose only copy missed a session is
    # untouched — that is the typhoon case, and it is the one to postpone.
    if len(ev) > 1:
        traded = ev['date'].isin(set(px['date']))
        twin_traded = traded.groupby(
            [ev['kind'], ev['before'], ev['after']]).transform('any')
        ev = ev[traded | ~twin_traded]

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

    mixed = ev['has_cash'] & ev['has_stock']
    d_ps = ev['date'].map(_cash_dps(stock_id)) if mixed.any() else np.nan
    ev['pr_step'] = np.where(
        mixed, ev['step'] * (1.0 - d_ps / ev['before']),
        np.where(ev['has_cash'], 1.0, ev['step']))
    return ev[['date', 'before', 'step', 'pr_step', 'kind']].reset_index(drop=True)


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


def load_adjusted(stock_id: str,
                  ohlcv_dir: Path = OHLCV_DIR) -> pd.DataFrame:
    """One stock's raw OHLCV plus both adjusted closes.

    Added columns:
      ``tr_factor``    total-return back-adjustment factor, 1.0 on the last row
      ``adj_close_tr`` ``close * tr_factor`` — cash dividends removed as well
      ``pr_factor``    price-return factor, structural actions only
      ``adj_close_pr`` ``close * pr_factor`` — the cash drop left in as a return
      ``is_ex_date``   row carries a 除權息 step (the Korean ``is_ex_date`` analogue)
      ``is_cap_red``   row carries a 減資 step

    Any other price column adjusts the same way — ``adj_open_tr = open *
    tr_factor`` — which is what makes the factors rather than the adjusted
    closes the primary output.

    ``df.attrs`` carries ``events_placed``, ``events_postponed`` (the disclosed
    date was not a session, so the step sits on the next one — see the placement
    comment below), ``events_unplaced`` (no session on or after the event date at
    all, so nothing is left to adjust), ``events_dropped`` (a non-positive
    reference leg, or a duplicate filing superseded by the copy the exchange
    priced) and ``pr_unresolved`` (mixed event with no declared cash leg — the
    price-return columns are NaN before the last such event, and only there).

    Which one to use is a research choice, not a quality ranking.
    ``adj_close_tr`` measures what a holder earned; ``adj_close_pr`` measures the
    price alone and is what most vendors call "adjusted close", so it is the
    series to pick for symmetry with KRX ``ChangesRatio``. The cost of ``pr`` is
    that the ex-day drop survives as a large mechanical negative return on a
    seasonally clustered set of sessions, which any flow-return study has to
    handle rather than ignore.

    ``is_ex_date`` rows keep a real residual after total-return adjustment
    (+31 bp on the 2020-2024 panel) because prices fall short of the full
    distribution. That is the ex-day tax/clientele effect, not a defect — daily-
    horizon work should flag or drop those sessions explicitly rather than
    expect zero.
    """
    p = Path(ohlcv_dir) / f'{stock_id}.parquet'
    if not p.exists():
        raise FileNotFoundError(f'no price series for {stock_id} at {p}')
    out = pd.read_parquet(p)
    out['date'] = pd.to_datetime(out['date'])
    out = out.sort_values('date').reset_index(drop=True)

    ev = _read_events(str(stock_id), out[['date', 'close']])
    _assert_disjoint(ev, str(stock_id))

    steps = np.ones(len(out))
    pr_steps = np.ones(len(out))
    is_ex = np.zeros(len(out), dtype=bool)
    is_red = np.zeros(len(out), dtype=bool)
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
    idx = (np.searchsorted(out['date'].to_numpy(), ev['date'].to_numpy(), 'left')
           if len(ev) else np.array([], int))
    unresolved, pr_cut, postponed = 0, 0, 0
    for i, ev_date, step, pr_step, kind in zip(
            idx, ev['date'].to_numpy(), ev['step'].to_numpy(),
            ev['pr_step'].to_numpy(), ev['kind'].to_numpy()):
        # 0 == at or before the first row, where a step has no history to scale
        # and cancels in the normalisation; len(out) == no session on or after
        # the event date, so there is nothing left to adjust.
        if i <= 0 or i >= len(out):
            continue
        postponed += out['date'].to_numpy()[i] != ev_date
        steps[i] *= step
        if np.isfinite(pr_step):
            pr_steps[i] *= pr_step
        else:
            # A mixed event with no declared cash leg cannot be split. Everything
            # earlier than it is then not a price-return series; everything from
            # it onward still is, so only the history behind it is marked.
            unresolved += 1
            pr_cut = max(pr_cut, i)
        if kind == '除權息':
            is_ex[i] = True
        else:
            is_red[i] = True

    tr = np.cumprod(steps)
    if not np.all(np.isfinite(tr)) or np.any(tr <= 0):
        raise ValueError(f'{stock_id}: non-finite or non-positive adjustment chain')
    pr = np.cumprod(pr_steps)
    if not np.all(np.isfinite(pr)) or np.any(pr <= 0):
        raise ValueError(f'{stock_id}: non-finite or non-positive price-return chain')
    pr = pr / pr[-1]
    pr[:pr_cut] = np.nan
    close = out['close'].to_numpy(dtype=float)
    out['tr_factor'] = tr / tr[-1]
    out['adj_close_tr'] = close * out['tr_factor'].to_numpy()
    out['pr_factor'] = pr
    out['adj_close_pr'] = close * pr
    out['is_ex_date'] = is_ex
    out['is_cap_red'] = is_red
    out.attrs['events_placed'] = int(((idx > 0) & (idx < len(out))).sum())
    out.attrs['events_unplaced'] = int(((idx <= 0) | (idx >= len(out))).sum())
    out.attrs['events_postponed'] = int(postponed)
    out.attrs['events_dropped'] = int(_raw_event_count(str(stock_id)) - len(ev))
    out.attrs['pr_unresolved'] = unresolved
    return out


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


def available_stocks(ohlcv_dir: Path = OHLCV_DIR) -> list[str]:
    """Stocks with at least one price row. The download writes a zero-row file
    for every stock the endpoint returned nothing for, so the directory listing
    alone overstates coverage."""
    out = []
    for p in sorted(Path(ohlcv_dir).glob('*.parquet')):
        if len(pd.read_parquet(p)):
            out.append(p.stem)
    return out


if __name__ == '__main__':
    for sid in ('2330', '2412', '1101'):
        df = load_adjusted(sid)
        ex = df[df['is_ex_date'] | df['is_cap_red']]
        print(f'\n{sid}: {len(df):,} sessions '
              f'{df["date"].min().date()}..{df["date"].max().date()} | '
              f'placed {df.attrs["events_placed"]} '
              f'postponed {df.attrs["events_postponed"]} '
              f'unplaced {df.attrs["events_unplaced"]} '
              f'dropped {df.attrs["events_dropped"]}')
        print(f'  tr_factor {df["tr_factor"].min():.4f}..{df["tr_factor"].max():.4f}'
              f' | pr_factor {df["pr_factor"].min():.4f}..{df["pr_factor"].max():.4f}'
              f' | 除權息 {int(df["is_ex_date"].sum())} | 減資 {int(df["is_cap_red"].sum())}'
              f' | pr_unresolved {df.attrs["pr_unresolved"]}')
        print(f'  anchor |adj_close_tr[-1] - close[-1]| = '
              f'{abs(df["adj_close_tr"].iloc[-1] - df["close"].iloc[-1]):.3e}')
        if len(ex):
            last = ex.iloc[-1]
            print(f'  last event {last["date"].date()}  close {last["close"]:.2f}  '
                  f'adj_close_tr {last["adj_close_tr"]:.2f}  '
                  f'adj_close_pr {last["adj_close_pr"]:.2f}')
