"""Read-only checks on the Taiwan adjusted series. `python -m finmind_data.validate_adjust`

Counterpart to ``kr_marcap.validate_dividend_events``. Each check answers "what
would have broken if this were wrong?" rather than restating the build; the six
families and the per-market results are written up in ADJUSTED_PRICE_VERIFICATION.md.

  [1] the input is raw          before_price vs our own stored prior close
  [2] the factor is understood  before - 차감액 == after, from the exchange's own columns
  [3] the event date is right   declared CashExDividendTradingDate as a 2nd source
  [4] the code is right         adj_close_tr == close * tr_factor, anchor, disjointness
  [5] the contamination is gone forward returns spanning an event, before vs after
  [6] the pr split is right      D checked where 配股率 is zero by construction
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from finmind_data.adjust import (CAP_RED_PATH, DIV_RESULT_DIR, DIVIDEND_DIR,
                                 OHLCV_DIR, _cash_dps, available_stocks,
                                 load_adjusted)

# The research window the documented figures are quoted on (twn_* pipeline).
Y0, Y1 = '2020-01-01', '2024-12-31'
# before_price is published to 2 decimals; 1e-6 is "bit-identical", 1e-2 is
# "identical at the exchange's own published precision". Both are reported so
# neither doubles as a tuned pass mark.
_TOL_EXACT, _TOL_PUBLISHED = 1e-6, 1e-2


def _events() -> pd.DataFrame:
    f = []
    for p in sorted(DIV_RESULT_DIR.glob('*.parquet')):
        d = pd.read_parquet(p)
        if len(d):
            f.append(d)
    ev = pd.concat(f, ignore_index=True)
    ev['date'] = pd.to_datetime(ev['date'])
    ev['stock_id'] = ev['stock_id'].astype(str)
    return ev


def _closes() -> pd.DataFrame:
    f = []
    for p in sorted(OHLCV_DIR.glob('*.parquet')):
        # A stock the endpoint returned nothing for is written as a zero-row
        # file with no schema, so the column projection cannot be pushed down.
        d = pd.read_parquet(p)
        if len(d):
            f.append(d[['date', 'stock_id', 'close']])
    px = pd.concat(f, ignore_index=True)
    px['date'] = pd.to_datetime(px['date'])
    px['stock_id'] = px['stock_id'].astype(str)
    return px.sort_values(['stock_id', 'date']).reset_index(drop=True)


def check_input_is_raw(ev: pd.DataFrame, px: pd.DataFrame) -> None:
    """If our closes were pre-adjusted, before_price could not match them."""
    px = px.copy()
    px['prev_close'] = px.groupby('stock_id')['close'].shift(1)
    j = ev.merge(px[['stock_id', 'date', 'prev_close']], on=['stock_id', 'date'],
                 how='inner').dropna(subset=['prev_close'])
    w = j[(j['date'] >= Y0) & (j['date'] <= Y1)]
    print(f'\n[1] input is raw  (before_price vs our stored prior close)')
    for lab, s in (('all years', j), (f'{Y0[:4]}-{Y1[:4]}', w)):
        d = (s['before_price'] - s['prev_close']).abs()
        print(f'  {lab:14} n={len(s):>6,}  '
              f'|diff|<1e-6 {(d < _TOL_EXACT).mean() * 100:>6.2f}%  '
              f'<1e-2 {(d < _TOL_PUBLISHED).mean() * 100:>6.2f}%')
    print('  → one comparison settles three things: closes are raw, event dates '
          'align, ticker join is right')


def check_factor_identity(ev: pd.DataFrame) -> None:
    """The exchange's three published numbers must satisfy one relation."""
    e = ev.copy()
    e['kind'] = e['stock_or_cache_dividend'].astype(str)
    sub = e[e['kind'].str.startswith('除')]
    d = (sub['before_price'] - sub['stock_and_cache_dividend'] - sub['after_price']).abs()
    print(f'\n[2] factor identity  (before - 차감액 == after)')
    print(f'  除-prefixed kinds  n={len(sub):>6,}  exact {(d < 5e-3).mean() * 100:>6.2f}%')
    other = e[~e['kind'].str.startswith('除')]
    if len(other):
        d2 = (other['before_price'] - other['stock_and_cache_dividend']
              - other['after_price']).abs()
        print(f'  bare kinds        n={len(other):>6,}  exact {(d2 < 5e-3).mean() * 100:>6.2f}%'
              f'   ← stock_and_cache_dividend semantics; the build never reads it')


def check_declared_ex_date(ev: pd.DataFrame) -> None:
    """A second, independently disclosed ex-date, from 股利分派公告 not 結果表."""
    rows, out_of_span, inside = 0, 0, 0
    matched = 0
    for p in sorted((DIV_RESULT_DIR.parent / 'dividend').glob('*.parquet')):
        sid = p.stem
        rp = DIV_RESULT_DIR / f'{sid}.parquet'
        if not rp.exists():
            continue
        d, r = pd.read_parquet(p), pd.read_parquet(rp)
        if 'CashExDividendTradingDate' not in d.columns or r.empty:
            continue
        dec = pd.to_datetime(d['CashExDividendTradingDate'], errors='coerce').dropna()
        if dec.empty:
            continue
        evt = pd.to_datetime(r['date']).dt.normalize()
        s = set(evt)
        for x in dec.dt.normalize():
            rows += 1
            if x in s:
                matched += 1
            elif x < evt.min() or x > evt.max():
                out_of_span += 1
            else:
                inside += 1
    comparable = rows - out_of_span
    print(f'\n[3] declared ex-date as a second source')
    print(f'  declared cash ex-dates      {rows:>7,}')
    print(f'  outside this stock\'s span   {out_of_span:>7,}   not comparable')
    print(f'  comparable                  {comparable:>7,}   '
          f'matched {matched:,} ({100 * matched / max(comparable, 1):.2f}%)')
    print(f'  genuine disagreements       {inside:>7,}')
    print('  → confirms div_result.date is the ex-dividend *trading* date, not the '
          'record or announcement date')


def check_code_identities(sample: list[str]) -> None:
    """Identities that must hold by construction, and the disjointness guard."""
    ident, anchor, unplaced, dropped = [], [], 0, 0
    pr_ident, pr_anchor, pr_unres, pr_stocks, pr_nan = [], [], 0, 0, 0
    for sid in sample:
        df = load_adjusted(sid)
        ident.append(float(np.abs(df['adj_close_tr']
                                  - df['close'] * df['tr_factor']).max()))
        anchor.append(abs(float(df['adj_close_tr'].iloc[-1] - df['close'].iloc[-1])))
        unplaced += df.attrs['events_unplaced']
        dropped += df.attrs['events_dropped']
        pr_ident.append(float(np.abs(df['adj_close_pr']
                                     - df['close'] * df['pr_factor']).max()))
        pr_anchor.append(abs(float(df['adj_close_pr'].iloc[-1] - df['close'].iloc[-1])))
        pr_unres += df.attrs['pr_unresolved']
        pr_stocks += int(df.attrs['pr_unresolved'] > 0)
        pr_nan += int(df['pr_factor'].isna().sum())
    print(f'\n[4] construction identities  (n={len(sample)} stocks)')
    print(f'  max |adj_close_tr - close*tr_factor|   {np.nanmax(ident):.3e}')
    print(f'  max |adj_close_tr[-1] - close[-1]|     {max(anchor):.3e}')
    print(f'  max |adj_close_pr - close*pr_factor|   {np.nanmax(pr_ident):.3e}')
    print(f'  max |adj_close_pr[-1] - close[-1]|     {max(pr_anchor):.3e}')
    print(f'  events unplaced {unplaced:,}   dropped (non-positive leg) {dropped:,}')
    print(f'  pr unresolved (mixed event, no declared cash leg) {pr_unres:,} '
          f'in {pr_stocks:,} stocks → {pr_nan:,} NaN rows')

    ev = _events()
    cr = pd.read_parquet(CAP_RED_PATH)
    cr['date'] = pd.to_datetime(cr['date'])
    cr['stock_id'] = cr['stock_id'].astype(str)
    overlap = ev[['stock_id', 'date']].merge(cr[['stock_id', 'date']],
                                             on=['stock_id', 'date'], how='inner')
    print(f'  除權息 ∩ 減資 sessions                  {len(overlap):,}   '
          f'← must be 0, else the chains double count')


def check_contamination(sample: list[str]) -> None:
    """R_t1 is a *forward* return, so an ex-event contaminates the CUM-date row.

    Joining on the ex-date row instead measures the post-drop session and
    understates the contamination roughly twentyfold.
    """
    parts = {'除權息': ([], [], []), '減資': ([], [], [])}
    n_rows, n_hit = 0, 0
    for sid in sample:
        df = load_adjusted(sid)
        df = df[(df['date'] >= Y0) & (df['date'] <= Y1)]
        if len(df) < 3:
            continue
        c = df['close'].to_numpy(dtype=float)
        a = df['adj_close_tr'].to_numpy(dtype=float)
        p = df['adj_close_pr'].to_numpy(dtype=float)
        # A zero or absent close is a halted/unpriced session, not a -100 % return.
        ok = np.isfinite(c[:-1]) & (c[:-1] > 0) & np.isfinite(c[1:]) & (c[1:] > 0)
        r_raw = np.where(ok, c[1:] / np.where(ok, c[:-1], 1.0) - 1.0, np.nan)
        r_adj = np.where(ok, a[1:] / np.where(ok, a[:-1], 1.0) - 1.0, np.nan)
        r_pr = np.where(ok, p[1:] / np.where(ok, p[:-1], 1.0) - 1.0, np.nan)
        n_rows += int(ok.sum())
        # Row t's forward return spans t -> t+1, so an event on t+1 contaminates
        # row t. Joining on the event row instead measures the post-drop session.
        for kind, col in (('除權息', 'is_ex_date'), ('減資', 'is_cap_red')):
            m = df[col].to_numpy()[1:] & ok
            n_hit += int(m.sum())
            parts[kind][0].append(r_raw[m])
            parts[kind][1].append(r_adj[m])
            parts[kind][2].append(r_pr[m])

    print(f'\n[5] contamination on forward returns  ({Y0[:4]}-{Y1[:4]}, '
          f'full {len(sample):,}-stock universe)')
    print(f'  rows whose forward window spans an event  {n_hit:,} / {n_rows:,} '
          f'({100 * n_hit / max(n_rows, 1):.3f}%)')
    print(f'  {"event":8} {"n":>6} {"raw mean":>10} {"pr mean":>10} {"tr mean":>10} '
          f'{"raw med":>9} {"pr med":>9} {"tr med":>9}')
    for kind, (rs, as_, ps) in parts.items():
        r, a, p = np.concatenate(rs), np.concatenate(as_), np.concatenate(ps)
        k = np.isfinite(r) & np.isfinite(a) & np.isfinite(p)
        r, a, p = r[k], a[k], p[k]
        if not len(r):
            continue
        print(f'  {kind:8} {len(r):>6,} {r.mean() * 1e4:>9.1f}b {p.mean() * 1e4:>9.1f}b '
              f'{a.mean() * 1e4:>9.1f}b {np.median(r) * 1e4:>8.1f}b '
              f'{np.median(p) * 1e4:>8.1f}b {np.median(a) * 1e4:>8.1f}b')
    print('  → 除權息 removes a price drop, 減資 removes a price rise, so the two are '
          'reported apart rather than netted')
    print('  → pr keeps the cash drop by design, so on 除權息 it stays negative and on '
          '減資 (no cash leg) it must equal tr exactly')
    print('  → tr\'s residual is the ex-day tax/clientele effect, not a defect: prices '
          'fall short of the full distribution, so it is marked, not erased')


def measure_pr_split() -> dict:
    """The figures behind [6], returned rather than printed.

    Split out so a downstream consumer of ``adj_close_pr`` can quote the
    validation hit rate as a generated number instead of hardcoding it, and so
    the printed check below and that number can never drift apart.

    Keys: ``cash_only_events`` and ``cash_only_share_within_2e2`` (the identity
    test the split's only input has to pass), ``mixed_events`` with
    ``mixed_share_implied_positive`` / ``mixed_share_implied_ge_declared`` (the
    one-sided consistency of the events the split is actually used on), and
    ``cash_only_median_abs_err`` in TWD per share.
    """
    co_err, mx_pos, mx_ge, mx_n, co_n = [], 0, 0, 0, 0
    for p in sorted(DIV_RESULT_DIR.glob('*.parquet')):
        r = pd.read_parquet(p)
        if not len(r):
            continue
        d_ps = _cash_dps(p.stem)
        if d_ps.empty:
            continue
        k = r['stock_or_cache_dividend'].astype(str)
        dt = pd.to_datetime(r['date'])
        D = dt.map(d_ps).to_numpy(dtype=float)
        before, after = r['before_price'].to_numpy(), r['after_price'].to_numpy()
        ok = np.isfinite(D) & (before > 0) & (after > 0)
        cash_only = (k.str.contains('息') & ~k.str.contains('權')).to_numpy() & ok
        co_err.append(np.abs((before - D - after)[cash_only]))
        co_n += int(cash_only.sum())
        mixed = (k.str.contains('息') & k.str.contains('權')).to_numpy() & ok
        # `ok` already excludes non-positive legs; evaluate only there so an
        # unpriced row does not raise a divide warning on its way to being masked.
        r_imp = np.full(len(r), np.nan)
        r_imp[mixed] = ((before[mixed] / after[mixed])
                        * (1.0 - D[mixed] / before[mixed]) - 1.0)
        mx_pos += int((r_imp[mixed] > 0).sum())
        mx_n += int(mixed.sum())
        mx_ge += int((r_imp[mixed] >= _declared_ratio(p.stem, dt[mixed]) - 1e-3).sum())

    e = np.concatenate(co_err)
    return {
        'cash_only_events': co_n,
        'cash_only_share_within_5e3': float((e < 5e-3).mean()),
        'cash_only_share_within_2e2': float((e < 2e-2).mean()),
        'cash_only_median_abs_err': float(np.median(e)),
        'mixed_events': mx_n,
        'mixed_share_implied_positive': mx_pos / max(mx_n, 1),
        'mixed_share_implied_ge_declared': mx_ge / max(mx_n, 1),
    }


def check_pr_split() -> None:
    """The price-return split rests entirely on the declared cash dividend D.

    D cannot be checked on the mixed events it is used for — that is the whole
    reason it is needed there. It can be checked on the cash-only events, where
    配股率 is zero by construction and the exchange's own identity collapses to
    ``after == before - D``, and the column is the same one either way.

    The mixed events then get a one-sided consistency check instead: the implied
    structural step must exceed 1 (a 權 event dilutes) and must not fall below
    the declared 配股率, since the declaration omits 員工配股 and 董監酬勞.
    """
    s = measure_pr_split()
    print(f'\n[6] the pr split  (D from dividend/, the only input the split needs)')
    print(f'  cash-only, 配股率 == 0 by construction:  after == before - D')
    print(f'    n={s["cash_only_events"]:,}   '
          f'|err|<{_TOL_PUBLISHED / 2:g} {100 * s["cash_only_share_within_5e3"]:>6.2f}%'
          f'   <2e-2 {100 * s["cash_only_share_within_2e2"]:>6.2f}%'
          f'   median {s["cash_only_median_abs_err"]:.5f}')
    print(f'  mixed, one-sided consistency of the implied structural step:')
    print(f'    n={s["mixed_events"]:,}   '
          f'implied r > 0 {100 * s["mixed_share_implied_positive"]:>6.2f}%'
          f'   implied r >= declared {100 * s["mixed_share_implied_ge_declared"]:>6.2f}%')
    print('  → a two-sided failure would mean D is wrong; a one-sided one is the '
          'declaration omitting employee/director dilution, which the split never reads')


def _declared_ratio(stock_id: str, dates: pd.Series) -> np.ndarray:
    """Declared 配股率 on each date — the comparison target of [6], never an input."""
    p = DIVIDEND_DIR / f'{stock_id}.parquet'
    if not p.exists():
        return np.zeros(len(dates))
    d = pd.read_parquet(p)
    if not len(d) or 'CashExDividendTradingDate' not in d.columns:
        return np.zeros(len(dates))
    d = d[d['CashExDividendTradingDate'].astype(str).str.len() == 10]
    g = (d.assign(r=(d['StockEarningsDistribution']
                     + d['StockStatutorySurplus']) / 10.0)
          .groupby(pd.to_datetime(d['CashExDividendTradingDate']))['r'].sum())
    return dates.map(g).fillna(0.0).to_numpy(dtype=float)


def main() -> None:
    ev, px = _events(), _closes()
    print(f'div_result events {len(ev):,} / {ev["stock_id"].nunique():,} stocks   '
          f'closes {len(px):,} rows')
    check_input_is_raw(ev, px)
    check_factor_identity(ev)
    check_declared_ex_date(ev)
    stocks = available_stocks()
    check_code_identities(stocks)
    check_contamination(stocks)
    check_pr_split()


if __name__ == '__main__':
    main()
