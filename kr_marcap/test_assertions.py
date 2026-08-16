"""Integrity assertions for the claims `kr_marcap`'s documentation makes.

This repo has no CI; verification is ad-hoc. Run with the data trees populated,
from anywhere:

    python kr_marcap/test_assertions.py

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
# The manuscript's study window (fn_percolation). Duplicated in each package's
# assertion file because the container holds no shared module to import it from;
# `run_assertions.sh` fails if the copies ever disagree.
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


# ---- a SEIBro ₩0 dividend means non-payment, not a lost amount --------------
def test_seibro_zero_is_non_payment():
    """`load_cash_events` keeps only `dps > 0`, so every ₩0 cash-kind event is
    dropped as a non-payer. If a zero instead meant "amount not recorded", each
    one would be an uncorrected 배당락 sitting inside `adj_close_tr` — the whole
    total-return layer rests on the reading. DART is the independent test: it
    confirms a payment for a few percent of the zeros against ~78 % of the
    priced control (kr_marcap/README.md, 'A zero is a non-payment').
    """
    sys.path.insert(0, str(REPO))
    ev_fp = REPO / "kr_marcap/cache/dividend_events.parquet"
    dart_fp = REPO / "kr_marcap/cache/dividends.parquet"
    if not (ev_fp.exists() and dart_fp.exists()):
        return "SKIP (dividend caches not built)"
    from kr_marcap.dividend_events import _CASH_KINDS

    ev = pd.read_parquet(ev_fp)
    ev = ev[ev["kind"].isin(_CASH_KINDS)]
    dart = pd.read_parquet(dart_fp)
    dart["code"] = dart["code"].astype(str).str.zfill(6)
    dart = dart[dart["dps"] > 0]
    paid = set(zip(dart["code"], dart["fiscal_year"]))
    fy0, fy1 = int(dart["fiscal_year"].min()), int(dart["fiscal_year"].max())

    def confirmed(sub):
        w = sub[sub["record_date"].dt.year.between(fy0, fy1)]
        return sum((c, y) in paid for c, y in
                   zip(w["code"], w["record_date"].dt.year)) / len(w)

    zero, priced = confirmed(ev[ev["dps"] == 0]), confirmed(ev[ev["dps"] > 0])
    # A zero row that duplicated a priced one would be a 차등배당 artifact, not a
    # standalone event, and would make the comparison meaningless.
    sib = set(map(tuple, ev.loc[ev["dps"] > 0, ["code", "record_date"]].to_numpy()))
    dup = sum((c, d) in sib for c, d in
              zip(*[ev.loc[ev["dps"] == 0, k] for k in ("code", "record_date")]))
    assert dup == 0, (
        f"README claims ₩0 events are standalone ('None shares a 기준일 with a "
        f"priced row') but {dup} share one — the zeros may be 차등배당 halves"
    )
    assert zero < 0.10 and priced > 0.70, (
        f"README claims DART confirms '5.1 % of the zeros against 78.3 % of the "
        f"priced control'; got {zero:.1%} vs {priced:.1%}. A zero no longer reads "
        f"as a non-payment, so `dps > 0` is dropping real dividends"
    )
    return (f"SEIBro ₩0 → DART confirms {zero:.1%} vs {priced:.1%} priced "
            f"(FY{fy0}-{fy1}), {dup} shared 기준일")


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


# ---- the open-data reconstruction reaches the paid series it reproduces ------
def test_fnguide_benchmark_agreement():
    """CONSTRUCTION.md leads on '99.977 %' of price-return and '99.969 %' of
    total-return daily returns agreeing with FnGuide. Recomputed here from the
    gate's own per-ticker output rather than re-run, so a rebuild that degrades
    the reconstruction fails the suite even if nobody reads stdout.
    """
    fp = REPO / "kr_marcap/cache/fnguide_validation.csv"
    if not fp.exists():
        return "SKIP (run kr_marcap.validate_against_fnguide first)"
    per = pd.read_csv(fp, dtype={"code": str})
    out = []
    for conv, claim in (("pr", 0.99977), ("tr", 0.99969)):
        days = int(per[f"n_days_{conv}"].sum())
        bad = int(per[f"n_disagree_{conv}"].sum())
        rate = 1.0 - bad / days
        # 1e-5 absolute: the claim is quoted to 3 decimal places as a percentage.
        assert rate >= claim - 1e-5, (
            f"CONSTRUCTION.md claims {conv.upper()} daily returns agree with "
            f"FnGuide on {claim:.5%} of ticker-days, but the gate's output gives "
            f"{rate:.5%} ({bad:,} disagreeing of {days:,})"
        )
        out.append(f"{conv.upper()} {rate:.4%} ({bad:,}/{days:,})")
    return "; ".join(out)


def test_fnguide_disagreement_is_the_stuck_oracle():
    """CONSTRUCTION.md attributes 59.8 % of all disagreement to a stuck KRX
    oracle value freezing our series, and calls the defect 'severe per name and
    narrow across names' — 9 tickers. Both halves are load-bearing: the first
    says the residue is one diagnosed bug rather than diffuse noise, the second
    is why an aggregate per-ticker rate never surfaced it. If a future oracle
    re-pull fixes the artifact this fails, and the document's causal account
    needs rewriting rather than quietly carrying on.
    """
    fp = REPO / "kr_marcap/cache/fnguide_validation_days.csv"
    if not fp.exists():
        return "SKIP (run kr_marcap.validate_against_fnguide first)"
    days = pd.read_csv(fp, dtype={"code": str})
    stuck = days["cause"] == "ours frozen — stuck KRX oracle"
    share = stuck.mean()
    n_tickers = days.loc[stuck, "code"].nunique()
    assert share > 0.5, (
        f"CONSTRUCTION.md attributes 59.8 % of disagreeing ticker-days to the "
        f"stuck KRX oracle; the gate's output attributes {share:.1%}"
    )
    assert n_tickers <= 20, (
        f"CONSTRUCTION.md calls the stuck-oracle defect narrow across names "
        f"(9 tickers); the gate's output shows {n_tickers}"
    )
    return f"stuck oracle = {share:.1%} of {len(days):,} disagreeing days, {n_tickers} tickers"


CHECKS = [
    test_kr_trading_days_2005_2024,
    test_kr_kospi_common_count,
    test_adjust_heuristics_removed,
    test_adjust_canonical_cases,
    test_fnguide_benchmark_agreement,
    test_fnguide_disagreement_is_the_stuck_oracle,
    test_seibro_zero_is_non_payment,
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
