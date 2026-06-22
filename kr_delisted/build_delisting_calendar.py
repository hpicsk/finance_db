"""Regenerate delisting_calendar.csv from KIND + a marcap-derived preferred-share scan.

The canonical file has two sources, stitched together:

  1. KIND (kind.krx.co.kr) → POST /investwarn/delcompany.do with
     method=searchDelCompanySub.  One request with currentPageSize=5000
     returns every delisting event since 2005-01-01 in a single HTML page
     (~1,181 rows as of 2025-10-23).  Covers main shares (6-digit codes
     ending in '0') and 18 foreign issuers (9xxxxx codes).

  2. marcap (~/finance_db/marcap/data/marcap-YYYY.parquet) → preferred-share
     proxy.  KIND does not publish 우/우B/전환상환 etc. (codes ending in a
     non-zero digit).  We recover them by taking each non-zero-ending
     6-digit ticker's last appearance in marcap as a proxy delisting date.
     Filtered to delisting_date >= 2005-01-01 to match the curated file.

Output: ticker,name,market,delisting_date,reason,is_genuine

is_genuine classifier (keyword on KIND reason; proxy rows are always Y):
    N — exchange transfer:   '코스닥시장 이전상장' / '유가증권시장 상장' / '코스닥시장 상장'
    N — merger / absorption: contains 피흡수합병 / 완전자회사화 / 완전자회사로 편입
                             / 스팩소멸합병 / 주식교환
    Y — everything else (bankruptcies, audit refusals, voluntary delistings,
        SPAC liquidations, capital impairment, etc.)
    These match README.md §"Methodology notes" counts: ~107 transfers,
    ~186 merger/absorptions, 1,004 genuine delistings in the 6-digit universe.

Foreign-issuer ticker resolution:
    Most KIND rows expose the 6-digit KRX code via the JS handler
    `companysummary_open('NNNNN')` — NNNNN is the leading 5 digits;
    suffix is '0' for every 6-digit common-stock code.  18 foreign issuers
    (CHN/HKG/CYM/JPN/SGP-prefixed isurCd's) have alphanumeric IDs in KIND
    that do not map by string transform; for those we POST
    /common/companysummary.do with method=searchCompanySummaryOvrvwDetail
    and parse 종목코드 from the response table.

If is_genuine_overrides.csv exists in the same directory (produced by
build_is_genuine_overrides.py), it is applied as a final post-step.

Usage:
    python build_delisting_calendar.py                # KIND + proxy + overrides → delisting_calendar.regen.csv
    python build_delisting_calendar.py --no-proxy     # KIND only                → delisting_calendar.kind.csv
    python build_delisting_calendar.py --no-overrides # skip the overrides post-step
    python build_delisting_calendar.py --from 2005-01-01 --to 2025-10-23
"""
from __future__ import annotations
import argparse
import csv
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from _classify import classify, TRANSFER_REASONS, MERGER_SUBSTRINGS

KIND_BASE        = "https://kind.krx.co.kr"
KIND_FORM_URL    = f"{KIND_BASE}/investwarn/delcompany.do?method=searchDelCompanyMain"
KIND_QUERY_URL   = f"{KIND_BASE}/investwarn/delcompany.do"
KIND_SUMMARY_URL = f"{KIND_BASE}/common/companysummary.do"
MARCAP_DIR       = Path(__file__).resolve().parents[1] / "marcap" / "data"
PROXY_REASON     = "(not in KIND — proxy date from last-CSV-date)"
OVERRIDES_CSV    = Path(__file__).parent / "is_genuine_overrides.csv"

MARKET_ICON = {"yu": "KOSPI", "ko": "KOSDAQ", "konex": "KONEX"}


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124 Safari/537.36"),
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Referer": KIND_FORM_URL,
    })
    s.get(KIND_FORM_URL, timeout=20).raise_for_status()  # warm-up: set JSESSIONID
    return s


def fetch_delisting_table(session: requests.Session, from_date: str, to_date: str) -> str:
    payload = {
        "method": "searchDelCompanySub",
        "forward": "delcompany_sub",
        "currentPageSize": "5000",   # KIND's UI dropdown caps at 100; the
                                     # server respects larger values and
                                     # returns all rows in one page.
        "pageIndex": "1",
        "orderMode": "2",
        "orderStat": "D",
        "tabType": "1",
        "marketType": "",            # blank == all (KOSPI + KOSDAQ + KONEX)
        "fromDate": from_date,
        "toDate": to_date,
        "searchCorpName": "",
        "searchCorpNameTmp": "",
        "searchMode": "",
        "searchCodeType": "",
        "searchType": "",
        "repIsuSrtCd": "",
    }
    headers = {"X-Requested-With": "XMLHttpRequest"}
    r = session.post(KIND_QUERY_URL, data=payload, headers=headers, timeout=60)
    r.raise_for_status()
    return r.text


def resolve_foreign_ticker(session: requests.Session, isur_cd: str) -> str:
    """Look up the 6-digit KRX 종목코드 for a foreign-issuer KIND isurCd."""
    r = session.post(KIND_SUMMARY_URL, data={
        "method": "searchCompanySummaryOvrvwDetail",
        "strIsurCd": isur_cd,
        "menuIndex": "0",
        "lstCd": "",
        "taskDd": "",
        "spotIsuTrdMktTpCd": "",
        "methodType": "0",
    }, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=20)
    r.raise_for_status()
    m = re.search(r'<th[^>]*>\s*종목코드\s*</th>\s*<td[^>]*>\s*(\d{6})', r.text)
    if not m:
        raise RuntimeError(f"종목코드 not found for isurCd={isur_cd!r}")
    return m.group(1)


def parse_rows(html: str, session: requests.Session) -> list[dict]:
    """Extract one dict per delisting event from the KIND result HTML."""
    soup = BeautifulSoup(html, "lxml")
    tbody = soup.find("tbody")
    if tbody is None:
        raise RuntimeError("KIND response missing <tbody> — endpoint shape changed")

    rows: list[dict] = []
    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 5:
            continue

        # Market icon: first img with src matching icn_t_(yu|ko|konex).gif
        market = None
        for img in tds[1].find_all("img"):
            m = re.search(r"icn_t_(yu|ko|konex)\.gif", img.get("src", ""))
            if m:
                market = MARKET_ICON[m.group(1)]
                break

        anchor = tds[1].find("a")
        onclick = anchor.get("onclick", "") if anchor else ""
        m = re.search(r"companysummary_open\('([^']+)'\)", onclick)
        stub = m.group(1) if m else ""
        name = (anchor.get("title", "") if anchor else "").strip()
        date = tds[2].get_text(strip=True)
        reason = tds[3].get_text(strip=True)

        if stub.isdigit() and len(stub) == 5:
            ticker = stub + "0"
        elif stub.isalnum() and not stub.isdigit():
            # Foreign issuer: KIND uses alphanumeric isurCd, needs a lookup.
            ticker = resolve_foreign_ticker(session, stub)
            time.sleep(0.1)  # be polite
        else:
            raise RuntimeError(f"Unexpected isurCd shape: {stub!r} (name={name!r})")

        if not market:
            raise RuntimeError(f"Could not determine market for {ticker} {name}")

        rows.append({
            "ticker": ticker,
            "name": name,
            "market": market,
            "delisting_date": date,
            "reason": reason,
            "is_genuine": classify(reason),
        })
    return rows


def scan_marcap_proxies(kind_tickers: set[str],
                        marcap_dir: Path = MARCAP_DIR,
                        start_date: str = "2005-01-01",
                        stale_days: int = 30) -> list[dict]:
    """Recover preferred-share delistings (codes ending != '0') from marcap.

    KIND only publishes main-share delistings.  For preferred shares the
    last appearance in marcap is the most reliable delisting-date proxy:
    in 107/109 cases in the curated CSV it matched the curated date exactly.

    Filter: 6-digit numeric ticker NOT ending in '0' (so it's not a main
    share), not already in KIND, last_date >= start_date, and last_date
    older than (marcap_latest - stale_days) so we don't flag still-trading
    issues as delisted just because the most recent marcap update lags.
    """
    files = sorted(marcap_dir.glob("marcap-*.parquet"))
    if not files:
        raise RuntimeError(f"no marcap files in {marcap_dir}")

    last_seen: dict[str, tuple] = {}
    for f in files:
        df = pd.read_parquet(f, columns=["Code", "Date", "Name", "Market"])
        df["Code"] = df["Code"].astype(str).str.zfill(6)
        # idxmax picks one row per ticker — the one on its latest date that
        # year — so Name/Market reflect the at-delisting values, not the
        # earliest values, which matters for renames.
        idx = df.groupby("Code")["Date"].idxmax()
        for r in df.loc[idx, ["Code", "Date", "Name", "Market"]].itertuples(index=False):
            prev = last_seen.get(r.Code)
            if prev is None or r.Date > prev[0]:
                last_seen[r.Code] = (r.Date, r.Name, r.Market)

    marcap_latest = max(d[0] for d in last_seen.values())
    cutoff_active = marcap_latest - pd.Timedelta(days=stale_days)
    start = pd.Timestamp(start_date)

    proxies: list[dict] = []
    for code, (date, name, market) in last_seen.items():
        if not (len(code) == 6 and code.isdigit()):
            continue
        if code[-1] == "0":         # main shares (and all 9xxxxx foreign issuers) come from KIND
            continue
        if date < start:
            continue
        if date >= cutoff_active:   # still trading
            continue
        # marcap wraps the share-class suffix in parens, e.g. "굿모닝신한증권(1우)";
        # the curated file strips them ("굿모닝신한증권1우").  Match that.
        clean_name = re.sub(r"\(([^)]+)\)$", r"\1", name.strip())
        proxies.append({
            "ticker":         code,
            "name":           clean_name,
            "market":         market,
            "delisting_date": date.strftime("%Y-%m-%d"),
            "reason":         PROXY_REASON,
            "is_genuine":     "Y",
        })
    return proxies


def apply_overrides(rows: list[dict], overrides_csv: Path) -> int:
    """Apply is_genuine overrides (from build_is_genuine_overrides.py).

    Returns the number of rows whose is_genuine was changed.
    """
    if not overrides_csv.exists():
        return 0
    ov = pd.read_csv(overrides_csv, dtype={"ticker": str})
    keyed = {(r.ticker, r.delisting_date): r.is_genuine for r in ov.itertuples(index=False)}
    changed = 0
    for row in rows:
        key = (row["ticker"], row["delisting_date"])
        new = keyed.get(key)
        if new is not None and new != row["is_genuine"]:
            row["is_genuine"] = new
            changed += 1
    return changed


def write_csv(rows: list[dict], path: Path) -> None:
    # Match existing CSV's sort order: ascending by date, then ticker
    rows = sorted(rows, key=lambda r: (r["delisting_date"], r["ticker"]))
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "name", "market",
                                          "delisting_date", "reason", "is_genuine"])
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="from_date", default="2005-01-01")
    ap.add_argument("--to",   dest="to_date",   default=time.strftime("%Y-%m-%d"))
    ap.add_argument("--no-proxy", action="store_true",
                    help="skip the marcap preferred-share proxy scan")
    ap.add_argument("--no-overrides", action="store_true",
                    help="skip applying is_genuine_overrides.csv post-step")
    ap.add_argument("--out", default=None,
                    help="output CSV path (default depends on --no-proxy)")
    args = ap.parse_args(argv)

    sess = make_session()
    print(f"[1/3] POST KIND  fromDate={args.from_date} toDate={args.to_date}", file=sys.stderr)
    html = fetch_delisting_table(sess, args.from_date, args.to_date)

    print(f"[2/3] parse KIND + foreign-ticker lookups", file=sys.stderr)
    rows = parse_rows(html, sess)

    if not args.no_proxy:
        print(f"[3/3] scan marcap for preferred-share proxies", file=sys.stderr)
        kind_tickers = {r["ticker"] for r in rows}
        proxy_rows = scan_marcap_proxies(kind_tickers, start_date=args.from_date)
        rows.extend(proxy_rows)
        print(f"      marcap proxy rows: {len(proxy_rows)}", file=sys.stderr)

    if not args.no_overrides:
        n_overrides = apply_overrides(rows, OVERRIDES_CSV)
        if n_overrides:
            print(f"      applied {n_overrides} is_genuine overrides from {OVERRIDES_CSV.name}", file=sys.stderr)

    default_name = "delisting_calendar.kind.csv" if args.no_proxy else "delisting_calendar.regen.csv"
    out = Path(args.out) if args.out else Path(__file__).parent / default_name
    write_csv(rows, out)
    n_y = sum(1 for r in rows if r["is_genuine"] == "Y")
    n_n = len(rows) - n_y
    by_mkt: dict[str, int] = {}
    by_src: dict[str, int] = {"kind": 0, "proxy": 0}
    for r in rows:
        by_mkt[r["market"]] = by_mkt.get(r["market"], 0) + 1
        by_src["proxy" if r["reason"] == PROXY_REASON else "kind"] += 1
    print(f"wrote {len(rows)} rows -> {out}", file=sys.stderr)
    print(f"  by market : {by_mkt}", file=sys.stderr)
    print(f"  by source : {by_src}", file=sys.stderr)
    print(f"  is_genuine: Y={n_y}  N={n_n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
