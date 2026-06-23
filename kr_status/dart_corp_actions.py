"""DART harvest of corporate-action events → ground truth for price adjustment.

This replaces the *calibrated* entity-vs-genuine classification heuristics in
``kr_marcap/adjust.py`` (``_CORROBORATION_TOL``) with official DART filings.
For every candidate ticker it pulls the 주요사항보고서 events that move the share
count, split into two categories:

  GENUINE  (price-affecting corporate action — KRX ChangesRatio already adjusts
            it correctly, so the marcap share-count jump must NOT be read as an
            entity break):
              유상증자, 무상증자, 유무상증자, 감자

  ENTITY   (the listing's economic identity may change — candidate series break):
              회사합병, 회사분할, 회사분할합병, 주식교환

Note on coverage:
  - 액면분할/병합 are NOT in DART's 주요사항보고서 event API and are deliberately
    omitted: a 액면 change always moves the price inversely (it is corroborated)
    so it is never misread as an entity break, and ChangesRatio adjusts it anyway.
  - Preferred shares (codes not ending in '0') have no own corp_code; they are
    resolved to their parent common share (``code[:5] + '0'``) — the issuer's
    events apply to every share class.
  - DART structured coverage is reliable from ~2015; pre-2015 events are sparse,
    so pre-2015 share jumps with no DART match fall to the manual-override path
    (see ``kr_marcap/corp_actions.py``). The post-2015 research window is covered.

Output (``data/dart_corp_action_events.parquet``): one row per (ticker, event,
filing), columns: ticker, parent, corp_code, event, category, rcept_dt, rcept_no.
Resume-safe: tickers already in the cache are skipped unless ``--restart``.

Usage:
    export OPEN_DART_API_KEY=...
    python -m kr_status.dart_corp_actions                 # default: adjust candidates
    python -m kr_status.dart_corp_actions --tickers 052670,013890
    python -m kr_status.dart_corp_actions --all-universe  # every universe ticker
    python -m kr_status.dart_corp_actions --restart
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
from importlib.metadata import version
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from OpenDartReader import dart_event

from kr_status.corp_code_map import (
    DATA_DIR, get_corp_code, flush_cache, flush_misses, open_dart,
)

EVENTS_PATH = DATA_DIR / "dart_corp_action_events.parquet"

# event key_word (OpenDartReader) -> category
GENUINE_EVENTS = ("유상증자", "무상증자", "유무상증자", "감자")
ENTITY_EVENTS = ("회사합병", "회사분할", "회사분할합병", "주식교환")
CATEGORY = {**{e: "genuine" for e in GENUINE_EVENTS},
            **{e: "entity" for e in ENTITY_EVENTS}}

START = "1999-01-01"   # DART receipt-date floor; events before this are absent anyway


def _parent_common(ticker: str) -> str:
    """Preferred/2nd-class shares (suffix != '0') inherit the common issuer's
    corp_code; map e.g. 005965 -> 005960, 000725 -> 000720."""
    ticker = str(ticker).zfill(6)
    return ticker if ticker[-1] == "0" else ticker[:5] + "0"


def _candidate_tickers() -> list[str]:
    """Tickers with a material share-count change in marcap (the only tickers
    whose adjustment can hinge on an entity-vs-genuine decision)."""
    anomalies = Path(__file__).resolve().parents[1] / "kr_marcap" / "cache" / "adjust_anomalies.csv"
    if not anomalies.exists():
        raise FileNotFoundError(
            f"{anomalies} not found — run `python -m kr_marcap.adjust build` first "
            "to materialise the candidate share-jump list, or pass --tickers / --all-universe."
        )
    a = pd.read_csv(anomalies, dtype={"Code": str})
    return sorted(a["Code"].str.zfill(6).unique())


def _all_universe_tickers() -> list[str]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _universe import load_working_universe
    u = load_working_universe(include_dates=False)
    return sorted(u["ticker"].astype(str).str.zfill(6).unique())


def _load_done(path: Path) -> set[str]:
    if path.exists():
        return set(pd.read_parquet(path, columns=["ticker"])["ticker"].astype(str).str.zfill(6))
    return set()


def collect(tickers: list[str], out_path: Path = EVENTS_PATH,
            restart: bool = False, delay: float = 0.25) -> pd.DataFrame:
    dart = open_dart()
    key = dart.api_key

    existing = pd.DataFrame()
    done: set[str] = set()
    if out_path.exists() and not restart:
        existing = pd.read_parquet(out_path)
        done = set(existing["ticker"].astype(str).str.zfill(6))

    todo = [t for t in tickers if t not in done]
    print(f"[dart_corp_actions] {len(tickers)} tickers, {len(done)} cached, {len(todo)} to fetch",
          file=sys.stderr)

    rows: list[dict] = []
    for i, ticker in enumerate(todo):
        parent = _parent_common(ticker)
        cc = get_corp_code(dart, parent)
        # One sentinel row per processed ticker (category "none") so resume skips
        # it even when it has zero events / no resolvable corp_code.
        rows.append({"ticker": ticker, "parent": parent, "corp_code": cc or "",
                     "event": "", "category": "none", "rcept_dt": "", "rcept_no": ""})
        if cc:
            for event in CATEGORY:
                try:
                    df = dart_event.event(key, cc, event, START, None)
                except Exception as e:
                    print(f"  {ticker} [{event}] error: {e}", file=sys.stderr)
                    time.sleep(2.0)
                    continue
                if df is not None and len(df):
                    for _, r in df.iterrows():
                        rows.append({
                            "ticker": ticker, "parent": parent, "corp_code": cc,
                            "event": event, "category": CATEGORY[event],
                            "rcept_dt": str(r.get("rcept_dt") or r.get("rcept_no", "")[:8]),
                            "rcept_no": str(r.get("rcept_no", "")),
                        })
                time.sleep(delay)
        if (i + 1) % 25 == 0:
            print(f"  progress {i+1}/{len(todo)}  rows={len(rows)}", file=sys.stderr)
            _checkpoint(existing, rows, out_path)

    out = _checkpoint(existing, rows, out_path)
    flush_cache(); flush_misses()
    print(f"[dart_corp_actions] wrote {len(out)} rows "
          f"({(out['category'] != 'none').sum()} events) -> {out_path}", file=sys.stderr)
    return out


_COLS = ["ticker", "parent", "corp_code", "event", "category", "rcept_dt", "rcept_no"]


def _stamp(df: pd.DataFrame, collected_at: str) -> dict:
    """Vintage of this DART snapshot — a live API harvest (no commit to pin),
    so the snapshot self-describes when/with-what it was collected."""
    rcept = df.loc[df["rcept_dt"].astype(str) != "", "rcept_dt"] if len(df) else []
    return {
        "dart_collected_at": collected_at,
        "dart_source": f"DART/OpenDartReader {version('OpenDartReader')}",
        "dart_n_tickers": df["ticker"].nunique() if len(df) else 0,
        "dart_n_events": int((df["category"] != "none").sum()) if len(df) else 0,
        "dart_rcept_max": str(max(rcept)) if len(rcept) else "",
    }


def _write_stamped(df: pd.DataFrame, out_path: Path, stamp: dict) -> None:
    table = pa.Table.from_pandas(df, preserve_index=False)
    md = {str(k).encode(): str(v).encode() for k, v in stamp.items()}
    table = table.replace_schema_metadata({**(table.schema.metadata or {}), **md})
    pq.write_table(table, out_path)


def provenance(path: Path = EVENTS_PATH) -> dict[str, str]:
    """Vintage stamp embedded in the corp-action events parquet (see _stamp)."""
    md = pq.read_schema(str(path)).metadata or {}
    return {k.decode(): v.decode() for k, v in md.items()
            if k.decode().startswith("dart_")}


def _checkpoint(existing, rows, out_path):
    fetched = pd.DataFrame(rows, columns=_COLS)
    parts = [df for df in (existing, fetched) if len(df)]
    out = pd.concat(parts, ignore_index=True) if parts else fetched
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    # dedupe: real events by rcept_no; sentinels by ticker
    out = out.drop_duplicates(subset=["ticker", "event", "rcept_no"]).reset_index(drop=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_stamped(out, out_path, _stamp(out, datetime.datetime.now().isoformat(timespec="seconds")))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tickers", help="comma-separated tickers (default: adjust candidates)")
    ap.add_argument("--all-universe", action="store_true", help="every universe ticker")
    ap.add_argument("--restart", action="store_true", help="ignore cache, re-fetch all")
    ap.add_argument("--delay", type=float, default=0.25)
    args = ap.parse_args(argv)

    if not os.environ.get("OPEN_DART_API_KEY"):
        print("OPEN_DART_API_KEY not set", file=sys.stderr)
        return 1

    if args.tickers:
        tickers = [t.strip().zfill(6) for t in args.tickers.split(",") if t.strip()]
    elif args.all_universe:
        tickers = _all_universe_tickers()
    else:
        tickers = _candidate_tickers()

    collect(tickers, restart=args.restart, delay=args.delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
