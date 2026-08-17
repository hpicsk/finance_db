"""Integrity assertions for the claims `kr_marcap`'s documentation makes.

This repo has no CI; verification is ad-hoc. Run with the data trees populated,
from anywhere:

    python kr_marcap/test_assertions.py

or run every package's assertions at once with `./run_assertions.sh` from the
repo root. Each check prints PASS, FAIL, or SKIP where a prerequisite
artifact is absent, along with `n`, the size of the population it examined.
The script exits non-zero if any check fails, if any examined nothing, and if
any skipped — a skip verified nothing, so iterating without the artifact takes
`--allow-skips`. `n` is held against `populations.json`, which records what
each check last read; re-seed it with `--write-populations` after a refresh.
"""
from __future__ import annotations

import glob
import json
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
# Each check's population, recorded so a tree that lost rows fails rather
# than passing on a smaller one. Per package, not per repo: the root is a
# container and holds no package's numbers.
POPULATIONS = Path(__file__).with_name("populations.json")


class Skipped(Exception):
    """A prerequisite artifact is absent, so this check verified nothing.

    Distinct from a pass because it is: it used to print as one, which is the
    same confusion the population guard below exists to remove.
    """


# ---- Korea: trading days in the study window --------------------------------
# The session calendar every per-date panel in this repo is built on, so a
# marcap re-clone that shifts it shifts every downstream count silently.
def test_kr_trading_days_2005_2024():
    dates = set()
    for fp in sorted(glob.glob(str(REPO / "marcap/data/marcap-*.parquet"))):
        y = int(os.path.basename(fp).split("-")[-1][:4])
        if WIN_START.year <= y <= WIN_END.year:
            d = pd.to_datetime(pd.read_parquet(fp, columns=["Date"])["Date"]).dt.normalize()
            dates |= set(d.unique())
    n = sum(1 for x in dates if WIN_START <= x <= WIN_END)
    assert n == 4940, (
        f"KR trading days 2005-2024 = {n}; the marcap clone this repo is built "
        f"on carries 4,940 sessions in the window"
    )
    return f"KR trading days = {n}", n


# ---- Korea: KOSPI-only common count -----------------------------------------
# All-time count. Was 1,272 until 2026-06-23, when classify.py stopped routing
# names ending in 우 to 'preferred' — 003810 대우
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
        f"(1,272 predates the 우-suffix classifier fix)"
    )
    return f"KOSPI common = {n_kospi}; total panel common = {n_common}", n_common


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
    return "adjustment heuristics removed; official sources wired", len(forbidden)


# ---- Korea: adjusted series matches KRX official 수정주가 on the canonical cases -
def test_adjust_canonical_cases():
    sys.path.insert(0, str(REPO))
    if not (REPO / "kr_marcap/cache/adj_factors.parquet").exists():
        raise Skipped("adj_factors.parquet not built")
    from kr_marcap.adjust import load_adjusted

    read = []

    def adj_ret(code, day):
        d = load_adjusted(code).sort_values("date")
        read.append(len(d))
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
    return (f"canonical: Samsung split adj_ret={s:+.3f}, "
            f"232830 reset adj_ret={r:+.3f}"), sum(read)


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
        raise Skipped("dividend caches not built")
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
            f"(FY{fy0}-{fy1}), {dup} shared 기준일"), len(ev)


# ---- adj_factors carries the marcap vintage stamp (reproducibility provenance) -
def test_adjust_provenance_stamp():
    """A factors file must self-describe the marcap vintage it was built from
    (commit + data span), so a later rebuild that drifts is attributable."""
    sys.path.insert(0, str(REPO))
    if not (REPO / "kr_marcap/cache/adj_factors.parquet").exists():
        raise Skipped("adj_factors.parquet not built")
    from kr_marcap.adjust import provenance
    p = provenance()
    assert p.get("marcap_commit"), f"no marcap_commit stamp in adj_factors: {p}"
    assert p.get("marcap_data_max_date"), f"no marcap_data_max_date stamp: {p}"
    return (f"provenance: marcap @{p['marcap_commit'][:7]} through "
            f"{p['marcap_data_max_date']}"), len(p)


# ---- the open-data reconstruction reaches the paid series it reproduces ------
def test_fnguide_benchmark_agreement():
    """CONSTRUCTION.md leads on '99.977 %' of price-return and '99.969 %' of
    total-return daily returns agreeing with FnGuide. Recomputed here from the
    gate's own per-ticker output rather than re-run, so a rebuild that degrades
    the reconstruction fails the suite even if nobody reads stdout.
    """
    fp = REPO / "kr_marcap/cache/fnguide_validation.csv"
    if not fp.exists():
        raise Skipped("run kr_marcap.validate_against_fnguide first")
    per = pd.read_csv(fp, dtype={"code": str})
    out = []
    for conv, claim in (("pr", 0.99977), ("tr", 0.99969)):
        days = int(per[f"n_days_{conv}"].sum())
        bad = int(per[f"n_disagree_{conv}"].sum())
        # The rate is only a claim about the reconstruction while it is measured
        # over the population CONSTRUCTION.md quotes it over. A gate re-run that
        # covered a handful of tickers would push `rate` toward 1.0 and pass the
        # bound below while the headline described nothing.
        assert (len(per), days) == (3535, 10255070), (
            f"CONSTRUCTION.md quotes {conv.upper()} agreement over 10,255,070 "
            f"shared ticker-days across 3,535 tickers; this validation run "
            f"covers {days:,} across {len(per):,}. A re-run against a newer "
            f"marcap vintage owes the document a re-quote, not a passing test"
        )
        rate = 1.0 - bad / days
        # 1e-5 absolute: the claim is quoted to 3 decimal places as a percentage.
        assert rate >= claim - 1e-5, (
            f"CONSTRUCTION.md claims {conv.upper()} daily returns agree with "
            f"FnGuide on {claim:.5%} of ticker-days, but the gate's output gives "
            f"{rate:.5%} ({bad:,} disagreeing of {days:,})"
        )
        out.append(f"{conv.upper()} {rate:.4%} ({bad:,}/{days:,})")
    return "; ".join(out), len(per)


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
        raise Skipped("run kr_marcap.validate_against_fnguide first")
    days = pd.read_csv(fp, dtype={"code": str})
    # Both bounds below are shares or ceilings, and a residue that collapsed
    # would satisfy them without the defect being there to describe: an empty
    # `days` makes `n_tickers` 0, and a one-row one makes `share` 1.0. Pin the
    # population first so the two bounds are bounds on something.
    assert len(days) == 5511, (
        f"CONSTRUCTION.md puts the residue at 5,511 disagreeing ticker-days and "
        f"apportions it in a table; the gate's output now holds {len(days):,}, "
        f"so the apportionment is measured over a different denominator"
    )
    stuck = days["cause"] == "ours frozen — stuck KRX oracle"
    share = stuck.mean()
    n_tickers = days.loc[stuck, "code"].nunique()
    assert share > 0.5, (
        f"CONSTRUCTION.md attributes 59.8 % of disagreeing ticker-days to the "
        f"stuck KRX oracle; the gate's output attributes {share:.1%}"
    )
    # Two-sided: the docstring's own case for this check is that a re-pull which
    # *fixes* the oracle must fail it, and a one-sided ceiling is satisfied most
    # comfortably by the defect disappearing.
    assert 5 <= n_tickers <= 20, (
        f"CONSTRUCTION.md calls the stuck-oracle defect narrow across names but "
        f"present (9 tickers); the gate's output shows {n_tickers}"
    )
    return (f"stuck oracle = {share:.1%} of {len(days):,} disagreeing days, "
            f"{n_tickers} tickers"), len(days)


CHECKS = [
    test_kr_trading_days_2005_2024,
    test_kr_kospi_common_count,
    test_adjust_heuristics_removed,
    test_adjust_canonical_cases,
    test_adjust_provenance_stamp,
    test_fnguide_benchmark_agreement,
    test_fnguide_disagreement_is_the_stuck_oracle,
    test_seibro_zero_is_non_payment,
]


if __name__ == "__main__":
    # A check that skipped verified nothing, which is the state this runner
    # exists to tell apart from a pass — and a suite of nothing but skips used to
    # exit 0, which is the same confusion one layer up from the one `Skipped`
    # fixed. Tolerable while iterating locally, never on the path that reproduces
    # the tree, so the strict reading is the default and the loose one is asked
    # for by name.
    allow_skips = "--allow-skips" in sys.argv[1:]
    # The population a check examined fingerprints the tree it read, and non-zero
    # is only the floor of what that fingerprint catches: a count that halves
    # still passes. A population that *grew* is a re-pull and says nothing; one
    # that *shrank* means the check now reads less of the tree than it did, which
    # is the same silent weakening `n` was added to expose, one revision later.
    # The bound is per check because a population clipped to the study window
    # cannot legitimately move at all, while one open past the window grows every
    # time the vendor is re-pulled — a single rule would either fail every
    # refresh or catch nothing.
    baseline = json.loads(POPULATIONS.read_text()) if POPULATIONS.exists() else {}
    observed = {}
    failures = skipped = 0
    for fn in CHECKS:
        try:
            # Every check returns the size of the population it examined. One that
            # examined none of it cannot have found anything wrong, and prints the
            # same PASS as one that examined all of it — so the empty case fails
            # here, once, rather than in each check that remembers to guard it.
            # int() because a numpy count is not JSON-serialisable, and the
            # baseline below is written as JSON.
            msg, n = fn()
            n = int(n)
            assert n, ("examined an empty population, so nothing it asserts was "
                       "tested — the inputs it reads are missing, filtered away, "
                       "or no longer shaped the way it expects")
            observed[fn.__name__] = n
            want = baseline.get(fn.__name__)
            if want:
                moved = (n != want["n"] if want["bound"] == "exact"
                         else n < want["n"])
                assert not moved, (
                    f"examined {n:,} where {POPULATIONS.name} records "
                    f"{want['n']:,} ({want['bound']}). A shrink means the check "
                    f"now reads less of the tree than it did, or the tree lost "
                    f"rows; a move under `exact` means a population clipped to "
                    f"the study window changed, which it cannot do from a "
                    f"re-pull alone. Re-seed with --write-populations once the "
                    f"change is understood")
            print(f"PASS  {fn.__name__} [n={n:,}]: {msg}")
        except Skipped as e:
            skipped += 1
            print(f"SKIP  {fn.__name__}: {e}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # missing data tree, etc. — report, don't hide
            failures += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(CHECKS) - failures - skipped}/{len(CHECKS)} checks passed"
          + (f", {skipped} skipped" if skipped else ""))
    if skipped and not allow_skips:
        print(f"FAIL  {skipped} check(s) read an artifact that is not built, so "
              f"they verified nothing. Build it, or pass --allow-skips to "
              f"iterate without it.")
    unseeded = [f.__name__ for f in CHECKS if f.__name__ not in baseline]
    if unseeded:
        print(f"NOTE  {len(unseeded)} check(s) absent from {POPULATIONS.name}, so "
              f"their population is unbounded above zero: {', '.join(unseeded)}")
    if "--write-populations" in sys.argv[1:]:
        # Re-seeding is the maintenance path after a refresh, so it takes its
        # numbers only from a run that passed — a baseline written from a broken
        # tree records the breakage as the expectation.
        if failures or skipped:
            print("REFUSED to re-seed from a run that did not pass every check")
            failures += 1
        else:
            merged = {k: {"n": v,
                          "bound": baseline.get(k, {}).get("bound", "monotone")}
                      for k, v in observed.items()}
            POPULATIONS.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
            print(f"wrote {POPULATIONS.name} for {len(merged)} checks")
    sys.exit(1 if failures or (skipped and not allow_skips) else 0)
