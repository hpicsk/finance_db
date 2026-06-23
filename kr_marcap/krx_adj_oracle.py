"""KRX official 수정주가 oracle — ground truth for the 거래재개 reset + validation.

KRX computes its own back-adjusted close (수정주가); ``pykrx``'s
``adjusted=True`` series is sourced from Naver Finance (not a ``data.krx.co.kr``
endpoint), so it is reachable from this host even though ``data.krx.co.kr`` is
edge-blocked (verified 2026-06).  This module caches that adjusted close per
ticker and serves two purposes in the de-heuristicised pipeline:

  1. **거래재개 reset detection** (replaces ``_RESET_VOL_SPIKE`` & friends):
     a day is a 기준가-reset iff our compounded-ChangesRatio return disagrees with
     KRX's official adjusted return on that day (and no data-integrity guard
     fired).  No volume-spike / share-band thresholds — the divergence from the
     official series *is* the signal, and the official move is the answer.
  2. **Automated validation gate** (replaces the manual FnGuide cross-check):
     ``kr_marcap/validate_against_oracle.py`` compares our adjusted returns to
     this series for every covered ticker.

Coverage (measured 2026-06): currently-listed and delisted common shares back to
≥2016 are covered; the oracle returns empty for some preferred shares, SPAC
shells and pre-2016 / very-recent windows, so reset detection is a no-op there
(the ChangesRatio backbone stands) and validation simply skips them.  The oracle
is NOT clean on ₩1 ticker-reuse sentinels (008080) — those are handled by the
deterministic data-integrity guard in ``adjust.py``, which takes precedence.

Output: ``cache/krx_adj_oracle.parquet`` — columns date, code, krx_adj_close.
Resume-safe: tickers already cached are skipped unless ``--restart``.

Usage:
    python -m kr_marcap.krx_adj_oracle --candidates      # adjust candidates (validation subset)
    python -m kr_marcap.krx_adj_oracle --all             # full universe (long-running)
    python -m kr_marcap.krx_adj_oracle --tickers 232830,005930
"""
from __future__ import annotations

import argparse
import datetime
import sys
import time
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pykrx import stock

CACHE_DIR = Path(__file__).resolve().parent / "cache"
ORACLE_PATH = CACHE_DIR / "krx_adj_oracle.parquet"
DEFAULT_START = "19950101"
_COLS = ["date", "code", "krx_adj_close"]


def _fetch_one(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Official adjusted close for one ticker, or empty frame if uncovered.

    pykrx's adjusted series caps at ~3000 rows (~12y) and, for names active near
    or through ~2014, floors at ~2014 regardless of ``start`` — pre-2014 daily adj
    is simply not served (verified 2026-06-23: narrow pre-2014 windows return
    empty), so date-chunking does NOT recover it; one wide call already returns the
    maximum pykrx has. Exception: names delisted well before 2014 (e.g. 2009) get
    their full archived life. The pre-2014 gap is validation-only — marcap remains
    the price source there.
    """
    df = stock.get_market_ohlcv(start, end, ticker, adjusted=True)
    if df is None or len(df) == 0 or "종가" not in df.columns:
        return pd.DataFrame(columns=_COLS)
    out = pd.DataFrame({
        "date": pd.to_datetime(df.index),
        "code": ticker,
        "krx_adj_close": pd.to_numeric(df["종가"], errors="coerce"),
    })
    return out[out["krx_adj_close"] > 0].reset_index(drop=True)


def collect(tickers: list[str], out_path: Path = ORACLE_PATH,
            start: str = DEFAULT_START, end: str | None = None,
            restart: bool = False, delay: float = 0.4) -> pd.DataFrame:
    end = end or pd.Timestamp.today().strftime("%Y%m%d")
    existing = pd.DataFrame(columns=_COLS)
    done_with_data: set[str] = set()
    done_empty: set[str] = set()
    if out_path.exists() and not restart:
        existing = pd.read_parquet(out_path)
        existing["code"] = existing["code"].astype(str).str.zfill(6)
        done_with_data = set(existing["code"])
    # tickers fetched but empty are recorded in a sidecar so resume skips them
    empty_sidecar = out_path.with_suffix(".empty.txt")
    if empty_sidecar.exists() and not restart:
        done_empty = set(empty_sidecar.read_text().split())

    todo = [t for t in tickers if t not in done_with_data and t not in done_empty]
    print(f"[krx_adj_oracle] {len(tickers)} tickers, "
          f"{len(done_with_data)} cached + {len(done_empty)} known-empty, "
          f"{len(todo)} to fetch", file=sys.stderr)

    frames: list[pd.DataFrame] = [existing] if len(existing) else []
    new_empty: list[str] = []
    for i, ticker in enumerate(todo):
        try:
            df = _fetch_one(ticker, start, end)
        except Exception as e:
            print(f"  {ticker} error: {e} — retry after 3s", file=sys.stderr)
            time.sleep(3.0)
            try:
                df = _fetch_one(ticker, start, end)
            except Exception as e2:
                print(f"  {ticker} failed twice: {e2} — skip", file=sys.stderr)
                continue
        if len(df):
            frames.append(df)
        else:
            new_empty.append(ticker)
        time.sleep(delay)
        if (i + 1) % 50 == 0:
            print(f"  progress {i+1}/{len(todo)}", file=sys.stderr)
            _persist(frames, out_path)
            _append_empty(empty_sidecar, new_empty); new_empty = []

    out = _persist(frames, out_path)
    _append_empty(empty_sidecar, new_empty)
    print(f"[krx_adj_oracle] {out['code'].nunique()} tickers covered, "
          f"{len(out):,} rows -> {out_path}", file=sys.stderr)
    return out


def _stamp(df: pd.DataFrame, collected_at: str) -> dict:
    """Vintage of this oracle snapshot — pykrx is a live KRX call (no commit to
    pin), so the snapshot self-describes when/with-what it was collected."""
    d = pd.to_datetime(df["date"]) if len(df) else pd.Series([], dtype="datetime64[ns]")
    return {
        "oracle_collected_at": collected_at,
        "oracle_source": f"pykrx {version('pykrx')}",
        "oracle_n_tickers": df["code"].nunique() if len(df) else 0,
        "oracle_n_rows": len(df),
        "oracle_date_min": str(d.min().date()) if len(df) else "",
        "oracle_date_max": str(d.max().date()) if len(df) else "",
    }


def _write_stamped(df: pd.DataFrame, out_path: Path, stamp: dict) -> None:
    table = pa.Table.from_pandas(df, preserve_index=False)
    md = {str(k).encode(): str(v).encode() for k, v in stamp.items()}
    table = table.replace_schema_metadata({**(table.schema.metadata or {}), **md})
    pq.write_table(table, out_path)


def provenance(path: str = str(ORACLE_PATH)) -> dict[str, str]:
    """Vintage stamp embedded in the oracle parquet (see _stamp)."""
    md = pq.read_schema(str(path)).metadata or {}
    return {k.decode(): v.decode() for k, v in md.items()
            if k.decode().startswith("oracle_")}


def _persist(frames: list[pd.DataFrame], out_path: Path) -> pd.DataFrame:
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=_COLS)
    if len(out):
        out["code"] = out["code"].astype(str).str.zfill(6)
        out = out.drop_duplicates(subset=["code", "date"]).sort_values(["code", "date"])
        out = out.reset_index(drop=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_stamped(out, out_path, _stamp(out, datetime.datetime.now().isoformat(timespec="seconds")))
    return out


def _append_empty(sidecar: Path, tickers: list[str]) -> None:
    if not tickers:
        return
    prev = sidecar.read_text().split() if sidecar.exists() else []
    sidecar.write_text("\n".join(sorted(set(prev) | set(tickers))))


@lru_cache(maxsize=1)
def load_oracle(path: str = str(ORACLE_PATH)) -> pd.DataFrame:
    """Load the cached oracle (date, code, krx_adj_close). Empty if uncollected."""
    if not Path(path).exists():
        return pd.DataFrame(columns=_COLS)
    f = pd.read_parquet(path)
    f["date"] = pd.to_datetime(f["date"])
    f["code"] = f["code"].astype(str).str.zfill(6)
    return f


def _candidate_tickers() -> list[str]:
    a = pd.read_csv(CACHE_DIR / "adjust_anomalies.csv", dtype={"Code": str})
    return sorted(a["Code"].str.zfill(6).unique())


def _all_tickers() -> list[str]:
    import glob
    seen: set[str] = set()
    for fp in glob.glob(str(Path(__file__).resolve().parents[1] / "marcap" / "data" / "marcap-*.parquet")):
        c = pd.read_parquet(fp, columns=["Code"])["Code"].astype(str).str.zfill(6)
        seen |= set(c)
    return sorted(seen)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tickers", help="comma-separated tickers")
    ap.add_argument("--candidates", action="store_true", help="adjust candidate tickers")
    ap.add_argument("--all", action="store_true", help="every marcap ticker (long-running)")
    ap.add_argument("--restart", action="store_true")
    ap.add_argument("--delay", type=float, default=0.4)
    args = ap.parse_args(argv)

    if args.tickers:
        tickers = [t.strip().zfill(6) for t in args.tickers.split(",") if t.strip()]
    elif args.all:
        tickers = _all_tickers()
    else:
        tickers = _candidate_tickers()

    collect(tickers, restart=args.restart, delay=args.delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
