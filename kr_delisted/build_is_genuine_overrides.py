"""Generate is_genuine overrides for delisting_calendar.csv from DART filings.

The keyword classifier in build_delisting_calendar.py is correct for the
clear-cut cases (피흡수합병, 신청에 의한 상장폐지, 감사의견 거절, etc.) but
fails on two ambiguous reason families (해산 사유 발생 and 지주회사의
완전자회사화(지주회사 신규상장)), plus acquirer-side merger-filing edge
cases.  This script resolves them via four overrides applied in order.

Override 1 — Dissolution-after-merger (Y → N).
    "해산 사유 발생" by itself does not say whether the company dissolved
    because of bankruptcy (genuine) or because it was absorbed into an
    acquirer (merger).  Query DART 주요사항보고서 (corp-action filings) in
    the 9 months before delisting; if any 합병결정 / 주식의 포괄적 교환·이전 /
    주식교환 filing exists, override to N.

Override 2 — REIT / SPC end-of-life dissolution (Y → N).
    Real-estate trusts and special-purpose vehicles are designed to wind
    down at maturity, so their "해산 사유 발생" is a planned end, not a
    business failure.  Detect by querying DART's company info and matching
    the legal entity name against 투자회사 / 리츠 / REIT / 기업구조조정 patterns.

Override 3 — Holding-company restructuring (N → Y).
    "지주회사의 완전자회사화(지주회사 신규상장)" is the case where the company
    becomes a subsidiary of a newly-listed holding company.  Economically
    the same shareholders retain a listing (in the holdco), so for
    survivorship-bias purposes this is a continuation, not a true exit.
    The user's convention is to mark it Y.  Rule-based, no DART needed.

Output:
    is_genuine_overrides.csv  with columns
      ticker, delisting_date, reason, is_genuine_keyword, is_genuine,
      rule, evidence

The downstream build_delisting_calendar.py reads this file (if present)
and applies the overrides as a final post-step.

Usage:
    export OPEN_DART_API_KEY=...
    python build_is_genuine_overrides.py
    python build_is_genuine_overrides.py --kind-csv path.csv --out path.csv

Override 4 — Manual entries (Y → N or N → Y) for cases the three rules above
cannot reach.  Currently one row: 001370 FNC코오롱 (merged into 코오롱 with
the merger 주요사항보고서 filed acquirer-side under 코오롱's corp_code, so an
acquiree-side `dart.list(corp=ticker, kind='B')` query returns nothing).
See MANUAL_OVERRIDES below.

Coverage (as of 2025-10-23 KIND cutoff):
    Produces 80 overrides — 55 dissolution-post-merger (DART-verified),
    15 spc-end-of-life (REIT/SPC name pattern), 9 holdco-new-listing
    (rule-based), 1 manual.

Reconciliation against the legacy curated CSV (delisting_calendar.curated.csv):
    Of the 81 hand-curated is_genuine deviations, 75 are reproduced by
    rules 1-3 and 1 more (001370 FNC코오롱) by rule 4's manual override,
    for 76/81 = 94 %.  The remaining 5 curated entries are all verified
    curated bugs — the regenerator's classification is more correct than
    the curated's, with web-sourced evidence (researched 2026-05-11):

    (a) Curated YES, regen NO — 4 cases.  All are M&A continuations:
        shareholders received shares of a listed acquirer that kept
        trading.  By the project's merger=N convention, regen N is
        correct and curated Y is inconsistent:
          • 037150 CJ인터넷    2011-03-22  피흡수합병 → CJ E&M (130960)
          • 056200 엠넷미디어  2011-03-22  피흡수합병 → CJ E&M (130960)
          • 228180 티씨엠생명과학 2020-08-07 주식의 포괄적 교환 → 넥스트BT (065170)
          • 323350 다원넥스뷰  2024-06-11  스팩소멸합병; merged with
                                       신한제9호스팩 (405640) and re-listed
                                       on KOSDAQ same day under ticker
                                       323350 (KONEX → KOSDAQ transfer).
        Refs: ko.wikipedia.org/wiki/CJ인터넷, ko.wikipedia.org/wiki/엠넷미디어,
              thebell.co.kr 202005271435073400106123, etoday.co.kr 2353520.

    (b) Curated NO, regen YES — 1 case.  Real bankruptcy with shareholders
        receiving nothing; regen Y is correct, curated N is wrong:
          • 117930 한진해운 2017-03-07.  Court terminated rehabilitation
            2017-02-02; bankruptcy declared 2017-02-17; only ~2 % of the
            $10.5B owed creditors was recovered.
        Refs: en.wikipedia.org/wiki/Hanjin_Shipping,
              koreaherald.com/article/1257958.
"""
from __future__ import annotations
import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import OpenDartReader  # the package's __init__ rebinds the module to its main class

MERGER_REPORT_RE = re.compile(r"(?:합병|주식의\s*포괄적\s*(?:교환|이전)|주식교환)")
SPC_NAME_RE      = re.compile(r"(투자회사|리츠|REIT|기업구조조정)")
DISSOLUTION_REASON = "해산 사유 발생"
HOLDCO_REASON      = "지주회사의 완전자회사화(지주회사 신규상장)"

# Manual overrides for cases the three DART/rule-based passes cannot reach.
# Keyed by (ticker, delisting_date) → (is_genuine, evidence_string).
# Add an entry here only with a verified citation.
MANUAL_OVERRIDES: dict[tuple[str, str], tuple[str, str]] = {
    ("001370", "2009-08-17"): (
        "N",
        "Merged into (주)코오롱; 회사합병결정 filed acquirer-side under 코오롱's "
        "corp_code so acquiree-side DART query returns nothing. "
        "ref: ko.wikipedia.org/wiki/코오롱, namu.wiki/w/코오롱",
    ),
}

# Merger keyword set matching build_delisting_calendar.py's classifier.
# Used here only to recompute is_genuine_keyword for each row.
TRANSFER_REASONS = {"코스닥시장 이전상장", "유가증권시장 상장", "코스닥시장 상장"}
MERGER_SUBSTRINGS = ("피흡수합병", "완전자회사화", "완전자회사로 편입",
                     "스팩소멸합병", "주식교환")


def classify_keyword(reason: str) -> str:
    if reason in TRANSFER_REASONS:
        return "N"
    if any(k in reason for k in MERGER_SUBSTRINGS):
        return "N"
    return "Y"


def dart_had_merger_filing(dart, ticker: str, delisting_date: str,
                           window_months: int = 9) -> tuple[bool, str]:
    """Return (had_merger_filing, evidence_string) for one delisting."""
    d = pd.Timestamp(delisting_date)
    start = (d - pd.DateOffset(months=window_months)).strftime("%Y%m%d")
    end   = (d + pd.DateOffset(days=30)).strftime("%Y%m%d")
    try:
        df = dart.list(corp=ticker, start=start, end=end, kind="B")
    except Exception as e:
        return False, f"dart-error:{e}"
    if df is None or len(df) == 0:
        return False, ""
    hits = df[df["report_nm"].astype(str).str.contains(MERGER_REPORT_RE, na=False, regex=True)]
    if len(hits) == 0:
        return False, ""
    first = hits.iloc[0]
    return True, f"{first.rcept_no} {first.report_nm} {first.rcept_dt}"


def dart_is_spc_or_reit(dart, ticker: str) -> tuple[bool, str]:
    """Return (is_spc_or_reit, evidence) based on the legal entity name in DART.

    REITs and corporate-restructuring SPCs carry the entity type in their
    registered name (e.g. '(주)코크렙제2호기업구조조정부동산투자회사' or
    '굿앤리치부동산공경매투자회사1호').  Plain joint-stock companies do not.
    """
    try:
        info = dart.company(ticker)
    except Exception as e:
        return False, f"dart-error:{e}"
    if not info:
        return False, ""
    corp_name = info.get("corp_name", "") or ""
    if SPC_NAME_RE.search(corp_name):
        return True, f"corp_name={corp_name}"
    return False, corp_name


def build_overrides(kind_csv: Path, dart,
                    progress=True) -> list[dict]:
    df = pd.read_csv(kind_csv, dtype={"ticker": str})

    overrides: list[dict] = []

    # ---- Override 3 (rule-based, fast) ----
    holdco_mask = df["reason"] == HOLDCO_REASON
    for _, row in df[holdco_mask].iterrows():
        kw = classify_keyword(row["reason"])
        if kw == "Y":
            continue   # already matches
        overrides.append({
            "ticker": row["ticker"],
            "delisting_date": row["delisting_date"],
            "reason": row["reason"],
            "is_genuine_keyword": kw,
            "is_genuine": "Y",
            "rule": "holdco-new-listing",
            "evidence": "reason ends in '지주회사 신규상장' — restructure, not exit",
        })

    # ---- Override 4 (manual, hard-coded with citations) ----
    keyed = df.set_index(["ticker", "delisting_date"])
    for (ticker, date), (new_val, evidence) in MANUAL_OVERRIDES.items():
        try:
            row = keyed.loc[(ticker, date)]
        except KeyError:
            print(f"WARN: manual override ({ticker}, {date}) not in KIND CSV — skipping",
                  file=sys.stderr)
            continue
        reason = row["reason"] if isinstance(row, pd.Series) else row.iloc[0]["reason"]
        kw = classify_keyword(reason)
        if kw == new_val:
            continue   # already correct, no override needed
        overrides.append({
            "ticker": ticker,
            "delisting_date": date,
            "reason": reason,
            "is_genuine_keyword": kw,
            "is_genuine": new_val,
            "rule": "manual",
            "evidence": evidence,
        })

    # ---- Overrides 1+2 (DART-driven: merger-filing search then SPC-name match) ----
    diss = df[df["reason"] == DISSOLUTION_REASON].copy()
    n_total = len(diss)
    if progress:
        print(f"querying DART for {n_total} '{DISSOLUTION_REASON}' rows", file=sys.stderr)

    n_merger = n_spc = 0
    for i, (_, row) in enumerate(diss.iterrows(), 1):
        kw = classify_keyword(row["reason"])   # always "Y" for 해산 사유 발생
        had, evidence = dart_had_merger_filing(dart, row["ticker"], row["delisting_date"])
        if had:
            n_merger += 1
            overrides.append({
                "ticker": row["ticker"],
                "delisting_date": row["delisting_date"],
                "reason": row["reason"],
                "is_genuine_keyword": kw,
                "is_genuine": "N",
                "rule": "dissolution-post-merger",
                "evidence": evidence,
            })
        else:
            is_spc, spc_ev = dart_is_spc_or_reit(dart, row["ticker"])
            if is_spc:
                n_spc += 1
                overrides.append({
                    "ticker": row["ticker"],
                    "delisting_date": row["delisting_date"],
                    "reason": row["reason"],
                    "is_genuine_keyword": kw,
                    "is_genuine": "N",
                    "rule": "spc-end-of-life",
                    "evidence": spc_ev,
                })
        if progress and (i % 10 == 0 or i == n_total):
            print(f"  [{i}/{n_total}]  merger={n_merger} spc={n_spc}", file=sys.stderr)
        time.sleep(0.05)   # be polite

    return overrides


def write_overrides(rows: list[dict], path: Path) -> None:
    rows = sorted(rows, key=lambda r: (r["delisting_date"], r["ticker"]))
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "delisting_date", "reason",
                                          "is_genuine_keyword", "is_genuine",
                                          "rule", "evidence"])
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kind-csv",
                    default=str(Path(__file__).parent / "delisting_calendar.kind.csv"),
                    help="path to KIND-only CSV (run build_delisting_calendar.py --no-proxy first)")
    ap.add_argument("--out",
                    default=str(Path(__file__).parent / "is_genuine_overrides.csv"))
    ap.add_argument("--api-key", default=os.environ.get("OPEN_DART_API_KEY"))
    args = ap.parse_args(argv)

    if not args.api_key:
        print("ERROR: pass --api-key or set OPEN_DART_API_KEY", file=sys.stderr)
        return 2

    dart = OpenDartReader(args.api_key)
    overrides = build_overrides(Path(args.kind_csv), dart)

    out = Path(args.out)
    write_overrides(overrides, out)
    by_rule: dict[str, int] = {}
    for r in overrides:
        by_rule[r["rule"]] = by_rule.get(r["rule"], 0) + 1
    print(f"wrote {len(overrides)} overrides -> {out}", file=sys.stderr)
    for rule, n in by_rule.items():
        print(f"  {rule}: {n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
