"""Korean equity security-type classifier.

Pure functions. Consolidates the ticker-classification rules that were
previously scattered across kr_delisted/build_delisting_calendar.py and
the (now-retired) FnGuide-based market loader.

KOSDAQ GLOBAL is a tier of KOSDAQ (premium-listed names that meet stricter
disclosure requirements) and is folded into 'common' under the KOSDAQ market.
"""
from __future__ import annotations

import re

KINDS = ('common', 'preferred', 'spac', 'reit', 'fund', 'etf', 'konex', 'other')

# Compiled once at import.
_PREF_SUFFIX_RE = re.compile(r'(?:우B|우|1우|2우|3우|MF)$')
_SPAC_RE = re.compile(r'스팩|SPAC', re.IGNORECASE)
_REIT_RE = re.compile(r'리츠|REIT', re.IGNORECASE)
_FUND_RE = re.compile(r'선박투자')
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
      3. Code last char != '0' OR name ends with 우|우B|1우|2우|3우|MF
                              → 'preferred'
      4. Name contains 스팩 / SPAC                → 'spac'
      5. Name contains 리츠 / REIT                → 'reit'
      6. Name ends with 호 OR contains 선박투자    → 'fund'
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

    if code[-1] != '0' or _PREF_SUFFIX_RE.search(name):
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
    ]
    pass_n = 0
    for code, name, market, expected in cases:
        got = classify_ticker(code, name, market)
        ok = got == expected
        pass_n += ok
        marker = 'OK ' if ok else 'FAIL'
        print(f'  [{marker}] ({code}, {name!r}, {market!r}) → {got} (expected {expected})')
    print(f'{pass_n}/{len(cases)} passed')
