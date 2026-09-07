"""Integrity assertions for the claims `kr_delisted`'s documentation makes.

This repo has no CI; verification is ad-hoc. Run with the data trees populated,
from anywhere:

    python kr_delisted/test_assertions.py

or run every package's assertions at once with `./run_assertions.sh` from the
repo root. Each check prints PASS or FAIL along with `n`, the size of the
population it examined; the script exits non-zero if any fail and if any
examined nothing. `n` is held against `populations.json`, which records what
each check last read; re-seed it with `--write-populations` after a refresh.

The counts in README.md are properties of one KIND vintage, not constants, so
a refresh that adds delistings is *meant* to fail these — that failure is what
carries the new numbers into the prose in the same commit.
"""
from __future__ import annotations

import glob
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

# Imported rather than restated: the keyword sets are the classifier's, and a
# second copy here would agree with the CSV while disagreeing with the code
# that built it. Addressed through the package so `run_assertions.sh`'s import
# preflight can resolve it — a bare `_classify` reads as a missing third-party
# module and aborts every package's run.
sys.path.insert(0, str(REPO))
from kr_delisted._classify import TRANSFER_REASONS          # noqa: E402

CALENDAR = REPO / "kr_delisted/delisting_calendar.csv"
KIND_CSV = REPO / "kr_delisted/delisting_calendar.kind.csv"
OVERRIDES = REPO / "kr_delisted/is_genuine_overrides.csv"
# `build_delisting_calendar.PROXY_REASON`, restated rather than imported: the
# module makes a KIND request at import time under some flag combinations, and
# a check that reaches the network is a check that fails on a train.
PROXY_REASON = "(not in KIND — proxy date from last-CSV-date)"
DISSOLUTION_REASON = "해산 사유 발생"


def _calendar() -> pd.DataFrame:
    cal = pd.read_csv(CALENDAR, dtype={"ticker": str})
    cal["delisting_date"] = pd.to_datetime(cal["delisting_date"])
    return cal


# ---- Scope: the calendar is KIND plus the marcap-derived preferred proxies --
def test_calendar_composition():
    """README.md "Scope" states the calendar as 1,386 rows = 1,268 KIND events
    + 118 preferred-share proxies, of which 196 are KONEX.

    The split is not cosmetic: the proxy rows carry a *last-traded* date where
    the KIND rows carry a real delisting date, so a study that treats the two
    as one field is off by a session on 118 names. Asserting the composition
    is what keeps the two paths distinguishable after a refresh.
    """
    cal = _calendar()
    proxy = cal["reason"].fillna("") == PROXY_REASON
    n_kind, n_proxy = int((~proxy).sum()), int(proxy.sum())
    n_konex = int((cal["market"] == "KONEX").sum())
    assert (len(cal), n_kind, n_proxy, n_konex) == (1386, 1268, 118, 196), (
        f"README.md 'Scope' claims '1,386 rows' = '1,268 KIND delisting events' "
        f"+ '118 preferred-share / 신주 / 전환 tickers recovered from marcap', "
        f"with KONEX at '196 rows'; the CSV now holds {len(cal):,} = {n_kind:,} "
        f"+ {n_proxy:,}, KONEX {n_konex:,}"
    )
    # The proxy rows are exactly the non-common-terminal-digit codes the Scope
    # section describes recovering; a proxy row ending in '0' would mean the
    # marcap sweep picked up a main share KIND should have carried.
    stray = cal[proxy & cal["ticker"].str.endswith("0")]
    assert stray.empty, (
        f"README.md 'Scope' derives the proxy rows from 'codes ending in a "
        f"non-zero digit', but {len(stray)} proxy row(s) end in '0': "
        f"{stray['ticker'].tolist()[:5]}"
    )
    assert (cal["ticker"].str.len() == 6).all(), (
        "README.md 'Calendar schema' says every ticker is a '6-digit KRX code "
        "(zero-padded string)'; the CSV now carries other lengths"
    )
    assert cal["delisting_date"].min() >= WIN_START, (
        f"README.md 'Scope' bounds the calendar at '2005-01-02 onward'; the "
        f"earliest row is now {cal['delisting_date'].min():%Y-%m-%d}"
    )
    return (f"{len(cal):,} rows = {n_kind:,} KIND + {n_proxy:,} proxy; "
            f"{n_konex} KONEX; all 6-digit, all >= {WIN_START:%Y-%m-%d}"), len(cal)


# ---- The genuine/continuation split the survivorship universe rests on ------
def test_is_genuine_split():
    """README.md "`is_genuine` classification" reports Y=1,018 / N=368 after
    the four layers, and decomposes N as 107 exchange transfers + 261
    mergers / 주식교환 / SPC dissolutions.

    `universe(genuine_only=True)` is the survivorship-bias-free set the whole
    package exists to serve, and it is exactly the Y side. A drift here moves
    which companies count as failures, which is the one thing a delisting
    calendar must not do quietly.
    """
    cal = _calendar()
    counts = cal["is_genuine"].value_counts()
    n_y, n_n = int(counts.get("Y", 0)), int(counts.get("N", 0))
    assert (n_y, n_n) == (1018, 368), (
        f"README.md claims 'the regenerated calendar has Y=1,018, N=368 (out "
        f"of 1,386)'; the CSV now has Y={n_y:,}, N={n_n:,} of {len(cal):,}"
    )
    n = cal[cal["is_genuine"] == "N"]
    n_transfer = int(n["reason"].fillna("").isin(TRANSFER_REASONS).sum())
    n_merger = len(n) - n_transfer
    assert (n_transfer, n_merger) == (107, 261), (
        f"README.md decomposes the continuation side as '107 exchange "
        f"transfers' + '261 mergers / 주식교환 / SPC dissolutions'; the CSV "
        f"now splits {len(n):,} N rows into {n_transfer:,} + {n_merger:,}"
    )
    assert set(cal["is_genuine"].unique()) <= {"Y", "N"}, (
        "README.md 'Calendar schema' allows only Y / N in `is_genuine`"
    )
    return (f"Y={n_y:,} / N={n_n:,}; N = {n_transfer} transfers "
            f"+ {n_merger} mergers"), len(cal)


# ---- The four override layers, each with the row count the README cites -----
def test_override_layers():
    """README.md "`is_genuine` classification" gives each layer a row count:
    59 dissolution-post-merger, 16 REIT/SPC end-of-life, 9 holding-company
    restructuring, 1 manual — 85 rows in `is_genuine_overrides.csv`.

    Layer 2 costs a DART query per row and layer 3 costs nothing, so the two
    are easy to conflate when the file is rebuilt; the per-rule counts are
    what says which layers actually ran.
    """
    ov = pd.read_csv(OVERRIDES, dtype={"ticker": str})
    got = {k: int(v) for k, v in ov["rule"].value_counts().items()}
    want = {"dissolution-post-merger": 59, "spc-end-of-life": 16,
            "holdco-new-listing": 9, "manual": 1}
    assert got == want, (
        f"README.md documents the override layers as {want} (85 rows); "
        f"`is_genuine_overrides.csv` now holds {got} ({len(ov)} rows)"
    )
    return f"{len(ov)} overrides: " + ", ".join(
        f"{k}={v}" for k, v in sorted(want.items())), len(ov)


# ---- Every dissolution row must have been offered to the DART pass ----------
def test_dissolution_rows_all_saw_the_dart_pass():
    """`해산 사유 발생` is the reason the keyword baseline cannot decide — it
    reads Y, and README.md's layer 2 exists because a dissolution that
    followed a merger is a continuation. That layer runs over
    `delisting_calendar.kind.csv`, an intermediate committed separately from
    the calendar it feeds.

    So the failure mode is a KIND refresh that lands in the canonical CSV
    while the intermediate stays where it was: the new dissolutions keep the
    baseline's Y, enter `universe(genuine_only=True)` as failures, and nothing
    in the pipeline notices, because every layer that did run ran correctly.
    Coverage is checked by date span rather than by row identity — a row the
    pass queried and found nothing for writes no override, so absence from
    `is_genuine_overrides.csv` is not by itself evidence it was skipped.
    """
    cal = _calendar()
    kind = pd.read_csv(KIND_CSV, dtype={"ticker": str})
    kind["delisting_date"] = pd.to_datetime(kind["delisting_date"])
    covered_through = kind["delisting_date"].max()
    diss = cal[cal["reason"].fillna("") == DISSOLUTION_REASON]
    unseen = diss[diss["delisting_date"] > covered_through]
    assert unseen.empty, (
        f"README.md documents a four-layer `is_genuine` classification, but "
        f"layer 2 reads {KIND_CSV.name}, which only reaches "
        f"{covered_through:%Y-%m-%d}. {len(unseen)} dissolution row(s) past "
        f"that date hold the keyword baseline's Y unchecked: "
        f"{', '.join(f'{t} {n} {d:%Y-%m-%d}' for t, n, d in zip(unseen['ticker'], unseen['name'], unseen['delisting_date']))}"
        f" — regenerate the intermediate, then the overrides, then the calendar "
        f"(see README.md 'Regenerating the calendar')"
    )
    return (f"all {len(diss)} dissolution rows inside the override pass's span "
            f"(through {covered_through:%Y-%m-%d})"), len(diss)


# ---- The survivorship premise: marcap kept every delisted name --------------
def test_marcap_carries_every_kind_ticker():
    """README.md "marcap coverage verification" states that 'Every one of the
    1,268 KIND-sourced 6-digit tickers is present in marcap', which is what
    makes `load_delisted(ticker)` able to return a price history at all and
    what the repo's no-survivorship-bias claim rests on.

    marcap is an external clone re-pulled by hand, and a pull that dropped
    delisted rows would leave every loader returning an empty frame for the
    names that matter most, silently — `load_delisted` returns an empty
    DataFrame rather than raising when a code is absent.
    """
    files = sorted(glob.glob(str(REPO / "marcap/data/marcap-*.parquet")))
    assert files, (
        f"no marcap parquets under {REPO / 'marcap/data'} — the clone is "
        f"gitignored; re-clone from github.com/FinanceData/marcap"
    )
    codes: set[str] = set()
    for fp in files:
        codes |= set(pd.read_parquet(fp, columns=["Code"])["Code"]
                     .astype(str).str.zfill(6).unique())
    cal = _calendar()
    kind = cal[cal["reason"].fillna("") != PROXY_REASON]
    missing = sorted(set(kind["ticker"]) - codes)
    assert not missing, (
        f"README.md 'marcap coverage verification' claims 'Every one of the "
        f"1,268 KIND-sourced 6-digit tickers is present in marcap'; "
        f"{len(missing)} are absent from the {len(files)} local parquets: "
        f"{missing[:10]}"
    )
    return (f"all {len(kind):,} KIND tickers present across {len(files)} "
            f"marcap years ({len(codes):,} distinct codes)"), len(kind)


CHECKS = [
    test_calendar_composition,
    test_is_genuine_split,
    test_override_layers,
    test_dissolution_rows_all_saw_the_dart_pass,
    test_marcap_carries_every_kind_ticker,
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
