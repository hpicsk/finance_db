"""Historical audit_qualified seed from KIND delisting CSV.

``--seed-historical`` walks ``../kr_delisted/delisting_calendar.csv``
and emits one ``audit_qualified`` event for each delisted ticker
whose reason mentions 감사의견거절 / 부적정 / 한정 etc.  Window:
``[delisting_date - 6 months, delisting_date]`` — a coarse proxy
since the exact 감사의견 publication date isn't on KIND's delisting
feed.  Phase B's ``dart_audit`` collector replaces these rows with
DART receipt_dt-anchored events for 2015+ filings.

Output schema follows kr_status.schema.STATUS_COLUMNS.

The previous FDR ``KRX-ADMINISTRATIVE`` snapshot / consolidate flow has
been retired: marcap.Dept is now the canonical source for 관리종목 (see
``marcap_halt_infer.py``).

Usage:
    python -m kr_status.fdr_collect --seed-historical   # KIND → historical_audit_events.parquet
    python -m kr_status.fdr_collect --check             # smoke tests
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from kr_delisted.delisted_loader import CALENDAR
from kr_status.schema import STATUS_COLUMNS, events_path

HISTORICAL_AUDIT_EVENTS = events_path("historical_audit")
DELISTING_CSV = Path(CALENDAR)

# Reason substrings that indicate a non-적정 audit opinion.  Matches the
# Korean delisting-reason corpus in delisting_calendar.csv (samples observed:
# "감사의견거절", "감사의견 의견거절", "감사의견 부적정", "감사범위제한 한정",
# "반기검토의견 의견거절").
AUDIT_QUAL_RE = re.compile(
    r"감사의견\s*(?:거절|의견거절|부적정|한정)"
    r"|감사범위제한\s*한정"
    r"|반기검토의견\s*(?:거절|의견거절)"
)

# Length of the proxy audit-flag window before delisting (days).  60–180 covers
# the typical 사유발생 → 정리매매 → 상장폐지 timeline; 180 is conservative for
# a "don't hold this" filter.
HISTORICAL_PROXY_WINDOW_DAYS = 180


def _zfill6(s) -> str:
    return str(s).strip().zfill(6)


def seed_historical_audit(delisting_csv: Path = DELISTING_CSV,
                          out_path: Path = HISTORICAL_AUDIT_EVENTS,
                          window_days: int = HISTORICAL_PROXY_WINDOW_DAYS) -> pd.DataFrame:
    """Emit ``audit_qualified`` events for delisted tickers with audit-rejection reasons.

    Window: [delisting_date - window_days, delisting_date].  This is a proxy;
    the actual 감사의견 publication date is not in KIND's delisting feed.
    Phase B's dart_audit collector replaces these rows with receipt_dt-anchored
    events for 2015+ filings.
    """
    if not delisting_csv.exists():
        raise FileNotFoundError(f"delisting calendar not found: {delisting_csv}")

    df = pd.read_csv(delisting_csv, dtype={"ticker": str})
    df["ticker"] = df["ticker"].str.zfill(6)
    df["delisting_date"] = pd.to_datetime(df["delisting_date"])

    mask = df["reason"].astype(str).str.contains(AUDIT_QUAL_RE, na=False, regex=True)
    hits = df.loc[mask].copy()

    fetched = pd.Timestamp.now()
    window = pd.Timedelta(days=window_days)
    out = pd.DataFrame({
        "ticker":      hits["ticker"].values,
        "status":      "audit_qualified",
        "start_date":  hits["delisting_date"].values - window,
        "end_date":    hits["delisting_date"].values,
        "source":      f"kind_delisting_csv (proxy, window={window_days}d)",
        "fetched_at":  fetched,
        "detail":      hits["reason"].astype(str).values,
    }, columns=STATUS_COLUMNS)
    out = out.sort_values(["start_date", "ticker"]).reset_index(drop=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)
    return out


def check() -> int:
    """Smoke test — exit 0 on pass, non-zero on fail."""
    failures: list[str] = []
    try:
        ha = seed_historical_audit()
        if len(ha) < 100:
            failures.append(f"historical audit events rowcount {len(ha)} < 100")
        print(f"  historical audit_qualified events: {len(ha)} rows", file=sys.stderr)
    except Exception as e:
        failures.append(f"seed_historical_audit raised: {e}")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1
    print("OK — all checks passed", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed-historical",  action="store_true",
                    help="emit historical audit_qualified events from KIND delisting CSV")
    ap.add_argument("--check",            action="store_true",
                    help="run smoke checks; exit non-zero on fail")
    args = ap.parse_args(argv)

    if args.check:
        return check()

    if args.seed_historical:
        ev = seed_historical_audit()
        print(f"seeded {len(ev)} historical audit_qualified events → {HISTORICAL_AUDIT_EVENTS}",
              file=sys.stderr)
        return 0

    ap.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
