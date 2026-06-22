"""Generate is_genuine overrides for delisting_calendar.csv from DART filings.

The keyword classifier in build_delisting_calendar.py handles the clear-cut
cases but fails on two ambiguous reason families (해산 사유 발생 and 지주회사의
완전자회사화(지주회사 신규상장)) plus acquirer-side merger filings. Four
overrides resolve them:

  1. Dissolution-after-merger (Y->N): query DART 주요사항보고서 in the 9 months
     before delisting; override to N if a 합병/주식교환 filing exists.
  2. REIT / SPC end-of-life (Y->N): planned wind-down, not failure; detected by
     matching the DART legal entity name against 투자회사/리츠/REIT/기업구조조정.
  3. Holdco new-listing (N->Y): 완전자회사화(지주회사 신규상장) keeps a listing
     in the holdco — a continuation, marked Y. Rule-based, no DART.
  4. Manual entries — cases the rules can't reach (see MANUAL_OVERRIDES).

Output: is_genuine_overrides.csv with columns ticker, delisting_date, reason,
is_genuine_keyword, is_genuine, rule, evidence. build_delisting_calendar.py
applies it as a final post-step.

Usage:
    export OPEN_DART_API_KEY=...
    python build_is_genuine_overrides.py
    python build_is_genuine_overrides.py --kind-csv path.csv --out path.csv
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
import OpenDartReader

from _classify import classify

MERGER_REPORT_RE = re.compile(r"(?:합병|주식의\s*포괄적\s*(?:교환|이전)|주식교환)")
SPC_NAME_RE      = re.compile(r"(투자회사|리츠|REIT|기업구조조정)")
DISSOLUTION_REASON = "해산 사유 발생"
HOLDCO_REASON      = "지주회사의 완전자회사화(지주회사 신규상장)"

# Manual overrides for cases the DART/rule passes cannot reach, keyed by
# (ticker, delisting_date) -> (is_genuine, evidence). Add only with a citation.
MANUAL_OVERRIDES: dict[tuple[str, str], tuple[str, str]] = {
    ("001370", "2009-08-17"): (
        "N",
        "Merged into (주)코오롱; 회사합병결정 filed acquirer-side under 코오롱's "
        "corp_code so acquiree-side DART query returns nothing. "
        "ref: ko.wikipedia.org/wiki/코오롱, namu.wiki/w/코오롱",
    ),
}


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
    """Return (is_spc_or_reit, evidence) from the DART legal entity name.

    REITs and restructuring SPCs carry the entity type in their registered name
    (e.g. '코크렙제2호기업구조조정부동산투자회사'); plain joint-stocks do not.
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


def build_overrides(kind_csv: Path, dart, progress=True) -> list[dict]:
    df = pd.read_csv(kind_csv, dtype={"ticker": str})
    overrides: list[dict] = []

    # ---- Override 3 (rule-based, fast) ----
    holdco_mask = df["reason"] == HOLDCO_REASON
    for _, row in df[holdco_mask].iterrows():
        overrides.append({
            "ticker": row["ticker"],
            "delisting_date": row["delisting_date"],
            "reason": row["reason"],
            "is_genuine_keyword": classify(row["reason"]),
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
        kw = classify(reason)
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

    # ---- Overrides 1+2 (DART: merger-filing search, then SPC-name match) ----
    diss = df[df["reason"] == DISSOLUTION_REASON].copy()
    n_total = len(diss)
    if progress:
        print(f"querying DART for {n_total} '{DISSOLUTION_REASON}' rows", file=sys.stderr)

    n_merger = n_spc = 0
    for i, (_, row) in enumerate(diss.iterrows(), 1):
        kw = classify(row["reason"])   # always "Y" for 해산 사유 발생
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
        time.sleep(0.05)

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
