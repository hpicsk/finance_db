"""Event-level cash-dividend collection from SEIBro → total-return layer.

Why this replaced the DART annual layer
---------------------------------------
``kr_marcap.dividends`` crawls DART's structured 배당 report, which is *annual*:
one 현금배당수익률 per (ticker, fiscal year), with no 기준일 and no 결산/중간/분기
split. ``adjust.py`` therefore had to guess where the 배당락 landed and reinvested
the whole year on the fiscal year's last trading row. Measured on 2020-2024
KOSPI+KOSDAQ common, that guess is wrong by one trading day: the 배당락 sits on
the *second*-to-last December row (폐장일 −1), so the annual bump neither cancels
the real drop nor lands on an ordinary day — it left the −135 bp ex-day artifact
in place and added a spurious +190 bp spike on 폐장일.

SEIBro (한국예탁결제원 배당내역전체검색) publishes the same dividends per *event*:
배정기준일, 배당구분 (결산/중간/분기), and 주당배당금. No API key, ~30 s for the
full 2000-2025 history. Samsung's four quarterly payments stop being one December
lump; the 배당락 lands on the day it actually happened.

배당락일 is derived, not scraped
--------------------------------
SEIBro carries 배정기준일 (record date), not 배당락일. The ex-date follows from
KRX's T+2 settlement and is exact, not a heuristic: to be on the register at the
record date a purchase must settle by it, so with ``j`` = index of the last
trading day on or before the record date, the last cum-dividend session is
``cal[j-2]`` and the ex-date is ``cal[j-1]``.

One rule covers both regimes, because it keys off the calendar rather than a
fixed offset. A 12월 결산 record date (12/31, a market holiday) puts the ex-date
one session *before* 폐장일; a 중간/분기 record date that is itself a trading day
puts it on the immediately preceding session. Validated by cross-sectional
drop-off regression ``r_i = a + b·yield_i`` with date fixed effects on 5,774
events (KOSPI+KOSDAQ common, 2020-2024): ``b = -0.809`` (t = -37.0) on the
derived ex-date against ``+0.08`` and ``+0.11`` on the two preceding sessions.
Every figure in this docstring is reproduced by
``python -m kr_marcap.validate_dividend_events``.

That regression is trimmed at the 99th percentile of yield. Untrimmed it reads
``-0.311``, not because the ex-date is wrong but because a handful of genuine
return-of-capital distributions (152550 paying ₩1,670 against a ₩1,675 close;
168490 winding down) carry enough leverage to swing the slope on their own. The
estimate is stable at -0.81/-0.81/-0.79 for 1/2/5 % trims. Those events are still
reinvested in full — the holder received the cash — they are only excluded from
*estimating* the ratio.

The residual is real, not error
-------------------------------
Against non-payers on the same session, payers run -155 bp on the December
ex-date under price return and +71 bp once each event is reinvested, versus a
+42 bp baseline on neighbouring sessions. The ~+29 bp that survives is the
well-known ex-day tax/clientele effect — Korean prices fall ~81 % of the
dividend, so (1-0.81) x 206 bp ~ 39 bp of the dividend is never given up in the
price — not a data defect: the holder did receive 100 % of the cash, so the
total-return series must add 100 %. ``load_adjusted`` exposes ``is_ex_date`` so
daily-horizon studies can flag or drop those sessions explicitly instead of
inheriting an undated contamination.

Only cash is added here. 주식배당 (``STK_ALOC_RATIO``) already resets KRX's 기준가
and is therefore inside ``ChangesRatio`` / ``adj_close`` — adding it again would
double-count.

Build (no API key needed):

    python -m kr_marcap.dividend_events build

Output: ``cache/dividend_events.parquet``
(code, record_date, ex_date, cum_date, kind, share_class, dps, stock_ratio,
 pay_date, market_label).
"""
from __future__ import annotations

import glob
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
MARCAP_DIR = REPO_ROOT / 'marcap' / 'data'
CACHE_DIR = Path(__file__).resolve().parent / 'cache'
EVENTS_PATH = CACHE_DIR / 'dividend_events.parquet'

_BASE = 'https://seibro.or.kr'
_W2X = '/IPORTAL/user/company/BIP_CNTS01041V.xml'
_ENDPOINT = f'{_BASE}/websquare/engine/proworks/callServletService.jsp'
_TASK = 'ksd.safe.bip.cnts.Company.process.EntrFnafInfoPTask'

# SEIBro's 배당내역 grid, in its own field names.
_FIELDS = {
    'RGT_STD_DT': 'record_date',            # 배정기준일
    'TH1_PAY_TERM_BEGIN_DT': 'pay_date',    # 현금배당 지급일
    'SHOTN_ISIN': 'code',
    'KOR_SECN_NM': 'name',
    'LIST_TPNM': 'market_label',            # 현재 시점 라벨 — PIT 아님 (아래 주의)
    'RGT_RSN_DTAIL_SORT_NM': 'kind',        # 현금배당 / 무배당 / 주식배당 / 동시배당
    'SECN_DTAIL_KANM': 'share_class',       # 보통주 / 우선주 / ...
    'CASH_ALOC_AMT': 'dps',                 # 주당 현금배당금
    'STK_ALOC_RATIO': 'stock_ratio',        # 주식배당률 — 이미 ChangesRatio에 반영됨
}
_CASH_KINDS = ('현금배당', '동시배당', '현물동시배당')

# The count query (divStatInfoListCnt) and the list query disagree by a stable
# ~0.4 % server-side; paging does not recover the difference. Anything larger is
# a real truncation and must fail rather than silently under-collect.
_SHORTFALL_TOL = 0.02


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0 Safari/537.36'),
        'Referer': f'{_BASE}/websquare/control.jsp?w2xPath={_W2X}&menuNo=285',
        'Content-Type': 'application/xml; charset=UTF-8',
        'Origin': _BASE,
    })
    s.get(f'{_BASE}/websquare/control.jsp?w2xPath={_W2X}&menuNo=285', timeout=30)
    return s


def _post(s: requests.Session, action: str, lo: str, hi: str,
          start: int, end: int) -> str:
    body = (
        f'<reqParam action="{action}" task="{_TASK}">'
        f'<MENU_ID value="46"/><W2XPATH value="{_W2X}"/>'
        f'<RGT_STD_DT_FROM value="{lo}"/><RGT_STD_DT_TO value="{hi}"/>'
        f'<ISSUCO_CUSTNO value=""/><KOR_SECN_NM value=""/><SECN_KACD value=""/>'
        f'<RGT_RSN_DTAIL_SORT_CD value=""/><LIST_TPCD value=""/>'
        f'<START_PAGE value="{start}"/><END_PAGE value="{end}"/>'
        f'</reqParam>'
    )
    r = s.post(_ENDPOINT, data=body.encode('utf-8'), timeout=120)
    r.raise_for_status()
    return r.content.decode('utf-8', 'replace')


def _count(s: requests.Session, lo: str, hi: str) -> int:
    m = re.search(r'<LIST_CNT value="(\d+)"', _post(s, 'divStatInfoListCnt', lo, hi, 1, 15))
    if m is None:
        raise RuntimeError(f'SEIBro count query returned no LIST_CNT for {lo}..{hi}')
    return int(m.group(1))


def _parse(txt: str) -> list[dict]:
    rows = []
    for block in re.findall(r'<result>(.*?)</result>', txt, re.S):
        d = dict(re.findall(r'<(\w+)\s+value="([^"]*)"', block))
        rows.append({dst: d.get(src) for src, dst in _FIELDS.items()})
    return rows


def _is_error(txt: str) -> bool:
    """SEIBro answers some legacy ranges with a ``<WARNING>서버오류2</WARNING>``
    envelope instead of rows. It parses to zero results, so it must be detected
    explicitly or a failed window is indistinguishable from an empty one."""
    return '<WARNING>' in txt[:400]


def _fetch(s: requests.Session, lo: str, hi: str, page: int = 300) -> tuple[list[dict], int]:
    """Rows in a record-date window, plus the count SEIBro refused to serve.

    One request covers a normal window. Where the server errors, it does so for
    every request touching the offending offsets — end-2004 serves rows 1-325 and
    fails on anything beyond, single rows included — so the fallback walks the
    window in pages, keeps what is reachable, and counts the rest as lost instead
    of reporting a short window as complete.
    """
    txt = _post(s, 'divStatInfoPList', lo, hi, 1, 100000)
    if not _is_error(txt):
        return _parse(txt), 0

    total = _count(s, lo, hi)
    rows, lost, start = [], 0, 1
    while start <= total:
        end = min(start + page - 1, total)
        chunk = _post(s, 'divStatInfoPList', lo, hi, start, end)
        if not _is_error(chunk):
            got = _parse(chunk)
            if not got:
                break                       # server has no rows left despite LIST_CNT
            rows += got
            start = end + 1
        elif _is_error(_post(s, 'divStatInfoPList', lo, hi, start, start)):
            lost += end - start + 1         # whole page unreachable, skip past it
            start = end + 1
        else:
            rows += _parse(_post(s, 'divStatInfoPList', lo, hi, start, start))
            start += 1
    return rows, lost


def trading_calendar(marcap_dir: Path = MARCAP_DIR) -> np.ndarray:
    """Sorted market-wide trading days from marcap (the KRX session calendar)."""
    days = set()
    for fp in sorted(glob.glob(str(marcap_dir / 'marcap-*.parquet'))):
        days.update(pd.read_parquet(fp, columns=['Date'])['Date'].unique())
    if not days:
        raise FileNotFoundError(f'no marcap year files under {marcap_dir}')
    return np.sort(np.array(sorted(days), dtype='datetime64[ns]'))


def derive_ex_dates(record_dates: pd.Series, cal: np.ndarray) -> pd.DataFrame:
    """Map 배정기준일 → (ex_date, cum_date) under KRX T+2 settlement.

    ``j`` is the last trading session on or before the record date; a purchase
    settles two sessions later, so ``cal[j-2]`` is the last cum-dividend session
    and ``cal[j-1]`` is the ex-date. Record dates outside the calendar (before it
    starts, or still in the future relative to the marcap vintage) resolve to NaT
    rather than to a guessed date.
    """
    rec = pd.to_datetime(record_dates).to_numpy(dtype='datetime64[ns]')
    j = np.searchsorted(cal, rec, side='right') - 1
    ok = (j >= 2) & (rec <= cal[-1])
    ex = np.full(len(rec), np.datetime64('NaT'), dtype='datetime64[ns]')
    cum = np.full(len(rec), np.datetime64('NaT'), dtype='datetime64[ns]')
    ex[ok] = cal[j[ok] - 1]
    cum[ok] = cal[j[ok] - 2]
    return pd.DataFrame({'ex_date': ex, 'cum_date': cum}, index=record_dates.index)


def build_dividend_events(start_year: int = 2000,
                          end_year: int | None = None,
                          marcap_dir: Path = MARCAP_DIR) -> pd.DataFrame:
    """Pull every SEIBro dividend event in [start_year, end_year]; cache to parquet."""
    end_year = end_year or pd.Timestamp.today().year
    s = _session()
    rows, expected, refused = [], 0, 0
    for y in range(start_year, end_year + 1):
        y_refused = 0
        for lo, hi in (('0101', '0331'), ('0401', '0630'),
                       ('0701', '0930'), ('1001', '1231')):
            a, b = f'{y}{lo}', f'{y}{hi}'
            expected += _count(s, a, b)
            got, lost = _fetch(s, a, b)
            rows += got
            y_refused += lost
            time.sleep(0.2)
        refused += y_refused
        note = f'  ({y_refused} refused by server)' if y_refused else ''
        print(f'  {y}: {len(rows):>6} rows cumulative{note}', file=sys.stderr, flush=True)

    # Two different gaps. `refused` is SEIBro failing to serve rows it says exist
    # (a real hole — reported, never smoothed over). The remainder is the count
    # query over-reporting the list query by a stable fraction; paging and
    # narrower windows do not recover it, so it is tolerated but still bounded.
    residual = expected - len(rows) - refused
    if expected and residual / expected > _SHORTFALL_TOL:
        raise RuntimeError(
            f'SEIBro returned {len(rows)} rows against a reported {expected} '
            f'({residual} unexplained, {residual / expected:.1%}) — window '
            'truncated, beyond the known count/list discrepancy'
        )

    df = pd.DataFrame(rows)
    df['code'] = df['code'].astype(str).str.zfill(6)
    df['record_date'] = pd.to_datetime(df['record_date'], format='%Y%m%d', errors='coerce')
    df['pay_date'] = pd.to_datetime(df['pay_date'], format='%Y%m%d', errors='coerce')
    for c in ('dps', 'stock_ratio'):
        df[c] = pd.to_numeric(df[c].str.replace(',', ''), errors='coerce').fillna(0.0)
    df = df[df['record_date'].notna()].reset_index(drop=True)

    # SEIBro renders a 차등배당 (controlling holders taking less) as two rows for
    # the *same* payment — identical 기준일/종목/주당배당금, differing only in the
    # 차등 columns this loader drops. Summing them double-counts the dividend, so
    # collapse exact repeats of the event key.
    key = ['code', 'record_date', 'kind', 'share_class', 'dps']
    n_before = len(df)
    df = df.drop_duplicates(subset=key).reset_index(drop=True)
    n_dupes = n_before - len(df)

    df = df.join(derive_ex_dates(df['record_date'], trading_calendar(marcap_dir)))

    # Canary: Samsung pays quarterly from 2020 — four cash events per year, each
    # on its own 기준일. If this collapses to one row the endpoint changed shape.
    q = df[(df['code'] == '005930') & (df['record_date'].dt.year == 2023)
           & df['kind'].isin(_CASH_KINDS)]
    if len(q) != 4:
        raise RuntimeError(
            f'SEIBro canary failed: 005930 FY2023 returned {len(q)} cash events, '
            'expected 4 quarterly — endpoint or field mapping changed'
        )

    df = df.sort_values(['code', 'record_date']).reset_index(drop=True)
    df.to_parquet(EVENTS_PATH, index=False)
    cash = df[df['kind'].isin(_CASH_KINDS) & (df['dps'] > 0)]
    print(f'WROTE {EVENTS_PATH}  {df.shape}\n'
          f'  {len(cash)} cash events, {cash["code"].nunique()} tickers, '
          f'{df["record_date"].dt.year.min()}-{df["record_date"].dt.year.max()}\n'
          f'  unresolved ex_date (future/pre-calendar): {df["ex_date"].isna().sum()}\n'
          f'  차등배당 duplicate rows collapsed: {n_dupes}\n'
          f'  rows SEIBro refused to serve: {refused} of {expected} reported',
          file=sys.stderr, flush=True)
    return df


def load_cash_events(path: Path | None = None) -> pd.DataFrame:
    """Cash dividend events with a resolved ex-date: (code, ex_date, cum_date, dps).

    Preferred/common share classes carry distinct tickers, so no share-class
    filter is applied. ``market_label`` is deliberately *not* filtered on: SEIBro
    relabels delisted issuers 기타비상장 in the current snapshot, so filtering it
    would silently drop every payer that later delisted. Restrict the universe
    point-in-time via ``kr_marcap.universe`` instead.
    """
    p = Path(path or EVENTS_PATH)
    if not p.exists():
        raise FileNotFoundError(
            f'dividend events not found at {p} — run '
            '`python -m kr_marcap.dividend_events build` first'
        )
    df = pd.read_parquet(p)
    return df[df['kind'].isin(_CASH_KINDS) & (df['dps'] > 0)
              & df['ex_date'].notna()].reset_index(drop=True)


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == 'build':
        kw = {}
        for a in sys.argv[2:]:
            if a.startswith('--from='):
                kw['start_year'] = int(a.split('=')[1])
            elif a.startswith('--to='):
                kw['end_year'] = int(a.split('=')[1])
        build_dividend_events(**kw)
    else:
        ev = load_cash_events()
        s = ev[(ev['code'] == '005930') & (ev['record_date'].dt.year == 2023)]
        print('Samsung 005930 FY2023 cash-dividend events:')
        print(s[['record_date', 'ex_date', 'cum_date', 'kind', 'dps']].to_string(index=False))
