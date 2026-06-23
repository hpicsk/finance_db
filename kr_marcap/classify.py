"""Korean equity security-type classifier (pure functions).

KOSDAQ GLOBAL is a tier of KOSDAQ (premium-listed names that meet stricter
disclosure requirements) and is folded into 'common' under the KOSDAQ market.

What marcap (the universe source) does and does NOT carry — verify before
adding an "official label" collector for any of these axes:
  - marcap is 주권-only (보통주/우선주). ETF/ETN/펀드 are NOT in marcap at all
    (e.g. 069500 KODEX 200 is absent; Market ∈ {KOSPI, KOSDAQ, KONEX}). So the
    'etf' branch below never fires on marcap-sourced rows — it only matters for
    other callers (fnguide/kr_delisted exports). An official ETF/ETN label
    pull does not improve the marcap universe.
  - marcap's `Dept` column already carries official KRX 소속부 flags this
    name-based classifier deliberately does NOT read: 'SPAC(소속부없음)' (an
    official SPAC flag — better-founded than the 스팩 name match), plus
    '관리종목'/'투자주의환기종목'/'외국기업' (admin/alert/foreign — consumed by
    kr_status, see CLAUDE.md). classify_ticker takes only (code, name, market),
    so it can't see Dept; a Dept-aware caller can flag SPAC officially.
"""
from __future__ import annotations

import re

KINDS = ('common', 'preferred', 'spac', 'reit', 'fund', 'etf', 'konex', 'other')

# Compiled once at import. The preferred test is keyed on the code's terminal
# digit (KRX gives preferred shares a non-'0' last char), which is
# authoritative — see the alphanumeric-code note in classify_ticker. We do NOT
# match a 우-family name suffix: over the code test it adds zero true preferred
# and wrongly catches commons whose names merely end in 우 (대우 / 미래에셋대우
# / 포스코대우 / 연우 / 베스트플로우).
_SPAC_RE = re.compile(r'스팩|SPAC', re.IGNORECASE)
_REIT_RE = re.compile(r'리츠|REIT', re.IGNORECASE)
# Ship-investment funds (선박투자) and mutual funds (뮤추얼펀드, '…MF') → 'fund'.
# MF names carry code last-digit '0', so the preferred test above skips them.
_FUND_RE = re.compile(r'선박투자|MF$')
# ETF brand-name prefixes. Brand must be followed by whitespace so we don't
# catch e.g. "ACE손해보험" or "타임폴리오". The list covers the major and
# mid-tier brands that fnguide ships in its currently-listed export; extend
# whenever a new ETF brand appears in the universe.
_ETF_NAME_RE = re.compile(
    r'^(?:KODEX|TIGER|ARIRANG|PLUS|KINDEX|ACE|KBSTAR|RISE|SOL|HANARO|KoAct'
    r'|KIWOOM|TREX|KOSEF|TIME|ITF|1Q|HK|FOCUS|WON|마이티|에셋플러스|아이엠에셋'
    r'|더제이|대신|BNK|유진|파워|마이다스|VITA|UNICORN|DAISHIN343|TRUSTON|KCGI)\s',
    re.IGNORECASE,
)


def classify_ticker(code: str, name: str, market: str) -> str:
    """Return the security kind for a Korean equity ticker.

    First-match-wins ordering:
      1. Name starts with an ETF brand prefix → 'etf'  (KODEX/TIGER/RISE/...)
      2. KONEX market         → 'konex'
      3. Code last char != '0'                    → 'preferred'
                          (authoritative; KRX preferred shares end non-'0')
      4. Name contains 스팩 / SPAC                → 'spac'
      5. Name contains 리츠 / REIT                → 'reit'
      6. Name ends 호 / MF OR contains 선박투자    → 'fund'
      7. Market in KOSPI / KOSDAQ / KOSDAQ GLOBAL → 'common'
      8. Otherwise                                → 'other'

    Note on alphanumeric codes: KRX uses 6-character alphanumeric codes for
    newly-listed names too (e.g. ``00088K`` for 한화3우B, ``0001A0`` for
    덕양에너젠). The ``code[-1] != '0'`` test correctly catches the
    K/L/M-suffixed preferred shares; alphanumeric commons end in '0' and fall
    through. We deliberately do NOT route alphanumeric codes to 'etf' because
    plenty of plain-equity issuers use that format.
    """
    code = str(code).strip()
    name = str(name).strip()

    if _ETF_NAME_RE.match(name):
        return 'etf'

    if market == 'KONEX':
        return 'konex'

    if code[-1] != '0':
        return 'preferred'

    if _SPAC_RE.search(name):
        return 'spac'

    if _REIT_RE.search(name):
        return 'reit'

    if name.endswith('호') or _FUND_RE.search(name):
        return 'fund'

    if market in ('KOSPI', 'KOSDAQ', 'KOSDAQ GLOBAL'):
        return 'common'

    return 'other'


if __name__ == '__main__':
    # Smoke tests.
    cases = [
        ('005930', '삼성전자',       'KOSPI',         'common'),
        ('005935', '삼성전자우',     'KOSPI',         'preferred'),
        ('005385', '현대자동차2우B', 'KOSPI',         'preferred'),
        ('035915', '현대멀티캡우',   'KOSDAQ',        'preferred'),
        ('365590', '엔에이치스팩22호','KOSDAQ',       'spac'),
        ('330590', '롯데리츠',       'KOSPI',         'reit'),
        ('900110', '이스트아시아홀딩스','KOSDAQ',     'common'),
        ('357870', '엔에이치프라임리츠','KOSPI',      'reit'),
        ('123450', '코람코더원제1호','KOSPI',         'fund'),
        ('088980', '맥쿼리한국인프라투융자회사','KOSPI','common'),
        ('999999', '뭐든지',         'KONEX',         'konex'),
        ('264900', '크라운제과',     'KOSDAQ GLOBAL', 'common'),
        ('0000D0', 'TIGER 엔비디아미국채커버드콜밸런스(합성)', 'KOSPI', 'etf'),
        ('069500', 'KODEX 200',     'KOSPI',         'etf'),
        # Alphanumeric codes are NOT auto-ETF: real equities use them too.
        ('00088K', '한화3우B',       'KOSPI',         'preferred'),
        ('0001A0', '덕양에너젠',     'KOSDAQ',        'common'),
        ('0030R0', '대신밸류리츠',   'KOSPI',         'reit'),
        ('0004Y0', '디비금융제14호스팩','KOSDAQ',     'spac'),
        # Regression: real commons whose NAME ends in 우 must NOT be routed
        # to 'preferred' — the code's '0' terminal digit governs. (A 우$
        # name-suffix OR previously misclassified these.)
        ('047050', '포스코대우',     'KOSPI',         'common'),
        ('006800', '미래에셋대우',   'KOSPI',         'common'),
        ('115960', '연우',           'KOSDAQ',        'common'),
        ('294090', '이오플로우',     'KOSDAQ',        'common'),
        # 뮤추얼펀드 → 'fund' (code ends '0', name ends MF)
        ('035030', '파이오니어MF',   'KOSDAQ',        'fund'),
    ]
    pass_n = 0
    for code, name, market, expected in cases:
        got = classify_ticker(code, name, market)
        ok = got == expected
        pass_n += ok
        marker = 'OK ' if ok else 'FAIL'
        print(f'  [{marker}] ({code}, {name!r}, {market!r}) → {got} (expected {expected})')
    print(f'{pass_n}/{len(cases)} passed')
