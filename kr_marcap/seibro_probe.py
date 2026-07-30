"""Raw SEIBro endpoint probe — protocol inspection for dividend_events.

``dividend_events.py`` reads one grid from SEIBro's WebSquare/proworks servlet
and keeps nine of its columns. This is the tool that endpoint was reverse-
engineered with, kept so the wire protocol can be re-checked directly when a
build looks wrong, without editing the collector.

Three questions it answers:

``raw``    what the server actually returns for a window — *every* field, not
           the nine ``_FIELDS`` keeps. This is how the 차등배당 double-count was
           found: two ``<result>`` blocks identical except ``DIFF_ALOC_AMT`` /
           ``DIFF_ALOC_RATIO3``, which the loader drops, so summing them doubled
           the dividend. Use it before trusting any new field.
``count``  the count query (``divStatInfoListCnt``) against the rows the list
           query actually serves, per quarter. The two disagree by a stable
           fraction server-side and narrowing the window does not recover it;
           ``build_dividend_events`` tolerates that up to ``_SHORTFALL_TOL`` and
           raises past it. This shows which quarter moved.
``hole``   where a window starts failing. SEIBro answers some legacy ranges with
           a ``<WARNING>서버오류2</WARNING>`` envelope instead of rows — end-2004
           serves rows 1-325 and refuses everything past it, single-row requests
           included, deterministically. Bisects for that first bad offset.

Run:

    python -m kr_marcap.seibro_probe raw 20231201 20231231 --rows 3
    python -m kr_marcap.seibro_probe raw 20231201 20231231 --code 000480   # 차등배당
    python -m kr_marcap.seibro_probe count 2004 2023
    python -m kr_marcap.seibro_probe hole 20041001 20041231
"""
from __future__ import annotations

import argparse
import re

from kr_marcap.dividend_events import _count, _is_error, _post, _session


def _parse_all(txt: str) -> list[dict]:
    """Every field of every row, unmapped — the loader's ``_parse`` keeps nine."""
    return [dict(re.findall(r'<(\w+)\s+value="([^"]*)"', block))
            for block in re.findall(r'<result>(.*?)</result>', txt, re.S)]


def cmd_raw(lo: str, hi: str, rows: int, code: str | None = None) -> None:
    s = _session()
    # The endpoint pages by offset, not by ticker, so a single-issuer look-up
    # pulls the window and filters here. Keep the window narrow when using --code.
    txt = _post(s, 'divStatInfoPList', lo, hi, 1, 100000 if code else max(rows, 1))
    print(f'{lo}..{hi}   {len(txt)} chars   error_envelope={_is_error(txt)}   '
          f'LIST_CNT={_count(s, lo, hi)}')
    print('\n--- envelope head ---')
    print(txt[:400].replace('><', '>\n<'))
    parsed = _parse_all(txt)
    if code:
        parsed = [r for r in parsed if r.get('SHOTN_ISIN') == code]
    print(f'\n--- {len(parsed)} <result> blocks, first {min(rows, len(parsed))} ---')
    for r in parsed[:rows]:
        print()
        for k, v in r.items():
            if v:
                print(f'  {k:26} {v}')


def cmd_count(years: list[int]) -> None:
    s = _session()
    print(f'{"window":>20} {"LIST_CNT":>9} {"served":>7} {"gap":>6}  note')
    for y in years:
        for lo, hi in (('0101', '0331'), ('0401', '0630'),
                       ('0701', '0930'), ('1001', '1231')):
            a, b = f'{y}{lo}', f'{y}{hi}'
            n = _count(s, a, b)
            txt = _post(s, 'divStatInfoPList', a, b, 1, 100000)
            served = 0 if _is_error(txt) else len(_parse_all(txt))
            note = '서버오류2 — run `hole`' if _is_error(txt) else ''
            print(f'{a}..{b:>8} {n:>9} {served:>7} {n - served:>6}  {note}')


def cmd_hole(lo: str, hi: str) -> None:
    """Locate the first row offset SEIBro refuses to serve in this window.

    Assumes the boundary is monotone — every offset past the first bad one also
    fails — which is what end-2004 does. The two endpoints are probed first, so a
    window that is wholly fine or wholly broken is reported as such rather than
    bisected into a meaningless answer.
    """
    s = _session()
    total = _count(s, lo, hi)

    def ok(i: int) -> bool:
        return not _is_error(_post(s, 'divStatInfoPList', lo, hi, i, i))

    print(f'{lo}..{hi}   LIST_CNT={total}')
    if total == 0:
        print('  empty window — nothing to probe')
        return
    if ok(total):
        print(f'  rows 1..{total} all serve — no hole')
        return
    if not ok(1):
        print('  row 1 already refused — the whole window is unreachable')
        return

    good, bad = 1, total                      # ok(good), not ok(bad)
    while bad - good > 1:
        mid = (good + bad) // 2
        if ok(mid):
            good = mid
        else:
            bad = mid
    print(f'  rows 1..{good} serve; {bad}..{total} refused '
          f'({total - good} of {total} lost, {(total - good) / total:.1%})')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('raw', help='dump every field of a window')
    p.add_argument('lo'); p.add_argument('hi')
    p.add_argument('--rows', type=int, default=3)
    p.add_argument('--code', help='keep only this 6-digit ticker')
    p = sub.add_parser('count', help='LIST_CNT vs rows served, per quarter')
    p.add_argument('years', nargs='+', type=int)
    p = sub.add_parser('hole', help='bisect for the first refused row offset')
    p.add_argument('lo'); p.add_argument('hi')
    a = ap.parse_args()

    if a.cmd == 'raw':
        cmd_raw(a.lo, a.hi, a.rows, a.code)
    elif a.cmd == 'count':
        cmd_count(a.years)
    else:
        cmd_hole(a.lo, a.hi)
