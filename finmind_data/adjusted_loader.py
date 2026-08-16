"""Taiwan back-adjusted, dividend-inclusive prices — FinMind's series, with the
holes filled, the defects patched, and both marked in the frame.

``TaiwanStockPriceAdj`` (→ ``price_adj/``) is the 還原股價 series, and it is
**total return**: cash dividends come out along with 無償配股, 現增 and 減資.
That is measured, not assumed — on 2330, 2317 and 1101 the series tracks a
cash-removed reconstruction to a median 1e-5..2.5e-4 of relative error and
departs from a cash-retained one by 25-36 %. There is no price-return variant of
the endpoint at any tier, so a study that needs the price alone has no source
here.

Five things happen on top of the vendor series, all of them marked in a column
rather than done silently.

**The survivorship hole is filled.** ``price_adj/`` serves nothing at all for 38
of the 173 in-window universe delistings — every one a 2005-2007 delisting,
10,981 traded sessions, and 38 of the 42 names the universe carries precisely as
its survivorship overlay, dropped from FinMind's live registry and from this
endpoint on the same list. ``adjust.rebuild_tr_factor`` rebuilds those 38 from
the exchange's own reference prices, which is why they are recoverable at all:
the reference prices are published per event and do not depend on the registry.
Validated on the 134 covered in-window delistings — the same era, the same
situation, the vendor present to compare against — where the rebuild reproduces
99.93 % of 268,503 daily adjusted returns to 1e-6 and 99.997 % to 1e-3.

**Seven vendor events are replaced with the exchange's own step.** Six are
現金增資 subscribed above the market, where the reference price *rises* and the
vendor scaled the history the other way, up to 4.11 % on one session and
carried through the whole history behind it; one is a filing the vendor added a
malformed duplicate row into. ``vendor_event_audit`` grades every event and
finds both by shape, not by stock id.

**Both edges of the vendor series are carried outward.** It begins one session
after the raw series on 903 stocks and ends before it on 7, and a factor moves
only on an ex date — so where no filing sits in the gap, the adjacent covered
session's factor *is* the missing one, and carrying it is exact rather than an
interpolation or a splice. That recovers 902 **first returns** — the price was
never the loss; the session-1-to-session-2 return was — and prices the 3,089
sessions seven delisted names went on being quoted for. The condition is tested
per row against every filed 除權息 and 減資 plus the cancellations no filing
explains, and it refuses the 903rd: 4141's first print sits 376 days before the
vendor's first session, with a cancellation on that session. Those rows are
``vendor_carried``.

**The sessions the raw endpoint dropped are put back.** ``ohlcv/`` has no row
at all for 600 sessions ``price_adj/`` carries, in 159 stocks, and every one of
them is a 補行交易日 — a Saturday worked to make up a holiday. The cost is not
the missing row but the return after it, which spans two sessions instead of one:
600 absent rows are 600 overstated returns, clustered on 22 holiday-adjacent
dates rather than scattered. ``price_adj/`` carries the whole row — ``open``,
``max`` and ``min`` on the close's own factor, the volume columns unadjusted — so
the raw row is the vendor's divided by the factor at an adjacent session, a
vendor factor over a vendor factor, and the declared-vs-published cent below
cancels instead of propagating. 419 come back as traded sessions and the 181 the
vendor reports no volume on as the zero rows ``ohlcv/`` writes for a session with
none. Those rows are ``raw_covered`` False.

**Two conventions therefore live in one panel**, and ``adj_method`` says which.
FinMind subtracts the *declared* distribution from the prior close; the rebuild
reads the exchange's *published reference price*. The two name the same number
to 1e-6 on 83.3 % of 22,336 graded events and to 1e-3 on 99.5 %, and where they
differ it is by a whole cent in the per-share distribution — bounded, not
cumulative, and confined to the ex-date session. ``vendor_event_audit.parquet``
is the fixed record of that, so a step found at a vendor/rebuilt boundary is
answered by a file rather than re-derived.

Nothing else on the vendor side is re-derived. What this module adds beyond the
above is the three places where the adjusted panel says something a return
calculation should not believe, all measured against ``ohlcv/`` and
``unpriced_actions.parquet``:

**A no-trade session carries a price.** FinMind writes a session the stock did
not trade as ``close == 0`` in ``ohlcv/`` — 179,749 rows there in 1,325 stocks,
and 179,930 in this panel once the make-up sessions above are put back, 2.34 %
of it. The adjusted series fills 179,622 of the ones ``ohlcv/`` holds with the
last traded price instead (8934 has 2,441 of them, every one carrying a number),
so the zero that identifies them is gone and a caller filtering on
``adj_close_tr > 0`` keeps all of them. They are NaN here, the raw ``close`` is
kept alongside so the test stays available, and they are ``is_valid`` False
under ``invalid_reason = 'no_trade'``: a price nobody could transact at is not a
position, and a backtest that filtered on the flag alone would otherwise assume
a fill on a day the stock did not trade.

**A share cancellation no filing priced goes through unadjusted.**
``capital_reduction.parquet`` starts on 2011-01-25 while prices start in 2005,
and the vendor is subject to the same publication limit: 2357's 85 % reduction
on 2010-06-24 has a vendor factor step of 1.0000, which leaves the raw 53.2 →
240.5 jump in the adjusted series as a +351 % return. ``detect_unpriced_actions``
finds those cancellations in the share count, and ``is_valid`` is False for every
row before the last of them. The same flag carries series splices, where a ticker
stops trading for years and comes back as a different listing, so
``invalid_reason`` names which of the four disqualified it.

**A price is not a permission.** The 3,089 carried sessions are 興櫃 quotes for
names that left the exchange — 1107 is the largest at 1,151: the vendor ends
2007-10-19 against a 2007-10-20 delisting and ``ohlcv/`` runs to 2012-06-06.
興櫃 is a negotiated market: ``open`` is the previous session's average rather
than a trade, a quote depends on a recommending broker standing behind it, and
median volume across the seven runs at 3.6-48 % of each name's own listed-era
median. A backtest holding those rows would be trading a book it could not have
filled, which is why they carry ``is_valid`` False under
``invalid_reason = 'post_delisting_emerging'``. What they *are* is the terminal
value: where a delisted name converges over the months after it leaves is a
market observation, and the last exchange close is not one. That is the use the
fill is for, and the flag is what keeps it to that use.

``is_valid`` is therefore "this row is a position a study could have held", and
it fails three ways. Two are the ends of the series: a row before the last break
belongs to a history this one does not continue, and a row after the last
exchange session belongs to a market it could not have traded in. The third is
one session anywhere between them — the stock did not trade, so there was no
price to transact at whatever level the panel carries. ``invalid_reason`` is
what separates the three, and none of them is "this price is wrong".

What is left uncovered stays NaN rather than being dropped, so the gap stays
visible beside the raw price that does cover it — the no-trade sessions, and the
one row the carry guard refuses. ``adj_source`` carries the distinction row by
row, through ``concat``, ``merge`` and ``groupby``, which is what ``df.attrs``
does not do.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import adjust
from .vendor_event_audit import defective_events

ROOT = Path(__file__).resolve().parent
OHLCV_DIR = ROOT / 'ohlcv'
PRICE_ADJ_DIR = ROOT / 'price_adj'
UNPRICED_PATH = ROOT / 'unpriced_actions.parquet'

# A listing that stops trading for two years and returns is not the same series.
# Observed gap lengths are empty between 419 and 738 days, so every cut in that
# range marks the same 17 splices; this is a materiality choice, not a tuned one.
_BREAK_GAP_DAYS = 730

# ``ohlcv/`` quotes every price to the cent, so a session reconstructed from the
# vendor's adjusted row is rounded onto that grid rather than left carrying the
# vendor's own rounding. It is not a tolerance: on the 418 make-up sessions with
# an anchor on either side the two reconstructions differ by at most 3.4e-6 and
# round to the same cent in every case.
_PRICE_DECIMALS = 2

# Which convention produced the ex-date steps in a row's factor chain. The
# vendor subtracts the declared distribution; the rebuild reads the exchange's
# published reference price. See the module docstring on how far apart they are.
_METHOD = {
    'vendor': 'declared_dividend',
    'vendor_patched': 'declared_dividend',
    'vendor_carried': 'declared_dividend',
    'rebuilt_factored': 'exchange_reference',
    'rebuilt_noevent': 'none',
    '': '',
}


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


def load_adjusted(stock_id: str,
                  ohlcv_dir: Path = OHLCV_DIR,
                  price_adj_dir: Path = PRICE_ADJ_DIR) -> pd.DataFrame:
    """One stock's raw OHLCV plus its total-return adjusted close.

    Added columns:
      ``tr_factor``      total-return back-adjustment factor, 1.0 on the last row
      ``adj_close_tr``   ``close * tr_factor`` — cash dividends removed as well
      ``adj_source``     where this row's factor came from: ``vendor``,
                         ``vendor_patched``, ``vendor_carried``,
                         ``rebuilt_factored``, ``rebuilt_noevent``, or ``''``
                         where nothing covers it
      ``adj_method``     which convention produced its ex-date steps:
                         ``declared_dividend``, ``exchange_reference``, ``none``
      ``adj_covered``    the *vendor* served this date — False across a rebuilt
                         stock and on a carried edge, so the survivorship hole
                         stays countable after it is filled
      ``raw_covered``    ``ohlcv/`` served this date — False on the 600 make-up
                         sessions reconstructed from the vendor's row, whose
                         fields are therefore derived rather than read
      ``is_valid``       this row is a position a study could have held
      ``invalid_reason`` why not: ``unpriced_cancellation`` or ``series_break``
                         behind the last break, ``post_delisting_emerging``
                         past the last exchange session, ``no_trade`` on a
                         session inside both that the stock did not trade,
                         ``''`` where valid

    Any other price column adjusts the same way — ``adj_open_tr = open *
    tr_factor`` — which is what makes the factor rather than the adjusted close
    the primary output.

    The factor is re-anchored to 1.0 on this slice's last priced session rather
    than left on the vendor's anchor, which is the latest session in FinMind's
    own database and therefore moves every time the download is repeated. Both
    anchors give identical returns; only this one gives identical *numbers* on a
    re-download.

    ``adj_close_tr`` is NaN on a session the stock did not trade and on any
    session nothing covers; ``adj_source`` separates the two. ``df.attrs``
    carries ``adj_coverage``, ``series_breaks``, ``vendor_only_sessions``,
    ``sessions_recovered``, ``events_patched`` and ``sessions_carried`` for a
    single stock, and is **not** the safe route for a panel — read provenance off
    ``adj_source`` and ``raw_covered`` there.
    """
    p = Path(ohlcv_dir) / f'{stock_id}.parquet'
    if not p.exists():
        raise FileNotFoundError(f'no price series for {stock_id} at {p}')
    out = pd.read_parquet(p)
    # A stock the price endpoint returned nothing for is written as a zero-row
    # file with no schema — 13 of them, all listed after the 2024-12-31 window.
    if not len(out):
        raise ValueError(f'{stock_id}: {p} holds no rows, so there is no series '
                         f'to adjust (listed outside the download window?)')
    out['date'] = pd.to_datetime(out['date'])
    out = out.sort_values('date').reset_index(drop=True)

    a = Path(price_adj_dir) / f'{stock_id}.parquet'
    if not a.exists():
        raise FileNotFoundError(
            f'no adjusted series for {stock_id} at {a} — run '
            f'`python download.py --datasets price_adj --stocks {stock_id}`')
    # Whether ``ohlcv/`` served this date. False only on the make-up sessions
    # recovered below, where it is what says the row's fields were reconstructed
    # from the vendor's rather than read.
    out['raw_covered'] = True

    adj = pd.read_parquet(a)
    if len(adj):
        adj['date'] = pd.to_datetime(adj['date'])
        out, vendor_only, recovered = _recover_make_up_sessions(
            str(stock_id), out, adj)
        adj = adj[['date', 'close']].rename(columns={'close': 'adj_close_tr'})
        out = out.merge(adj, on='date', how='left')
    else:
        vendor_only = recovered = 0
        out['adj_close_tr'] = np.nan

    # Whether the *vendor* served this date, captured before the no-trade masking
    # below folds "did not trade" into the same NaN and before the rebuild fills
    # a stock it serves nothing for. This is a column and not frame metadata on
    # purpose: ``DataFrame.attrs`` survives ``pd.concat`` only when every frame
    # agrees, so a panel of uniformly covered stocks keeps a figure nobody needs
    # and a panel mixing covered with uncovered stocks silently drops it — the
    # field would vanish in exactly the case it exists to flag, and ``merge`` and
    # ``groupby`` drop it always.
    out['adj_covered'] = out['adj_close_tr'].notna()

    # A no-trade session is written as close == 0, not omitted, and the vendor
    # fills it with the last traded price. Zero is not a price and neither is a
    # carried one, so the row holds no adjusted close either way.
    close = out['close'].to_numpy(dtype=float)
    traded = close > 0.0
    out.loc[~traded, 'adj_close_tr'] = np.nan
    factor = out['adj_close_tr'].to_numpy(dtype=float) / np.where(traded, close, np.nan)

    covered = np.isfinite(factor)
    n_patched = 0
    carried = np.zeros(len(out), dtype=bool)
    if covered.any():
        factor, n_patched = _patch(str(stock_id), out['date'].to_numpy(),
                                   covered, factor)
        source = np.where(covered, 'vendor', '').astype(object)
        if n_patched:
            source = _mark_patched(str(stock_id), out['date'].to_numpy(),
                                   covered, source)
        # After the patch, so a first session carried back across a patched
        # event inherits the corrected factor rather than the vendor's.
        factor, carried = _carry_edges(str(stock_id), out['date'].to_numpy(),
                                       traded, factor)
        source[carried] = 'vendor_carried'
    else:
        # The vendor serves this stock nothing at all — the survivorship hole.
        # Rebuild it from the exchange's reference prices rather than return a
        # column of NaN that a panel build would drop, reinstating the bias.
        factor, diag = adjust.rebuild_tr_factor(str(stock_id), out[['date', 'close']])
        factor = np.where(traded, factor, np.nan)
        kind = 'rebuilt_factored' if diag['events_placed'] else 'rebuilt_noevent'
        source = np.where(traded, kind, '').astype(object)

    have = np.isfinite(factor)
    if have.any():
        factor = factor / factor[np.nonzero(have)[0][-1]]
    out['tr_factor'] = factor
    out['adj_close_tr'] = np.where(traded, close, np.nan) * factor
    out['adj_source'] = source
    out['adj_method'] = pd.Series(source).map(_METHOD).to_numpy()

    # A break is a point the series does not carry across: a share cancellation
    # no filing priced, so its step is missing from the vendor chain rather than
    # wrong in it; or a hole in the calendar long enough that what came back is
    # not what left. Everything strictly before the last break belongs to a
    # series this one does not continue.
    dates = out['date'].to_numpy()
    reason = np.full(len(out), '', dtype=object)
    if len(out) > 1:
        gap = np.zeros(len(out), dtype=bool)
        gap[1:] = np.diff(dates) / np.timedelta64(1, 'D') >= _BREAK_GAP_DAYS
        reason[gap] = 'series_break'
    for bd in _unpriced_dates(str(stock_id)):
        i = int(np.searchsorted(dates, bd, 'left'))
        if 0 < i < len(out):
            reason[i] = 'unpriced_cancellation'
    valid = np.ones(len(out), dtype=bool)
    seen = np.nonzero(reason != '')[0]
    out['invalid_reason'] = ''
    if len(seen):
        valid[:seen[-1]] = False
        # The break that determines validity is the last one, so its reason is
        # what every row it cut off carries.
        out.loc[:seen[-1] - 1, 'invalid_reason'] = reason[seen[-1]]

    # The other end. A vendor series that stops while ``ohlcv/`` keeps printing
    # stopped at a delisting: the name left the exchange and the quotes that
    # follow are 興櫃, which is a negotiated market — ``open`` is the previous
    # session's average price rather than a trade, median volume runs at 3.6-48 %
    # of the prior year's, and a quote depends on a recommending broker standing
    # behind it. Carrying the factor over those sessions makes the level
    # continuous, which is what the price is wanted for; it does not make the
    # sessions tradable, and this reason is what keeps a backtest from assuming
    # they are. What they *are* good for is the terminal value — where a
    # delisted name converges over the following months is a market observation,
    # and the last exchange close is not one.
    vendor_served = out['adj_covered'].to_numpy()
    if vendor_served.any():
        after = np.arange(len(out)) > np.nonzero(vendor_served)[0][-1]
        if after.any():
            valid[after] = False
            out.loc[after, 'invalid_reason'] = 'post_delisting_emerging'

    # And the middle. The two reasons above describe a *segment* — everything
    # behind the last break, everything past the last exchange session — while a
    # no-trade session is one row inside the segment they leave standing, and it
    # is not a position either: there was nothing to buy at any price. The
    # adjusted close is already NaN on these rows, so the documented two-column
    # filter dropped them; what this reason adds is that ``is_valid`` alone now
    # does, which is what the column claims to mean. It fills only rows the
    # segment reasons did not claim, because a row behind a break would not have
    # been holdable had it traded either.
    no_trade = ~traded & (out['invalid_reason'].to_numpy() == '')
    valid[no_trade] = False
    out.loc[no_trade, 'invalid_reason'] = 'no_trade'
    out['is_valid'] = valid

    # Coverage is over traded sessions: the vendor also serves the no-trade rows
    # it filled with a carried price, and counting those would put the ratio
    # above 1 on a stock like 8934.
    out.attrs['adj_coverage'] = float(
        (out['adj_covered'].to_numpy() & traded).sum() / max(int(traded.sum()), 1))
    out.attrs['series_breaks'] = int(len(seen))
    out.attrs['vendor_only_sessions'] = vendor_only
    out.attrs['sessions_recovered'] = recovered
    out.attrs['events_patched'] = n_patched
    out.attrs['sessions_carried'] = int(carried.sum())
    return out


def _recover_make_up_sessions(stock_id: str, out: pd.DataFrame,
                              adj: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Put back the sessions ``price_adj/`` carries and ``ohlcv/`` has no row for.

    All 600 of them across the panel are 補行交易日 — Saturdays worked to make up
    a holiday — and the damage is not the missing row. A gap in the calendar
    makes the *next* session's return span two sessions instead of one, so 600
    absent rows are 600 overstated returns, every one of them on a
    holiday-adjacent Saturday rather than anywhere at random.

    ``price_adj/`` carries the whole row, not just the close: ``open``, ``max``
    and ``min`` sit on the same factor as the close (worst relative departure
    4.1e-5 over 7,674,204 shared ticker-days, which is the vendor's rounding),
    and the three volume columns come across unadjusted. So the raw row is the
    vendor's row divided by the factor at an adjacent session —

        ``close(sat) = adj_close(sat) * close(anchor) / adj_close(anchor)``

    — which is a vendor factor over a vendor factor, so the declared-vs-published
    cent that separates the two conventions cancels rather than propagating.
    Exact whenever no filing sits between the two, which is checked per row
    against every 除權息 and 減資 and the cancellations no filing explains, the
    same guard the edge carry uses. Unlike that one it does not fire on this
    vintage: no make-up session in the panel has an event in its interval.

    The check on the arithmetic is that 418 of the 419 traded sessions have a
    usable anchor on *both* sides, and the two reconstructions agree to 6.9e-7 —
    two different sessions, opposite directions, one answer. The nearer earlier
    anchor is the one used, and 4167's 2012-12-22 is the single session with
    nothing usable behind it.

    A session the vendor reports no volume on is written the way ``ohlcv/``
    writes one, as a zero row: across 151,304 zero-volume rows in that tree not
    one carries a close, so a zero is what the raw file would have held. Those
    181 rows land on ``invalid_reason = 'no_trade'`` with everything else that
    did not trade, and the return across them stays the one-session return it
    already was.

    Returns the frame with the rows inserted, how many sessions the vendor had
    and the raw file did not, and how many of them came back.
    """
    missing = adj[~adj['date'].isin(out['date'])]
    if not len(missing):
        return out, 0, 0

    dates = out['date'].to_numpy()
    close = out['close'].to_numpy(dtype=float)
    priced = dict(zip(adj['date'].to_numpy(), adj['close'].to_numpy(dtype=float)))
    # An anchor is a session both files carry and the stock traded on, so the
    # vendor's factor there is readable as adj_close / close.
    seat = np.nonzero([c > 0 and priced.get(d, 0.0) > 0
                       for d, c in zip(dates, close)])[0]
    blocking = np.concatenate([adjust.filed_event_dates(stock_id),
                               _unpriced_dates(stock_id)])

    rows = []
    for _, v in missing.iterrows():
        r = v.to_dict()
        r['stock_id'] = str(stock_id)
        r['raw_covered'] = False
        # FinMind's own close-minus-prior-close, taken on FinMind's own calendar
        # and so blind to this row. There is nothing to divide by a factor here.
        r['spread'] = np.nan
        if r['Trading_Volume'] == 0:
            for c in ('open', 'max', 'min', 'close'):
                r[c] = 0.0
        else:
            f = None
            d = np.datetime64(v['date'])
            k = int(np.searchsorted(dates[seat], d, 'left'))
            for i in [j for j in (k - 1, k) if 0 <= j < len(seat)]:
                lo, hi = sorted((dates[seat[i]], d))
                if not ((blocking > lo) & (blocking <= hi)).any():
                    f = priced[dates[seat[i]]] / close[seat[i]]
                    break
            if f is None:
                continue
            for c in ('open', 'max', 'min', 'close'):
                r[c] = round(r[c] / f, _PRICE_DECIMALS)
        rows.append(r)

    if not rows:
        return out, len(missing), 0
    got = pd.DataFrame(rows).reindex(columns=out.columns).astype(out.dtypes)
    out = (pd.concat([out, got], ignore_index=True)
             .sort_values('date').reset_index(drop=True))
    return out, len(missing), len(rows)


def _patch(stock_id: str, dates: np.ndarray, covered: np.ndarray,
           factor: np.ndarray) -> tuple[np.ndarray, int]:
    """Replace the vendor's step with the exchange's on its defective events.

    A back-adjustment factor anchored at the present carries an event only in
    the rows *behind* it, so swapping one step rescales exactly that history:
    ``factor[:ex] *= vendor_step / exchange_step``. Rows from the ex date onward
    never saw the step and are untouched.
    """
    d = defective_events()
    d = d[d['stock_id'].astype(str) == str(stock_id)]
    if not len(d):
        return factor, 0
    n = 0
    for _, e in d.iterrows():
        i = int(np.searchsorted(dates, np.datetime64(e['date']), 'left'))
        # The audit graded this event between two adjacent covered sessions, so
        # the ex row is the first covered session at or after it.
        while i < len(dates) and not covered[i]:
            i += 1
        if i <= 0 or i >= len(dates):
            continue
        factor[:i] *= e['vendor_step'] / e['exchange_step']
        n += 1
    return factor, n


def _carry_edges(stock_id: str, dates: np.ndarray, traded: np.ndarray,
                 factor: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Extend the vendor's factor onto the traded sessions at either edge of it.

    A back-adjustment factor moves only on an ex date, so between two filings it
    is constant and a covered session's factor is also the factor of every
    uncovered session next to it — not an interpolation but the same number, and
    the level is continuous by construction rather than by a splice.

    Two edges need it. The vendor series begins one session after the raw one on
    903 stocks, which costs each of them its **first return** rather than its
    first price, and a first return is the whole observation in a listing study.
    It ends before the raw one on 7, which is the 3,089 sessions a delisted name
    went on being quoted for.

    The condition is checked per row rather than assumed: every date the stock
    filed a 除權息 or a 減資 on, plus the share cancellations no filing explains,
    and a row whose gap to its anchor contains one of them is left NaN. That is
    not hypothetical — 4141's first print sits 376 days before the vendor's
    first session with a cancellation on that very session, and it is the one
    row of the 903 this refuses.

    Returns the factor and the mask of rows it filled.
    """
    have = np.isfinite(factor)
    carried = np.zeros(len(factor), dtype=bool)
    if not have.any():
        return factor, carried
    blocking = np.concatenate([adjust.filed_event_dates(stock_id),
                               _unpriced_dates(stock_id)])
    seat = np.nonzero(have)[0]
    todo = np.nonzero(traded & ~have)[0]
    for i in todo[(todo < seat[0]) | (todo > seat[-1])]:
        a = seat[0] if i < seat[0] else seat[-1]
        lo, hi = sorted((dates[i], dates[a]))
        # Half-open at the earlier end, whichever side the anchor is on: an
        # event is placed on the first session at or after its date and carries
        # in every row *behind* that, so it separates two rows exactly when it
        # falls strictly after the earlier and no later than the later.
        if ((blocking > lo) & (blocking <= hi)).any():
            continue
        factor[i] = factor[a]
        carried[i] = True
    return factor, carried


def _mark_patched(stock_id: str, dates: np.ndarray, covered: np.ndarray,
                  source: np.ndarray) -> np.ndarray:
    """Label the rows a patch actually moved — those behind the last one."""
    d = defective_events()
    d = d[d['stock_id'].astype(str) == str(stock_id)]
    last = 0
    for _, e in d.iterrows():
        i = int(np.searchsorted(dates, np.datetime64(e['date']), 'left'))
        while i < len(dates) and not covered[i]:
            i += 1
        last = max(last, i if i < len(dates) else 0)
    head = source[:last]
    source[:last] = np.where(head == 'vendor', 'vendor_patched', head)
    return source


def available_stocks(price_adj_dir: Path = PRICE_ADJ_DIR) -> list[str]:
    """Stock ids whose adjusted series is non-empty.

    51 of the 2,154 downloaded files hold zero rows. 38 of those are the
    survivorship hole ``load_adjusted`` now rebuilds, so they *do* come back
    with an adjusted series and this list understates the panel by them; the
    other 13 have no raw prices either. Use it to ask what the vendor covers,
    not what the loader returns.
    """
    return sorted(p.stem for p in Path(price_adj_dir).glob('*.parquet')
                  if len(pd.read_parquet(p)))


if __name__ == '__main__':
    for sid in ('2330', '8934', '2396', '2822', '1207'):
        df = load_adjusted(sid)
        src = df.loc[df['adj_source'] != '', 'adj_source'].unique()
        print(f'{sid}: {len(df):,} rows {df["date"].min().date()}..'
              f'{df["date"].max().date()}  vendor coverage '
              f'{df.attrs["adj_coverage"]:.4f}  source {list(src)}  '
              f'patched {df.attrs["events_patched"]}  '
              f'breaks {df.attrs["series_breaks"]}')
        print(f'  tr_factor {df["tr_factor"].min():.4f}..{df["tr_factor"].max():.4f}'
              f'  |adj_close_tr[-1] - close[-1]| = '
              f'{abs(df["adj_close_tr"].iloc[-1] - df["close"].iloc[-1]):.3e}')
