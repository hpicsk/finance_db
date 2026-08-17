"""Integrity assertions for the claims `krx_supplement`'s documentation makes.

This repo has no CI; verification is ad-hoc. Run with the data trees populated,
from anywhere:

    python krx_supplement/test_assertions.py

or run every package's assertions at once with `./run_assertions.sh` from the
repo root. Each check prints PASS or FAIL along with `n`, the size of the
population it examined; the script exits non-zero if any fail and if any
examined nothing. `n` is held against `populations.json`, which records what
each check last read; re-seed it with `--write-populations` after a refresh.
"""
from __future__ import annotations

import json
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


# ---- KOSPI200 index panel: in-window membership stays complete --------------
def test_kospi200_panel_inwindow_complete():
    """Any index-exclusion filter built on this panel relies on it carrying a
    complete ~200 members on every in-window date.
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
    return (f"KOSPI200 in-window membership median={med}, "
            f"range [{inwin.min()},{inwin.max()}]"), len(inwin)


CHECKS = [
    test_kospi200_panel_inwindow_complete,
]


if __name__ == "__main__":
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
    failures = 0
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
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # missing data tree, etc. — report, don't hide
            failures += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(CHECKS) - failures}/{len(CHECKS)} checks passed")
    unseeded = [f.__name__ for f in CHECKS if f.__name__ not in baseline]
    if unseeded:
        print(f"NOTE  {len(unseeded)} check(s) absent from {POPULATIONS.name}, so "
              f"their population is unbounded above zero: {', '.join(unseeded)}")
    if "--write-populations" in sys.argv[1:]:
        # Re-seeding is the maintenance path after a refresh, so it takes its
        # numbers only from a run that passed — a baseline written from a broken
        # tree records the breakage as the expectation.
        if failures:
            print("REFUSED to re-seed from a run that did not pass every check")
            failures += 1
        else:
            merged = {k: {"n": v,
                          "bound": baseline.get(k, {}).get("bound", "monotone")}
                      for k, v in observed.items()}
            POPULATIONS.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
            print(f"wrote {POPULATIONS.name} for {len(merged)} checks")
    sys.exit(1 if failures else 0)
