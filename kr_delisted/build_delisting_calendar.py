"""Regenerate delisting_calendar.csv from KIND + a marcap preferred-share scan.

Two sources, stitched:
  1. KIND delcompany.do — every delisting since 2005-01-01 in one page
     (main shares: 6-digit codes ending '0', plus foreign 9xxxxx issuers).
  2. marcap — preferred shares (codes ending != '0') that KIND omits; each
     ticker's last marcap appearance is its proxy delisting date.

Output columns: ticker,name,market,delisting_date,reason,is_genuine
(is_genuine = classify() on the KIND reason; proxy rows are always Y.)

If is_genuine_overrides.csv (from build_is_genuine_overrides.py) exists it is
applied as a final post-step.

Usage:
    python build_delisting_calendar.py                # KIND + proxy + overrides -> .regen.csv
    python build_delisting_calendar.py --no-proxy     # KIND only                -> .kind.csv
    python build_delisting_calendar.py --no-overrides
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

from _classify import classify

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
        "currentPageSize": "5000",   # server returns all rows in one page
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
            ticker = resolve_foreign_ticker(session, stub)   # foreign issuer: alphanumeric isurCd
            time.sleep(0.1)
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

    KIND only publishes main-share delistings; for preferred shares the last
    marcap appearance is the delisting-date proxy. Filter: 6-digit numeric,
    not ending in '0', last_date >= start_date, and last_date older than
    (marcap_latest - stale_days) so still-trading issues aren't flagged.
    """
    files = sorted(marcap_dir.glob("marcap-*.parquet"))
    if not files:
        raise RuntimeError(f"no marcap files in {marcap_dir}")

    last_seen: dict[str, tuple] = {}
    for f in files:
        df = pd.read_parquet(f, columns=["Code", "Date", "Name", "Market"])
        df["Code"] = df["Code"].astype(str).str.zfill(6)
        # idxmax -> one row per ticker on its latest date that year, so
        # Name/Market reflect at-delisting values (matters for renames).
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
        if code[-1] == "0":         # main shares + 9xxxxx foreign issuers come from KIND
            continue
        if date < start:
            continue
        if date >= cutoff_active:   # still trading
            continue
        # marcap wraps the share-class suffix in parens ("신한증권(1우)"); the
        # curated file strips them ("신한증권1우"). Match that.
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
    """Apply is_genuine overrides; return the number of rows changed."""
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
