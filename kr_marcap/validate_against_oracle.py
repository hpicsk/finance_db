"""Automated validation of our adjusted series against KRX official 수정주가.

Replaces the manual FnGuide cross-check with an official, reproducible gate.
For every ticker the KRX oracle (``krx_adj_oracle.parquet``) covers, it compares
our adjusted daily return (from ``adj_factors.parquet``) to KRX's own official
adjusted daily return on the shared trading days, and reports the days that
disagree beyond a rounding tolerance.

A disagreement means one of:
  - a 거래재개 reset the oracle override should have caught (our gross != official),
  - a series break the corp_actions calendar missed (our pre-break history is
    scaled differently from KRX's current entity),
  - or a genuine oracle gap / artifact (the oracle is itself dirty on ₩1
    sentinels etc. — those are expected and listed for inspection).

Output: ``cache/oracle_validation.csv`` — one row per disagreeing (code, date)
with our vs official return; plus a per-ticker summary to stdout.

Usage:
    python -m kr_marcap.validate_against_oracle
    python -m kr_marcap.validate_against_oracle --tol 0.01 --tickers 232830,005930
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from kr_marcap.adjust import FACTORS_PATH
from kr_marcap.krx_adj_oracle import load_oracle

CACHE_DIR = Path(__file__).resolve().parent / "cache"
OUT_PATH = CACHE_DIR / "oracle_validation.csv"
# |our_ret - official_ret|. marcap rounds 등락률 to 0.01% while KRX 수정주가 uses the
# exact move, so legitimate days differ by up to ~0.01; 0.02 surfaces only real
# divergences (missed resets/breaks). Pass --tol 0.005 to also see the rounding.
DEFAULT_TOL = 0.02


def validate(tol: float = DEFAULT_TOL, tickers: list[str] | None = None,
             factors_path: Path = FACTORS_PATH) -> pd.DataFrame:
    fac = pd.read_parquet(factors_path, columns=["date", "code", "adj_close", "valid"])
    fac["date"] = pd.to_datetime(fac["date"])
    fac["code"] = fac["code"].astype(str).str.zfill(6)
    fac = fac[fac["valid"] & (fac["adj_close"] > 0)]

    oracle = load_oracle()
    if oracle.empty:
        raise FileNotFoundError("oracle empty — run `python -m kr_marcap.krx_adj_oracle` first")

    if tickers:
        tickers = [t.zfill(6) for t in tickers]
        fac = fac[fac["code"].isin(tickers)]
        oracle = oracle[oracle["code"].isin(tickers)]

    m = fac.merge(oracle, on=["code", "date"], how="inner").sort_values(["code", "date"])
    our_prev = m.groupby("code", sort=False)["adj_close"].shift(1)
    ora_prev = m.groupby("code", sort=False)["krx_adj_close"].shift(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        m["our_ret"] = m["adj_close"] / our_prev - 1.0
        m["official_ret"] = m["krx_adj_close"] / ora_prev - 1.0
    m["diff"] = (m["our_ret"] - m["official_ret"]).abs()

    bad = m[m["diff"] > tol].dropna(subset=["diff"]).copy()
    bad = bad[["code", "date", "our_ret", "official_ret", "diff"]].sort_values("diff", ascending=False)

    n_tickers = m["code"].nunique()
    bad_tickers = bad["code"].nunique()
    print(f"[validate] {n_tickers} tickers cross-checked vs KRX 수정주가, tol={tol}", file=sys.stderr)
    print(f"  disagreeing days: {len(bad):,} across {bad_tickers} tickers "
          f"({100*(n_tickers-bad_tickers)/max(n_tickers,1):.1f}% of tickers agree on every shared day)",
          file=sys.stderr)
    if len(bad):
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        bad.to_csv(OUT_PATH, index=False)
        print(f"  worst:\n{bad.head(12).to_string(index=False)}", file=sys.stderr)
        print(f"  -> {OUT_PATH}", file=sys.stderr)
    elif OUT_PATH.exists():
        OUT_PATH.unlink()
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tol", type=float, default=DEFAULT_TOL)
    ap.add_argument("--tickers", help="comma-separated subset")
    args = ap.parse_args(argv)
    tickers = [t.strip() for t in args.tickers.split(",")] if args.tickers else None
    validate(tol=args.tol, tickers=tickers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
