"""Integrity assertions for the claims `kr_status`'s documentation makes.

This repo has no CI; verification is ad-hoc. Run with the data trees populated,
from anywhere:

    python kr_status/test_assertions.py

or run every package's assertions at once with `./run_assertions.sh` from the
repo root. Each check prints PASS, FAIL, or SKIP where a prerequisite
artifact is absent, along with `n`, the size of the population it examined.
The script exits non-zero if any check fails, if any examined nothing, and if
any skipped — a skip verified nothing, so iterating without the artifact takes
`--allow-skips`. `n` is held against `populations.json`, which records what
each check last read; re-seed it with `--write-populations` after a refresh.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from kr_status.corp_code_map import DATA_DIR  # noqa: E402
from kr_status.dart_audit import MIN_YEAR, OPINIONS_PATH, _classify  # noqa: E402
from kr_status.dart_audit_first import FIRST_PATH  # noqa: E402

# Each check's population, recorded so a tree that lost rows fails rather
# than passing on a smaller one. Per package, not per repo: the root is a
# container and holds no package's numbers.
POPULATIONS = Path(__file__).with_name("populations.json")


class Skipped(Exception):
    """A prerequisite artifact is absent, so this check verified nothing.

    Distinct from a pass because it is: it used to print as one, which is the
    same confusion the population guard below exists to remove.
    """


# README § dart_corp_actions: the table's columns, and the two event families
# its `category` splits.
CORP_ACTION_COLUMNS = ["ticker", "parent", "corp_code", "event", "category",
                       "rcept_dt", "rcept_no"]
GENUINE_EVENTS = {"유상증자", "무상증자", "유무상증자", "감자"}
ENTITY_EVENTS = {"회사합병", "회사분할", "회사분할합병", "주식교환"}

# README § dart_audit: the span the cache holds, and the two consequences of
# reading the endpoint at harvest time. A row is "stamped late" when its receipt
# falls more than a year after 31 March of bsns_year + 1, the filing deadline.
LAST_YEAR = 2025
STAMPED_LATE = 702
AMENDED_EXAMPLE = ("015540", range(2019, 2023), 2023)
FOUR_OPINIONS = {"적정", "한정", "부적정", "의견거절"}
NO_TEXT, OTHER_TEXT = 1251, 229

# README § dart_corp_actions: the first receipt DART's event API served.
FIRST_EVENT = pd.Timestamp("2015-01-07")

# README § dart_audit_first: the first-filings table against the opinions cache.
# A re-harvest that moves them fails the check, which carries the new numbers into
# the README in the same commit.
FIRST_COLUMNS = ["ticker", "bsns_year", "rcept_no", "receipt_dt", "opinion_code", "raw",
                 "n_amendments"]
QUALIFIED = {"한정", "부적정", "의견거절"}
AMENDED, SERVED_LATER, HIDDEN, REVEALED, UNREAD, NO_ORIGINAL = 6060, 5468, 118, 13, 319, 0
HIDDEN_EXAMPLE = ("015540", range(2020, 2023))


# ---- README § dart_audit ------------------------------------------------------

def test_audit_opinions_start_at_2015():
    if not OPINIONS_PATH.exists():
        raise Skipped(f"{OPINIONS_PATH.name} not harvested")
    opinions = pd.read_parquet(OPINIONS_PATH)
    assert list(opinions.columns) == ["ticker", "bsns_year", "opinion_code", "receipt_dt", "raw"], (
        f"README § dart_audit: the opinions cache is (ticker, bsns_year, opinion_code, "
        f"receipt_dt, raw) — found {list(opinions.columns)}")
    assert int(opinions["bsns_year"].min()) == MIN_YEAR, (
        f"README § dart_audit: DART's structured audit-opinion endpoint is populated "
        f"for bsns_year ≥ {MIN_YEAR} only — the cache starts at "
        f"{opinions['bsns_year'].min()}")
    assert int(opinions["bsns_year"].max()) == LAST_YEAR, (
        f"README § dart_audit: 'The cache holds bsns_year {MIN_YEAR}–{LAST_YEAR}' — "
        f"it runs to {opinions['bsns_year'].max()}")
    return (f"{len(opinions):,} opinions on bsns_year {MIN_YEAR}–"
            f"{int(opinions['bsns_year'].max())}"), len(opinions)


def test_audit_rows_are_what_dart_serves_at_harvest():
    if not OPINIONS_PATH.exists():
        raise Skipped(f"{OPINIONS_PATH.name} not harvested")
    op = pd.read_parquet(OPINIONS_PATH)
    deadline = pd.to_datetime((op["bsns_year"] + 1).astype(str) + "-03-31")
    late = int((op["receipt_dt"] > deadline + pd.DateOffset(years=1)).sum())
    assert late == STAMPED_LATE, (
        f"README § dart_audit: '{STAMPED_LATE} rows (2.7 %) are stamped more than a "
        f"year after the 31 March filing deadline' — {late} are")
    ticker, years, stamp = AMENDED_EXAMPLE
    ex = op[(op["ticker"] == ticker) & op["bsns_year"].isin(years)]
    assert len(ex) == len(years) and (ex["receipt_dt"].dt.year == stamp).all(), (
        f"README § dart_audit: '{ticker}'s rows for FY{years[0]}–{years[-1]} all carry "
        f"receipt dates in {stamp}' — found "
        f"{sorted(zip(ex['bsns_year'], ex['receipt_dt'].dt.date))}")
    stale = int((op["raw"].map(_classify) != op["opinion_code"]).sum())
    assert not stale, (
        f"README § dart_audit: 'Both collectors re-derive the label from raw whenever "
        f"they write' — {stale} rows carry a label _classify no longer gives; run "
        f"python -m kr_status.dart_audit --relabel")
    label = op["opinion_code"]
    got = (int((label == "unknown").sum()), int((~label.isin(FOUR_OPINIONS | {"unknown"})).sum()))
    assert got == (NO_TEXT, OTHER_TEXT), (
        f"README § dart_audit: '{NO_TEXT:,} rows carry no opinion text (unknown), and "
        f"{OTHER_TEXT} carry text with none of those words' — (unknown, other text) is {got}")
    return (f"{late} of {len(op):,} rows stamped more than a year past the deadline; "
            f"every label is _classify(raw); {got[0]:,} unknown, {got[1]} other text"), len(op)


# ---- README § dart_audit_first ------------------------------------------------

def test_first_filings_match_the_opinions_row_for_row():
    if not FIRST_PATH.exists():
        raise Skipped(f"{FIRST_PATH.name} not built (python -m kr_status.dart_audit_first)")
    first = pd.read_parquet(FIRST_PATH)
    served = pd.read_parquet(OPINIONS_PATH)
    assert list(first.columns) == FIRST_COLUMNS, (
        f"README § dart_audit_first: the table is {FIRST_COLUMNS} — found {list(first.columns)}")
    keys = sorted(zip(first["ticker"], first["bsns_year"]))
    assert keys == sorted(zip(served["ticker"], served["bsns_year"])), (
        "README § dart_audit_first: one row per row of dart_audit_opinions.parquet — "
        "the (ticker, bsns_year) sets differ")
    read = first["raw"].notna()
    stale = int((first.loc[read, "raw"].map(_classify) != first.loc[read, "opinion_code"]).sum())
    assert not stale and first.loc[~read, "opinion_code"].isna().all(), (
        f"README § dart_audit_first: the label is _classify(raw), and empty where the "
        f"first filing was unread — {stale} rows break it")
    m = first.merge(served, on=["ticker", "bsns_year"], suffixes=("_first", "_served"))
    amended = m["n_amendments"] > 0
    number_dt = pd.to_datetime(m["rcept_no"].str[:8], format="%Y%m%d")
    later = amended & (m["receipt_dt_served"] > number_dt)
    label = {s: m[f"opinion_code_{s}"].fillna("").astype(str).str.replace(r"\s+", "", regex=True)
             for s in ("first", "served")}
    hidden = label["first"].isin(QUALIFIED) & (label["served"] == "적정")
    revealed = (label["first"] == "적정") & label["served"].isin(QUALIFIED)
    unread = amended & m["rcept_no"].notna() & m["raw_first"].isna()
    no_original = m["rcept_no"].isna()
    got = (int(amended.sum()), int(later.sum()), int(hidden.sum()), int(revealed.sum()),
           int(unread.sum()), int(no_original.sum()))
    want = (AMENDED, SERVED_LATER, HIDDEN, REVEALED, UNREAD, NO_ORIGINAL)
    assert got == want, (
        f"README § dart_audit_first: (amended, served later than the first filing, "
        f"qualified first and 적정 served, the reverse, unreadable first filing, no "
        f"original listed) is {want} in the README — {got} on disk")
    ticker, years = HIDDEN_EXAMPLE
    ex = m[(m["ticker"] == ticker) & m["bsns_year"].isin(years)]
    assert len(ex) == len(years) and hidden[ex.index].all(), (
        f"README § dart_audit_first: {ticker}'s FY{years[0]}–{years[-1]} first filings read "
        f"의견거절 and the served rows 적정 — found "
        f"{list(zip(ex['bsns_year'], ex['opinion_code_first'], ex['opinion_code_served']))}")
    return (f"{len(first):,} rows: {got[0]:,} amended, {got[1]:,} served from a later "
            f"filing; {got[2]} qualified-then-적정, {got[3]} the reverse; {got[4]} "
            f"unreadable, {got[5]} with no original listed"), len(first)


# ---- README § dart_corp_actions -----------------------------------------------

def test_corp_actions_split_genuine_from_entity():
    p = DATA_DIR / "dart_corp_action_events.parquet"
    if not p.exists():
        raise Skipped(f"{p.name} not built")
    ca = pd.read_parquet(p)
    assert list(ca.columns) == CORP_ACTION_COLUMNS, (
        f"README § dart_corp_actions: output columns are {CORP_ACTION_COLUMNS} — "
        f"found {list(ca.columns)}")
    want = ca["event"].map(lambda e: "genuine" if e in GENUINE_EVENTS
                           else "entity" if e in ENTITY_EVENTS
                           else "none" if e == "" else None)
    assert want.notna().all(), (
        f"README § dart_corp_actions: every event is 유상증자/무상증자/유무상증자/감자 "
        f"or 회사합병/회사분할/회사분할합병/주식교환 — also found "
        f"{sorted(set(ca.loc[want.isna(), 'event']))}")
    assert (want == ca["category"]).all(), (
        "README § dart_corp_actions: `category` is genuine for the share-count "
        "events and entity for the identity events — the split on disk differs")
    pref = ca["ticker"].str[-1] != "0"
    assert (ca.loc[pref, "parent"] == ca.loc[pref, "ticker"].str[:5] + "0").all(), (
        "README § dart_corp_actions: a preferred share resolves to the parent "
        "common (code[:5] + '0')")
    assert (ca.loc[~pref, "parent"] == ca.loc[~pref, "ticker"]).all(), (
        "README § dart_corp_actions: a common is its own parent")
    first = pd.to_datetime(ca.loc[ca["category"] != "none", "rcept_dt"]).min()
    assert first == FIRST_EVENT, (
        f"README § dart_corp_actions: 'DART's event API serves nothing filed before "
        f"2015; the earliest receipt here is {FIRST_EVENT.date()}' — the earliest is "
        f"{first.date()}")
    return (f"{len(ca):,} rows split {want.value_counts().to_dict()}; "
            f"{int(pref.sum())} preferred rows resolve to their parent common; first "
            f"receipt {first.date()}"), len(ca)


# ---- README § Shared utility ------------------------------------------------

def test_corp_code_cache_records_its_misses():
    cache, misses = DATA_DIR / "corp_code_cache.parquet", DATA_DIR / "corp_code_misses.csv"
    if not cache.exists():
        raise Skipped(f"{cache.name} not built")
    cc = pd.read_parquet(cache)
    m = pd.read_csv(misses, dtype=str)
    assert cc["ticker"].is_unique, "README § Shared utility: one corp_code per ticker"
    assert list(m.columns) == ["ticker", "name"], (
        f"README § Shared utility: corp_code_misses.csv is (ticker, name) — "
        f"found {list(m.columns)}")
    unresolved = set(cc.loc[cc["corp_code"].isna(), "ticker"])
    assert set(m["ticker"]) == unresolved, (
        f"README § Shared utility: 'misses are logged to data/corp_code_misses.csv' — "
        f"the CSV lists {len(m)} tickers, the cache leaves {len(unresolved)} unresolved, "
        f"and they differ")
    return (f"{len(cc):,} tickers cached, {len(unresolved)} unresolved and every one "
            f"of them in corp_code_misses.csv"), len(cc)


CHECKS = [
    test_audit_opinions_start_at_2015,
    test_audit_rows_are_what_dart_serves_at_harvest,
    test_first_filings_match_the_opinions_row_for_row,
    test_corp_actions_split_genuine_from_entity,
    test_corp_code_cache_records_its_misses,
]


if __name__ == "__main__":
    # This block is the same in every package's test_assertions.py, and
    # run_assertions.sh fails when the copies differ: edit it in one, then copy
    # it to the rest. Nothing below is package-specific — it needs CHECKS,
    # Skipped and POPULATIONS from above, and nothing else.
    #
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
    # The bound is per check because a population clipped to a window moves only
    # when the window does, while one open past it grows every time the vendor
    # is re-pulled — a single rule would either fail every refresh or catch
    # nothing.
    # Re-seeding is the documented path after a refresh, and it was unreachable:
    # a legitimately moved population fails its own guard, which counts as a
    # failure, which makes the re-seed refuse — so the path existed only while it
    # was not needed. Under `--write-populations` the recorded numbers are being
    # replaced on purpose, so the comparison against them is reported and not
    # enforced. Every other assertion still has to pass, which is what stops a
    # broken tree from being written down as the expectation.
    reseed = "--write-populations" in sys.argv[1:]
    baseline = json.loads(POPULATIONS.read_text()) if POPULATIONS.exists() else {}
    observed = {}
    drift = []
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
                if moved and reseed:
                    drift.append(f"{fn.__name__} {want['n']:,} -> {n:,}")
                    moved = False
                assert not moved, (
                    f"examined {n:,} where {POPULATIONS.name} records "
                    f"{want['n']:,} ({want['bound']}). A shrink means the check "
                    f"now reads less of the tree than it did, or the tree lost "
                    f"rows; a move under `exact` means a population clipped to "
                    f"a window changed, which a re-pull does only by moving the "
                    f"window. Re-seed with --write-populations once the change "
                    f"is understood")
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
    if reseed:
        # Re-seeding takes its numbers only from a run that passed — a baseline
        # written from a broken tree records the breakage as the expectation.
        for d in drift:
            print(f"MOVED {d}")
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
