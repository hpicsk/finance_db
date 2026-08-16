"""Validation suite for cache/dividend_events.parquet.

Reproduces the numbers the kr_marcap README and the ``dividend_events`` module
docstring claim about the SEIBro total-return layer. Each check is here because
it is the one that would have caught a specific failure:

1. ex-date localisation — the derived 배당락일 is where the drop actually is.
   Cross-sectional ``r_i = a + b·yield_i`` with date fixed effects gives b ≈ -0.81
   on the derived date and ≈ 0 on both preceding sessions. A T+1/T+3 error, or a
   record-date/ex-date confusion, would smear the slope across the offsets.
2. drop-off robustness — that -0.81 is a *trimmed* estimate. Untrimmed it reads
   -0.31, not because the ex-date is wrong but because a handful of genuine
   return-of-capital distributions carry enough leverage to swing OLS on their
   own. Printed side by side so the trim is never mistaken for the headline.
3. December artifact — the reason this layer replaced the DART annual one.
   Payers vs non-payers on the same December session, price return vs
   event-level TR.
4. event placement — how many events land on a real trading row for that ticker,
   and what the rest are (issuers absent from marcap, pre-listing, post-delisting,
   genuine failures). Only the last category is a defect.
5. DART reconciliation — SEIBro events summed over a December fiscal year against
   DART's annual 주당 현금배당금 from ``cache/dividends.parquet``. The two are
   collected independently (예탁원 권리배정 record vs 사업보고서 disclosure), so
   agreement is a real check rather than a tautology. Second half: the events
   SEIBro prices at ₩0, which ``dps > 0`` discards as non-payers. If that reading
   were wrong they would be uncorrected ex-days inside ``adj_close_tr``, so the
   confirmation rate is measured against the priced control rather than assumed.

Sections 1-3 need ``marcap/`` populated, 4 needs ``cache/adj_factors.parquet``,
5 needs ``cache/dividends.parquet``. Whole run ~1 min.

Run:

    python -m kr_marcap.validate_dividend_events
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from kr_marcap.dividend_events import (EVENTS_PATH, MARCAP_DIR, _CASH_KINDS,
                                       load_cash_events)

CACHE_DIR = Path(__file__).resolve().parent / 'cache'
REPO_ROOT = Path(__file__).resolve().parents[1]

# The window the documented figures were estimated on: five full years ending
# before the 2024 배당절차 개선 finished dispersing record dates out of December.
Y0, Y1 = 2020, 2024
TRIM_Q = 0.99


def _marcap(y0: int = Y0, y1: int = Y1) -> pd.DataFrame:
    mc = pd.concat([pd.read_parquet(MARCAP_DIR / f'marcap-{y}.parquet',
                                    columns=['Date', 'Code', 'Close',
                                             'ChangesRatio', 'Market'])
                    for y in range(y0, y1 + 1)], ignore_index=True)
    mc = mc[mc['Market'].isin(['KOSPI', 'KOSDAQ']) & (mc['Code'].str.len() == 6)]
    mc['Date'] = pd.to_datetime(mc['Date'])
    return mc


def _common_codes() -> set[str]:
    u = pd.read_parquet(CACHE_DIR / 'universe_panel.parquet')
    u['code'] = u['code'].astype(str).str.zfill(6)
    return set(u[(u['kind'] == 'common')
                 & u['market'].isin(['KOSPI', 'KOSDAQ'])]['code'])


def _events_with_yield(px: pd.DataFrame) -> pd.DataFrame:
    """Cash events on the research universe, with yield against the cum-date close."""
    ev = load_cash_events()
    ev = ev[ev['record_date'].dt.year.between(Y0, Y1)
            & ev['code'].isin(_common_codes())].copy()
    cum = px['Close'].reindex(
        pd.MultiIndex.from_arrays([ev['code'], ev['cum_date']])).to_numpy()
    ev['yld'] = ev['dps'].to_numpy() / cum * 100
    return ev[np.isfinite(ev['yld'])]


def _ols(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Slope and t-stat of y on x, both demeaned. Homoskedastic se — the point
    is localisation across offsets, not a precise standard error."""
    x, y = x - x.mean(), y - y.mean()
    b = (x @ y) / (x @ x)
    res = y - b * x
    se = np.sqrt((res @ res) / (len(x) - 1) / (x @ x))
    return b, b / se


def check_ex_date_localisation(mc: pd.DataFrame, px: pd.DataFrame,
                               ev: pd.DataFrame) -> None:
    cal = np.sort(mc['Date'].unique())
    mkt = mc.groupby('Date')['ChangesRatio'].mean()

    # The trim is reported across levels rather than fixed at one, because it is
    # load-bearing for the slope: untrimmed reads -0.35 at ex+0 against -0.78 at
    # any trim from the top 1 % down to the top 10 %, so a single quoted level
    # would hide that a handful of return-of-capital events drive the difference.
    # The claim this check makes -- the drop sits on ex+0 and nowhere else --
    # holds at every level, which is what makes the free parameter harmless here.
    print(f'\n[1] ex-date localisation  (common, {Y0}-{Y1})')
    print(f'  {"trim":>6} {"n":>6} ' + ''.join(f'{f"ex{o:+d}":>9}' for o in (-2, -1, 0, 1, 2)))
    for q in (1.0, TRIM_Q, 0.95, 0.90):
        t = ev[ev['yld'] <= ev['yld'].quantile(q)]
        i0 = np.searchsorted(cal, t['ex_date'].to_numpy())
        row = []
        for off in (-2, -1, 0, 1, 2):
            d = cal[np.clip(i0 + off, 0, len(cal) - 1)]
            r = px['ChangesRatio'].reindex(
                pd.MultiIndex.from_arrays([t['code'], d])).to_numpy()
            s = pd.DataFrame({'d': d, 'r': r, 'y': t['yld'].to_numpy()}).dropna()
            rd = s['r'] - s.groupby('d')['r'].transform('mean')
            b, _ = _ols(s['y'].to_numpy(), rd.to_numpy())
            row.append(b)
        lab = 'none' if q == 1.0 else f'top-{(1 - q) * 100:.0f}%'
        print(f'  {lab:>6} {len(t):>6,} ' + ''.join(f'{b:>9.3f}' for b in row))

    t = ev[ev['yld'] <= ev['yld'].quantile(TRIM_Q)]
    i0 = np.searchsorted(cal, t['ex_date'].to_numpy())
    print(f'  mean abnormal return at trim top-{(1 - TRIM_Q) * 100:.0f}% (n={len(t):,}):')
    for off in (-2, -1, 0, 1, 2):
        d = cal[np.clip(i0 + off, 0, len(cal) - 1)]
        r = px['ChangesRatio'].reindex(
            pd.MultiIndex.from_arrays([t['code'], d])).to_numpy()
        s = pd.DataFrame({'d': d, 'r': r}).dropna()
        ar = s['r'].to_numpy() - mkt.reindex(s['d']).to_numpy()
        print(f'    ex{off:+d} {np.nanmean(ar) * 100:>7.0f} bp')
    print('  → the drop lands on ex+0 at every trim; the two preceding sessions are '
          'flat, which is what pins the derived date')


def check_dropoff_robustness(px: pd.DataFrame, ev: pd.DataFrame) -> None:
    r = px['ChangesRatio'].reindex(
        pd.MultiIndex.from_arrays([ev['code'], ev['ex_date']])).to_numpy()
    t = pd.DataFrame({'date': ev['ex_date'].values, 'r': r,
                      'yld': ev['yld'].to_numpy()}).dropna()
    t = t[t['yld'] > 0]
    t['rd'] = t['r'] - t.groupby('date')['r'].transform('mean')

    print(f'\n[2] drop-off robustness  (n={len(t)})')
    b, _ = _ols(t['yld'].to_numpy(), t['rd'].to_numpy())
    print(f'  untrimmed                 {b:>7.3f}')
    for q in (0.99, 0.98, 0.95):
        s = t[t['yld'] <= t['yld'].quantile(q)]
        b, _ = _ols(s['yld'].to_numpy(), s['rd'].to_numpy())
        print(f'  top-{(1 - q) * 100:>2.0f}% yield trimmed      {b:>7.3f}   n={len(s)}')
    big = ev.nlargest(4, 'yld')[['code', 'ex_date', 'dps', 'yld']]
    print(f'  highest yields (p99={t["yld"].quantile(.99):.1f}%, '
          f'max={t["yld"].max():.1f}%) — return-of-capital, still reinvested in full:')
    for _, x in big.iterrows():
        print(f'    {x["code"]}  {x["ex_date"].date()}  dps={x["dps"]:>8,.0f}  '
              f'yld={x["yld"]:>5.1f}%')


def check_december_artifact(mc: pd.DataFrame, px: pd.DataFrame) -> None:
    """Payer vs non-payer on the same session, price return vs event-level TR.

    Deliberately *not* restricted to the common-stock universe: a preferred share
    that pays is a payer. Filtering the event set to common stock would leave
    those in the control group, which then drops on the ex-date too and biases
    the gap toward zero (-127 bp instead of -155 bp).
    """
    cal = np.sort(mc['Date'].unique())
    ev = load_cash_events()
    cum = px['Close'].reindex(
        pd.MultiIndex.from_arrays([ev['code'], ev['cum_date']])).to_numpy()
    ev = ev.assign(yld=ev['dps'].to_numpy() / cum * 100)
    ev = ev[np.isfinite(ev['yld'])]
    add = ev.groupby(['code', 'ex_date'])['yld'].sum()
    mci = mc.set_index(['Code', 'Date'])
    mci['tr'] = mci['ChangesRatio'] + add.reindex(mci.index).fillna(0.0)
    m = mci.reset_index()
    payers = {y: set(ev.loc[(ev['record_date'].dt.year == y)
                            & (ev['record_date'].dt.month == 12), 'code'])
              for y in range(Y0, Y1 + 1)}

    print(f'\n[3] December artifact — payer minus non-payer, {Y0}-{Y1} mean (bp)')
    print(f'  {"session":>9} {"price return":>13} {"event TR":>10}')
    for pos in range(-5, 0):
        a, b = [], []
        for y in range(Y0, Y1 + 1):
            days = cal[(cal >= np.datetime64(f'{y}-12-01'))
                       & (cal < np.datetime64(f'{y + 1}-01-01'))]
            s = m[m['Date'] == days[pos]]
            d = s['Code'].isin(payers[y])
            a.append(s.loc[d, 'ChangesRatio'].mean() - s.loc[~d, 'ChangesRatio'].mean())
            b.append(s.loc[d, 'tr'].mean() - s.loc[~d, 'tr'].mean())
        tag = '  ← 배당락' if pos == -2 else ''
        print(f'  {pos:>9} {np.mean(a) * 100:>12.0f} {np.mean(b) * 100:>10.0f}{tag}')
    print('  → the pos -2 hole closes; what remains is the ex-day tax/clientele '
          'effect, not a data defect')


def check_event_placement() -> None:
    ev = load_cash_events()
    f = pd.read_parquet(CACHE_DIR / 'adj_factors.parquet',
                        columns=['date', 'code', 'valid'])
    f['date'] = pd.to_datetime(f['date'])
    f = f[f['valid'].fillna(True)]
    rows = set(map(tuple, f[['code', 'date']].to_numpy()))
    codes = set(f['code'])
    span = f.groupby('code')['date'].agg(['min', 'max'])

    placed = np.array([(c, d) in rows for c, d in zip(ev['code'], ev['ex_date'])])
    un = ev[~placed].copy()
    no_code = ~un['code'].isin(codes)
    rest = un[~no_code].join(span, on='code')
    before = rest['ex_date'] < rest['min']
    after = rest['ex_date'] > rest['max']
    inside = rest[~before & ~after]

    print(f'\n[4] event placement  ({len(ev):,} cash events, full history)')
    print(f'  ex_date on a real trading row     {placed.sum():>7,} '
          f'({placed.mean() * 100:.1f}%)')
    print(f'  ticker absent from marcap         {no_code.sum():>7,}   '
          f'비상장 / K-OTC / 프리보드')
    print(f'  before first listed session       {before.sum():>7,}')
    print(f'  after last listed session         {after.sum():>7,}')
    print(f'  inside a listed window, no row    {len(inside):>7,}   '
          f'← genuine failures ({len(inside) / len(ev) * 100:.2f}%)')
    if len(inside):
        print(inside[['code', 'record_date', 'ex_date', 'dps']]
              .head(8).to_string(index=False))


def check_dart_reconciliation() -> None:
    """SEIBro events summed per December fiscal year vs DART's annual DPS.

    Restricted to December-fiscal-year issuers: SEIBro is keyed by 배정기준일, so
    summing calendar-year events only equals the fiscal-year total when FY == CY.
    """
    ev = load_cash_events().copy()
    dart = pd.read_parquet(CACHE_DIR / 'dividends.parquet')
    dart['code'] = dart['code'].astype(str).str.zfill(6)
    dart = dart[dart['dps'].notna() & (dart['dps'] > 0)]

    ev['cy'] = ev['record_date'].dt.year
    dec = ev.groupby('code')['record_date'].apply(lambda s: (s.dt.month == 12).any())
    seibro = (ev[ev['code'].isin(set(dec[dec].index))]
              .groupby(['code', 'cy'])['dps'].sum()
              .rename('seibro_dps').reset_index())
    j = dart.merge(seibro, left_on=['code', 'fiscal_year'],
                   right_on=['code', 'cy'], how='inner')
    j['rel'] = (j['seibro_dps'] - j['dps']).abs() / j['dps']

    # Whole calendar, not a cut-off slice. An earlier version split on
    # delisting_date > 2021-01-01 and labelled the remainder 'still listed',
    # which silently filed 360 rows / 62 pre-2021 delistings under 'still
    # listed' — the survivorship subset then read 98.9% because it excluded
    # the older, messier delistings rather than because delisted issuers
    # reconcile better. The cut-off was also a free parameter no result needs.
    dl = pd.read_csv(REPO_ROOT / 'kr_delisted' / 'delisting_calendar.csv',
                     dtype={'ticker': str})
    delisted = set(dl['ticker'])

    print(f'\n[5] DART reconciliation  ({len(j):,} of {len(dart):,} DART '
          f'(ticker, FY) rows matched to a SEIBro Dec-FY sum)')
    print(f'  {"subset":26} {"n":>6} {"±0.5원":>8} {"±1%":>7} {"±5%":>7}')
    for lab, s in [('all', j),
                   (f'FY{Y0}-{Y1}', j[j['fiscal_year'].between(Y0, Y1)]),
                   ('delisted (KIND, any year)', j[j['code'].isin(delisted)]),
                   ('never delisted', j[~j['code'].isin(delisted)])]:
        if not len(s):
            continue
        exact = ((s['seibro_dps'] - s['dps']).abs() < 0.51).mean() * 100
        print(f'  {lab:26} {len(s):>6} {exact:>7.1f}% '
              f'{(s["rel"] <= 0.01).mean() * 100:>6.1f}% '
              f'{(s["rel"] <= 0.05).mean() * 100:>6.1f}%')
    print('  → the delisted subset is the one that matters: it is the survivorship '
          'evidence')

    # The premise under `dps > 0`: a zero means the company paid nothing, not
    # that SEIBro lost the amount. Read the other way, every zero would be an
    # uncorrected ex-day drop sitting in adj_close_tr, so the layer rests on
    # this. None of the zeros shares a 기준일 with a priced row — they are
    # standalone events, not the 대주주 half of a 차등배당 — which leaves DART as
    # the only independent test. A missing amount would confirm at the priced
    # rate; a real non-payment confirms near zero.
    allev = pd.read_parquet(EVENTS_PATH)
    allev = allev[allev['kind'].isin(_CASH_KINDS)].copy()
    allev['fy'] = allev['record_date'].dt.year
    fy0, fy1 = int(dart['fiscal_year'].min()), int(dart['fiscal_year'].max())
    paid = set(zip(dart['code'], dart['fiscal_year']))
    sib = set(map(tuple, allev.loc[allev['dps'] > 0,
                                   ['code', 'record_date']].to_numpy()))
    zero = allev[allev['dps'] == 0]
    shared = np.fromiter(((c, d) in sib for c, d in
                          zip(zero['code'], zero['record_date'])),
                         dtype=bool, count=len(zero))

    print(f'\n  ₩0 cash events: is a zero a non-payment or a lost amount?  '
          f'(n={len(zero):,}, {int(shared.sum())} sharing a 기준일 with a priced row)')
    print(f'  {"subset":26} {"n":>6} {"DART reports a payment":>24}')
    for lab, s in (('dps == 0', zero), ('dps > 0  (control)', allev[allev['dps'] > 0])):
        w = s[s['fy'].between(fy0, fy1)]
        hit = np.fromiter(((c, y) in paid for c, y in zip(w['code'], w['fy'])),
                          dtype=bool, count=len(w))
        print(f'  {lab:26} {len(w):>6} {hit.sum():>15,} ({hit.mean() * 100:.1f}%)')
    print(f'  → a zero reads as a real non-payment. The first row is the '
          f'false-negative rate of `dps > 0`, bounded only over FY{fy0}-{fy1}')


if __name__ == '__main__':
    mc = _marcap()
    px = mc.set_index(['Code', 'Date'])
    ev = _events_with_yield(px)
    print(f'dividend_events validation — {len(ev):,} cash events on '
          f'KOSPI+KOSDAQ common, {Y0}-{Y1}', file=sys.stderr)

    check_ex_date_localisation(mc, px, ev)
    check_dropoff_robustness(px, ev)
    check_december_artifact(mc, px)
    check_event_placement()
    check_dart_reconciliation()
