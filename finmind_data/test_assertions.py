"""Integrity assertions for the claims `finmind_data`'s documentation makes.

This repo has no CI; verification is ad-hoc. Run with the data trees populated,
from anywhere:

    python finmind_data/test_assertions.py

or run every package's assertions at once with `./run_assertions.sh` from the
repo root. Each check prints PASS/FAIL; the script exits non-zero if any fail.
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
# The study window every package's figures are quoted on. Duplicated in each
# assertion file because the container holds no shared module to import it from;
# `run_assertions.sh` fails if the copies ever disagree.
WIN_START = pd.Timestamp("2005-01-01")
WIN_END = pd.Timestamp("2024-12-31")


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
    """VERIFICATION.md §§6-9, on the cases they name.

    One case per mechanism the four sections claim: the 現金減資 split, the
    pre-2011 reduction the event file cannot see, FinMind's zero-close encoding
    for a session that did not trade, the cash leg TWSE's 息值 supplies where
    nothing was declared, and the par-value inversion that stays exact on a
    reason it was not written for.
    """
    sys.path.insert(0, str(REPO))
    if not (REPO / "finmind_data/unpriced_actions.parquet").exists():
        return "SKIP (unpriced_actions.parquet not built)"
    import numpy as np

    from finmind_data.adjust import (_PAR_VALUE, _refund_per_share,
                                     load_adjusted)

    # 2412 中華電: a 20 % cash reduction, the filed ratio. §6 claims the par-10
    # identity recovers the refund from the two reference prices alone, so the
    # cash stays in the price-return chain: pr_step = step * (1 - C/before).
    cr = pd.read_parquet(REPO / "finmind_data/capital_reduction.parquet")
    e = cr[cr["stock_id"].astype(str) == "2412"].iloc[0]
    b = float(e["ClosingPriceonTheLastTradingDay"])
    a = float(e["PostReductionReferencePrice"])
    r = (a - b) / (a - 10.0)
    assert abs(r - 0.20) < 0.01, (
        f"VERIFICATION.md §6 claims the par-10 identity returns "
        f"the filed reduction ratio (0.20 for 2412); got r={r:.4f}"
    )
    d = load_adjusted("2412")
    i = int(d.index[d["is_cap_red"]][0])
    step = d["tr_factor"].iloc[i] / d["tr_factor"].iloc[i - 1]
    pr_step = d["pr_factor"].iloc[i] / d["pr_factor"].iloc[i - 1]
    assert abs(pr_step - step * (1.0 - 10.0 * r / b)) < 1e-6, (
        f"§6 claims a 現金減資 keeps its refund in adj_close_pr via "
        f"pr_step = step*(1 - C/before); got pr_step={pr_step:.6f} against "
        f"step={step:.6f}, which would be a cash-free treatment"
    )

    # 2357 華碩 2010-06-24: an 85 % share cancellation six months before the 減資
    # endpoint's first row. §7 claims nothing prices it, so the history behind it
    # is marked instead of silently carrying the jump.
    d = load_adjusted("2357")
    brk = pd.Timestamp("2010-06-24")
    assert not d.loc[d["date"] < brk, "is_valid"].any(), (
        "§7 claims 2357's pre-2010-06-24 history is marked is_valid=False "
        "(unpriced capital reduction); some of it is still flagged valid"
    )
    assert d.loc[d["date"] >= brk, "is_valid"].all(), (
        "§7 claims is_valid is False only *behind* the last break; 2357 has "
        "invalid rows on or after 2010-06-24"
    )

    # §7: close == 0 is a no-trade session, not a price, so it adjusts to NaN.
    d = load_adjusted("8934")
    z = d["close"] == 0
    assert z.sum() > 0 and d.loc[z, ["adj_close_tr", "adj_close_pr"]].isna().all().all(), (
        f"§7 claims a close of 0 adjusts to NaN rather than 0.0; 8934 has "
        f"{int(z.sum())} zero-close rows and "
        f"{int(d.loc[z, 'adj_close_tr'].notna().sum())} of them carry a number"
    )
    # §8: TWSE's own 息值 names the cash leg where nothing was declared. 1520
    # 復盛 2007-08-10 is one of the 143 it resolves — the exchange publishes
    # 權值 0.51 and 息值 2.50 against a before of 37.05.
    if not (REPO / "finmind_data/exright_reference.parquet").exists():
        return "SKIP (exright_reference.parquet not built)"
    ex = pd.read_parquet(REPO / "finmind_data/exright_reference.parquet")
    row = ex[(ex["stock_id"] == "1520")
             & (ex["date"] == pd.Timestamp("2007-08-10"))]
    assert len(row) == 1, "§8 names 1520 2007-08-10 as a TWT49U event; not found"
    row = row.iloc[0]
    assert abs(row["before_price"] - row["after_price"]
               - row["total_value"]) < 1e-6, (
        "§8 claims TWSE's own columns satisfy before - (權值+息值) == after; "
        f"1520 gives {row['before_price']} - {row['total_value']} != "
        f"{row['after_price']}"
    )
    d = load_adjusted("1520")
    i = int(d.index[d["date"] == pd.Timestamp("2007-08-10")][0])
    step = d["tr_factor"].iloc[i] / d["tr_factor"].iloc[i - 1]
    pr_step = d["pr_factor"].iloc[i] / d["pr_factor"].iloc[i - 1]
    want = step * (1.0 - row["cash_value"] / row["before_price"])
    assert abs(pr_step - want) < 1e-6, (
        f"§8 claims a mixed 權息 with no declaration takes its cash leg from "
        f"TWSE's 息值; 1520 2007-08-10 gives pr_step={pr_step:.6f}, expected "
        f"{want:.6f} from 息值={row['cash_value']}"
    )
    # §9: FinMind's removed implementation inverts the par-value rule for every
    # reason. 2364 倫飛 2021-10-08 is a 彌補虧損 that refunds nothing and reprices
    # 3.04 → 24.01, so that inversion yields r = 1.497 — more shares cancelled
    # than exist. The composition is exact anyway, which is why its total-return
    # step needs no reason branch and why the pr split, which uses r itself,
    # rejects the same number.
    red = pd.read_parquet(REPO / "finmind_data/capital_reduction.parquet")
    rr = red[(red["stock_id"] == "2364") & (red["date"] == "2021-10-08")].iloc[0]
    before = float(rr["ClosingPriceonTheLastTradingDay"])
    after = float(rr["PostReductionReferencePrice"])
    r_fm = (after - before) / (after - _PAR_VALUE)
    assert r_fm > 1.0, (
        f"§9 names 2364 as a case where the par-value inversion returns an "
        f"impossible cancelled fraction; it returns {r_fm:.3f}"
    )
    assert abs((before - _PAR_VALUE * r_fm) / (1.0 - r_fm) - after) < 1e-9, (
        "§9 claims the par-value assumption cancels, so the inversion "
        f"reproduces the reference price for any reason; 2364 gives "
        f"{(before - _PAR_VALUE * r_fm) / (1.0 - r_fm):.6f} vs {after}"
    )
    assert np.isnan(_refund_per_share(np.array([before]), np.array([after]))[0]), (
        f"§9 claims the pr split rejects the same r the tr chain survives; "
        f"_refund_per_share accepted 2364's r={r_fm:.3f}"
    )
    return (f"2412 現金減資 r={r:.3f} split; 2357 pre-2011 break marked; "
            f"8934 {int(z.sum())} zero closes → NaN; "
            f"1520 cash leg {row['cash_value']} from TWSE 息值; "
            f"2364 par inversion r={r_fm:.3f} yet exact")


CHECKS = [
    test_taiwan_ohlcv_one_per_universe,
    test_taiwan_overlay_covers_2005_2014,
    test_capital_reduction_artifact_exists,
    test_taiwan_adjust_canonical_cases,
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
