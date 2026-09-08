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
import pyarrow.parquet as pq

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


# ---- The session calendar both tripwires below are read against -------------
def _marcap_sessions() -> set[pd.Timestamp]:
    """Every trading session the marcap clone carries, at day resolution.

    Read off the clone rather than imported from kr_marcap, because
    `run_assertions.sh` runs each package on its own and a cross-package import
    would make this file fail for a reason that is not krx_supplement's.
    """
    sessions: set[pd.Timestamp] = set()
    for fp in sorted((REPO / "marcap/data").glob("marcap-*.parquet")):
        d = pd.to_datetime(pd.read_parquet(fp, columns=["Date"])["Date"])
        sessions |= set(d.dt.normalize().unique())
    assert sessions, f"no marcap-*.parquet under {REPO / 'marcap/data'}"
    return sessions


# ---- Sector panel: a failed fetch is absent from it, not raised -------------
def test_sector_panel_covers_every_session():
    """`fetch_sector_snapshot` catches `Exception` per (date, market), logs a
    warning and moves on, so a fetch that failed leaves that cell out of
    sector_mapping.parquet rather than stopping the run (limitation 6). Nothing
    downstream can tell that absence from "the exchange listed nothing that
    day", and the log is long gone by the time anyone reads the panel. The
    absence itself is checkable: every session the calendar carries inside the
    panel's span appears in it, in both markets.
    """
    fp = REPO / "krx_supplement/output/sector_mapping.parquet"
    df = pd.read_parquet(fp, columns=["date", "market"])
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    cells = df.drop_duplicates()
    markets = set(cells["market"])
    assert markets == {"KOSPI", "KOSDAQ"}, (
        f"the panel carries markets {sorted(markets)}, where collect_sector's "
        f"MARKET_CODES fetches KOSPI and KOSDAQ — either a market stopped being "
        f"collected, or one was added and this check has not been re-read")
    have = set(zip(cells["date"], cells["market"]))
    sessions = _marcap_sessions()
    # The panel runs past the marcap clone's last session, and a date the
    # calendar cannot reach is classifiable neither way, so the span stops where
    # the calendar does.
    lo, hi = df["date"].min(), min(df["date"].max(), max(sessions))
    span = sorted(d for d in sessions if lo <= d <= hi)
    cells_wanted = len(span) * len(markets)
    missing = [(d, m) for d in span for m in sorted(markets) if (d, m) not in have]
    assert not missing, (
        f"{len(missing)} of {cells_wanted:,} session-market cells are absent "
        f"from sector_mapping.parquet, so a 업종분류현황 fetch failed and was "
        f"skipped: {[(str(d.date()), m) for d, m in missing[:5]]}")
    return (f"sector panel covers all {len(span):,} sessions "
            f"{span[0].date()}..{span[-1].date()} in both markets"), cells_wanted


# ---- Foreign-ownership dailies: an empty file is the failure and the record --
def test_foreign_ownership_empty_files_fall_on_non_sessions():
    """`_fetch` maps `KeyError` to `None`, which is right when KRX returns an
    empty `output` array on a holiday and wrong when the response schema moved,
    and `None` writes an `_EMPTY_SCHEMA` parquet either way (limitation 6). That
    file is a real artifact, so the `out.exists()` resume check skips the date on
    every later run and the gap never refills. An empty file therefore has to
    fall on a day the market was shut.
    """
    base = REPO / "krx_supplement/output/foreign_ownership_daily"
    sessions = _marcap_sessions()
    cal_end = max(sessions)
    on_session, n_empty, examined, past_calendar = [], 0, 0, 0
    for fp in sorted(base.rglob("*.parquet")):
        date = pd.Timestamp(fp.stem.split("_")[0])
        if date > cal_end:
            past_calendar += 1
            continue
        examined += 1
        if pq.ParquetFile(fp).metadata.num_rows:
            continue
        n_empty += 1
        if date in sessions:
            on_session.append(fp.name)
    assert not on_session, (
        f"{len(on_session)} of {n_empty} empty-schema files fall on a trading "
        f"session, so the endpoint returned nothing on a day the market was open "
        f"and the resume check will never fetch that date again — delete them to "
        f"re-fetch: {on_session[:5]}")
    return (f"{examined:,} dailies through {cal_end.date()}: {n_empty} empty, "
            f"none on a session; {past_calendar} later files sit past the "
            f"calendar and are unchecked"), examined


CHECKS = [
    test_kospi200_panel_inwindow_complete,
    test_sector_panel_covers_every_session,
    test_foreign_ownership_empty_files_fall_on_non_sessions,
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
