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

Cash inside a 減資. 276 of the 627 capital reductions (44 %) are 現金減資: the
company cancels shares and refunds cash for them, so treating the endpoint as
cash-free would strip a real payment to holders out of the price-return series
as though it were a share-count artefact. ``ReasonforCapitalReduction``
separates the two reasons, and the refund follows from the reference prices
alone. Par value is NT$10 and a cash reduction refunds par, so cancelling a
fraction ``r`` of the shares pays ``C = 10r`` per share and the exchange prices
``after = (before - C)/(1 - r)``. Eliminating ``r`` between the two,

    r = (after - before) / (after - 10),    C = 10 r

after which ``pr_step = step * (1 - C/before)`` — the identical expression the
mixed 除權息 split uses. Both branches are checked against a third source,
``shares/NumberOfSharesIssued``: on 現金減資 the implied ``r`` matches the share
count actually cancelled to a median 1.8e-4, and on 彌補虧損 the cash-free
``r = 1 - before/after`` matches to a median 1.2e-4. Each formula misses by two
to three orders of magnitude on the other reason's events, and the refund
identity is not even defined on 225 of the 351 loss-offset filings, so the label
is carrying real information rather than being taken on trust.

Coverage and validity. ``capital_reduction.parquet`` starts on 2011-01-25 while
prices and 除權息 start in 2005, so a reduction filed in the first six years is
invisible to both chains and its mechanical price jump survives adjustment in
full. Nothing this account can reach repairs that window — the reference prices
were never published to it — so it is marked rather than guessed.
``detect_unpriced_actions`` reports the share cancellations no filing explains,
and ``is_valid`` is False for every row before the last of them. The same flag
carries series splices, where a ticker stops trading for years and comes back as
a different listing. ``is_valid`` says "this row connects to the rows after it",
not "this row is wrong".

Convention. Each event contributes ``step = before / after``, placed on the
event row, accumulated with ``cumprod`` and normalised so the factor is 1.0 on
the last row — ``adj_close_tr[today] == close[today]`` whenever today traded.
This is the exact
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
UNPRICED_PATH = ROOT / 'unpriced_actions.parquet'

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
# The reason a reduction was filed, and the two of its four values that refund
# cash. The endpoint labels the same reason in English and Chinese depending on
# vintage; the other two ("Making up losses" / 彌補虧損) cancel shares against
# accumulated deficit and pay nothing.
_RED_REASON = 'ReasonforCapitalReduction'
_RED_CASH_REASONS = 'Cash refund|現金減資'
# Taiwanese common stock carries a statutory par value of NT$10, and a 現金減資
# refunds par on the shares it cancels. This is what turns the exchange's two
# published reference prices into the refund per share (see module docstring).
_PAR_VALUE = 10.0
# A filing repeated under both its suspension and its resumption date sits days
# apart, never years. Two filings carrying identical reference prices further
# apart than this are separate actions that happen to have repriced alike — 28
# of the 31 such pairs in the panel — and both are real.
_TWIN_WINDOW_DAYS = 30
# A listing that stops trading for two years and returns is not the same series.
# Observed gap lengths are empty between 419 and 738 days, so every cut in that
# range marks the same 17 splices; this is a materiality choice, not a tuned one.
_BREAK_GAP_DAYS = 730


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


def _refund_per_share(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Cash a 現金減資 refunds per share, implied by its two reference prices.

    ``C = 10 r`` with ``r = (after - before)/(after - 10)`` — the module
    docstring derives it from par value and the exchange's own pricing rule, and
    checks it against the share count actually cancelled.

    Two boundaries are handled rather than assumed away. Where the exchange did
    not reprice at all (``before == after``, two filings in the panel) nothing
    was refunded and nothing needs splitting. Where the identity puts ``r``
    outside ``[0, 1)`` — including ``after == 10``, where it is undefined — the
    filing is not describing a par-value refund and the caller is told so with
    NaN rather than handed a fabricated leg.
    """
    with np.errstate(divide='ignore', invalid='ignore'):
        r = (after - before) / (after - _PAR_VALUE)
    r = np.where(before == after, 0.0, r)
    return _PAR_VALUE * np.where((r >= 0.0) & (r < 1.0), r, np.nan)


def _read_events(stock_id: str, px: pd.DataFrame) -> pd.DataFrame:
    """Both event chains for one stock as (date, before, step, pr_step, kind).

    Earliest first.

    ``step = before / after`` for both endpoints. For 除權息 the reference price
    falls, so step > 1 and history is scaled down; for 減資 it rises, so step < 1
    and history is scaled up. Same formula, opposite direction, no special case.

    ``pr_step`` is the same step with the cash leg taken back out, so that cash
    paid to holders stays in the return series as a real price drop. A stock-only
    除權 and a 彌補虧損 減資 carry no cash and pass through unchanged; a cash-only
    除息 is entirely cash, so its ``pr_step`` is 1. Two kinds fuse cash with a
    share-count change and need the cash leg named: a mixed 權息 takes it from the
    declaration, a 現金減資 from ``_refund_per_share``. Either way ``pr_step`` is
    NaN when the leg cannot be recovered, rather than silently 1.

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
                       .assign(kind='減資',
                               has_cash=c[_RED_REASON].astype(str)
                               .str.contains(_RED_CASH_REASONS, regex=True).to_numpy(),
                               has_stock=True))
    if not out:
        return pd.DataFrame(columns=['date', 'before', 'step', 'pr_step', 'kind'])

    ev = pd.concat(out, ignore_index=True)
    ev['date'] = pd.to_datetime(ev['date'])
    ev[['before', 'after']] = ev[['before', 'after']].astype(float)
    # A non-positive leg is a missing disclosure, not a price. Dropping is the
    # only safe reading -- a zero would make the chain infinite or zero -- so it
    # is dropped here and counted by the caller into `events_dropped`.
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

    # The cash leg to take back out, per share, for the two kinds whose step
    # fuses cash with a share-count change. Where it comes from differs by chain
    # — a 除權息 declares it, a 現金減資 implies it — but what is done with it
    # afterwards does not.
    fused = ev['has_cash'] & ev['has_stock']
    cash_leg = np.full(len(ev), np.nan)
    mixed = (fused & (ev['kind'] == '除權息')).to_numpy()
    if mixed.any():
        cash_leg[mixed] = ev['date'].map(_cash_dps(stock_id)).to_numpy()[mixed]
    refund = (fused & (ev['kind'] == '減資')).to_numpy()
    if refund.any():
        cash_leg[refund] = _refund_per_share(ev['before'].to_numpy(),
                                             ev['after'].to_numpy())[refund]
    ev['pr_step'] = np.where(
        fused, ev['step'] * (1.0 - cash_leg / ev['before']),
        np.where(ev['has_cash'], 1.0, ev['step']))
    return ev[['date', 'before', 'step', 'pr_step', 'kind']].reset_index(drop=True)


def _unpriced_dates(stock_id: str) -> np.ndarray:
    """Dates of this stock's share cancellations that no filing explains.

    Built by ``detect_unpriced_actions``. A missing file raises rather than
    returning nothing: skipping it quietly would leave every capital reduction
    filed before 2011-01-25 unmarked, which is the failure it exists to prevent.
    """
    if not UNPRICED_PATH.exists():
        raise FileNotFoundError(
            f'{UNPRICED_PATH} is missing — run '
            f'`python -m finmind_data.detect_unpriced_actions` first. Without it '
            f'the capital reductions filed before the event file starts '
            f'(2011-01-25) stay unmarked in is_valid.')
    u = pd.read_parquet(UNPRICED_PATH)
    u = u[(u['stock_id'].astype(str) == str(stock_id)) & ~u['explained']]
    return pd.to_datetime(u['date']).to_numpy()


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
      ``is_valid``     row connects to the rows after it — False before the last
                       series break (see below), as in ``kr_marcap.adjust``

    Any other price column adjusts the same way — ``adj_open_tr = open *
    tr_factor`` — which is what makes the factors rather than the adjusted
    closes the primary output.

    A session the stock did not trade is written by FinMind as ``close == 0``
    rather than omitted — 179,749 rows, 2.34 % of the panel, in 1,325 stocks.
    Zero is not a price, so both adjusted closes are NaN on those rows; the
    factors stay defined, because the chain is a property of the events and not
    of any one session. Callers taking returns should drop them rather than read
    a -100 % followed by an infinite one.

    ``df.attrs`` carries ``events_placed``, ``events_postponed`` (the disclosed
    date was not a session, so the step sits on the next one — see the placement
    comment below), ``events_unplaced`` (no session on or after the event date at
    all, so nothing is left to adjust), ``events_dropped`` (a non-positive
    reference leg, or a duplicate filing superseded by the copy the exchange
    priced), ``pr_unresolved`` (a fused cash-and-share event whose cash leg could
    not be recovered — the price-return columns are NaN before the last such
    event, and only there) and ``series_breaks``.

    Which one to use is a research choice, not a quality ranking.
    ``adj_close_tr`` measures what a holder earned; ``adj_close_pr`` measures the
    price alone and is what most vendors call "adjusted close", so it is the
    series to pick for symmetry with KRX ``ChangesRatio``. The cost of ``pr`` is
    that the ex-day drop survives as a large mechanical negative return on a
    seasonally clustered set of sessions, which any flow-return study has to
    handle rather than ignore.

    ``is_ex_date`` rows keep a real residual after total-return adjustment
    (+29 bp on the 2020-2024 panel) because prices fall short of the full
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
            # A fused cash-and-share event whose cash leg could not be recovered
            # cannot be split into its two parts. Everything earlier than it is
            # then not a price-return series; everything from it onward still
            # is, so only the history behind it is marked.
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
    # A no-trade session is written as close == 0, not omitted. Zero is not a
    # price, so it cannot be adjusted into one -- carrying it through would put a
    # -100 % return and an infinite one into an otherwise clean series.
    close = out['close'].to_numpy(dtype=float)
    close = np.where(close > 0.0, close, np.nan)
    out['tr_factor'] = tr / tr[-1]
    out['adj_close_tr'] = close * out['tr_factor'].to_numpy()
    out['pr_factor'] = pr
    out['adj_close_pr'] = close * pr
    out['is_ex_date'] = is_ex
    out['is_cap_red'] = is_red

    # A break is a point the series does not carry across: a share cancellation
    # no filing priced, so its step is missing from the chain rather than wrong
    # in it; or a hole in the calendar long enough that what came back is not
    # what left. Everything strictly before the last break belongs to a series
    # this one does not continue, which is what kr_marcap.adjust marks with the
    # same flag for pre-relisting Korean history.
    dates = out['date'].to_numpy()
    brk = np.zeros(len(out), dtype=bool)
    if len(out) > 1:
        brk[1:] = np.diff(dates) / np.timedelta64(1, 'D') >= _BREAK_GAP_DAYS
    for bd in _unpriced_dates(str(stock_id)):
        i = int(np.searchsorted(dates, bd, 'left'))
        if 0 < i < len(out):
            brk[i] = True
    valid = np.ones(len(out), dtype=bool)
    seen = np.nonzero(brk)[0]
    if len(seen):
        valid[:seen[-1]] = False
    out['is_valid'] = valid

    out.attrs['events_placed'] = int(((idx > 0) & (idx < len(out))).sum())
    out.attrs['events_unplaced'] = int(((idx <= 0) | (idx >= len(out))).sum())
    out.attrs['events_postponed'] = int(postponed)
    out.attrs['events_dropped'] = int(_raw_event_count(str(stock_id)) - len(ev))
    out.attrs['pr_unresolved'] = unresolved
    out.attrs['series_breaks'] = int(brk.sum())
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
              f'dropped {df.attrs["events_dropped"]} '
              f'breaks {df.attrs["series_breaks"]}')
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
