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

**The survivorship hole is filled.** ``price_adj/`` serves nothing at all
inside the window for 54 stocks, 61,505 traded sessions. Fifty are in-window
universe delistings — 50 of the 164, delisted 2012-2020, and 50 of the 57 names
the universe carries precisely as its survivorship overlay, dropped from
FinMind's live registry and from this endpoint on the same list. The other four
delisted between 2007 and 2010 and went on being quoted on 興櫃 into the window,
so the vendor's series for them ends before ``COVERAGE_START`` and covers none
of their in-window sessions. ``adjust.rebuild_tr_factor`` rebuilds all 54 from
the exchange's own reference prices, which is why they are recoverable at all:
the reference prices are published per event and do not depend on the registry.
Validated on the 116 covered in-window delistings — the same era, the same
situation, the vendor present to compare against — where the rebuild reproduces
99.954 % of 203,671 daily adjusted returns to 1e-6 and 99.998 % to 1e-3.

**One vendor event is replaced with the exchange's own step.** 3454's
2011-07-27 除權息 is filed twice, the second row reading before 0.00 / after
−2.30, and the vendor read both as one distribution — a step 2.98 % off the
exchange's, carried through the whole history behind it. A second defect class
exists and the window holds none of it: on six 現金增資 subscribed above the
market, where the reference price *rises*, the vendor scaled the history the
other way, and all six are dated 2005-2008. ``vendor_event_audit`` grades every
event and finds both shapes by shape, not by stock id.

**The one edge of the vendor series is carried outward.** It begins one traded
session after the raw series on 493 stocks, and a factor moves only on an ex
date — so where no filing sits in the gap, the adjacent covered session's factor
*is* the missing one, and carrying it is exact rather than an interpolation or a
splice. That recovers 492 **first returns** — the price was never the loss; the
session-1-to-session-2 return was. The condition is tested per row against every
filed 除權息 and 減資 plus the cancellations no filing explains, and it refuses
the 493rd: 4141's first print sits 376 days before the vendor's first session,
with a cancellation on that session. Those rows are ``vendor_carried``. The
other edge — a vendor series stopping at a delisting while ``ohlcv/`` keeps
printing — has no in-window instance: every name it applies to delisted before
the window, which is what makes those four a hole for the rebuild rather than an
edge for the carry.

**The sessions the raw endpoint dropped are back in the tree, not rebuilt
here.** ``ohlcv/`` used to have no row at all for 1,941 sessions the vendor
serves, in 507 stocks. 1,940 of them fall on 14 補行交易日 — Saturdays worked to
make up a holiday — and the last is one no-trade row for 2910 on an ordinary
Wednesday. The cost is not the missing row but the return after it, which spans
two sessions instead of one: 1,940 absent Saturdays are 1,940 overstated
returns, clustered on 14 holiday-adjacent dates rather than scattered. ``backfill_make_up_sessions.py`` read every one of them back from the
date-keyed endpoint, so the loader now reads those prices rather than deriving
them, and what stands here in place of the reconstruction is the guard that
refuses to derive one — see ``_require_raw_covers_vendor``.

**Two conventions therefore live in one panel**, and ``adj_method`` says which.
FinMind subtracts the *declared* distribution from the prior close; the rebuild
reads the exchange's *published reference price*. The two name the same number
to 1e-6 on 84.2 % of 18,087 graded events and to 1e-3 on 99.5 %, and where they
differ it is by a whole cent in the per-share distribution — bounded, not
cumulative, and confined to the ex-date session. ``vendor_event_audit.parquet``
is the fixed record of that, so a step found at a vendor/rebuilt boundary is
answered by a file rather than re-derived.

Nothing else on the vendor side is re-derived. What this module adds beyond the
above is the three places where the adjusted panel says something a return
calculation should not believe, all measured against ``ohlcv/`` and
``unpriced_actions.parquet``:

**A no-trade session carries a price.** FinMind writes a session the stock did
not trade as ``close == 0`` in ``ohlcv/`` — 127,745 rows there in 1,150 stocks,
and 127,838 in this panel once the make-up sessions above are put back, 2.17 %
of it. The adjusted series fills 125,904 of the ones ``ohlcv/`` holds with the
last traded price instead (8934 has 1,321 of them, every one carrying a number),
so the zero that identifies them is gone and a caller filtering on
``adj_close_tr > 0`` keeps all of them. They are NaN here, the raw ``close`` is
kept alongside so the test stays available, and they are ``is_valid`` False
under ``invalid_reason = 'no_trade'``: a price nobody could transact at is not a
position, and a backtest that filtered on the flag alone would otherwise assume
a fill on a day the stock did not trade.

**A share cancellation no filing priced goes through unadjusted.** A filing is
not the only way one reaches the tape: 8101 stopped trading 2024-08-21 at 1.90,
cancelled 80 % of its shares over a 90-day suspension, and resumed 2024-11-19 at
10.45 with a vendor factor step of 1.0000, leaving a +450 % return across the
gap. ``detect_unpriced_actions``
finds those cancellations in the share count, and ``is_valid`` is False for every
row before the last of them. The same flag carries series splices, where a ticker
stops trading for years and comes back as a different listing, so
``invalid_reason`` names which of the four disqualified it.

**A price is not a permission.** 1,134 in-window sessions across four names —
1107, 2341, 2381 and 2396 — print after the exchange ended the listing. The
boundary is the delisting table's date and not the session where the vendor's
series stops, because a rebuilt name has no vendor series to stop: reading the
stop found only the names the vendor serves, and all four of these are rebuilt.
A backtest holding any of them would be trading a book it could not have filled,
which is why they carry ``is_valid`` False under ``invalid_reason =
'post_delisting_emerging'``. The destination is 興櫃, a negotiated market:
``open`` is the previous session's average rather than a trade, a quote depends
on a recommending broker standing behind it, and median volume runs at 3.0-49 %
of each name's own listed-era median. Turnover that thin is not a demotion to
another board, and none of the four goes on trading: all stop for good by
2012-11, where a name that changes boards does not. What they *are* is the
terminal value: where a delisted name converges over the months after it leaves
is a market observation, and the last exchange close is not one. That is the use
the fill is for, and the flag is what keeps it to that use.

A name the vendor keeps pricing past that date did not leave, and the carve-out
below is for that case. It has no subject today: the 2026-08-17 refresh dropped
the one board transfer the delisting table used to carry, and the two reused
codes with it, so no name in the table is still quoted on the panel's last
session. The rule stays because the table is re-collected, not because a name
needs it now.

That carve-out reads the vendor's coverage, and so has the blind spot the
boundary above had: ``adj_covered`` is False across every rebuilt name, so a
rebuilt name that changed boards would be marked here and nothing in this module
could tell. It stays vendor-side because the alternative is a panel-wide fact and
this loads one stock. What closes it is that
``test_taiwan_post_delisting_sessions_are_marked`` classifies on that fact
instead — still quoted on the panel's last session — so the two routes can
disagree, and today they agree on all fourteen.

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
from .window import COVERAGE_START, COVERAGE_END, clip

ROOT = Path(__file__).resolve().parent
OHLCV_DIR = ROOT / 'ohlcv'
PRICE_ADJ_DIR = ROOT / 'price_adj'
UNPRICED_PATH = ROOT / 'unpriced_actions.parquet'
DELISTED_PATH = ROOT / 'delisted_universe.parquet'

# A listing that stops trading for two years and returns is not the same series.
# Observed gap lengths are empty between 419 and 738 days, so every cut in that
# range marks the same 10 splices; this is a materiality choice, not a tuned one.
_BREAK_GAP_DAYS = 730

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


def _delisting_date(stock_id: str):
    """The date this stock left the exchange, or None if it never did.

    A missing file raises for the reason ``_unpriced_dates`` does: returning
    nothing quietly would leave every delisted name's tail reading as a tradable
    position, which is the failure the date exists to prevent.
    """
    if not DELISTED_PATH.exists():
        raise FileNotFoundError(
            f'{DELISTED_PATH} is missing — run '
            f'`python -m finmind_data.build_universe` first. Without it the '
            f'sessions a delisted name goes on printing stay is_valid and a '
            f'backtest holds them.')
    d = pd.read_parquet(DELISTED_PATH)
    hit = d.loc[d['stock_id'].astype(str) == str(stock_id), 'date']
    return pd.to_datetime(hit.iloc[0]) if len(hit) else None


def load_adjusted(stock_id: str,
                  ohlcv_dir: Path = OHLCV_DIR,
                  price_adj_dir: Path = PRICE_ADJ_DIR) -> pd.DataFrame:
    """One stock's raw OHLCV plus its total-return adjusted close, windowed.

    Returns `COVERAGE_START..COVERAGE_END` only. The per-stock files are wider
    on both sides — prices from 2005, and whatever `download.py --extend` last
    reached — and the window is applied here rather than left to the caller,
    because the derivations below are properties of the rows they were given.

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
      ``is_valid``       this row is a position a study could have held
      ``invalid_reason`` why not: ``unpriced_cancellation`` or ``series_break``
                         behind the last break, ``post_delisting_emerging``
                         past the last exchange session, ``no_trade`` on a
                         session inside both that the stock did not trade,
                         ``''`` where valid

    Any other price column adjusts the same way — ``adj_open_tr = open *
    tr_factor`` — which is what makes the factor rather than the adjusted close
    the primary output.

    The factor is re-anchored to 1.0 on the window's last priced session rather
    than left on the vendor's anchor, which is the latest session in FinMind's
    own database and therefore moves every time the download is repeated. Both
    anchors give identical returns; only this one gives identical *numbers* on a
    re-download — and only because the frame is windowed first. Anchored on the
    file's last session instead, the numbers would move whenever the tree grew,
    which is the drift the re-anchoring exists to remove.

    ``adj_close_tr`` is NaN on a session the stock did not trade and on any
    session nothing covers; ``adj_source`` separates the two. ``df.attrs``
    carries ``adj_coverage``, ``series_breaks``, ``events_patched`` and
    ``sessions_carried`` for a single stock, and is **not** the safe route for a
    panel — read provenance off ``adj_source`` there.
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
    # Everything below derives from this frame, so the window is applied here
    # rather than to the result. Two properties depend on it. The factor is
    # anchored on the last priced session (below), so a frame running past the
    # window would anchor on a session the package does not answer for and move
    # every adjusted number the day the download is extended — which is the
    # re-download stability the anchoring exists to provide, lost to the same
    # cause it was written against. And every count quoted on this panel would
    # otherwise be a count over the tree, which holds prices from 2005 and past
    # the window's end, rather than over the window those counts are published
    # on. Clipping before the derivations rather than after also keeps the
    # break rule intact: a gap that straddles a window edge separates rows
    # this frame does not contain from rows that are all on one side of it.
    out = clip(out)
    if not len(out):
        raise ValueError(f'{stock_id}: no sessions inside '
                         f'{COVERAGE_START.date()}..{COVERAGE_END.date()}, so '
                         f'there is no series this package answers for')

    a = Path(price_adj_dir) / f'{stock_id}.parquet'
    if not a.exists():
        raise FileNotFoundError(
            f'no adjusted series for {stock_id} at {a} — run '
            f'`python download.py --datasets price_adj --stocks {stock_id}`')
    adj = pd.read_parquet(a)
    if len(adj):
        adj['date'] = pd.to_datetime(adj['date'])
        adj = clip(adj)
    if len(adj):
        _require_raw_covers_vendor(str(stock_id), out, adj)
        adj = adj[['date', 'close']].rename(columns={'close': 'adj_close_tr'})
        out = out.merge(adj, on='date', how='left')
    else:
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
    # session's average price rather than a trade, median volume runs at 3.0-49 %
    # of the prior year's, and a quote depends on a recommending broker standing
    # behind it. Carrying the factor over those sessions makes the level
    # continuous, which is what the price is wanted for; it does not make the
    # sessions tradable, and this reason is what keeps a backtest from assuming
    # they are. What they *are* good for is the terminal value — where a
    # delisted name converges over the following months is a market observation,
    # and the last exchange close is not one.
    #
    # The boundary is the delisting table's date, not the session where the
    # vendor's series stops, because the stop was only ever standing in for the
    # date; a rebuilt name has ``adj_covered`` False throughout and no stop to
    # read, so the stand-in was silent on exactly the names the rebuild added.
    # Inside this window that is every one of them: all four names with sessions
    # past a delisting are rebuilt, 1,134 rows the stop would have left tradable
    # by a fix for the opposite bias.
    delisted_on = _delisting_date(stock_id)
    if delisted_on is not None:
        after = out['date'].to_numpy() > np.datetime64(delisted_on)
        # A name the vendor keeps pricing past that date did not leave the
        # market, it changed boards: 6446 moved to the exchange in 2024 and the
        # delisting table records the departure without recording the arrival.
        # Those sessions are exchange sessions and a study could have held them.
        if after.any() and not (out['adj_covered'].to_numpy() & after).any():
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
    out.attrs['events_patched'] = n_patched
    out.attrs['sessions_carried'] = int(carried.sum())
    return out


def _require_raw_covers_vendor(stock_id: str, out: pd.DataFrame,
                               adj: pd.DataFrame) -> None:
    """Refuse to load a stock whose raw tree is behind the vendor's adjusted one.

    ``ohlcv/`` once had no row at all for 1,941 sessions the vendor serves, in
    507 stocks — 1,940 of them on 14 補行交易日, Saturdays worked to make up a
    holiday. The cost was never the missing row. A gap in the calendar makes the
    *next* session's return span two sessions instead of one, so those were
    1,940 overstated returns sitting on 14 holiday-adjacent dates rather than
    anywhere at random, which is the shape a study reads as an effect.

    This function used to reconstruct the 303 of them ``price_adj/`` carried,
    dividing the vendor's row by the factor at an adjacent session. That
    arithmetic was exact — checked per row against every filed 除權息 and 減資,
    and 209 of the 210 traded sessions reconstructed from anchors on both sides
    agreed to 1.8e-7 — but it could only reach a session at least one local tree
    held, and 1,638 of the 1,941 were in neither. ``backfill_make_up_sessions.py``
    reads all of them from the date-keyed endpoint that serves them, so the rows
    are in the tree and the panel derives nothing.

    What is left is the guard, because the condition can recur: the trees fell
    behind a vendor backfill once and nothing in the package noticed. A
    reconstructed price is a derived field wearing a read one's clothes, so the
    answer to the tree falling behind again is to stop, not to paper over it —
    the repair belongs in the tree, where a later download keeps it, rather than
    in a loader that re-derives it on every call.

    This sees only the half of the condition ``price_adj/`` exposes; the 1,638
    rows neither tree held were invisible to it by construction, and measuring
    the tree against the vendor rather than against another tree is what
    ``test_taiwan_no_session_the_tape_holds_is_missing`` does with the tape.
    """
    missing = adj[~adj['date'].isin(out['date'])]
    if not len(missing):
        return
    dates = [str(d)[:10] for d in missing['date'].head(5)]
    raise ValueError(
        f'{stock_id}: price_adj/ carries {len(missing)} '
        f'session{"s" if len(missing) > 1 else ""} ohlcv/ has no row for ({", ".join(dates)}{" ..." if len(missing) > 5 else ""}), so '
        f'the return after each one spans two sessions. The raw tree is behind '
        f'a vendor backfill — repair the tree, do not derive the rows: '
        f'`python -m finmind_data.backfill_make_up_sessions --dry-run`')


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

    One edge needs it inside this window. The vendor series begins one traded
    session after the raw one on 493 stocks, which costs each of them its
    **first return** rather than its first price, and a first return is the whole
    observation in a listing study. The other edge — a series ending before the
    raw one, at a delisting ``ohlcv/`` kept printing through — has no in-window
    instance: every such name delisted before the window, so the rebuild supplies
    the whole of it and there is no covered session next to it to carry from.

    The condition is checked per row rather than assumed: every date the stock
    filed a 除權息 or a 減資 on, plus the share cancellations no filing explains,
    and a row whose gap to its anchor contains one of them is left NaN. That is
    not hypothetical — 4141's first print sits 376 days before the vendor's
    first session with a cancellation on that very session, and it is the one
    row of the 493 this refuses.

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
