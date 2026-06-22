"""Integrity assertions for finance_db outputs that the manuscripts pin to.

Canonical home for claim checks (this repo has no CI; verification is ad-hoc).
Run from the repo root with the data trees populated:

    python test_assertions.py

Each check prints PASS/FAIL; the script exits non-zero if any fail. See
Research_Integrity_Audit.md for the finding each check guards.
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent
WIN_START = pd.Timestamp("2005-01-01")
WIN_END = pd.Timestamp("2024-12-31")


# ---- Korea: trading days (fn_percolation \nDaysKoreaTotal = 4,940) ----------
def test_kr_trading_days_2005_2024():
    dates = set()
    for fp in sorted(glob.glob(str(REPO / "marcap/data/marcap-*.parquet"))):
        y = int(os.path.basename(fp).split("-")[-1][:4])
        if WIN_START.year <= y <= WIN_END.year:
            d = pd.to_datetime(pd.read_parquet(fp, columns=["Date"])["Date"]).dt.normalize()
            dates |= set(d.unique())
    n = sum(1 for x in dates if WIN_START <= x <= WIN_END)
    assert n == 4940, f"KR trading days 2005-2024 = {n}, manuscript pins 4,940"
    return f"KR trading days = {n}"


# ---- Korea: KOSPI-only common count (fn_percolation \nKospiTickers = 1,272) --
def test_kr_kospi_common_count():
    pan = pd.read_parquet(REPO / "kr_marcap/cache/universe_panel.parquet")
    com = pan[pan["kind"] == "common"]
    dominant = com.groupby("code")["market"].agg(lambda s: s.value_counts().index[0])
    n_kospi = int((dominant == "KOSPI").sum())
    n_common = int(com["code"].nunique())
    assert n_kospi == 1272, f"KOSPI common = {n_kospi}, manuscript pins 1,272"
    return f"KOSPI common = {n_kospi}; total panel common = {n_common}"


# ---- Korea: price-adjustment constants stay equal to PRICE_ADJUSTMENT.md ----
def test_adjust_constants_match_doc():
    sys.path.insert(0, str(REPO))
    from kr_marcap import adjust as A
    expected = {
        "_CORROBORATION_TOL": 0.5, "_GAP_DAYS": 365, "_GAP_SHARE_LOW": 0.67,
        "_GAP_SHARE_HIGH": 1.5, "_GAP_RESUME_RET": 3.0, "_RESET_VOL_SPIKE": 30.0,
        "_RESET_SHARE_MIN": 0.005, "_RESET_SHARE_MAX": 0.5, "_RESET_DIVERGE": 0.05,
        "_RATIO_FLAG_LOW": 0.1, "_RATIO_FLAG_HIGH": 10.0,
    }
    bad = {k: getattr(A, k) for k, v in expected.items() if getattr(A, k) != v}
    assert not bad, f"adjust.py constants drifted from PRICE_ADJUSTMENT.md: {bad}"
    return "adjust.py constants == PRICE_ADJUSTMENT.md"


# ---- Taiwan: one OHLCV file per universe id --------------------------------
def _tw_ids():
    u = pd.read_parquet(REPO / "finmind_data/universe.parquet")
    d = pd.read_parquet(REPO / "finmind_data/delisted_universe.parquet")
    uid = set(u["stock_id"].astype(str))
    files = {os.path.basename(p).split(".")[0]
             for p in glob.glob(str(REPO / "finmind_data/ohlcv/*"))}
    return u, d, uid, files


def test_taiwan_ohlcv_one_per_universe():
    u, _, uid, files = _tw_ids()
    missing = uid - files
    assert len(u) == 2154, f"Taiwan universe = {len(u)}, README pins 2,154"
    assert not missing, f"{len(missing)} universe ids have no OHLCV file"
    return f"Taiwan universe = {len(u)}; all have OHLCV"


def test_taiwan_overlay_covers_2005_2014():
    """Survivorship invariant (Research_Integrity_Audit.md §1).

    The 42-name overlay must cover every 2005-2014 4-digit common delisting
    FinMind purged. Codes are restricted to 4-digit numeric (the universe's own
    filter); pre-2005 names never trade in-window and 2015+ absentees are
    ETF/TDR instruments the universe excludes. The naive "all delisted ids have
    OHLCV" form was a false alarm — see §1.
    """
    u, d, uid, _ = _tw_ids()
    d = d.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["sid"] = d["stock_id"].astype(str)
    d4 = d[d["sid"].str.fullmatch(r"\d{4}")]
    in_2005_2014 = d4[(d4["date"] >= WIN_START) & (d4["date"] <= pd.Timestamp("2014-12-31"))]
    missing = sorted(set(in_2005_2014["sid"]) - uid)
    assert not missing, (
        f"{len(missing)} 2005-2014 4-digit common delistings absent from "
        f"universe.parquet (overlay gap): {missing}"
    )
    n_overlay = int(u[u["type"].isna()]["stock_id"].astype(str).str.fullmatch(r"\d{4}").sum())
    assert n_overlay == 42, f"4-digit type=NaN overlay ids = {n_overlay}, expected 42"
    return "2005-2014 commons fully covered; 42-name overlay present"


# ---- consolidate_capred delivered artifact (S2) ----------------------------
def test_capital_reduction_artifact_exists():
    fp = REPO / "finmind_data/capital_reduction.parquet"
    assert fp.exists(), "capital_reduction.parquet documented as delivered but missing"
    return "capital_reduction.parquet present"


# ---- KOSPI200 index panel: in-window membership stays complete (App. B.3) ---
def test_kospi200_panel_inwindow_complete():
    """fn_percolation's index-exclusion robustness (App. B.3) relies on the
    KOSPI200 panel carrying a complete ~200 members on every in-window date.
    Pre-2005 the panel ramps 1->200 (event-log-only reconstruction); that is
    out of scope. This tripwire fires if a panel regeneration ever collapses
    in-window membership. See Research_Integrity_Audit.md D1/S4.
    """
    fp = REPO / "krx_supplement/output/index_panel_daily.parquet"
    df = pd.read_parquet(fp)
    df["date"] = pd.to_datetime(df["date"])
    k = df[df["index"] == "코스피 200"]
    g = k.groupby("date")["ticker"].nunique()
    inwin = g[(g.index >= WIN_START) & (g.index <= WIN_END)]
    med = int(inwin.median())
    assert inwin.min() >= 199 and med == 200, (
        f"KOSPI200 in-window membership degraded: min={inwin.min()} "
        f"median={med} max={inwin.max()}"
    )
    return f"KOSPI200 in-window membership median={med}, range [{inwin.min()},{inwin.max()}]"


CHECKS = [
    test_kr_trading_days_2005_2024,
    test_kr_kospi_common_count,
    test_adjust_constants_match_doc,
    test_taiwan_ohlcv_one_per_universe,
    test_taiwan_overlay_covers_2005_2014,
    test_capital_reduction_artifact_exists,
    test_kospi200_panel_inwindow_complete,
]


if __name__ == "__main__":
    failures = 0
    for fn in CHECKS:
        try:
            msg = fn()
            print(f"PASS  {fn.__name__}: {msg}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # missing data tree, etc. — report, don't hide
            failures += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(CHECKS) - failures}/{len(CHECKS)} checks passed")
    sys.exit(1 if failures else 0)
