"""DART harvest of 불성실공시법인 지정 filings → insincere event panel.

Scan dart.list per corp_code, regex-filter report_nm for "불성실공시법인지정"
titles, emit one event per hit. Default release rule:
``end_date = start_date + 12 months`` (KRX's standard 1-year window).

Resumable via runtime/_dart_insincere_progress.json.

Usage:
    export OPEN_DART_API_KEY=...
    python -m kr_status.dart_insincere
    python -m kr_status.dart_insincere --limit 100 --restart
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time

import pandas as pd

from kr_status.schema import STATUS_COLUMNS, events_path
from kr_status.corp_code_map import (
    DATA_DIR, get_corp_code, flush_cache, flush_misses, open_dart,
)

EVENTS_PATH   = events_path("dart_insincere")
RUNTIME_DIR   = DATA_DIR.parent / "runtime"
PROGRESS_PATH = RUNTIME_DIR / "_dart_insincere_progress.json"

# Match an actual 불성실공시법인 지정 (designation), excluding:
#   지정예고 — pre-announcement (look-ahead; the designation may not happen)
#   지정여부 — "기타시장안내(불성실공시법인 지정여부 결정 안내)" inquiry notices,
#              which are NOT designations and were producing false-positive events.
INSINCERE_RE = re.compile(r"불성실공시법인\s*지정(?!예고|여부)")
DEFAULT_START = "2005-01-01"
DEFAULT_DURATION_MONTHS = 12


def _load_progress() -> set[str]:
    if not PROGRESS_PATH.exists():
        return set()
    return set(json.loads(PROGRESS_PATH.read_text()).get("done", []))


def _save_progress(done: set[str]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text(json.dumps({"done": sorted(done)}))


def _working_universe() -> pd.DataFrame:
    from _universe import load_working_universe
    return load_working_universe(include_dates=False)


def harvest(api_key: str | None = None,
            start_date: str = DEFAULT_START,
            limit: int | None = None,
            tickers: list[str] | None = None,
            restart: bool = False,
            duration_months: int = DEFAULT_DURATION_MONTHS,
            sleep_s: float = 0.05) -> pd.DataFrame:
    dart = open_dart(api_key)

    universe = _working_universe()
    if tickers:
        wanted = {str(t).zfill(6) for t in tickers}
        universe = universe[universe["ticker"].isin(wanted)]
    if universe.empty:
        raise RuntimeError("working universe is empty")

    done = set() if restart else _load_progress()
    pending = [r for r in universe.to_dict("records") if r["ticker"] not in done]
    if limit:
        pending = pending[:limit]
    n_total = len(pending)
    print(f"harvest 불성실공시법인 filings: {n_total} tickers pending "
          f"(already done={len(done)})", file=sys.stderr)

    end_date = pd.Timestamp.today().strftime("%Y%m%d")
    start_yyyymmdd = pd.Timestamp(start_date).strftime("%Y%m%d")
    duration = pd.DateOffset(months=duration_months)
    fetched = pd.Timestamp.now()

    # An unreadable events file is not an empty one, and the difference is
    # destructive: the write at the end replaces the archive with `rows`, while
    # the progress file keeps most tickers marked done and so refills almost
    # none of it. Starting from nothing is what --restart asks for.
    rows: list[dict] = []
    if EVENTS_PATH.exists() and not restart:
        rows = pd.read_parquet(EVENTS_PATH).to_dict("records")

    n_hits = 0
    for i, row in enumerate(pending, 1):
        ticker = row["ticker"]
        name = row["name"]
        corp_code = get_corp_code(dart, ticker, name)
        if not corp_code:
            done.add(ticker)
            continue
        try:
            df = dart.list(corp=corp_code, start=start_yyyymmdd, end=end_date, kind=None)
        except Exception as e:
            print(f"  [{ticker}] dart.list failed: {e}", file=sys.stderr)
            time.sleep(sleep_s)
            continue

        if df is not None and len(df) > 0:
            mask = df["report_nm"].astype(str).str.contains(INSINCERE_RE, na=False, regex=True)
            hits = df.loc[mask]
            for _, h in hits.iterrows():
                start = pd.to_datetime(h["rcept_dt"])
                rows.append({
                    "ticker":     ticker,
                    "status":     "insincere",
                    "start_date": start,
                    "end_date":   start + duration,
                    "source":     f"dart_insincere:{h['rcept_no']}",
                    "fetched_at": fetched,
                    "detail":     str(h["report_nm"]),
                })
            n_hits += len(hits)

        done.add(ticker)
        time.sleep(sleep_s)
        if i % 50 == 0 or i == n_total:
            print(f"  [{i}/{n_total}]  hits so far: {n_hits}", file=sys.stderr)
            _save_progress(done)
            flush_cache()

    flush_cache()
    flush_misses()
    _save_progress(done)

    out = pd.DataFrame(rows, columns=STATUS_COLUMNS).drop_duplicates(
        subset=["ticker", "status", "start_date"]
    )
    out = out.sort_values(["start_date", "ticker"]).reset_index(drop=True)
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(EVENTS_PATH, index=False)
    print(f"wrote {len(out)} insincere events → {EVENTS_PATH}", file=sys.stderr)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--api-key",  default=None)
    ap.add_argument("--start",    default=DEFAULT_START)
    ap.add_argument("--limit",    type=int, default=None)
    ap.add_argument("--tickers",  default=None)
    ap.add_argument("--restart",  action="store_true")
    ap.add_argument("--duration-months", type=int, default=DEFAULT_DURATION_MONTHS,
                    help="default end_date offset from start_date (KRX standard = 12)")
    ap.add_argument("--refilter-events", action="store_true",
                    help="re-apply INSINCERE_RE to the existing events' detail column "
                         "and drop newly-excluded rows (no DART)")
    args = ap.parse_args(argv)
    if args.refilter_events:
        if not EVENTS_PATH.exists():
            raise SystemExit(f"no events parquet at {EVENTS_PATH} to refilter")
        ev = pd.read_parquet(EVENTS_PATH)
        keep = ev["detail"].astype(str).str.contains(INSINCERE_RE, na=False, regex=True)
        dropped = int((~keep).sum())
        ev = ev[keep].reset_index(drop=True)
        ev.to_parquet(EVENTS_PATH, index=False)
        print(f"refiltered insincere events: dropped {dropped}, kept {len(ev)} → {EVENTS_PATH}",
              file=sys.stderr)
        return 0
    tickers = [t.strip() for t in args.tickers.split(",")] if args.tickers else None
    harvest(api_key=args.api_key, start_date=args.start, limit=args.limit,
            tickers=tickers, restart=args.restart, duration_months=args.duration_months)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
