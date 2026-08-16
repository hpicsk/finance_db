"""Integrity assertions for the claims `krx_supplement`'s documentation makes.

This repo has no CI; verification is ad-hoc. Run with the data trees populated,
from anywhere:

    python krx_supplement/test_assertions.py

or run every package's assertions at once with `./run_assertions.sh` from the
repo root. Each check prints PASS/FAIL; the script exits non-zero if any fail.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
# The study window every package's figures are quoted on. Duplicated in each
# assertion file because the container holds no shared module to import it from;
# `run_assertions.sh` fails if the copies ever disagree.
WIN_START = pd.Timestamp("2005-01-01")
WIN_END = pd.Timestamp("2024-12-31")


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
    return f"KOSPI200 in-window membership median={med}, range [{inwin.min()},{inwin.max()}]"


CHECKS = [
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
