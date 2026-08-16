"""Taiwan back-adjusted, dividend-inclusive prices — FinMind's series, with the
holes filled, the defects patched, and both marked in the frame.

``TaiwanStockPriceAdj`` (→ ``price_adj/``) is the 還原股價 series, and it is
**total return**: cash dividends come out along with 無償配股, 現增 and 減資.
That is measured, not assumed — on 2330, 2317 and 1101 the series tracks a
cash-removed reconstruction to a median 1e-5..2.5e-4 of relative error and
departs from a cash-retained one by 25-36 %. There is no price-return variant of
the endpoint at any tier, so a study that needs the price alone has no source
here.

Three things happen on top of the vendor series, all of them marked in a column
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
99.93 % of 268,485 daily adjusted returns to 1e-6 and 99.997 % to 1e-3.

**Seven vendor events are replaced with the exchange's own step.** Six are
現金增資 subscribed above the market, where the reference price *rises* and the
vendor scaled the history the other way, up to 4.11 % on one session and
carried through the whole history behind it; one is a filing the vendor added a
malformed duplicate row into. ``vendor_event_audit`` grades every event and
finds both by shape, not by stock id.

**Two conventions therefore live in one panel**, and ``adj_method`` says which.
FinMind subtracts the *declared* distribution from the prior close; the rebuild
reads the exchange's *published reference price*. The two name the same number
to 1e-6 on 83.3 % of 22,336 graded events and to 1e-3 on 99.5 %, and where they
differ it is by a whole cent in the per-share distribution — bounded, not
cumulative, and confined to the ex-date session. ``vendor_event_audit.parquet``
is the fixed record of that, so a step found at a vendor/rebuilt boundary is
answered by a file rather than re-derived.

Nothing else on the vendor side is re-derived. What this module adds beyond the
above is the two places where the vendor series says something a return
calculation should not believe, both measured against ``ohlcv/`` and
``unpriced_actions.parquet``:

**A no-trade session carries a price.** FinMind writes a session the stock did
not trade as ``close == 0`` in ``ohlcv/`` — 179,749 rows, 2.34 % of the panel,
in 1,325 stocks. The adjusted series fills those rows with the last traded price
instead (8934 has 2,441 of them, every one carrying a number), so the zero that
identifies them is gone and a caller filtering on ``adj_close_tr > 0`` keeps all
of them. They are NaN here, and the raw ``close`` is kept alongside so the test
stays available.

**A share cancellation no filing priced goes through unadjusted.**
``capital_reduction.parquet`` starts on 2011-01-25 while prices start in 2005,
and the vendor is subject to the same publication limit: 2357's 85 % reduction
on 2010-06-24 has a vendor factor step of 1.0000, which leaves the raw 53.2 →
240.5 jump in the adjusted series as a +351 % return. ``detect_unpriced_actions``
finds those cancellations in the share count, and ``is_valid`` is False for every
row before the last of them. The same flag carries series splices, where a ticker
stops trading for years and comes back as a different listing, so
``invalid_reason`` names which of the two cut the row off. ``is_valid`` says
"this row connects to the rows after it", not "this row is wrong".

Coverage after the fill is still not complete, and what remains is benign. 903
stocks are short exactly their first traded session, which the vendor series
begins one session after. 3,089 sessions sit past the end of a vendor series
that stopped at a delisting while ``ohlcv/`` kept printing — five names hold
3,001 of them, 1107 the largest at 1,151: adjusted ends 2007-10-19 against a
2007-10-20 delisting, raw runs to 2012-06-06 at 249 sessions/yr on half the
prior median volume. Those are 興櫃 quotes for a name that left the exchange, so
the raw panel is over-reaching the listing rather than the adjusted panel
falling short of it. Neither class is rebuilt: both would mean splicing a
rebuilt segment onto a vendor series at a level the two do not share, and the
whole-stock holes above have no such seam.

Both join as NaN rather than being dropped, so the gap stays visible beside the
raw price that does cover it, and ``adj_source`` carries the distinction row by
row — through ``concat``, ``merge`` and ``groupby``, which is what ``df.attrs``
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

# Which convention produced the ex-date steps in a row's factor chain. The
# vendor subtracts the declared distribution; the rebuild reads the exchange's
# published reference price. See the module docstring on how far apart they are.
_METHOD = {
    'vendor': 'declared_dividend',
    'vendor_patched': 'declared_dividend',
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
                         ``vendor_patched``, ``rebuilt_factored``,
                         ``rebuilt_noevent``, or ``''`` where nothing covers it
      ``adj_method``     which convention produced its ex-date steps:
                         ``declared_dividend``, ``exchange_reference``, ``none``
      ``adj_covered``    the *vendor* served this date — False across a rebuilt
                         stock, so the survivorship hole stays countable after
                         it is filled
      ``is_valid``       row connects to the rows after it — False before the
                         last series break
      ``invalid_reason`` which break cut it off: ``unpriced_cancellation`` or
                         ``series_break``, ``''`` where valid

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
    carries ``adj_coverage``, ``series_breaks``, ``vendor_only_sessions`` and
    ``events_patched`` for a single stock, and is **not** the safe route for a
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

    a = Path(price_adj_dir) / f'{stock_id}.parquet'
    if not a.exists():
        raise FileNotFoundError(
            f'no adjusted series for {stock_id} at {a} — run '
            f'`python download.py --datasets price_adj --stocks {stock_id}`')
    adj = pd.read_parquet(a)
    if len(adj):
        adj['date'] = pd.to_datetime(adj['date'])
        # The two endpoints disagree about 600 sessions across the panel — a
        # 補行交易日 or a stray 興櫃 print the adjusted side carries and the raw
        # side does not. The raw calendar defines the panel, so the left join
        # drops them; the count goes into attrs rather than nowhere.
        vendor_only = int((~adj['date'].isin(out['date'])).sum())
        adj = adj[['date', 'close']].rename(columns={'close': 'adj_close_tr'})
        out = out.merge(adj, on='date', how='left')
    else:
        vendor_only = 0
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
    if covered.any():
        factor, n_patched = _patch(str(stock_id), out['date'].to_numpy(),
                                   covered, factor)
        source = np.where(covered, 'vendor', '').astype(object)
        if n_patched:
            source = _mark_patched(str(stock_id), out['date'].to_numpy(),
                                   covered, source)
    else:
        # The vendor serves this stock nothing at all — the survivorship hole.
        # Rebuild it from the exchange's reference prices rather than return a
        # column of NaN that a panel build would drop, reinstating the bias.
        factor, diag = adjust.rebuild_tr_factor(str(stock_id), out[['date', 'close']])
        factor = np.where(traded, factor, np.nan)
        kind = 'rebuilt_factored' if diag['events_placed'] else 'rebuilt_noevent'
        source = np.where(traded, kind, '').astype(object)
        covered = np.isfinite(factor)

    if covered.any():
        factor = factor / factor[np.nonzero(covered)[0][-1]]
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
    out['is_valid'] = valid

    # Coverage is over traded sessions: the vendor also serves the no-trade rows
    # it filled with a carried price, and counting those would put the ratio
    # above 1 on a stock like 8934.
    out.attrs['adj_coverage'] = float(
        (out['adj_covered'].to_numpy() & traded).sum() / max(int(traded.sum()), 1))
    out.attrs['series_breaks'] = int(len(seen))
    out.attrs['vendor_only_sessions'] = vendor_only
    out.attrs['events_patched'] = n_patched
    return out


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
    source[:last] = np.where(source[:last] == 'vendor', 'vendor_patched', '')
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
