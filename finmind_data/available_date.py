"""When a fundamental figure could first have been read, as a bound.

``fin_is/``, ``fin_bs/`` and ``fin_cf/`` are keyed on the quarter that closed —
2005-03-31, 2005-06-30, … — not on the day the filing became public, and carry
no column for the latter. ``month_rev/`` has a ``create_time`` field that would,
and it is blank on every row. Joining any of them to prices on ``date`` hands a
trader figures weeks before they existed.

There is no announcement date to be had from this package, so what is computed
here is the statutory filing deadline: the **latest** date by which the figure
had to be public. That is a bound in the safe direction — assume a figure
arrived at its deadline and you can never use it before it existed — and it is
deliberately loose in two places named at the bottom.

``date`` is never overwritten. ``available_date`` is a new column beside it, so
the fiscal period a row describes and the day it could be traded on stay
separate facts.

**The window spans a regime change**, which is why the deadlines live in
``filing_deadlines.csv`` rather than in constants here. The 2010-06-02 amendment
to 證券交易法 §36 took effect 自一百零一年一月一日 (2012-01-01) and shortened the
annual report from four months to three and the half-year report from a
75-day consolidated back-stop to 45 days. A single constant fitted to either
side of that is wrong for a third of the window.

**Consolidated, not parent-only.** Under the pre-2012 regime a first- or
third-quarter report was due one month after quarter end, with the *consolidated*
statements allowed 45 days, and the half-year report two months with 75 days for
consolidated. ``fin_is/`` carries consolidated line items —
``EquityAttributableToOwnersOfParent``,
``ComprehensiveIncomeConsolidatedNetIncomeAttributedNonControllingInterest`` —
so the back-stop is the deadline that binds, and it is also the later of the two,
which is the direction this module errs in on purpose.

**Monthly revenue is already offset.** ``month_rev.date`` is the first of the
month *after* the revenue month — 2005-01-01 carries ``revenue_month`` 12 of
2004, on all 80,292 rows checked — so the deadline is the 10th of that same
month, nine days later, not a month and nine days.

**Two ways this bound stays loose**, both left in rather than closed:

*Shortened deadlines are not applied.* A listed company with paid-in capital of
NT$10bn or more files its annual report within 75 days rather than three months
from the ROC 111 (FY2022) accounts, and financial-sector issuers file earlier
still under 公開發行公司財務報告及營運情形公告申報特殊適用範圍辦法. Every such
rule *shortens* the deadline, so the general one remains a valid upper bound for
the companies they cover, and using it costs power rather than correctness.
``entity_class`` is a column of the rule table with one value, ``all``, so a
sourced row can be added as data when the classification is worth verifying.

That every variant shortens is a property of *this* universe, not of Taiwanese
law: ``universe.parquet`` is 上市 (``twse``) and 上櫃 (``tpex``) issuers only, so
the longer deadline an unlisted public company gets, and the quarterly exemption
the pre-2012 regime gave 興櫃 companies, reach nothing here. A universe widened
to either would need its own rows before this module could be trusted on them.

*A late filer is not covered.* The deadline is what the law required, not what
the company did. A company that filed late — or one granted a 不可抗力 extension,
which both regimes allow on application within three days — published after the
date computed here, and joining on it hands a trader that figure before it
existed. That is the one direction this module cannot bound away without the
announcement dates, which live in 公開資訊觀測站 filings that no FinMind endpoint
mirrors.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DEADLINES_PATH = ROOT / 'filing_deadlines.csv'

# Quarter-end month → the rule row that governs it. `fin_*` is dated on exactly
# these four; a 12-31 row is the annual report, not a fourth quarterly one.
_RULE_BY_MONTH = {3: 'q1', 6: 'q2', 9: 'q3', 12: 'annual'}


def _rules() -> pd.DataFrame:
    """The versioned deadline table, dates parsed.

    Hand-maintained and version-controlled: each row cites the instrument it
    comes from, and a rule change is a row rather than an edit to a constant.
    """
    if not DEADLINES_PATH.exists():
        raise FileNotFoundError(
            f'{DEADLINES_PATH} is missing — it is the source of every filing '
            f'deadline this module applies, and there is no default to fall '
            f'back on that would not be a guess.')
    r = pd.read_csv(DEADLINES_PATH, dtype=str).fillna('')
    r['effective_from'] = pd.to_datetime(r['effective_from'])
    # An open-ended row runs to the end of time rather than to the download's
    # last date, so adding data does not silently leave rows unruled.
    r['effective_to'] = pd.to_datetime(r['effective_to'].replace('', None)).fillna(
        pd.Timestamp.max.normalize())
    return r


def _apply(lag_rule: str, period_end: pd.Series) -> pd.Series:
    """One rule's ``lag_rule`` token applied to the period ends it governs."""
    kind, _, n = lag_rule.partition(':')
    n = int(n)
    if kind == 'months':
        # DateOffset clips to the shorter month, which is what a "within N
        # months of year end" deadline means: 2011-12-31 + 3 → 2012-03-31.
        return period_end + pd.DateOffset(months=n)
    if kind == 'days':
        return period_end + pd.Timedelta(days=n)
    if kind == 'next_month_day':
        # month_rev.date is already the first of the month after the revenue
        # month, so the deadline is that month's Nth day.
        return period_end + pd.Timedelta(days=n - 1)
    raise ValueError(f'unknown lag_rule {lag_rule!r} in {DEADLINES_PATH.name}')


def available_date(period_end, kind: str = 'financial_statement',
                   extra_days: int = 0) -> pd.Series:
    """Statutory deadline for the period each ``period_end`` closes.

    ``kind`` is ``'financial_statement'`` for ``fin_is`` / ``fin_bs`` / ``fin_cf``,
    whose rule follows from the quarter-end month, or ``'monthly_revenue'`` for
    ``month_rev``.

    ``extra_days`` is added on top. It is a research parameter, not a
    correction: whether a signal survives being read a fortnight later is a
    property of the signal worth measuring, and the deadline itself is already
    the latest lawful date.

    Raises if any period end falls outside every rule's window rather than
    returning NaT, since a silent NaT here drops rows from a join and looks
    like missing data instead of a missing rule.
    """
    pe = pd.to_datetime(pd.Series(period_end)).reset_index(drop=True)
    if kind == 'monthly_revenue':
        want = pd.Series('monthly_revenue', index=pe.index)
    elif kind == 'financial_statement':
        want = pe.dt.month.map(_RULE_BY_MONTH)
        bad = pe[want.isna()]
        if len(bad):
            raise ValueError(
                f'{len(bad)} period ends are not quarter ends — '
                f'{sorted(bad.dt.strftime("%Y-%m-%d").unique())[:3]}. '
                f'fin_is/fin_bs/fin_cf are dated on 03-31, 06-30, 09-30 and '
                f'12-31 only, so a different date is a different dataset.')
    else:
        raise ValueError(f'kind must be financial_statement or monthly_revenue, '
                         f'not {kind!r}')

    out = pd.Series(pd.NaT, index=pe.index, dtype='datetime64[ns]')
    for _, rule in _rules().iterrows():
        m = ((want == rule['rule_type'])
             & (pe >= rule['effective_from']) & (pe <= rule['effective_to']))
        if m.any():
            out[m] = _apply(rule['lag_rule'], pe[m])
    if out.isna().any():
        miss = pe[out.isna()]
        raise ValueError(
            f'{len(miss)} period ends are covered by no row of '
            f'{DEADLINES_PATH.name} — first {miss.min().date()}, last '
            f'{miss.max().date()}. Extend the table rather than letting these '
            f'join as NaT.')
    return out + pd.Timedelta(days=extra_days)


def with_available_date(df: pd.DataFrame, kind: str = 'financial_statement',
                        extra_days: int = 0) -> pd.DataFrame:
    """``df`` with an ``available_date`` column beside its ``date``.

    ``date`` is untouched: it is the fiscal period the row describes, and
    overwriting it would destroy the only key that says which period a figure
    belongs to.
    """
    if 'available_date' in df.columns:
        raise ValueError('df already carries an available_date column')
    out = df.copy()
    out['available_date'] = available_date(
        out['date'], kind=kind, extra_days=extra_days).to_numpy()
    return out


if __name__ == '__main__':
    for kind, pat in (('financial_statement', 'fin_is/2330.parquet'),
                      ('monthly_revenue', 'month_rev/2330.parquet')):
        d = pd.read_parquet(ROOT / pat)
        d = with_available_date(d, kind=kind)
        s = (d[['date', 'available_date']].drop_duplicates()
             .assign(lag=lambda x: (pd.to_datetime(x['available_date'])
                                    - pd.to_datetime(x['date'])).dt.days))
        print(f'\n{pat}  {len(s)} periods')
        print(s.head(3).to_string(index=False))
        print('  ...')
        print(s.tail(3).to_string(index=False))
        print(f'  lag in days: {sorted(int(x) for x in s["lag"].unique())}')
