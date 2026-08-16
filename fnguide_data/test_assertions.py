"""Integrity assertions for the claims `fnguide_data`'s documentation makes.

This repo has no CI; verification is ad-hoc. Run with the data trees populated,
from anywhere:

    python fnguide_data/test_assertions.py

or run every package's assertions at once with `./run_assertions.sh` from the
repo root. Each check prints PASS/FAIL; the script exits non-zero if any fail.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
# The study window every package's figures are quoted on. Duplicated in each
# assertion file because the container holds no shared module to import it from;
# `run_assertions.sh` fails if the copies ever disagree.
WIN_START = pd.Timestamp("2005-01-01")
WIN_END = pd.Timestamp("2024-12-31")


def test_fnguide_price_delisted_coverage():
    """README.md and kr_marcap/CONSTRUCTION.md both rest on the benchmark being
    survivorship-bias-free: '616 / 620 (99.4 %)' of genuine common delistings
    since 2005 carry real prices. A re-pull under DataGuide's 'currently listed'
    filter would silently drop them all and grade only the easy half of the
    problem, so the premise is checked, not trusted.

    The figure belongs to `raw/Price data.xlsx` and its own pull date, not to
    the directory — the other exports were pulled months earlier against a
    different live universe. See README.md, "Every sheet has its own pull date".
    """
    fp = REPO / "fnguide_data/cache/fnguide_price.parquet"
    if not fp.exists():
        return "SKIP (run fnguide_data.price_loader first)"
    sys.path.insert(0, str(REPO))
    from kr_marcap.classify import classify_ticker
    have = set(pd.read_parquet(fp, columns=["ticker"])["ticker"].unique())
    cal = pd.read_csv(REPO / "kr_delisted/delisting_calendar.csv", dtype={"ticker": str})
    cal["delisting_date"] = pd.to_datetime(cal["delisting_date"])
    g = cal[(cal["delisting_date"] >= WIN_START) & (cal["is_genuine"] == "Y")].copy()
    g["kind"] = [classify_ticker(t, n, m)
                 for t, n, m in zip(g["ticker"], g["name"], g["market"])]
    gc = g[g["kind"] == "common"]
    hit = int(gc["ticker"].isin(have).sum())
    assert hit / len(gc) >= 0.99, (
        f"the FnGuide price export is claimed survivorship-bias-free at "
        f"616/620 (99.4 %) of genuine common delistings since 2005; it now "
        f"covers {hit}/{len(gc)} ({hit/len(gc):.1%}) — check the export's "
        f"universe filter was 'all codes' (전체 / 상폐 포함)"
    )
    return f"delisted coverage {hit}/{len(gc)} = {hit/len(gc):.1%}"


def test_fnguide_price_segments_break_reissued_codes():
    """README.md and price_loader.py both claim the panel's `segment` column
    makes reissued codes safe to difference: '58 codes carry a handover, and
    every return computed within (ticker, segment) stays inside one company'.

    The failure this guards is silent and enormous rather than subtly wrong —
    the handover returns run to +8,136,485 % — so the check is the invariant
    itself, not the count: no `segment` boundary may sit anywhere other than a
    genuine delisting inside a price gap, and no such delisting may be missing
    a boundary.
    """
    fp = REPO / "fnguide_data/cache/fnguide_price.parquet"
    if not fp.exists():
        return "SKIP (run fnguide_data.price_loader first)"
    px = pd.read_parquet(fp, columns=["date", "ticker", "segment"])
    px = px.sort_values(["ticker", "date"])
    marked = set(zip(*px.loc[px.groupby("ticker")["segment"].diff() > 0,
                             ["ticker", "date"]].to_numpy().T))

    # Re-derive the breaks from the sources, independently of the loader.
    sessions = pd.Index(px["date"].drop_duplicates().sort_values())
    sess_no = px["date"].map(pd.Series(range(len(sessions)), index=sessions))
    prev_date = px["date"].groupby(px["ticker"], sort=False).shift(1)
    prev_sess = sess_no.groupby(px["ticker"], sort=False).shift(1)
    gapped = (sess_no - prev_sess) > 1
    cal = pd.read_csv(REPO / "kr_delisted/delisting_calendar.csv", dtype={"ticker": str})
    cal = cal[cal["is_genuine"] == "Y"]
    ev = pd.DataFrame({"ticker": cal["ticker"].str.zfill(6),
                       "event": pd.to_datetime(cal["delisting_date"])})
    cand = pd.DataFrame({"ticker": px.loc[gapped, "ticker"],
                         "date": px.loc[gapped, "date"],
                         "prev": prev_date[gapped]}).merge(ev, on="ticker")
    expected = set(map(tuple, cand.loc[cand["event"].between(cand["prev"], cand["date"]),
                                       ["ticker", "date"]].to_numpy()))

    assert marked == expected, (
        f"the panel's `segment` breaks disagree with the delisting calendar: "
        f"{len(marked - expected)} boundaries sit where no genuine delisting "
        f"falls inside a price gap, {len(expected - marked)} such handovers "
        f"carry no boundary — a return differenced within (ticker, segment) "
        f"would span two different companies. Rebuild with "
        f"`python -m fnguide_data.price_loader`"
    )
    assert len(marked) == 58, (
        f"README.md §9 says '58 codes carry a handover'; the cache now has "
        f"{len(marked)} — re-measure the sentence"
    )
    return (f"{len(marked)} reissued-code handovers, all on a genuine "
            f"delisting inside a price gap")


def test_fnguide_price_impossible_returns_are_all_inspected():
    """README.md §9 claims the extreme returns left after segmenting are real KRX
    prints rather than defects: '52 returns exceed +100 %, every one a halt the
    exchange priced at a nominal constant or a 정리매매 session'.

    +100 % is not a tuned cut. KRX caps a normal session at ±30 %, so a
    one-session gain above +100 % cannot be ordinary trading — it is a
    placeholder run ending, a 정리매매 window where no limit applies, or a defect.
    The first two were inspected against `marcap/` and matched the raw close
    exactly; this pins the population so a re-pull that introduces a *new* one
    gets looked at rather than averaged into a cross-section.
    """
    fp = REPO / "fnguide_data/cache/fnguide_price.parquet"
    if not fp.exists():
        return "SKIP (run fnguide_data.price_loader first)"
    px = pd.read_parquet(fp).sort_values(["ticker", "segment", "date"])
    ret = px.groupby(["ticker", "segment"])["adj_close_pr"].pct_change(fill_method=None)
    impossible = int(((ret > 1.0) | ~np.isfinite(ret.fillna(0))).sum())
    assert impossible == 52, (
        f"README.md §9 says '52 returns exceed +100 %, every one a halt the "
        f"exchange priced at a nominal constant or a 정리매매 session'; the panel "
        f"now has {impossible}. Inspect the new ones against marcap/ (Volume, "
        f"ChangeCode) before trusting them — a flat run on zero volume is the "
        f"exchange holding a halted name, not a price"
    )
    return f"{impossible} above-limit returns, all attributed to halts or 정리매매"


def test_fnguide_vintage_manifest_matches_disk():
    """README.md's pull-date table and every coverage figure in this package are
    quoted against a specific export vintage: 'the exports span 2026-02-14 to
    2026-08-13 and each carries its own end date and its own ticker universe'.

    A re-pull re-dates one file and nothing downstream notices — the parse
    succeeds and the panel is just short or wide. `vintages.csv` is what makes
    the vintage readable without parsing 6.5 GB, so it is only useful while it
    describes the files that are actually there.
    """
    sys.path.insert(0, str(REPO))
    from fnguide_data.vintages import MANIFEST_PATH, RAW_DIR, check, load
    if not RAW_DIR.exists() or not any(RAW_DIR.glob("*.xlsx")):
        return "SKIP (raw/ exports not present)"
    assert MANIFEST_PATH.exists(), (
        f"{MANIFEST_PATH} is missing — regenerate it with "
        f"`python -m fnguide_data.vintages`"
    )
    stale = check()
    assert not stale, (
        f"the pull-vintage manifest disagrees with raw/ on {len(stale)} file(s): "
        f"{stale}. A re-pull changes what every end date and coverage figure in "
        f"README.md describes — regenerate with `python -m fnguide_data.vintages` "
        f"and re-check the figures the changed file backs"
    )
    man = load()
    return (f"{len(man)} sheets across {man.file.nunique()} files, "
            f"end dates {man.term_end.min():%Y-%m-%d}..{man.term_end.max():%Y-%m-%d}")


CHECKS = [
    test_fnguide_price_delisted_coverage,
    test_fnguide_price_segments_break_reissued_codes,
    test_fnguide_price_impossible_returns_are_all_inspected,
    test_fnguide_vintage_manifest_matches_disk,
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
