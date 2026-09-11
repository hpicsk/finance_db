"""When a fundamental figure could first have been read: the deadline, or the filing.

``fin_is/``, ``fin_bs/`` and ``fin_cf/`` are keyed on the quarter that closed —
2005-03-31, 2005-06-30, … — not on the day the filing became public, and carry
no column for the latter. ``month_rev/`` has a ``create_time`` field that would,
and it is blank on every row. Joining any of them to prices on ``date`` hands a
trader figures weeks before they existed.

Two answers to that, and they answer different questions. ``available_date``
computes the statutory filing deadline: the **latest** date by which the figure
had to be public. That is a bound in the safe direction — assume a figure
arrived at its deadline and you can never use it before it existed — and it is
deliberately loose in two places named at the bottom. ``observed_date`` reads
the day the filing actually landed instead, which is tighter wherever the
document server carried the report and absent where it did not.

``date`` is never overwritten. ``available_date`` and ``observed_date`` are new
columns beside it, so the fiscal period a row describes and the day it could be
traded on stay separate facts.

**The window spans a regime change**, which is why the deadlines live in
``filing_deadlines.csv`` rather than in constants here. The 2010-06-02 amendment
to 證券交易法 §36 took effect 自一百零一年一月一日 (2012-01-01) and shortened the
annual report from four months to three. A single constant fitted to either side
of that is wrong for a third of the window.

**The half-year breaks a year later than the rest of it.** §36 I(2) reads
第一季、第二季及第三季終了後四十五日內, and the 第二季 in it arrives with the
一百零一年一月四日 amendment, which §183 defers 自一百零二會計年度. So the
一百零一會計年度 mid-year document is still the 半年度財務報告 on the pre-2012
terms — 2 months, 75 days consolidated — and the table carries the two as
separate rows rather than one boundary. The filings agree with the statute about
where the break is: the FY2012 half-year files at a median 61 days like FY2011,
and FY2013 at 44.

**Consolidated, not parent-only.** Under the pre-2012 regime a first- or
third-quarter report was due one month after quarter end, with the *consolidated*
statements allowed 45 days, and the half-year report two months with 75 days for
consolidated. ``fin_is/`` carries consolidated line items —
``EquityAttributableToOwnersOfParent``,
``ComprehensiveIncomeConsolidatedNetIncomeAttributedNonControllingInterest`` —
so the back-stop is the deadline that binds, and it is also the later of the two,
which is the direction this module errs in on purpose.

**Monthly revenue is already offset.** ``month_rev.date`` is the first of the
month *after* the revenue month — 2011-02-01 carries ``revenue_month`` 1 of
2011, on all 320,533 in-window rows — so the deadline is the 10th of that same
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
existed. That is the one direction the deadline cannot bound away on its own,
and it is what ``observed_date`` below is for. ``filing_dates.parquet`` carries
the 上傳日期 of the report that first made each company-quarter public, collected
by ``filing_dates.py`` from TWSE's document server, and against it 6.56 % of the
company-quarters ending 2011-12-31..2024-12-31 were published after their
deadline (README caveat 9).

The tradable gap is wider than the published one, because three quarters of
reports are uploaded after the session closes: **14.66 %** of those
company-quarters could not be traded on by their deadline, against the 6.56 %
that were filed after it. The deadline is still the right default — it is what
the law required, it needs no external file, and where it holds it is tight, a
median three days ahead — but a study that cannot afford a look-ahead on one
quarter in seven should join ``observed_date`` instead.

The result carries the index of what was passed in, so
``d['deadline'] = available_date(d.period_end)`` lands on a filtered frame
rather than aligning against a RangeIndex the frame no longer has.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DEADLINES_PATH = ROOT / 'filing_deadlines.csv'
FILING_DATES_PATH = ROOT / 'filing_dates.parquet'

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
    pe_in = pd.Series(period_end)
    # Internals run on a fresh RangeIndex: the rule loop assigns through a
    # boolean mask, which pandas aligns on labels, and a duplicated label in a
    # concatenated panel would scatter the result. The caller's index is put
    # back on the way out so the return can be assigned to a filtered frame.
    pe = pd.to_datetime(pe_in).reset_index(drop=True)
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
    return (out + pd.Timedelta(days=extra_days)).set_axis(pe_in.index)


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


# TWSE's regular session ends at 13:30 and has for the whole window, so a report
# uploaded after it could not be acted on at that day's close and the first
# close that can be traded on its figures is the next session's. Three quarters
# of filings land after this hour, which is why the observed date is a roll and
# not a `.dt.normalize()` — README caveat 9. After-hours odd-lot trading at
# 14:00 settles at the closing price already set, so it does not move the hour;
# and rolling a borderline filing forward errs later, which is the direction
# this module errs in throughout.
SESSION_CLOSE = pd.Timedelta(hours=13, minutes=30)


def _filings() -> pd.DataFrame:
    """The collected 上傳日期 panel, one row per company-quarter."""
    if not FILING_DATES_PATH.exists():
        raise FileNotFoundError(
            f'{FILING_DATES_PATH} is missing — it is collected by '
            f'filing_dates.py, one request per company against TWSE\'s document '
            f'server and then --consolidate. There is nothing to fall back on: '
            f'the deadline is a different answer, and it is what '
            f'available_date returns.')
    d = pd.read_parquet(FILING_DATES_PATH,
                        columns=['stock_id', 'period_end', 'first_public'])
    dup = int(d.duplicated(['stock_id', 'period_end']).sum())
    if dup:
        raise ValueError(
            f'{dup} company-quarters appear twice in {FILING_DATES_PATH.name}; '
            f'a left join on a duplicated key multiplies rows rather than '
            f'dating them, so the panel is rebuilt rather than joined as is.')
    return d


def observed_date(stock_id, period_end) -> pd.Series:
    """First date each company-quarter's figures could be traded on, as observed.

    ``available_date`` returns what the law required; this returns what the
    company did. The 上傳日期 of the earliest Chinese report for the period comes
    from ``filing_dates.parquet``, and a filing that landed after
    ``SESSION_CLOSE`` is dated to the next day, because the first close its
    figures can be traded at is the following session's.

    ``NaT`` where the panel carries no filing for that company-quarter — 19 of
    the 106,472 in-window quarters ``fin_is`` holds, almost all of them an annual
    report from before the company listed or after it left, which the vendor
    kept and the document server never carried. They are left undated rather
    than dated by the deadline: substituting the bound there would put back
    exactly the look-ahead this function exists to remove, and a ``NaT`` drops
    the row from a join where a substituted date trades it.

    Financial statements only. ``filing_dates.parquet`` is 財務報告書, so monthly
    revenue has no observed date here and its period ends are refused rather
    than returned as an all-``NaT`` column that looks like missing data.
    """
    sid_in, pe_in = pd.Series(stock_id), pd.Series(period_end)
    if len(sid_in) != len(pe_in):
        raise ValueError(f'stock_id and period_end must be the same length, '
                         f'not {len(sid_in)} and {len(pe_in)}')
    # Internals run on a fresh RangeIndex for the same reason available_date
    # does — a merge reindexes, and a duplicated label in a concatenated panel
    # would scatter the result — and the caller's index goes back on at the end.
    keys = pd.DataFrame({'stock_id': sid_in.astype(str).to_numpy(),
                         'period_end': pd.to_datetime(pe_in).to_numpy()})
    qe = keys['period_end']
    bad = keys[~(qe.dt.month.isin(_RULE_BY_MONTH)
                 & (qe == qe + pd.offsets.MonthEnd(0)))]
    if len(bad):
        raise ValueError(
            f'{len(bad)} period ends are not quarter ends — '
            f'{sorted(bad["period_end"].dt.strftime("%Y-%m-%d").unique())[:3]}. '
            f'{FILING_DATES_PATH.name} dates 財務報告書 and is keyed on 03-31, '
            f'06-30, 09-30 and 12-31; month_rev has no filing date here.')

    filed = keys.merge(_filings(), on=['stock_id', 'period_end'],
                       how='left')['first_public']
    day = filed.dt.normalize()
    # NaT stays NaT: the comparison is False on a missing filing, so the roll
    # adds nothing and the absence survives instead of becoming a date.
    return (day + pd.to_timedelta(((filed - day) > SESSION_CLOSE).astype(int),
                                  unit='D')).set_axis(sid_in.index)


def with_observed_date(df: pd.DataFrame) -> pd.DataFrame:
    """``df`` with an ``observed_date`` column beside its ``date``.

    ``date`` is untouched, as in ``with_available_date``: the fiscal period the
    row describes and the day it became tradable are two separate facts.
    """
    if 'observed_date' in df.columns:
        raise ValueError('df already carries an observed_date column')
    missing = [c for c in ('stock_id', 'date') if c not in df.columns]
    if missing:
        raise ValueError(
            f'df is missing {missing} — an observed date is per company as well '
            f'as per period, unlike the deadline, which the period alone fixes.')
    out = df.copy()
    out['observed_date'] = observed_date(out['stock_id'], out['date']).to_numpy()
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

    d = with_observed_date(pd.read_parquet(ROOT / 'fin_is/2330.parquet'))
    d = with_available_date(d)
    s = (d[['date', 'available_date', 'observed_date']].drop_duplicates()
         .assign(bound_early=lambda x: (x['available_date']
                                        - x['observed_date']).dt.days))
    print(f'\nfin_is/2330.parquet  deadline against filing, {len(s)} periods')
    print(s.tail(4).to_string(index=False))
    print(f'  deadline precedes the filing on '
          f'{int((s["bound_early"] < 0).sum())} of {len(s)}')
