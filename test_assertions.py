"""Integrity assertions for finance_db outputs that the manuscripts pin to.

Canonical home for claim checks (this repo has no CI; verification is ad-hoc).
Run from the repo root with the data trees populated:

    python test_assertions.py

Each check prints PASS/FAIL; the script exits non-zero if any fail.
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


# ---- Korea: KOSPI-only common count (fn_percolation \nKospiTickers) ----------
# All-time count. Manuscript reported 1,272; corrected to 1,274 on 2026-06-23
# when classify.py stopped routing names ending in 우 to 'preferred' — 003810 대우
# and 009990 미우 are genuine KOSPI commons (code ends '0'), not preferred shares.
# Both delisted pre-2005, so the 2005-2024 study window (1,027 in-window) is
# unaffected; this is a descriptive all-time tally only.
def test_kr_kospi_common_count():
    pan = pd.read_parquet(REPO / "kr_marcap/cache/universe_panel.parquet")
    com = pan[pan["kind"] == "common"]
    dominant = com.groupby("code")["market"].agg(lambda s: s.value_counts().index[0])
    n_kospi = int((dominant == "KOSPI").sum())
    n_common = int(com["code"].nunique())
    assert n_kospi == 1274, (
        f"KOSPI common = {n_kospi}, expected 1,274 "
        f"(manuscript's 1,272 predates the 우-suffix classifier fix)"
    )
    return f"KOSPI common = {n_kospi}; total panel common = {n_common}"


# ---- Korea: the calibrated adjustment heuristics stay REMOVED (official only) --
def test_adjust_heuristics_removed():
    """Entity-break/reset classification must come from official ground truth
    (kr_marcap.corp_actions + krx_adj_oracle), never from constants tuned to a
    validation set. Guards against reintroducing the removed heuristics."""
    sys.path.insert(0, str(REPO))
    from kr_marcap import adjust as A
    forbidden = ["_CORROBORATION_TOL", "_GAP_DAYS", "_GAP_SHARE_LOW",
                 "_GAP_SHARE_HIGH", "_GAP_RESUME_RET", "_RESET_VOL_SPIKE",
                 "_RESET_SHARE_MIN", "_RESET_SHARE_MAX", "_RESET_DIVERGE"]
    present = [k for k in forbidden if hasattr(A, k)]
    assert not present, f"removed adjustment heuristics reintroduced: {present}"
    assert hasattr(A, "corp_actions") and hasattr(A, "load_oracle"), \
        "adjust.py must consume corp_actions (official breaks) + krx_adj_oracle (reset)"
    return "adjustment heuristics removed; official sources wired"


# ---- Korea: adjusted series matches KRX official 수정주가 on the canonical cases -
def test_adjust_canonical_cases():
    sys.path.insert(0, str(REPO))
    if not (REPO / "kr_marcap/cache/adj_factors.parquet").exists():
        return "SKIP (adj_factors.parquet not built)"
    from kr_marcap.adjust import load_adjusted

    def adj_ret(code, day):
        d = load_adjusted(code).sort_values("date")
        d["r"] = d["adj_close"].pct_change()
        row = d[d["date"] == pd.Timestamp(day)]
        return float(row["r"].iloc[0]) if len(row) else float("nan")

    # 005930 50:1 face split: adjusted series stays continuous (the ~ -2% it
    # traded), not the raw -98% drop — ChangesRatio backbone, no break.
    s = adj_ret("005930", "2018-05-04")
    assert abs(s) < 0.1, f"Samsung 2018-05-04 split not continuous: adj_ret={s}"
    # 232830 거래재개 reset: official KRX move (+21%), not the +205% admin-ref CR.
    r = adj_ret("232830", "2023-06-29")
    assert 0.15 < r < 0.30, f"232830 reset not at the traded move: adj_ret={r} (want ~0.21)"
    return f"canonical: Samsung split adj_ret={s:+.3f}, 232830 reset adj_ret={r:+.3f}"


# ---- adj_factors carries the marcap vintage stamp (reproducibility provenance) -
def test_adjust_provenance_stamp():
    """A factors file must self-describe the marcap vintage it was built from
    (commit + data span), so a later rebuild that drifts is attributable."""
    sys.path.insert(0, str(REPO))
    if not (REPO / "kr_marcap/cache/adj_factors.parquet").exists():
        return "SKIP (adj_factors.parquet not built)"
    from kr_marcap.adjust import provenance
    p = provenance()
    assert p.get("marcap_commit"), f"no marcap_commit stamp in adj_factors: {p}"
    assert p.get("marcap_data_max_date"), f"no marcap_data_max_date stamp: {p}"
    return f"provenance: marcap @{p['marcap_commit'][:7]} through {p['marcap_data_max_date']}"


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
    """Survivorship invariant.

    The 42-name overlay must cover every 2005-2014 4-digit common delisting
    FinMind purged. Codes are restricted to 4-digit numeric (the universe's own
    filter); pre-2005 names never trade in-window and 2015+ absentees are
    ETF/TDR instruments the universe excludes. The naive "all delisted ids have
    OHLCV" form was a false alarm.
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


# ---- consolidate_capred delivered artifact ---------------------------------
def test_capital_reduction_artifact_exists():
    fp = REPO / "finmind_data/capital_reduction.parquet"
    assert fp.exists(), "capital_reduction.parquet documented as delivered but missing"
    return "capital_reduction.parquet present"


# ---- Taiwan: the adjusted series on its three canonical corporate actions ---
def test_taiwan_adjust_canonical_cases():
    """ADJUSTED_PRICE_VERIFICATION.md §7 and §8, on the cases they name.

    One case per mechanism the two sections claim: the 現金減資 split, the
    pre-2011 reduction the event file cannot see, and FinMind's zero-close
    encoding for a session that did not trade.
    """
    sys.path.insert(0, str(REPO))
    if not (REPO / "finmind_data/unpriced_actions.parquet").exists():
        return "SKIP (unpriced_actions.parquet not built)"
    from finmind_data.adjust import load_adjusted

    # 2412 中華電: a 20 % cash reduction, the filed ratio. §7 claims the par-10
    # identity recovers the refund from the two reference prices alone, so the
    # cash stays in the price-return chain: pr_step = step * (1 - C/before).
    cr = pd.read_parquet(REPO / "finmind_data/capital_reduction.parquet")
    e = cr[cr["stock_id"].astype(str) == "2412"].iloc[0]
    b = float(e["ClosingPriceonTheLastTradingDay"])
    a = float(e["PostReductionReferencePrice"])
    r = (a - b) / (a - 10.0)
    assert abs(r - 0.20) < 0.01, (
        f"ADJUSTED_PRICE_VERIFICATION.md §7 claims the par-10 identity returns "
        f"the filed reduction ratio (0.20 for 2412); got r={r:.4f}"
    )
    d = load_adjusted("2412")
    i = int(d.index[d["is_cap_red"]][0])
    step = d["tr_factor"].iloc[i] / d["tr_factor"].iloc[i - 1]
    pr_step = d["pr_factor"].iloc[i] / d["pr_factor"].iloc[i - 1]
    assert abs(pr_step - step * (1.0 - 10.0 * r / b)) < 1e-6, (
        f"§7 claims a 現金減資 keeps its refund in adj_close_pr via "
        f"pr_step = step*(1 - C/before); got pr_step={pr_step:.6f} against "
        f"step={step:.6f}, which would be a cash-free treatment"
    )

    # 2357 華碩 2010-06-24: an 85 % share cancellation six months before the 減資
    # endpoint's first row. §8 claims nothing prices it, so the history behind it
    # is marked instead of silently carrying the jump.
    d = load_adjusted("2357")
    brk = pd.Timestamp("2010-06-24")
    assert not d.loc[d["date"] < brk, "is_valid"].any(), (
        "§8 claims 2357's pre-2010-06-24 history is marked is_valid=False "
        "(unpriced capital reduction); some of it is still flagged valid"
    )
    assert d.loc[d["date"] >= brk, "is_valid"].all(), (
        "§8 claims is_valid is False only *behind* the last break; 2357 has "
        "invalid rows on or after 2010-06-24"
    )

    # §8: close == 0 is a no-trade session, not a price, so it adjusts to NaN.
    d = load_adjusted("8934")
    z = d["close"] == 0
    assert z.sum() > 0 and d.loc[z, ["adj_close_tr", "adj_close_pr"]].isna().all().all(), (
        f"§8 claims a close of 0 adjusts to NaN rather than 0.0; 8934 has "
        f"{int(z.sum())} zero-close rows and "
        f"{int(d.loc[z, 'adj_close_tr'].notna().sum())} of them carry a number"
    )
    return (f"2412 現金減資 r={r:.3f} split; 2357 pre-2011 break marked; "
            f"8934 {int(z.sum())} zero closes → NaN")


# ---- KOSPI200 index panel: in-window membership stays complete (App. B.3) ---
def test_kospi200_panel_inwindow_complete():
    """fn_percolation's index-exclusion robustness (App. B.3) relies on the
    KOSPI200 panel carrying a complete ~200 members on every in-window date.
    Pre-2005 the panel ramps 1->200 (event-log-only reconstruction); that is
    out of scope. This tripwire fires if a panel regeneration ever collapses
    in-window membership.
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
    test_adjust_heuristics_removed,
    test_adjust_canonical_cases,
    test_taiwan_ohlcv_one_per_universe,
    test_taiwan_overlay_covers_2005_2014,
    test_capital_reduction_artifact_exists,
    test_taiwan_adjust_canonical_cases,
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
