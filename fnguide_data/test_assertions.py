"""Integrity assertions for the claims `fnguide_data`'s documentation makes.

This repo has no CI; verification is ad-hoc. Run with the data trees populated,
from anywhere:

    python fnguide_data/test_assertions.py

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
import re
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
# Each check's population, recorded so a tree that lost rows fails rather
# than passing on a smaller one. Per package, not per repo: the root is a
# container and holds no package's numbers.
POPULATIONS = Path(__file__).with_name("populations.json")


# Which delisted names are ordinary commons. The coverage claim below is about
# common stock, so the calendar has to be filtered before it can be counted, and
# the calendar carries only (ticker, name, market) — no security-type column.
# The rules are KRX's own: a preferred share's code ends in a character other
# than "0", KONEX is its own market, and SPACs, REITs, ship and mutual funds and
# ETFs name themselves. First match wins, and the name tests fire only after the
# code test, so a common whose name merely ends in 우 is not caught.
_ETF_BRAND_RE = re.compile(
    r"^(?:KODEX|TIGER|ARIRANG|PLUS|KINDEX|ACE|KBSTAR|RISE|SOL|HANARO|KoAct"
    r"|KIWOOM|TREX|KOSEF|TIME|ITF|1Q|HK|FOCUS|WON|마이티|에셋플러스|아이엠에셋"
    r"|더제이|대신|BNK|유진|파워|마이다스|VITA|UNICORN|DAISHIN343|TRUSTON|KCGI)\s",
    re.IGNORECASE,
)
_SPAC_RE = re.compile(r"스팩|SPAC", re.IGNORECASE)
_REIT_RE = re.compile(r"리츠|REIT", re.IGNORECASE)
_FUND_RE = re.compile(r"선박투자|MF$")


def _is_common(ticker: str, name: str, market: str) -> bool:
    """True for an ordinary KOSPI / KOSDAQ common stock."""
    name = str(name).strip()
    if _ETF_BRAND_RE.match(name) or market == "KONEX":
        return False
    if str(ticker).strip()[-1] != "0":
        return False
    if _SPAC_RE.search(name) or _REIT_RE.search(name):
        return False
    if name.endswith("호") or _FUND_RE.search(name):
        return False
    return market in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")


class Skipped(Exception):
    """A prerequisite artifact is absent, so this check verified nothing.

    Distinct from a pass because it is: it used to print as one, which is the
    same confusion the population guard below exists to remove.
    """


def test_fnguide_price_delisted_coverage():
    """README.md rests on this export being survivorship-bias-free:
    '622 / 625 (99.5 %)' of genuine common delistings since 2005 carry real
    prices. A re-pull under DataGuide's 'currently listed' filter would silently
    drop them all and grade only the easy half of the problem, so the premise is
    checked, not trusted.

    The figure belongs to `raw/fnguide_price_adjclose_20260813.xlsx` and its own
    pull date, not to
    the directory — the other exports were pulled months earlier against a
    different live universe. See README.md, "Every sheet has its own pull date".
    """
    fp = REPO / "fnguide_data/cache/fnguide_price.parquet"
    if not fp.exists():
        raise Skipped("run fnguide_data.price_loader first")
    have = set(pd.read_parquet(fp, columns=["ticker"])["ticker"].unique())
    cal = pd.read_csv(REPO / "kr_delisted/delisting_calendar.csv", dtype={"ticker": str})
    cal["delisting_date"] = pd.to_datetime(cal["delisting_date"])
    g = cal[(cal["delisting_date"] >= WIN_START) & (cal["is_genuine"] == "Y")].copy()
    gc = g[[_is_common(t, n, m)
            for t, n, m in zip(g["ticker"], g["name"], g["market"])]]
    hit = int(gc["ticker"].isin(have).sum())
    assert hit / len(gc) >= 0.99, (
        f"the FnGuide price export is claimed survivorship-bias-free at "
        f"622/625 (99.5 %) of genuine common delistings since 2005; it now "
        f"covers {hit}/{len(gc)} ({hit/len(gc):.1%}) — check the export's "
        f"universe filter was 'all codes' (전체 / 상폐 포함)"
    )
    return f"delisted coverage {hit}/{len(gc)} = {hit/len(gc):.1%}", len(gc)


def test_fnguide_price_segments_break_reissued_codes():
    """README.md and price_loader.py both claim the panel's `segment` column
    makes reissued codes safe to difference: '59 codes carry a handover, and
    every return computed within (ticker, segment) stays inside one company'.

    The failure this guards is silent and enormous rather than subtly wrong —
    the handover returns run to +8,136,485 % — so the check is the invariant
    itself, not the count: no `segment` boundary may sit anywhere other than a
    genuine delisting inside a price gap, and no such delisting may be missing
    a boundary.
    """
    fp = REPO / "fnguide_data/cache/fnguide_price.parquet"
    if not fp.exists():
        raise Skipped("run fnguide_data.price_loader first")
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
    assert len(marked) == 59, (
        f"README.md §9 says '59 codes carry a handover'; the cache now has "
        f"{len(marked)} — re-measure the sentence"
    )
    return (f"{len(marked)} reissued-code handovers, all on a genuine "
            f"delisting inside a price gap"), len(px)


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
        raise Skipped("run fnguide_data.price_loader first")
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
    return (f"{impossible} above-limit returns, all attributed to halts or "
            f"정리매매"), int(ret.notna().sum())


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
        raise Skipped("raw/ exports not present")
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
            f"end dates {man.term_end.min():%Y-%m-%d}.."
            f"{man.term_end.max():%Y-%m-%d}"), len(man)


def test_fnguide_sheets_documented_as_populated_carry_data():
    """README.md §7 documents `fnguide_financials_annual_20260219.xlsx` as eight
    populated annual sheets
    plus one 시가총액 sheet that DataGuide returned empty, and the Overview's
    "NOT available in this dataset" line rests on that emptiness: this package
    carries no market capitalisation at all, monthly or daily.

    A sheet with a full header block and no values parses successfully and
    yields an all-NaN frame, so nothing downstream raises on it — an empty pull
    is discovered by a consumer wondering where its numbers went, which is late.
    Both directions fail here. An annual sheet that empties on a re-pull is a
    broken export; 시가총액 filling in is the *good* outcome and still fails,
    because README.md would then describe a package with no market cap while it
    has one, and the consumers routed elsewhere for it were routed on that claim.
    """
    f = REPO / "fnguide_data/raw/fnguide_financials_annual_20260219.xlsx"
    if not f.exists():
        raise Skipped("raw/fnguide_financials_annual_20260219.xlsx not present")
    populated = ("보통주자본금", "자본잉여금", "이익잉여금", "이연법인세부채",
                 "자기주식", "자기주식 처분손실", "영업이익", "총자산")
    cells = {}
    for sheet in populated + ("시가총액",):
        block = pd.read_excel(f, sheet_name=sheet, header=None,
                              engine="calamine").iloc[14:, 1:]
        cells[sheet] = int(block.notna().sum().sum())

    empty = [s for s in populated if cells[s] == 0]
    assert not empty, (
        f"README.md §7 documents {len(populated)} populated annual sheets in "
        f"fnguide_financials_annual_20260219.xlsx; {empty} came back with no "
        f"values. A pull that "
        f"returns an empty grid parses without raising, so nothing else will "
        f"tell you — re-pull before anything reads them"
    )
    assert cells["시가총액"] == 0, (
        f"README.md §7 records the 시가총액 sheet as empty and the Overview "
        f"says this package carries no market capitalisation; the sheet now "
        f"has {cells['시가총액']:,} values. Update both, and revisit every "
        f"consumer that was sent elsewhere for market cap"
    )
    return (f"{len(populated)} annual sheets populated, 시가총액 empty"), sum(cells.values())


CHECKS = [
    test_fnguide_price_delisted_coverage,
    test_fnguide_price_segments_break_reissued_codes,
    test_fnguide_price_impossible_returns_are_all_inspected,
    test_fnguide_vintage_manifest_matches_disk,
    test_fnguide_sheets_documented_as_populated_carry_data,
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
