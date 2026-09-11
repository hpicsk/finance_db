"""Integrity assertions for the claims `finmind_data`'s documentation makes.

This repo has no CI; verification is ad-hoc. Run with the data trees populated,
from anywhere:

    python finmind_data/test_assertions.py

or run every package's assertions at once with `./run_assertions.sh` from the
repo root. Each check prints PASS, FAIL, or SKIP where a prerequisite
artifact is absent, along with `n`, the size of the population it examined.
The script exits non-zero if any check fails, if any examined nothing, and if
any skipped — a skip verified nothing, so iterating without the artifact takes
`--allow-skips`. `n` is held against `populations.json`, which records what
each check last read; re-seed it with `--write-populations` after a refresh.
"""
from __future__ import annotations

import ast
import glob
import json
import math
import os
import re
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from finmind_data.window import COVERAGE_START, COVERAGE_END, clip  # noqa: E402

# Each check's population, recorded so a tree that lost rows fails rather
# than passing on a smaller one. Per package, not per repo: the root is a
# container and holds no package's numbers.
POPULATIONS = Path(__file__).with_name("populations.json")


def _tree(path, columns=None):
    """One per-stock tree file, clipped to the window.

    The trees are wider than the window on both sides — prices from 2005, and
    whatever `download.py --extend` last reached — so an unclipped read counts
    sessions the package does not answer for and reports the total as the
    window's. Every figure below is quoted on the window, so every read of a
    dated file goes through here; a frame carrying no `date` is returned as it
    came. Reading through one helper rather than clipping at each call site is
    also what keeps the next check that opens a tree from being the one that
    forgets.
    """
    df = pd.read_parquet(path, columns=columns)
    if not len(df) or "date" not in df.columns:
        return df
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    return clip(df)


class Skipped(Exception):
    """A prerequisite artifact is absent, so this check verified nothing.

    Distinct from a pass because it is: it used to print as one, which is the
    same confusion the population guard below exists to remove.
    """


def _panel_ids():
    """The stocks the panel is made of: `universe.parquet`, not the tree.

    The tree carries 72 files the universe does not — names the universe filter
    removes as instruments rather than common stock, Innovation Board listings
    and TDRs among them. A panel-wide check that globs the tree reads them back
    in, so this suite could assert that the universe excludes an instrument and
    then report a panel total measured with it included. Thirty of the 72 still
    hold in-window rows, so the two answers really do differ. The universe is
    what the README's exclusion table describes, so it is what a panel figure is
    counted over.
    """
    u = pd.read_parquet(REPO / "finmind_data/universe.parquet")
    return sorted(u["stock_id"].astype(str))


# ---- Taiwan: every reader of the trees goes through the window -------------
def test_taiwan_tree_readers_import_the_window():
    """`window`'s own docstring: every module that reads the trees imports it.

    The trees hold sessions on both sides of `COVERAGE_START..COVERAGE_END`, so
    a module that reads one without clipping does not fail — it measures a wider
    panel than it reports, and that number is the kind that gets published. The
    invariant was written in prose and nothing enforced it, which is the state
    every figure in this suite was in before it was asserted.

    Two files are excepted and both are named here rather than skipped by
    pattern, so adding a third is a change to this list and not a silent one.
    `window.py` defines the window, and `download.py` writes the trees — writing
    them short is what the window is not for, since a wider tree costs nothing
    and a narrower one cannot be widened without a re-download.

    The import is what is checked, not the call, because that is what the
    docstring claims and a module may legitimately hold the dates rather than
    clip a frame (`build_universe` reads neither tree and does exactly that).
    A reader that imports and then forgets to clip is caught by the population
    guard instead: its count moves against `populations.json`.
    """
    src = sorted(glob.glob(str(REPO / "finmind_data/*.py")))
    readers = []
    for f in src:
        text = Path(f).read_text()
        if "ohlcv/" in text:
            readers.append((os.path.basename(f), text))
    assert readers, (
        "no module in the package names `ohlcv/` at all, so this check has no "
        "population — the trees moved, or the path spelling did, and the "
        "invariant is unverified rather than held"
    )
    excepted = {"window.py", "download.py"}
    names = {n for n, _ in readers}
    assert excepted <= names, (
        f"window.py's docstring excepts {sorted(excepted)} from the import "
        f"rule; {sorted(excepted - names)} no longer names `ohlcv/`, so the "
        f"exception is stale and the docstring names a file that is not there"
    )
    missing = sorted(n for n, t in readers
                     if n not in excepted
                     and "from .window import" not in t
                     and "from finmind_data.window import" not in t)
    assert not missing, (
        f"window.py's docstring claims every module that reads the trees "
        f"imports the window from it, `download.py` excepted; {missing} reads "
        f"them and does not. An unclipped read measures the sessions outside "
        f"{COVERAGE_START.date()}..{COVERAGE_END.date()} into a figure the "
        f"package publishes as being about the window"
    )
    return (f"{len(readers)} modules name the trees; "
            f"{len(readers) - len(excepted)} of them import the window, "
            f"{sorted(excepted)} excepted"), len(readers)


def test_taiwan_coverage_does_not_outrun_the_data():
    """`COVERAGE_END` is a claim about the artifacts, so it is read off them.

    The assertion this replaces compared the package's span against a `WIN_END`
    duplicated across the packages that quote figures on one — a study window,
    which is a research decision, sitting in a package that holds data and no
    study. It could not fail on anything the data did: coverage could name a
    session no artifact carries, and every figure quoted on the window would
    then be measured over a shorter panel than it claims, invisibly, because
    `clip` returns what exists rather than what was asked for.

    Three artifacts have to reach the far edge and they are three different
    claims. The session calendar is what `universe_at` snaps a date to, so a
    coverage end past its last row is a date with no universe. The price panel
    is what every count is taken over. And `listing_spans`' `registry_pull` is
    the day the 興櫃 boundary was read, so coverage past it dates names against
    a registry that had not yet seen them.

    Both ends must *be* sessions rather than merely lie inside the calendar. A
    coverage end on a Sunday would pass a `<=` against the last session and
    name a day the market was shut, which is the same defect one day wide.
    """
    cal_path = REPO / "finmind_data/trading_sessions.parquet"
    spans_path = REPO / "finmind_data/listing_spans.parquet"
    tape_path = REPO / f"finmind_data/tape/{COVERAGE_END.year}.parquet"
    if not cal_path.exists() or not spans_path.exists() or not tape_path.exists():
        raise Skipped("trading_sessions.parquet / listing_spans.parquet / the "
                      "tape year coverage ends in are not built — run "
                      "`python -m finmind_data.tape_universe` then "
                      "`python -m finmind_data.pit_universe`")
    cal = list(pd.read_parquet(cal_path)["date"])
    lo, hi = COVERAGE_START.strftime("%Y-%m-%d"), COVERAGE_END.strftime("%Y-%m-%d")
    assert lo in cal and hi in cal, (
        f"coverage runs {lo}..{hi} and the session calendar runs "
        f"{cal[0]}..{cal[-1]}; "
        f"{[d for d in (lo, hi) if d not in cal]} is not a session in it, so "
        f"the window opens or closes on a day the market was shut or on a day "
        f"the tape does not carry. Re-run `pit_universe` after extending the "
        f"tape, or move COVERAGE_END back to a session"
    )
    assert cal[-1] == hi, (
        f"the calendar holds {cal[-1]} after COVERAGE_END {hi}, so the tape "
        f"reaches further than the package answers for and the two were built "
        f"from different constants")

    pull = pd.read_parquet(spans_path)["registry_pull"]
    assert pull.nunique() == 1, (
        f"listing_spans carries {pull.nunique()} registry stamps; the 興櫃 "
        f"boundary is one pull and a second means two were spliced")
    stamp = str(pull.iloc[0])
    assert stamp >= hi, (
        f"the 興櫃 registry was read on {stamp} and coverage runs to {hi}, so "
        f"every name listed between the two is dated against a registry that "
        f"had not seen it")

    # `download.py` does not import the window, so its `--end` default is a
    # copy of this constant, and it is what a fresh clone pulls the trees to.
    # An extension that moves the constant and not the copy leaves the next
    # rebuild short of the coverage every figure here is quoted on.
    end_default = [kw.value.value
                   for node in ast.walk(ast.parse(
                       (REPO / "finmind_data/download.py").read_text()))
                   if isinstance(node, ast.Call)
                   and getattr(node.func, "attr", None) == "add_argument"
                   and node.args
                   and getattr(node.args[0], "value", None) == "--end"
                   for kw in node.keywords if kw.arg == "default"]
    assert end_default == [hi], (
        f"download.py's --end default is {end_default} and COVERAGE_END is "
        f"{hi}; a fresh clone pulls the trees to the default, so the two must "
        f"name one session")

    # A pull crossing the exchange's close leaves the trees holding that
    # session for the stocks fetched after it and not for the ones fetched
    # before, so the day reads as a market of a few hundred names. The tape says
    # who traded, so the shortfall is measured against it rather than against a
    # floor — a floor high enough to catch a half-written session is a number
    # nothing in the package derives, and one low enough to be safe catches
    # nothing.
    tape = pd.read_parquet(tape_path, columns=["date", "stock_id"])
    universe = set(pd.read_parquet(
        REPO / "finmind_data/universe.parquet", columns=["stock_id"])["stock_id"])
    on_last = sorted(universe & set(
        tape.loc[tape["date"].astype(str) == hi, "stock_id"]))
    assert on_last, (
        f"the tape carries {hi} and shows no universe name trading on it, so "
        f"coverage ends on a day the package holds no price for")
    silent = [s for s in on_last
              if hi not in set(pd.read_parquet(
                  REPO / f"finmind_data/ohlcv/{s}.parquet",
                  columns=["date"])["date"].astype(str))]
    assert not silent, (
        f"{len(silent)} of the {len(on_last):,} universe names the tape quotes "
        f"on {hi} carry no ohlcv row for it ({silent[:5]}); the download stopped "
        f"partway through that session, so move COVERAGE_END back to the last "
        f"one it finished")
    return (f"coverage {lo}..{hi} sits on sessions the calendar carries "
            f"({len(cal):,} of them), download.py defaults to it, the "
            f"registry was pulled {stamp}, and all "
            f"{len(on_last):,} universe names the tape quotes on the last one "
            f"have an ohlcv row for it"), len(cal)

def test_taiwan_tape_years_are_whole():
    """A tape year file is skipped because it exists, so a partial one is invisible.

    `tape_universe.sweep()` writes one file per year and skips a year whose file
    is already on disk. That is the right resume rule while every year inside
    coverage is whole, and it stops being right the moment coverage ends inside
    a year: the file written then holds January to the coverage end, the next
    extension skips it for existing, and the rest of that year never reaches the
    calendar `pit_universe` builds. `universe_at` would then raise on a session
    the market held.

    Nothing else sees it. The gap is not a hole in the middle of the calendar
    that a continuity check would find — it is the calendar ending early, which
    reads exactly like coverage ending early.

    A whole year opens in January and closes in December; the first and last
    files are the two that may be cut, and each is cut at a coverage end this
    file knows. Months rather than dates, because which session opens or closes
    a year is the tape's answer and not something to restate here.
    """
    import pyarrow.parquet as pq

    from finmind_data.tape_universe import _YEAR_END_SLACK

    files = sorted((REPO / "finmind_data/tape").glob("*.parquet"))
    if not files:
        raise Skipped("tape/ not built (python -m finmind_data.tape_universe)")
    years = [int(f.stem) for f in files]
    assert years == list(range(years[0], years[-1] + 1)), (
        f"the tape skips a year: {sorted(set(range(years[0], years[-1] + 1)) - set(years))}")
    assert years[0] == COVERAGE_START.year and years[-1] == COVERAGE_END.year, (
        f"the tape runs {years[0]}..{years[-1]} and coverage "
        f"{COVERAGE_START.year}..{COVERAGE_END.year}; the sweep was run under a "
        f"different window than the one applied to it")

    ragged = []
    for f, y in zip(files, years):
        d = pd.to_datetime(pd.read_parquet(f, columns=["date"])["date"])
        first, last = d.min(), d.max()
        want_open = COVERAGE_START if y == years[0] else pd.Timestamp(y, 1, 1)
        want_close = COVERAGE_END if y == years[-1] else pd.Timestamp(y, 12, 31)
        # The slack is `sweep()`'s own, imported rather than restated: it is
        # what decides whether that function re-sweeps a year, so a check
        # written to a second copy would disagree with the code it guards.
        if first > want_open + _YEAR_END_SLACK:
            ragged.append(f"{y} opens {first.date()}, a month after {want_open.date()}")
        if last < want_close - _YEAR_END_SLACK:
            ragged.append(f"{y} closes {last.date()}, a month before {want_close.date()}")
    assert not ragged, (
        f"{len(ragged)} tape year files do not span the coverage they were "
        f"swept for: {ragged[:4]}. `sweep()` skips a year whose file exists, so "
        f"re-running will not repair these — delete the file and re-sweep"
    )
    rows = sum(pq.read_metadata(f).num_rows for f in files)
    return (f"{len(files)} tape years {years[0]}..{years[-1]}, each spanning "
            f"the coverage swept for it, {rows:,} rows"), len(files)

def test_taiwan_delisting_frame_does_not_follow_coverage():
    """A frozen sample frame, and a coverage constant that moves under it.

    `delisting_sign` drew its accuracy sample on 2026-08-17 from the delistings
    inside `_WIN_START.._WIN_END`, stratified on the cuts and seeded. The draw
    is a function of that frame rather than a report over it, so a frame that
    grows re-strata a sample whose labels are already collected — the one edit
    the pre-registration exists to forbid. The frame used to be `window.py`'s
    `COVERAGE_END`, which moves for the package's reasons rather than this
    registration's, so the forbidden edit was available to whoever next had a
    reason to move coverage, with nobody deciding to make it.

    `test_taiwan_delisting_sign_sample_is_preregistered` catches the redraw and
    not the cause: its message names the cuts, the stratum edges, the seed and
    the population as equally likely, and a reader who moved none of them has
    no reason to suspect the fourth. This names it.

    Checked by moving `COVERAGE_END` and re-deriving, not by reading the source
    for the constant: `_WIN_END = COVERAGE_END` has other spellings, and a grep
    passes on all of them. The comparison is against the committed
    `delisting_sign.parquet` rather than a second call on the unperturbed
    frame, which would cost the same 13-second scan twice and compare the code
    against itself — git holds the frame the labels were drawn against.
    """
    import finmind_data.window as window
    from finmind_data import delisting_sign

    frozen = pd.read_parquet(REPO / "finmind_data/delisting_sign.parquet")
    frozen_ids = set(frozen["stock_id"].astype(str))

    saved = window.COVERAGE_END
    try:
        # Two years past the frame, which is more than the 13 delistings the
        # vendor has recorded since it closed — enough that a frame following
        # coverage cannot come back the same size by accident.
        window.COVERAGE_END = saved + pd.Timedelta(days=730)
        moved = delisting_sign.features()
    finally:
        window.COVERAGE_END = saved

    moved_ids = set(moved["stock_id"].astype(str))
    assert moved_ids == frozen_ids, (
        f"moving COVERAGE_END two years past the frame changed the delisting "
        f"population by {len(moved_ids ^ frozen_ids)} names "
        f"({sorted(moved_ids ^ frozen_ids)[:8]}), so the pre-registered frame "
        f"is following a constant that moves with the download. The stratified "
        f"draw is a function of that population, so the accuracy in README's "
        f"frozen baseline would be reported over a sample redrawn after its "
        f"labels were collected"
    )
    a = moved.set_index("stock_id")["drawdown"].astype(float)
    b = frozen.set_index("stock_id")["drawdown"].astype(float)
    b.index = b.index.astype(str)
    a.index = a.index.astype(str)
    worst = float((a - b.reindex(a.index)).abs().max())
    assert worst < 1e-12, (
        f"the population held but the drawdowns moved by up to {worst:.2e} "
        f"under a moved COVERAGE_END, so something downstream of the frame — "
        f"the peak lookback or the panel's last session — is still reading it"
    )
    return (f"{len(moved_ids)} names and their drawdowns are unchanged with "
            f"COVERAGE_END moved to "
            f"{(saved + pd.Timedelta(days=730)).date()}"), len(moved_ids)

def test_taiwan_loader_takes_the_callers_span():
    """A study names the period it reports on, because this package holds none.

    Two of `load_adjusted`'s derivations are read off the span's own edge —
    the factor anchors on its last priced session, and a series break is
    measured inside it — so the span is part of what the numbers say rather
    than a filter over them, and a figure taken on the package's coverage
    moves whenever that constant does, with nothing printed to say so. `clip`
    and `load_adjusted` take `start` and `end` for that, and
    the passthrough is what this checks: an argument accepted and then dropped
    would leave every caller on the default and read identically from outside.

    The cut is placed the session before a 除權息 event rather than at an
    arbitrary date. Anchored either side of a quiet stretch the two frames
    agree, so a check written at any other date would pass on a span that
    reached the read and not the derivation. Across an event the shared stretch
    rescales by one constant — the same series read off a second anchor — and
    that constant is 1.0 exactly when the argument was dropped.

    The witness is derived rather than named: the first stock whose events and
    session counts satisfy the shape above. Its event is the first at least 400
    days after `COVERAGE_START`, which is a bound that does not move when the
    trees are extended, so the span compared here is the same one on every run.
    """
    import numpy as np

    from finmind_data.adjusted_loader import load_adjusted, available_stocks

    days = pd.DataFrame({"date": pd.date_range(COVERAGE_START, "2030-12-31")})
    named = clip(days, start="2015-03-02", end="2015-03-06")
    assert (str(named["date"].min().date()),
            str(named["date"].max().date())) == ("2015-03-02", "2015-03-06"), (
        f"clip returned {named['date'].min().date()}..{named['date'].max().date()} "
        f"for a span of 2015-03-02..2015-03-06, so it is ignoring what it was "
        f"handed and every caller below it reads the package's coverage instead"
    )

    stocks = available_stocks()
    if not stocks:
        raise Skipped("price_adj/ not built — run `download.py`")

    scanned = 0
    witness = None
    for sid in stocks:
        f = REPO / f"finmind_data/div_result/{sid}.parquet"
        if not f.exists():
            continue
        ev = pd.read_parquet(f)
        if not len(ev) or "date" not in ev.columns:
            continue
        d = pd.to_datetime(ev["date"]).sort_values()
        d = d[d >= COVERAGE_START + pd.Timedelta(days=400)]
        if not len(d):
            continue
        scanned += 1
        if scanned > 50:
            break
        try:
            full = load_adjusted(sid)
        except (FileNotFoundError, ValueError):
            continue
        pre = full[full["date"] < d.iloc[0]]
        if len(pre) < 200 or len(full) - len(pre) < 200:
            continue
        witness = (sid, d.iloc[0], pre["date"].iloc[-1], full)
        break
    assert witness is not None, (
        f"no stock among the first {scanned} with an in-window 除權息 event "
        f"carries 200 sessions on each side of it, so the passthrough has "
        f"nothing to be measured on — div_result/ or price_adj/ lost rows"
    )
    sid, ev_date, cut, full = witness

    half = load_adjusted(sid, end=cut)
    assert half["date"].max() == cut, (
        f"{sid}: load_adjusted(end={cut.date()}) returned rows through "
        f"{half['date'].max().date()}, so `end` did not reach the read"
    )
    assert len(half) < len(full), (
        f"{sid}: the named span returned {len(half):,} rows against the "
        f"default's {len(full):,}, so the two frames are the same read"
    )

    for name, frame in (("default", full), ("named", half)):
        fin = frame["tr_factor"][np.isfinite(frame["tr_factor"])]
        assert len(fin) and math.isclose(float(fin.iloc[-1]), 1.0, abs_tol=1e-12), (
            f"{sid}: the {name} frame's last priced session carries "
            f"tr_factor={float(fin.iloc[-1]) if len(fin) else float('nan')}, "
            f"not the 1.0 the anchoring puts there — the span did not reach "
            f"the derivation"
        )

    a = full.set_index("date")["adj_close_tr"]
    b = half.set_index("date")["adj_close_tr"]
    shared = a.index.intersection(b.index)
    ratio = (a.loc[shared] / b.loc[shared]).dropna()
    assert len(ratio), f"{sid}: the two frames share no priced session"
    assert ratio.round(9).nunique() == 1, (
        f"{sid}: the two frames differ by {ratio.round(9).nunique()} ratios "
        f"over {len(ratio):,} shared sessions, so they are not the same series "
        f"on two anchors — one of them lost an event"
    )
    r = float(ratio.iloc[0])
    assert not math.isclose(r, 1.0, abs_tol=1e-9), (
        f"{sid}: the frame cut at {cut.date()} and the default frame carry the "
        f"same adjusted numbers, so `end` reached the read and not the anchor. "
        f"The cut sits the session before the 除權息 of {ev_date.date()}, which "
        f"rescales one and not the other"
    )
    return (f"{sid}: end={cut.date()} returns {len(half):,} of {len(full):,} "
            f"sessions and re-anchors across the {ev_date.date()} event; "
            f"{len(ratio):,} shared sessions rescale by {r:.6f}"), len(ratio)


# ---- Taiwan: no collector names a dataset the vendor does not publish ------
def test_taiwan_dataset_names_in_code_resolve():
    """`catalogue`'s own docstring: a dataset name is looked up, not guessed.

    A wrong dataset name is not a loud failure at this API. `/data` answers a
    name it does not know the same way it answers a name that is simply empty
    for the ticker asked for, so an invented endpoint and a genuinely absent
    series are told apart by probing, and the answer is then written down as a
    comment that nothing re-checks. `download.py` carries two such answers.

    The vendored catalogue is the enum itself, so the question is local. This
    checks it in both directions: every dataset name spelled anywhere in the
    package's own source resolves, and every name registered in
    `catalogue.KNOWN_ABSENT` is still absent — the second half is the one that
    decays, because the vendor adding a dataset silently converts a true note
    into a false one and no other check in this file would see it.

    The scan is over string constants rather than over a list of collectors, so
    a module added tomorrow is covered without editing anything here; it walks
    the AST rather than the raw text, which is what keeps a `#` comment about a
    name from being read as a use of it. Scope is the CamelCase REST enum, for
    the reason `catalogue`'s docstring gives: the lower-case spelling collides
    with the SDK's method namespace, and a bad SDK method already fails loudly.
    """
    from finmind_data import catalogue

    enum = set(catalogue.datasets())
    assert len(enum) > 50, (
        f"the vendored catalogue parsed to {len(enum)} datasets, which is too "
        f"few to be the published enum (FinMind advertises 75+) — the copy is "
        f"truncated or its heading format moved, and every name below would "
        f"then resolve against a set that cannot refute any of them"
    )
    token = re.compile(r"\bTaiwan[A-Z][A-Za-z0-9]*\b")
    seen = {}
    for f in sorted(glob.glob(str(REPO / "finmind_data/*.py"))):
        for node in ast.walk(ast.parse(Path(f).read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for t in token.findall(node.value):
                    seen.setdefault(t, set()).add(os.path.basename(f))
    used = {t: v for t, v in seen.items() if t not in catalogue.KNOWN_ABSENT}
    assert used, (
        "no module in the package spells a FinMind dataset name at all, so "
        "this check has no population — the collectors moved their names out "
        "of source, and the invariant is unverified rather than held"
    )
    unknown = sorted(t for t in used if t not in enum)
    assert not unknown, (
        f"{unknown} is named in {sorted(set().union(*(used[t] for t in unknown)))} "
        f"and is not in the enum the vendor publishes as of "
        f"{catalogue.pull_date()}. Either it was never a dataset, or it was "
        f"withdrawn and whatever reads it now collects nothing while looking "
        f"like it collects an empty series"
    )
    resurrected = sorted(t for t in catalogue.KNOWN_ABSENT if t in enum)
    assert not resurrected, (
        f"catalogue.KNOWN_ABSENT records {resurrected} as refused by the API, "
        f"and the vendor now publishes it. The note is false and the workaround "
        f"named beside it may no longer be the only way to get the series: "
        f"{ {t: catalogue.KNOWN_ABSENT[t] for t in resurrected} }"
    )
    return (f"{len(used)} dataset names in source all resolve against the "
            f"{len(enum)}-dataset enum pulled {catalogue.pull_date()}; "
            f"{len(catalogue.KNOWN_ABSENT)} registered absences still absent"), len(used)


# ---- Taiwan: one OHLCV file per universe id --------------------------------
def _tw_ids():
    u = pd.read_parquet(REPO / "finmind_data/universe.parquet")
    d = pd.read_parquet(REPO / "finmind_data/delisted_universe.parquet")
    uid = set(u["stock_id"].astype(str))
    files = {os.path.basename(p).split(".")[0]
             for p in glob.glob(str(REPO / "finmind_data/ohlcv/*"))}
    return u, d, uid, files


def _in_window_exits():
    """Every universe name that delisted inside coverage, with its last trade.

    The set `pit_universe.build()` dates as exits, read the way it reads it. Not
    `delisting_sign.parquet`: that is a pre-registered sample frozen on its own
    dates, and it was this set only while coverage ended where the frame does.
    A survivorship property checked over the frame skips every name that
    delisted after the frame closed — the newest delistings, which are exactly
    the ones an extension adds, so the check passes on the population it can no
    longer see. Names with no traded session inside coverage are left out: they
    have no last trade the universe could be asked about.
    """
    from finmind_data.pit_universe import sessions

    cal = sessions()
    _, d, uid, _ = _tw_ids()
    d = d[d["stock_id"].isin(uid) & (d["date"] >= cal[0]) & (d["date"] <= cal[-1])]
    rows = []
    for r in d.itertuples():
        p = _tree(REPO / f"finmind_data/ohlcv/{r.stock_id}.parquet",
                  columns=["date", "close"])
        if not len(p):
            continue
        p = p[(p["close"] > 0) & (p["date"] <= pd.Timestamp(r.date))]
        if len(p):
            rows.append((r.stock_id, p["date"].max(), pd.Timestamp(r.date)))
    return pd.DataFrame(rows, columns=["stock_id", "last_trade", "delist_date"])


def test_taiwan_ohlcv_one_per_universe():
    u, _, uid, files = _tw_ids()
    missing = uid - files
    assert len(u) == 2159, f"Taiwan universe = {len(u)}, README pins 2,159"
    assert not missing, f"{len(missing)} universe ids have no OHLCV file"
    return f"Taiwan universe = {len(u)}; all have OHLCV", len(u)


# TWSE appends this to the abbreviated name of an Innovation Board listing.
_INNOVATION_BOARD_SUFFIX = r"-(?:KY)?創$"

# A 4-digit code is not by itself a common stock. Taiwan assigns its ETFs the
# 00xx block and its depositary receipts the 91xx block, and both are among the
# instruments README "Universe" excludes; every 00xx and every 91xx code in
# `taiwan_stock_info` carries ETF or 存託憑證 respectively, with no common stock
# in either. The 2026-08-17 delisting refresh puts 11 of them inside the window,
# where a four-name exception list used to be enough.
_NON_COMMON_CODE_BLOCK = r"(?:00|91)\d\d"

# The instrument types README "Universe" excludes, as `taiwan_stock_info`
# spells them. Kept in step with `build_universe.exclude_industries`.
_EXCLUDED_INSTRUMENTS = {
    "ETF", "ETN", "受益證券", "存託憑證", "臺灣存託憑證",
    "創新版股票", "創新板股票",
}


def test_taiwan_universe_excludes_the_instruments_it_claims_to():
    """README "Universe": ETFs, ETNs, TDRs and the Innovation Board are excluded.

    The count beside that sentence used to be the only thing asserted, and a
    count cannot tell a universe of 2,154 correct names from one of 2,121
    correct names plus 33 the criterion forbids. That is what shipped: every
    Innovation Board name carries an ordinary industry row *as well as* its
    創新板股票 row, so a filter that dropped rows and deduplicated afterwards
    removed the tier row and kept the stock on the other one, admitting all 29
    of the names the exclusion was written to remove. Four TDRs arrived by a
    second route — the pre-2015 delisting overlay tested "absent from the
    filtered table" and so re-admitted exactly what the filter had removed.

    This check is deliberately partial, and the partiality is the point. A
    committed row records one classification, so it cannot show that a *second*
    row disqualifies the stock — 2432 sits here as 倚天/通信網路業, and only the
    live endpoint knows it is now 倚天酷碁-創/創新板股票. The complete test needs
    the source table and therefore lives at the generator, in
    `build_universe.py`, which asserts the exclusion dropped stocks rather than
    rows. What is checkable offline is the two signatures a leak leaves in the
    file itself, and both are enumerated over every row rather than looked up
    for the names this bug happened to involve.
    """
    u = pd.read_parquet(REPO / "finmind_data/universe.parquet")
    name = u["stock_name"].astype(str)

    bad_industry = u[u["industry_category"].isin(_EXCLUDED_INSTRUMENTS)]
    assert bad_industry.empty, (
        f"README 'Universe' excludes ETFs, ETNs, beneficiary certificates and "
        f"TDRs, but {len(bad_industry)} rows carry one as their "
        f"industry_category: "
        f"{bad_industry[['stock_id', 'stock_name', 'industry_category']].to_dict('records')[:5]}"
    )

    inn = u[name.str.contains(_INNOVATION_BOARD_SUFFIX, regex=True, na=False)]
    assert inn.empty, (
        f"README 'Universe' excludes the TWSE Innovation Board, but "
        f"{len(inn)} names carry its -創 suffix: "
        f"{sorted(inn['stock_id'].astype(str))}"
    )

    assert u["stock_id"].is_unique, (
        f"universe.parquet has {len(u) - u['stock_id'].nunique()} duplicate "
        f"stock_id — taiwan_stock_info returns one row per classification, not "
        f"per stock, and a duplicate means the reduction to one row per stock "
        f"did not happen"
    )
    return (f"{len(u)} ids, none carrying an excluded instrument type or the "
            f"Innovation Board -創 suffix"), len(u)


def test_taiwan_price_adj_one_per_universe():
    """Every universe id was fetched, and the empty ones are the known 92.

    `adjusted_loader.load_adjusted` raises when the file is absent, so a partial
    download is a hole in the panel rather than a degraded mode. An *empty* file
    is different: the vendor served nothing, and the README names how many.
    """
    _, _, uid, _ = _tw_ids()
    adj = {os.path.basename(p).split(".")[0]
           for p in glob.glob(str(REPO / "finmind_data/price_adj/*"))}
    missing = uid - adj
    assert not missing, (
        f"{len(missing)} universe ids have no price_adj file "
        f"(first few: {sorted(missing)[:5]})"
    )
    # "Served nothing" is judged on the window, the same test `load_adjusted`
    # and the hole count apply: a series the vendor supplies only for years the
    # package does not answer for is a name it serves nothing for here.
    empty = sum(1 for sid in uid
                if not len(_tree(
                    REPO / f"finmind_data/price_adj/{sid}.parquet")))
    assert empty == 92, (
        f"README pins 92 empty adjusted series — 50 in-window delistings and 42 "
        f"pre-window, and none of the third kind the shorter window had, a name "
        f"listed too recently for the vendor to carry an adjusted history yet; "
        f"the tree now has {empty}. A change here moves the survivorship hole "
        f"the README quantifies"
    )
    return (f"all {len(uid)} ids fetched; {empty} empty, {len(uid) - empty} "
            f"with data"), len(uid)


def test_taiwan_adjusted_survivorship_hole():
    """README, "The adjusted panel is survivorship-biased": 50 of 179.

    The universe carries a 57-name overlay of in-window delistings that
    FinMind's live `taiwan_stock_info` no longer returns (see
    `test_taiwan_overlay_covers_the_window`). `TaiwanStockPriceAdj` drops the
    same names, so the raw panel is survivorship-free and the adjusted one is
    not. This asserts the size of that hole, because a panel built by dropping
    NaN reinstates the bias without saying so.

    The hole used to read as an edge — 38 names, every one delisted 2005-2007,
    which invited the reading that the vendor's history simply starts later than
    the raw one. It is not an edge. Correcting the universe on 2026-08-17 put
    the missing names in, and they delisted 2012-2020: the vendor drops
    delistings scattered through the middle of the window, and the earlier shape
    was the biased overlay describing itself.
    """
    u = pd.read_parquet(REPO / "finmind_data/universe.parquet")
    d = pd.read_parquet(REPO / "finmind_data/delisted_universe.parquet")
    uid = set(u["stock_id"].astype(str))
    d = d.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["sid"] = d["stock_id"].astype(str)
    inwin = d[(d["date"] >= COVERAGE_START) & (d["date"] <= COVERAGE_END)
              & d["sid"].isin(uid)]

    hole = []
    for sid in sorted(set(inwin["sid"])):
        raw = _tree(REPO / f"finmind_data/ohlcv/{sid}.parquet")
        adj = _tree(REPO / f"finmind_data/price_adj/{sid}.parquet")
        if len(raw) and not len(adj):
            hole.append(sid)

    assert len(inwin["sid"].unique()) == 179, (
        f"README counts 179 in-window universe delistings; found "
        f"{len(inwin['sid'].unique())}"
    )
    assert len(hole) == 50, (
        f"README claims 50 of the 179 in-window delistings have raw prices and "
        f"no adjusted series; found {len(hole)}. If this shrank the vendor has "
        f"backfilled and the caveat is overstated; if it grew the hole is wider "
        f"than the paragraph says"
    )
    yrs = inwin.set_index("sid").loc[hole, "date"].dt.year
    assert (yrs.min(), yrs.max()) == (2012, 2020), (
        f"README claims the hole runs 2012-2020, scattered through the window "
        f"rather than sitting at its start; this tree gives "
        f"{yrs.min()}-{yrs.max()}"
    )
    return (f"{len(hole)} of {len(inwin['sid'].unique())} in-window delistings "
            f"have raw prices and no adjusted series, delisted "
            f"{yrs.min()}-{yrs.max()}"), len(inwin["sid"].unique())


def test_taiwan_adjusted_coverage_decomposition():
    """README, "The adjusted panel is survivorship-biased": 99.04 %, and why.

    The figure has to be quoted against every traded session in `ohlcv/`. Drop
    the 54 uncovered stocks from the denominator and the same files report
    99.98 % — the coverage of a panel the survivorship bias has already been
    taken out of, which is the one number a reader must not cite. This asserts
    the honest denominator and the split of what it misses, so the two cannot
    drift back into each other.

    Both figures moved when the universe was corrected on 2026-08-17, and only
    the honest one moved much: 99.80 % → 98.49 % against 99.95 % → 99.95 %. The
    old denominator was itself survivorship-biased — the 57 delistings the live
    endpoint had dropped were absent from the universe, so the sessions the
    vendor does not cover were absent from the count of what it does not cover.

    Coverage has two directions and only one of them is repairable. The
    sessions `price_adj/` is short of are filled from `ohlcv/`; the sessions
    `ohlcv/` is short of have no source behind them, so they are counted here
    beside the ones that do rather than left to a per-stock `attrs` field
    nobody sums.
    """
    u = pd.read_parquet(REPO / "finmind_data/universe.parquet")
    traded = covered = hole = tail = first = makeup = gap = 0
    vendor_only = []
    gaps = []
    for sid in sorted(set(u["stock_id"].astype(str))):
        fp = REPO / f"finmind_data/ohlcv/{sid}.parquet"
        if not fp.exists():
            continue
        raw = _tree(fp)
        if not len(raw):
            continue
        tr = raw[raw["close"] > 0].copy()
        tr["date"] = pd.to_datetime(tr["date"])
        tr = tr.sort_values("date").reset_index(drop=True)
        traded += len(tr)

        adj = _tree(REPO / f"finmind_data/price_adj/{sid}.parquet")
        if not len(adj):
            hole += len(tr)
            continue
        adj_dates = pd.to_datetime(adj["date"])
        # The other direction: dates the vendor prices that the raw file has no
        # row for at all — not a no-trade row, no row. Taken against every raw
        # date rather than the traded ones, so a no-trade session does not read
        # as a missing one.
        raw_dates = pd.to_datetime(raw["date"])
        vendor_only += [(sid, d, d < raw_dates.min(), d > raw_dates.max())
                        for d in set(adj_dates) - set(raw_dates)]
        miss = ~tr["date"].isin(set(adj_dates))
        covered += int((~miss).sum())
        # A session past the vendor's last is the series stopping at a delisting
        # the raw file kept printing through. Everything else is the raw series'
        # own first traded session, which the vendor series does not carry —
        # verified as exactly that, one per stock, in
        # test_taiwan_vendor_edges_are_carried. The vendor's own file may open on
        # an earlier *date* than that session, because a raw series can open on a
        # no-trade row the vendor still carries a price for; what it never does
        # is open before the raw file does, which the `lead` count below pins.
        tail += int((miss & (tr["date"] > adj_dates.max())).sum())
        inner = miss & (tr["date"] <= adj_dates.max())
        # The reverse gap runs both ways, and only one direction was known. The
        # 303 sessions below are Saturday 補行交易日 the vendor prices and the raw
        # endpoint has no row for; these 11 are the same Saturdays traded in
        # `ohlcv/` and absent from the vendor series. One stock, and the panel
        # marks every one of them `adj_covered=False` rather than carrying a
        # price across, so they are a disclosed hole and counted as one.
        mk = inner & (tr["date"].dt.dayofweek == 5) & (tr.index > 0)
        makeup += int(mk.sum())
        first += int((inner & ~mk & (tr.index == 0)).sum())
        # The fifth kind, and the only one that is the vendor being short rather
        # than the vendor's product being shaped that way: a weekday inside a
        # live series the adjusted endpoint has no row for. Both are a lone
        # traded day inside a suspension, and asking the endpoint for the stretch
        # directly returns the same short answer, so the tree records what is
        # served. Counted rather than forbidden — the coverage ratio asserted
        # below is what bounds it, and an outage large enough to matter moves it.
        g = inner & ~mk & (tr.index > 0)
        gap += int(g.sum())
        gaps += [(sid, d.strftime("%Y-%m-%d")) for d in tr.loc[g, "date"]]

    assert (traded, covered) == (6540520, 6477486), (
        f"README pins adjusted coverage at 6,477,486 of the 6,540,520 traded "
        f"sessions in ohlcv/ (99.04 %); this tree gives {covered:,} of "
        f"{traded:,} ({100 * covered / max(traded, 1):.2f} %)"
    )
    assert (hole, tail, first, makeup, gap) == (61505, 0, 494, 1033, 2), (
        f"README splits the {traded - covered:,} missing sessions into 61,505 "
        f"in the 54 stocks with no adjusted series, none past the end of a "
        f"vendor series that stopped at a delisting, 494 first sessions, "
        f"1,033 make-up sessions the vendor's adjusted product does not cover "
        f"and 2 weekdays inside a live series it is simply short of; this tree "
        f"gives {hole:,} / {tail:,} / {first:,} / {makeup} / {gap}. The first "
        f"number is the survivorship hole — if it moved, so did the bias"
    )
    # The split has to be exhaustive or the categories are a partial reading of
    # the shortfall, with whatever is left over invisible in both the ratio's
    # denominator and the parts.
    assert hole + tail + first + makeup + gap == traded - covered, (
        f"the decomposition accounts for {hole + tail + first + makeup + gap:,} "
        f"of the {traded - covered:,} sessions the vendor does not cover")

    # A gap the panel carried a price across would be a silent one. Disclosure
    # is the whole of what makes it tolerable, so it is checked rather than
    # asserted in prose.
    from finmind_data.adjusted_loader import load_adjusted
    for sid, day in gaps:
        row = load_adjusted(sid, start=day, end=day)
        assert len(row) == 1 and not bool(row["adj_covered"].iloc[0]), (
            f"{sid} {day} is a session the vendor's adjusted series is short "
            f"of, and the panel reports adj_covered=True for it, so the hole "
            f"reaches a reader as coverage")

    # The reverse gap — sessions `price_adj/` carries and `ohlcv/` does not —
    # used to be 303 rows in 96 stocks on 14 Saturdays, and was the whole of
    # what the loader could put back. It is now empty: those sessions are in the
    # raw tree, read from the endpoint that serves them rather than
    # reconstructed. What that count *measured* was never the size of the hole,
    # only the part of it a second local tree happened to reach;
    # `test_taiwan_no_session_the_tape_holds_is_missing` measures the whole of it
    # against the vendor.
    vo = pd.DataFrame(vendor_only, columns=["stock_id", "date", "lead", "trail"])
    assert len(vo) == 0, (
        f"{len(vo):,} sessions in {vo['stock_id'].nunique()} stocks are carried "
        f"by price_adj/ and absent from ohlcv/, so the loader is reconstructing "
        f"rows the raw tree should hold after backfill_make_up_sessions: "
        f"{vo[['stock_id', 'date']].head(10).to_dict('records')}"
    )
    return (f"{covered:,}/{traded:,} = {100 * covered / traded:.2f} % "
            f"(vs {100 * covered / (traded - hole):.2f} % on the bias-removed "
            f"denominator); missing = {hole:,} hole + {tail:,} tail + {first:,} "
            f"first + {makeup:,} make-up + {gap} vendor gap, all disclosed; "
            f"{len(vo)} the other way"
            ), traded


def test_taiwan_overlay_covers_the_window():
    """Survivorship invariant.

    Every in-window 4-digit common delisting must be in `universe.parquet`,
    whether or not FinMind's live `taiwan_stock_info` still serves it. The
    naive "all delisted ids have OHLCV" form was a false alarm.

    The overlay used to stop at 2014, on the premise that the endpoint keeps
    every name delisted from 2015 on. The 2026-08-17 refresh of the delisting
    table falsifies it — 46 of the names it adds delisted in 2015 or later and
    the endpoint has no row for any of them — so the gate is now the window,
    and what this checks is the whole of it rather than its first decade.
    """
    u, d, uid, _ = _tw_ids()
    d = d.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["sid"] = d["stock_id"].astype(str)
    d4 = d[d["sid"].str.fullmatch(r"\d{4}")]
    inwin = d4[(d4["date"] >= COVERAGE_START) & (d4["date"] <= COVERAGE_END)]
    commons = set(inwin["sid"][~inwin["sid"].str.fullmatch(_NON_COMMON_CODE_BLOCK)])
    missing = sorted(commons - uid)
    assert not missing, (
        f"{len(missing)} in-window 4-digit common delistings absent from "
        f"universe.parquet (overlay gap): {missing}"
    )
    n_overlay = int(u[u["type"].isna()]["stock_id"].astype(str).str.fullmatch(r"\d{4}").sum())
    assert n_overlay == 57, f"4-digit type=NaN overlay ids = {n_overlay}, expected 57"
    return ("in-window commons fully covered; 57-name overlay present",
            len(inwin))


def _tape_universe():
    p = REPO / "finmind_data/tape_universe.parquet"
    if not p.exists():
        raise Skipped("tape_universe.parquet not built "
                      "(python -m finmind_data.tape_universe)")
    return pd.read_parquet(p)


def test_taiwan_universe_holds_every_common_the_tape_shows():
    """README, "Survivorship bias": the universe checked against the trade record.

    Every other check on the universe compares it to a registry — the live
    `taiwan_stock_info`, or `delisted_universe.parquet` — and a registry is the
    artifact that forgets. The 2026-08-17 refresh took the delisting table from
    315 rows to 723 and retracted five committed rows; the gate that stood
    before it rested on a premise the table it was checked against could not
    have falsified. Nothing compared the universe to a source that is not a
    list of who was listed.

    `tape_universe.py` is that source: one date-keyed request per session over
    all 3,823 of them returns every instrument that traded, so the union is
    what the market executed rather than what a vendor still serves. A name
    delisted in 2016 is in the 2015 sessions whatever the registry says now.

    What the tape cannot do is say what a code *was* — it mixes ETFs, warrants,
    TDRs and 興櫃 in with the commons — so the instrument type is the registry
    classification stamped into the artifact when it was built. The claim
    asserted here is the conjunction: a code that traded, that the registry
    calls a TWSE or TPEx listing, that is not an excluded instrument, is in
    `universe.parquet`.
    """
    tape = _tape_universe()
    u, _, uid, _ = _tw_ids()
    listed = tape["registry_types"].str.contains("twse|tpex", regex=True)
    # `registry_types` is a union over a code's rows and carries no dates, so a
    # name that moved up from 興櫃 after the window closed reads as a listing
    # that traded inside it — the tape shows its emerging-board sessions and the
    # registry now types it TPEx. `emerging_until` is the registry's own date for
    # that boundary, joined into the tape artifact when it was built;
    # `pit_universe` cuts the same name out of the spans, one session at a time.
    still_emerging = pd.to_datetime(tape["emerging_until"]) >= COVERAGE_END
    common = (listed & ~tape["registry_excluded"] & ~still_emerging
              & ~tape["stock_id"].str.fullmatch(_NON_COMMON_CODE_BLOCK))
    missing = sorted(set(tape.loc[common, "stock_id"]) - uid)
    assert not missing, (
        f"{len(missing)} codes traded inside the window and the registry calls "
        f"each a TWSE/TPEx common, yet none is in universe.parquet — the "
        f"universe is survivorship-biased against them: {missing[:25]}")

    # The other direction is not an error but it is worth pinning: names the
    # universe carries that never traded in the window contribute no
    # observation to anything, so the answerable universe is smaller than the
    # headline count and a study that assumes uniform coverage over 2,159 is
    # measuring 42 empty series.
    never = sorted(uid - set(tape["stock_id"]))
    assert len(never) == 42, (
        f"README 'Universe' pins 2,159 names of which 42 never trade inside "
        f"{COVERAGE_START.date()}..{COVERAGE_END.date()}; this tree has "
        f"{len(never)}")
    assert len(u) - len(never) == 2117, (
        f"the in-window answerable universe is 2,117; this tree gives "
        f"{len(u) - len(never)}")
    return (f"{int(common.sum())} listed commons on the tape, all in the "
            f"universe; {len(never)} universe names never trade in window "
            f"(answerable universe {len(u) - len(never)})"), int(common.sum())


def test_taiwan_pit_universe_is_dated_and_keeps_its_delistings():
    """README "A universe is a name list until it is dated": `universe_at`.

    `universe.parquet` carries the same 2,159 names on every session, so a
    backtest that screens it at a 2013 rebalance holds 586 names that were dead,
    unlisted, or on 興櫃 that day. `listing_spans.parquet` dates it, and this is
    the property the dating exists for: every name that delisted inside the
    window is in the universe on its own last trading session, stays in it
    through the suspension to the session before its listing ends, and is gone
    the day it ends.

    It reads only committed artifacts, so a clone can run it without rebuilding
    the 78 MB tape — which costs an hour of API quota and a token, and would put
    the survivorship property out of reach of anyone who just cloned the repo.

    Which failures it actually catches was measured by breaking the artifact six
    ways rather than argued from what it reads. Dropping 台一's suspension
    bridge, holding 福盈 one session past its exit, deleting 必翔 outright and
    losing a session from the calendar all fail here, the first three naming the
    company. So does re-admitting a 興櫃 name across the full window — but only
    because the two size pins sit on the first and last session and it moves
    both.

    **Admit the same 興櫃 name for the middle of the window only and this check
    passes.** Nothing here reads a market classification; the edge pins are what
    caught the first case, and a span that touches neither edge moves nothing
    this check looks at. `test_taiwan_listing_spans_reconcile_with_the_tape` is
    the only thing that sees it, and it needs `tape/`. So the split is not
    tidiness: a clone can verify that the delistings are all here and cannot
    verify that the 興櫃 names are not.
    """
    from finmind_data.pit_universe import universe_at, sessions

    spans = pd.read_parquet(REPO / "finmind_data/listing_spans.parquet")
    cal = sessions()
    u, _, uid, _ = _tw_ids()
    assert len(cal) == 3_823 and (cal[0], cal[-1]) == (
            COVERAGE_START.strftime("%Y-%m-%d"), COVERAGE_END.strftime("%Y-%m-%d")), (
        f"README pins 3,823 sessions over {COVERAGE_START.date()}.."
        f"{COVERAGE_END.date()}; the calendar holds {len(cal)} over "
        f"{cal[0]}..{cal[-1]}")

    # Structure: one code's spans never touch or overlap, every endpoint is a
    # session, and no code is outside the name list the package screens.
    assert not (set(spans["stock_id"]) - uid), (
        f"{len(set(spans['stock_id']) - uid)} codes have a listing span and are "
        f"not in universe.parquet, so the dated universe admits names the "
        f"undated one screens out")
    at = {d: i for i, d in enumerate(cal)}
    assert set(spans["start"]) <= set(cal) and set(spans["end"]) <= set(cal), (
        "a span begins or ends on a day the market was shut")
    touching = 0
    for _, g in spans.groupby("stock_id"):
        prev = None
        for a, b in zip(g["start"], g["end"]):
            if at[a] > at[b] or (prev is not None and at[a] <= at[prev] + 1):
                touching += 1
            prev = b
    assert not touching, (
        f"{touching} spans overlap, run backwards, or abut the previous one — "
        f"the runs are not maximal, so a gap in the table is not a gap in the "
        f"listing")

    # The claim the artifact exists for: a name list is the same on every
    # session and the universe is not.
    first, last = len(universe_at(cal[0])), len(universe_at(cal[-1]))
    assert (first, last, len(u)) == (1_458, 1_935, 2_159), (
        f"README pins the dated universe at 1,458 names on the first session "
        f"and 1,935 on the last against a 2,159-name list; it is now "
        f"{first} / {last} / {len(u)}")

    # …and the reason it exists: every name that delisted inside the window is
    # in it on its last trading session, stays in it through the suspension, and
    # is gone the day the listing ends.
    frame = _in_window_exits()
    absent_last_trade, absent_at_exit, present_after = [], [], []
    for r in frame.itertuples():
        lt = r.last_trade.strftime("%Y-%m-%d")
        exit_ = r.delist_date.strftime("%Y-%m-%d")
        if r.stock_id not in universe_at(lt):
            absent_last_trade.append(r.stock_id)
        before = [d for d in cal if d < exit_]
        if r.stock_id not in universe_at(before[-1]):
            absent_at_exit.append(r.stock_id)
        after = [d for d in cal if d >= exit_]
        if after and r.stock_id in universe_at(after[0]):
            present_after.append(r.stock_id)
    assert not absent_last_trade, (
        f"{len(absent_last_trade)} of the {len(frame)} in-window delistings are "
        f"absent from the universe on their own last trading session "
        f"({absent_last_trade[:5]}) — a backtest rebalancing that day cannot "
        f"hold a name it held the day before, which is survivorship bias")
    assert not absent_at_exit, (
        f"{len(absent_at_exit)} delistings leave the universe before their "
        f"listing ends ({absent_at_exit[:5]}); the suspension is where the "
        f"delisting return is decided and the position is still open in it")
    assert not present_after, (
        f"{len(present_after)} delistings are still in the universe on or after "
        f"the day their listing ended ({present_after[:5]}), so a backtest "
        f"holds a company that no longer trades")

    # A day the market was shut has no universe, and must say so rather than
    # answer zero: a rebalance calendar written in month-ends lands on one.
    shut = "2016-01-01"
    try:
        universe_at(shut)
        raise AssertionError(
            f"universe_at({shut}) returned a universe for a day the exchange "
            f"was closed; a backtest reads the empty answer as 'nothing to "
            f"hold' and skips the rebalance without failing")
    except ValueError:
        pass
    return (f"{len(spans)} spans over {spans['stock_id'].nunique()} codes: "
            f"{first} names listed on {cal[0]}, {last} on {cal[-1]}, against a "
            f"{len(u)}-name list; all {len(frame)} delistings held to their "
            f"last session"), len(frame)


def test_taiwan_listing_spans_reconcile_with_the_tape():
    """README "A universe is a name list until it is dated": the two corrections.

    The tape is what the market executed, and the spans are that record with two
    corrections applied — 興櫃 sessions removed because the emerging board is not
    a listing, the suspension before a delisting added back because the company
    is still listed in it. This reconciles every one of the 6.6 M code-sessions
    against the tape and pins both corrections by count, so a correction that
    grows or shrinks fails rather than drifts.

    The 興櫃 side is the reason this check exists rather than being folded into
    the clone-safe one. Its boundary comes from the registry, which is a live
    pull and the one input here that is not fixed; the artifact stamps the date
    it was taken. Re-admitting a 興櫃 name for the middle of the window is caught
    here and by nothing else in the suite — the other check's population pins sit
    on the first and last session and a mid-window span moves neither — so
    without `tape/` the emerging-board correction is unverified rather than
    verified cheaply.

    Both counts also carry a membership claim beside the number, because the
    counts alone would be satisfied by the corrections landing on the wrong
    names: the bridge may only touch codes that delisted in-window, and the 興櫃
    removal may touch none of them.
    """
    import numpy as np

    tape_dir = REPO / "finmind_data/tape"
    if not tape_dir.exists():
        raise Skipped("tape/ not built (python -m finmind_data.tape_universe)")
    spans = pd.read_parquet(REPO / "finmind_data/listing_spans.parquet")
    cal = list(pd.read_parquet(REPO / "finmind_data/trading_sessions.parquet")["date"])
    at = {d: i for i, d in enumerate(cal)}
    _, _, uid, _ = _tw_ids()
    frame = set(_in_window_exits()["stock_id"])

    stray = sorted((set(spans["start"]) | set(spans["end"])) - set(cal))
    assert not stray, (
        f"a span begins or ends on a day the {len(cal)}-session calendar does "
        f"not hold ({stray[:5]}), so the two artifacts were not built from the "
        f"same tape and neither can be indexed by the other")
    codes = sorted(uid)
    slot = {c: i for i, c in enumerate(codes)}
    width = len(cal)
    tape = clip(pd.concat(
        [pd.read_parquet(q, columns=["date", "stock_id"])
         for q in sorted(tape_dir.glob("*.parquet"))], ignore_index=True))
    tape = tape[tape["stock_id"].isin(uid)]
    # Freshness, and the reason it is an assertion rather than a comment: the
    # calendar is the tape's own session list, so a session in one and not the
    # other means the tape has been re-swept and the spans are stale. Left
    # unguarded it is not even a wrong answer — `map` returns NaN for the
    # unknown session, the index arithmetic goes float, and the two set
    # differences below are computed over garbage that still counts.
    swept = set(tape["date"])
    assert swept == set(cal), (
        f"the tape holds {len(swept)} in-window sessions and "
        f"trading_sessions.parquet holds {len(cal)}; the tape has moved since "
        f"the spans were built, so rebuild both with "
        f"`python -m finmind_data.pit_universe`")
    quoted = np.unique(tape["stock_id"].map(slot).to_numpy() * width
                       + tape["date"].map(at).to_numpy())
    listed = np.unique(np.concatenate([
        np.arange(at[a], at[b] + 1) + slot[c] * width
        for c, a, b in zip(spans["stock_id"], spans["start"], spans["end"])]))

    added = np.setdiff1d(listed, quoted)
    removed = np.setdiff1d(quoted, listed)
    add_codes = {codes[i] for i in np.unique(added // width)}
    drop_codes = {codes[i] for i in np.unique(removed // width)}
    assert (len(added), len(add_codes)) == (5_538, 150), (
        f"README puts the suspension bridge at 5,538 sessions across 150 of "
        f"the delisted names; the spans add {len(added)} across "
        f"{len(add_codes)}")
    assert not (add_codes - frame), (
        f"the bridge added sessions to {len(add_codes - frame)} codes that did "
        f"not delist in-window ({sorted(add_codes - frame)[:5]}) — it is only "
        f"licensed to cover the suspension before a recorded delisting, and "
        f"anywhere else it is inventing a listing the tape denies")
    assert (len(removed), len(drop_codes)) == (90_406, 135), (
        f"README puts the 興櫃 removal at 90,406 sessions across 135 codes; the "
        f"spans drop {len(removed)} across {len(drop_codes)}. A registry pull "
        f"that moved a promotion date moves this, and it is the one input here "
        f"that is not fixed — the artifact stamps its pull as "
        f"{spans['registry_pull'].iat[0]}")
    assert not (drop_codes & frame), (
        f"{len(drop_codes & frame)} of the in-window delistings lost sessions "
        f"to the 興櫃 removal ({sorted(drop_codes & frame)[:5]}); the removal "
        f"would then be deleting exactly the names the universe exists to keep")
    return (f"{len(listed):,} code-sessions reconciled against the tape: "
            f"+{len(added):,} bridged suspensions in {len(add_codes)} delisted "
            f"names, −{len(removed):,} 興櫃 sessions in {len(drop_codes)} codes",
            int(len(listed)))


def test_taiwan_universe_bridges_a_halt_only_when_asked():
    """README "A universe is a name list until it is dated": the halt rule.

    The span table splits on every session the tape goes quiet, and 609 of the
    2,117 codes have at least one such gap. Whether a position survives one is
    the caller's rule, not the artifact's: a backtest that cannot sell into a
    halt holds through it, and one that marks to the last print does not. So
    `bridge_gaps_upto` closes gaps of at most n sessions at query time and has
    no default other than the artifact's own.

    What this pins is that the knob is real in both directions — that 0 is the
    committed spans untouched, that raising it monotonically merges runs, and
    that the two halves of the bimodal distribution really do move at different
    settings, which is the reason no single number is right. The 1,281 gaps run
    from a median of 7 sessions to 8227's 2,241, and a bridge wide enough to
    close the second is putting a name in the universe on sessions no registry
    in this package says it was listed on.

    It also pins the property bridging must not break. Merging runs within a
    code cannot move that code's last session, so no amount of bridging may put
    a delisted name back in the universe after its exit — the invariant the
    dated universe exists for, checked at the widest setting rather than
    argued from the loop.
    """
    from finmind_data.pit_universe import _bridged, sessions, universe_at

    cal = sessions()
    at = {d: i for i, d in enumerate(cal)}
    spans = _bridged(0)
    committed = pd.read_parquet(REPO / "finmind_data/listing_spans.parquet")
    assert spans[["stock_id", "start", "end"]].equals(
            committed[["stock_id", "start", "end"]]), (
        "bridge_gaps_upto=0 does not return the committed spans, so the default "
        "is a transformation rather than the artifact")

    gaps, wide = [], set()
    for code, g in spans.groupby("stock_id"):
        s, e = list(g["start"]), list(g["end"])
        for i in range(len(g) - 1):
            n = at[s[i + 1]] - at[e[i]] - 1
            gaps.append(n)
            if n >= 60:
                wide.add(code)
    split = int((spans.groupby("stock_id").size() > 1).sum())
    assert (split, len(gaps), len(wide)) == (609, 1_281, 48), (
        f"README puts 609 codes with an interior gap, 1,281 gaps in all and 48 "
        f"codes gapped 60 sessions or more; the spans give {split} / "
        f"{len(gaps)} / {len(wide)}")
    assert int(pd.Series(gaps).median()) == 7 and max(gaps) == 2_241, (
        f"README calls the gap distribution bimodal on a median of 7 sessions "
        f"against 8227's nine-year absence; it is now a median of "
        f"{pd.Series(gaps).median()} and a maximum of {max(gaps)}")

    # Monotone in n, and the two halves move at different settings — which is
    # what makes a single default wrong rather than merely unchosen.
    sizes = [len(_bridged(n)) for n in (0, 5, 20, 60, len(cal) - 1)]
    assert sizes == [3_398, 2_913, 2_186, 2_175, 2_117], (
        f"README pins the span count at 3,398 / 2,913 / 2,186 / 2,175 / 2,117 "
        f"for gaps of 0, 5, 20, 60 and the whole window; it is now {sizes}")
    assert sizes[-1] == spans["stock_id"].nunique(), (
        f"bridging every gap leaves {sizes[-1]} spans over "
        f"{spans['stock_id'].nunique()} codes, so some code still has a hole "
        f"the widest possible bridge did not close")

    # The universe on one session, at the settings a caller would reach for.
    day = "2016-06-30"
    held = [len(universe_at(day, bridge_gaps_upto=n)) for n in (0, 20, len(cal) - 1)]
    assert held == [1_702, 1_704, 1_711], (
        f"README pins {day} at 1,702 names undated by any halt rule, 1,704 "
        f"holding through 20 sessions and 1,711 holding through anything; it is "
        f"now {held}")

    # No bridge may resurrect a delisted name: the invariant the dating exists
    # for, checked where it is most likely to break.
    frame = _in_window_exits()
    widest = universe_at
    raised = []
    for r in frame.itertuples():
        after = [d for d in cal if d >= r.delist_date.strftime("%Y-%m-%d")]
        if after and r.stock_id in widest(after[0], bridge_gaps_upto=len(cal) - 1):
            raised.append(r.stock_id)
    assert not raised, (
        f"{len(raised)} delisted names are back in the universe after their "
        f"exit once gaps are bridged ({raised[:5]}); a bridge merges runs "
        f"inside a code and must never extend the last one")

    try:
        universe_at(day, bridge_gaps_upto=-1)
        raise AssertionError(
            "a negative bridge was accepted; it is a count of sessions to close "
            "up and there is nothing for it to mean")
    except ValueError:
        pass
    return (f"{split} of {spans['stock_id'].nunique()} codes carry an interior "
            f"gap over {len(gaps)} gaps (median {int(pd.Series(gaps).median())} "
            f"sessions, max {max(gaps)}); bridging takes {day} from "
            f"{held[0]} names to {held[-1]}"), split


# ---- Taiwan: the coverage flag has to survive a panel build -----------------
def test_taiwan_adj_covered_survives_concat():
    """README, "The adjusted panel is survivorship-biased": `adj_covered`.

    Coverage rides on a column rather than `df.attrs` because `attrs` survives
    `pd.concat` only when every frame agrees. That makes it present on a panel
    of uniformly covered stocks, which needs no warning, and absent on one that
    mixes covered with uncovered, which is the only panel that does. This pins
    both halves: that `attrs` really does drop, and that the column does not.
    """
    sys.path.insert(0, str(REPO))
    if not (REPO / "finmind_data/unpriced_actions.parquet").exists():
        raise Skipped("unpriced_actions.parquet not built")
    from finmind_data.adjusted_loader import load_adjusted

    full = load_adjusted("2330")       # vendor covers every session
    hole = load_adjusted("1566")       # delisted in-window, covered nowhere
    assert full.attrs["adj_coverage"] == 1.0 and hole.attrs["adj_coverage"] == 0.0, (
        f"2330/1566 chosen as the covered/uncovered pair; they now report "
        f"{full.attrs['adj_coverage']} and {hole.attrs['adj_coverage']}"
    )
    assert hole["adj_covered"].any() is not True and not hole["adj_covered"].any(), (
        "1566 has no adjusted series, so no row may be marked adj_covered"
    )
    assert full["adj_covered"].all(), "2330 is fully covered; every row should say so"

    panel = pd.concat([full, hole], ignore_index=True)
    assert "adj_coverage" not in panel.attrs, (
        "pandas has started propagating attrs across frames that disagree. The "
        "adj_covered column is no longer load-bearing for that reason, but the "
        "README paragraph explaining why it exists is now wrong"
    )
    traded = panel["close"] > 0
    frac = float(panel.loc[traded, "adj_covered"].mean())
    assert 0.0 < frac < 1.0, (
        f"the concatenated panel mixes a covered and an uncovered stock, so "
        f"adj_covered must land strictly between 0 and 1; it is {frac}"
    )
    for op, got in (("merge", panel.merge(panel[["date"]].head(1), on="date")),
                    ("groupby", panel.groupby("stock_id", as_index=False).head(1))):
        assert "adj_covered" in got.columns, (
            f"adj_covered did not survive {op}, which is the whole reason it is "
            f"a column rather than frame metadata"
        )
    return (f"adj_covered survives concat/merge/groupby; panel coverage "
            f"{frac:.4f} where attrs carries {dict(panel.attrs) or 'nothing'}"
            ), len(panel)


# ---- Taiwan: the open field disagrees with its own session bar -------------
def test_taiwan_open_outside_session_range():
    """README caveat 11: `open` sits outside [min, max] on 2.0 % of rows.

    `close` never does, which is what makes this a property of the `open` field
    rather than of the sessions. Asserted because the caveat is the only thing
    standing between the panel and a backtest that enters at the open.

    The shares the caveat prints after the count are measured on the sessions
    `pit_universe.py` keeps, read off the spans `universe_at` reads. The board
    is `type` in `universe.parquet`, the column the Universe table counts. The
    per-year claims range over every year of the window.
    """
    import pyarrow.parquet as pq
    from finmind_data.pit_universe import _spans

    spans = {s: list(zip(pd.to_datetime(g["start"]), pd.to_datetime(g["end"])))
             for s, g in _spans().groupby("stock_id")}
    u = pd.read_parquet(REPO / "finmind_data/universe.parquet")
    board = dict(zip(u["stock_id"].astype(str), u["type"]))
    until = pd.to_datetime(_tape_universe().set_index("stock_id")["emerging_until"])

    bad = tot = stocks = bad_close = gone = gone_emerging = 0
    kept = []
    for sid in _panel_ids():
        p = REPO / f"finmind_data/ohlcv/{sid}.parquet"
        # Some files hold no rows and carry no schema, so a column-projected
        # read would fail on them; the row count comes from the footer instead.
        if pq.ParquetFile(p).metadata.num_rows == 0:
            continue
        r = _tree(p, columns=["date", "open", "max", "min", "close"])
        r = r[r["close"] > 0]
        tot += len(r)
        out = (r["open"] > r["max"]) | (r["open"] < r["min"])
        n = int(out.sum())
        bad += n
        stocks += n > 0
        bad_close += int(((r["close"] > r["max"]) | (r["close"] < r["min"])).sum())
        keep = pd.Series(False, index=r.index)
        for a, b in spans.get(sid, []):
            keep |= r["date"].between(a, b)
        if keep.any():
            kept.append(out[keep].groupby(r.loc[keep, "date"].dt.year)
                        .agg(bad="sum", rows="size")
                        .assign(board=board[sid] or "none"))
        gone += int((out & ~keep).sum())
        gone_emerging += int((out & ~keep & (r["date"] <= until.get(sid, pd.NaT))).sum())

    assert bad_close == 0, (
        f"README caveat 11 rests on close being consistent with its own session "
        f"bar on every row; {bad_close:,} rows now break that, so the problem is "
        f"no longer confined to the open field"
    )
    assert (bad, stocks) == (131257, 684), (
        f"README caveat 11 pins 131,257 rows across 684 stocks with open "
        f"outside [min, max]; this tree gives {bad:,} across {stocks}"
    )
    # The rows `pit_universe.py` removes, each on or before the day its name
    # left 興櫃.
    assert (gone, gone_emerging) == (29651, 29651), (
        f"README caveat 11 says 29,651 of the 131,257 fall on 興櫃 sessions, "
        f"which pit_universe.py removes; it removes {gone:,} of them, "
        f"{gone_emerging:,} on or before their name left 興櫃")

    # The README quotes each share to its last printed digit.
    k = pd.concat(kept).rename_axis("year").reset_index()
    by_board = k.groupby("board")[["bad", "rows"]].sum()
    by_year = k.groupby("year")[["bad", "rows"]].sum()
    share = {"kept": by_board["bad"].sum() / by_board["rows"].sum(),
             **{b: by_board.loc[b, "bad"] / by_board.loc[b, "rows"]
                for b in ("tpex", "twse")},
             **{y: by_year.loc[y, "bad"] / by_year.loc[y, "rows"]
                for y in (2011, 2024)}}
    quoted = {"kept": 0.0157, "tpex": 0.0218, "twse": 0.0112,
              2011: 0.0333, 2024: 0.0006}
    off = {key: f"{share[key]:.2%}" for key, q in quoted.items()
           if not math.isclose(share[key], q, abs_tol=0.00005)}
    assert not off, (
        f"README caveat 11 says the share on the sessions pit_universe.py keeps "
        f"is 1.57 %, 2.18 % for the names the Universe table counts under TPEx "
        f"against 1.12 % for those under TWSE, and falls from 3.33 % of 2011's "
        f"rows to 0.06 % of 2024's; the tree gives {off}")

    window = list(range(COVERAGE_START.year, COVERAGE_END.year + 1))
    last = int(by_year.index[by_year["bad"] > 0].max())
    assert list(by_year.index) == window and last == 2024, (
        f"README caveat 11 says no session pit_universe.py keeps from 2025 on "
        f"carries such an open; kept sessions fall in {list(by_year.index)} "
        f"and the last such open is in {last}")
    g = k.groupby(["year", "board"])[["bad", "rows"]].sum()
    yearly = (g["bad"] / g["rows"]).unstack("board")
    lower = [y for y in range(COVERAGE_START.year, last + 1)
             if not yearly.loc[y, "tpex"] > yearly.loc[y, "twse"]]
    assert not lower, (
        f"README caveat 11 says the TPEx share is the higher of the two in every "
        f"year to 2024; it is not in {lower}")
    return (f"open outside [min,max] on {bad:,}/{tot:,} rows "
            f"({100 * bad / tot:.2f} %) in {stocks} stocks, {gone:,} on "
            f"興櫃; kept sessions {share['kept']:.2%}, TPEx {share['tpex']:.2%} "
            f"against TWSE {share['twse']:.2%}, higher in every year to {last}; "
            f"{share[2011]:.2%} in 2011, {share[2024]:.2%} in 2024, none from "
            f"{last + 1}; close on 0"), tot


def test_taiwan_repull_returns_the_stored_prices():
    """README Provenance, "Re-pull, 2026-09-11": the vendor has revised no price.

    `ohlcv/` holds each row as `download.py` first pulled it, and nothing asks
    the vendor for the row again. `ohlcv_repull.parquet` is a second pull of 60
    stocks, so a revision since the first shows here as a row that differs.
    After the sponsor tier lapses, the parquet is the only second pull there is.

    The sample is drawn again rather than trusted: `ohlcv_repull.draw` must
    return the committed 60 from today's strata, so a hand-picked sample fails.

    The repair under "The gap that runs the other way" has since written the
    re-pulled counts into `ohlcv/`. The rows that came back higher are
    therefore read off `volume_repair.parquet`, which keeps their first counts.
    """
    from finmind_data.ohlcv_repull import draw, strata

    fresh = pd.read_parquet(REPO / "finmind_data/ohlcv_repull.parquet")
    fresh["date"] = pd.to_datetime(fresh["date"])
    ids = sorted(fresh["stock_id"].unique())
    anomalous, clean = strata()
    split = (len(anomalous), len(clean),
             len(set(ids) & set(anomalous)), len(set(ids) & set(clean)))
    assert split == (684, 1437, 40, 20), (
        f"README Provenance says the re-pull drew 40 of the 684 stocks whose "
        f"open is outside [min, max] on some traded row, and 20 of the 1,437 "
        f"with traded rows and no such open; (684-set, 1,437-set, drawn from "
        f"each) now reads {split}")
    assert sorted(draw(anomalous, clean)) == ids, (
        "README Provenance says the 60 were drawn at random, and "
        "ohlcv_repull.draw no longer returns the stocks in "
        "ohlcv_repull.parquet, so the committed sample is not the seeded draw")

    stored = pd.concat([_tree(REPO / f"finmind_data/ohlcv/{s}.parquet")
                        for s in ids], ignore_index=True)
    m = stored.merge(clip(fresh), on=["date", "stock_id"], how="outer",
                     suffixes=("_s", "_f"), indicator=True)
    one_side = int((m["_merge"] != "both").sum())
    assert one_side == 0, (
        f"README Provenance compares the re-pull with ohlcv/ row by row; "
        f"{one_side:,} in-window rows are in only one of the two")
    moved = {c: int(m[f"{c}_s"].ne(m[f"{c}_f"]).sum())
             for c in ["open", "max", "min", "close", "spread"]}
    assert len(m) == 159684 and not any(moved.values()), (
        f"README Provenance says all 159,684 of the 60 stocks' in-window rows "
        f"came back with the same open, max, min, close and spread; "
        f"{len(m):,} rows compare, and these moved: {moved}")

    counts = ["Trading_Volume", "Trading_money", "Trading_turnover"]
    still = {c: int(m[f"{c}_s"].ne(m[f"{c}_f"]).sum()) for c in counts}
    assert not any(still.values()), (
        f"README Provenance says the repair has since written the re-pulled "
        f"counts into ohlcv/; these still differ: {still}")
    log = pd.read_parquet(REPO / "finmind_data/volume_repair.parquet")
    log = log[log["tree"] == "ohlcv"].assign(date=lambda x: pd.to_datetime(x["date"]))
    hit = m.merge(log, on=["date", "stock_id"])
    higher = all(((hit[f"{c}_old"] < hit[f"{c}_f"])
                  & (hit[f"{c}_new"] == hit[f"{c}_f"])).all() for c in counts)
    sessions = pd.to_datetime(pd.read_parquet(
        REPO / "finmind_data/trading_sessions.parquet")["date"])
    saturdays = sessions[sessions.dt.dayofweek == 5]
    got = (len(hit), higher, bool(hit["date"].isin(saturdays).all()))
    assert got == (138, True, True), (
        f"README Provenance says 138 rows came back with a higher volume, "
        f"value and trade count, every one on a make-up Saturday; (rows the "
        f"repair replaced, first count lower and new count the re-pull's on "
        f"all three, all on a Saturday session) now reads {got}")
    return (f"{len(ids)} stocks, {len(m):,} rows: every field as stored; "
            f"{got[0]} came back with higher counts, all on Saturday sessions, "
            f"and the repair wrote them in"), len(m)


# ---- Taiwan: the biases the delisting table does *not* fix -----------------
def test_taiwan_delisting_table_has_no_reason():
    """README caveat 8: the delisting table dates the exit and says nothing else.

    The universe overlay built from this table removes survivorship bias from
    the price panel — the names are all present, and caveat 10 is where that
    stops. It cannot touch delisting-return bias either, because nothing here
    separates a bankruptcy from a merger and no column records what a holder
    was paid. This asserts the absence, so that a vendor backfill
    retires the caveat instead of leaving it to contradict the data quietly.
    """
    d = pd.read_parquet(REPO / "finmind_data/delisted_universe.parquet")
    cols = set(d.columns)
    assert cols == {"date", "stock_id", "stock_name", "year"}, (
        f"README caveat 8 says TaiwanStockDelisting carries date, stock_id, "
        f"stock_name and a derived year and nothing else; the file now has "
        f"{sorted(cols)}. If a reason or terminal-value column has appeared, "
        f"delisting returns are measurable and the caveat is obsolete"
    )
    return (f"delisting table = {sorted(cols)}; no reason, no terminal value",
            len(d))


def test_taiwan_delisting_sign_sample_is_preregistered():
    """The label draw is fixed before the labels exist, and this is what pins it.

    `delisting_sign.py` splits the delisted names into failures and payouts on
    the shape of the price path, at two cuts chosen while no label existed to
    tune them against. That ordering is the whole defence of the accuracy the
    labels will eventually report — a cut moved after seeing the answers gives
    an accuracy of the moving — and a committed constant does not enforce it,
    because editing `_DD_DISTRESS` once the labels are in would change the
    reported rate with nothing to say so.

    What makes it enforceable is that the draw is a function of the cuts: the
    strata bracket them, so a cut that moves moves which names were sampled.
    Re-drawing here and comparing against the committed `delisting_labels.csv`
    turns that edit into a failing assertion. The independence is in the CSV
    being frozen in git rather than in a second implementation of the draw —
    this recomputes, git remembers, and the two can disagree.
    """
    from finmind_data.delisting_sign import (
        _DD_DISTRESS, _DD_MERGER, features, draw_sample)

    f = features()
    exited = len(f)
    # This used to be three wider than the universe-side count, because
    # `features()` selected on a 4-digit code and so kept the in-window TDR
    # delistings the universe excludes as instruments, plus 6446, which changed
    # boards rather than exiting. It now selects on the universe itself, which
    # is where common stock is decided, and the two counts are the same set read
    # from two sides wherever their frames overlap: the 164 here are exactly the
    # `test_taiwan_adjusted_survivorship_hole` exits dated inside this frozen
    # frame, and its other 15 delisted after 2024-12-31. A divergence inside the
    # frame is a real disagreement rather than a documented offset.
    assert exited == 164, (
        f"README's delisting-sign section counts 164 in-window delistings that "
        f"exited the market; features() now returns {exited}"
    )

    drawn = set(draw_sample(f)["stock_id"])
    labels = pd.read_csv(REPO / "finmind_data/delisting_labels.csv",
                         dtype={"stock_id": str})
    committed = set(labels.loc[labels["purpose"] == "measure", "stock_id"])
    assert drawn == committed, (
        f"the accuracy sample is pre-registered, so redrawing it must return "
        f"the committed draw; {len(drawn - committed)} names are new and "
        f"{len(committed - drawn)} have dropped out "
        f"({sorted(drawn ^ committed)[:6]}). Either a cut, a stratum edge, the "
        f"seed or the population moved — if that was intended, the labels "
        f"collected against the old draw no longer measure this classifier"
    )

    allowed = {"merger", "distress", ""}
    got = set(labels["label"].fillna("").unique())
    assert got <= allowed, (
        f"delisting_labels.csv carries labels outside {sorted(allowed - {''})}: "
        f"{sorted(got - allowed)}. A third outcome means the two-sign split the "
        f"README describes is wrong, not that the label is"
    )
    n_lab = int((labels["label"].fillna("") != "").sum())
    return (f"{exited} market exits classified at cuts "
            f"{_DD_DISTRESS}/{_DD_MERGER}; {len(committed)} pre-registered "
            f"accuracy names and {int((labels['purpose'] == 'resolve').sum())} "
            f"to resolve, {n_lab} of {len(labels)} labelled",
            exited)


def test_taiwan_delisting_sign_accuracy():
    """README caveat 8: the price shape is right on 99 % of the names it decides.

    The claim the labels bought, and the two ways it can rot. It can rot at the
    labels — a CSV half filled in would quietly shrink the sample the rate is
    computed over — so every drawn name must carry one. And it can rot at the
    code, if a change to the feature or the cuts moves which names are decided;
    the rate is recomputed here from the module and the committed labels rather
    than restated, so it moves when they do.

    The single miss is asserted by name because it is what the README says the
    method gets wrong: a failure whose price never panicked. If a second one
    appears, or this one stops missing, the sentence describing the error mode
    is no longer the sentence the data supports.
    """
    from finmind_data.delisting_sign import accuracy, features

    f = features()
    labels = pd.read_csv(REPO / "finmind_data/delisting_labels.csv",
                         dtype={"stock_id": str})
    blank = labels.loc[labels["label"].fillna("") == "", "stock_id"]
    assert not len(blank), (
        f"README caveat 8 reports a rate over all {len(labels)} labelled "
        f"names; {len(blank)} are still blank ({sorted(blank)[:5]}), so the "
        f"rate would be computed over a smaller sample than the text claims"
    )

    r = accuracy(f, labels, verbose=False)
    assert r["n_scored"] == 15, (
        f"the rate rests on 15 labelled names that carry a verdict; "
        f"{r['n_scored']} do now. The estimate is weighted by stratum, so a "
        f"change in which names are decided changes what the 99 % is over"
    )
    assert r["missed"] == ["1613"], (
        f"README caveat 8 says the one miss is 1613 台一, a forced delisting "
        f"for non-filing that never collapsed; the misses are now "
        f"{r['missed']}. The described error mode no longer matches the data"
    )
    assert math.isclose(r["accuracy"], 0.987, abs_tol=0.005), (
        f"README caveat 8 claims the shape is right on 99 % of the names "
        f"carrying a verdict; the weighted rate is now {r['accuracy']:.1%}"
    )
    assert math.isclose(r["n_verdict"], 126, abs_tol=3), (
        f"README caveat 8 puts 127 names under a verdict (29 + 98); the "
        f"stratum-weighted estimate is {r['n_verdict']:.0f}, so the sample no "
        f"longer reconstructs the population it is weighted to"
    )
    assert math.isclose(r["n_ambiguous_merger"], 24, abs_tol=3), (
        f"README caveat 8 says ~24 of the ~38 undecided names are payouts; "
        f"the weighted estimate is now {r['n_ambiguous_merger']:.0f}"
    )
    return (f"{r['accuracy']:.1%} of {r['n_verdict']:.0f} verdicts correct "
            f"from {r['n_scored']} labelled, miss = {r['missed']}; "
            f"undecided band ~{r['n_ambiguous']:.0f}, "
            f"~{r['n_ambiguous_merger']:.0f} payouts",
            len(labels))


def test_taiwan_single_cut_is_registered_unscored():
    """The cut that would close the undecided band, pinned before its labels exist.

    The labelled band suggests one cut near 0.50 would decide most of what the
    two cuts leave open, but it suggests that on the 28 band names already
    looked up, so those 28 cannot also test it. The 9 that were never looked up
    can, they are the only ones that ever will, and their labels arrive as a
    byproduct of the payout work — an announcement names its own reason. Hence
    the ordering this check exists to freeze: the calls are committed while no
    label exists, and the gate is written down with them.

    Nine is one short of `_GATE_MIN_LABELS`, so the gate is unreadable on the
    band that exists: the re-registration on the corrected frame drew two of the
    old twelve into the measured sample and put three others outside the window,
    and the null it has to beat rose from 0.55 to 0.571 at the same time. The
    8420 label correction took it to 0.607 and the minimum to eleven, which
    moves the gate further out of reach rather than nearer — the null is a
    measurement on the label sheet, so a label that changes moves it, and the
    direction it moved is the one no amount of wanting could have chosen. That
    is reported rather than repaired — the repair is a wider held-out set, and
    lowering the bar to fit nine names is the move this check exists to stop.

    Editing `_DD_SINGLE` afterwards moves a call and fails here, which is what
    makes the registration a property of the repo rather than a claim about
    intent. The halt rule is held to the same standard for the same reason: it
    is the free alternative to reading the price path, it was read off the same
    20, and registering only the rule one hopes will win turns a comparison into
    a formality.

    `_GATE_MIN_LABELS` is re-derived rather than trusted, so a change to the
    null or to alpha cannot leave a minimum behind that no longer matches them.

    What this catches is an edit that changes a call, which is not the same as
    any edit: the held-out names' suspensions run 3, 14, 14 days and then past
    200, so `_LONG_SUSPENSION_DAYS` can be moved anywhere inside 14..217 without
    moving a held-out call. That is not the same as passing here, and the
    difference is the useful half — the labelled band's halt score holds only
    across 16..75, so a move outside that fails on caveat 8 while the
    pre-registration sees nothing at all. The blind spot is real and it is the
    wider range; what covers most of it is a check written for something else.
    Both bounds are recomputed here from the features rather than quoted, so the
    two docstrings stating them fail together when the halts underneath move.
    Asserting the constant itself would restate it; asserting how far it can
    travel is the part neither docstring can hold up on its own.
    """
    from finmind_data.delisting_sign import (
        _DD_SINGLE, _GATE_MIN_LABELS, _GATE_NULL, _LONG_SUSPENSION_DAYS,
        band_holdout, features, gate_threshold, single_cut_gate)

    f = features()
    labels = pd.read_csv(REPO / "finmind_data/delisting_labels.csv",
                         dtype={"stock_id": str})
    band = pd.read_csv(REPO / "finmind_data/delisting_band.csv",
                       dtype={"stock_id": str})
    fresh = band_holdout(f, labels)

    for col in ("call", "halt_call"):
        want = dict(zip(fresh["stock_id"], fresh[col]))
        got = dict(zip(band["stock_id"], band[col]))
        assert want == got, (
            f"delisting_band.csv is the pre-registration of the {col} rule: it "
            f"records what the rule said before any of these names was looked "
            f"up. Recomputing now disagrees on "
            f"{sorted(k for k in want.keys() | got.keys() if want.get(k) != got.get(k))}. "
            f"A rule edited after its labels arrive is fitted to them, and the "
            f"held-out set cannot be refilled — the band does not grow"
        )

    # `_GATE_NULL` is what a reader gets inside the band by naming its larger
    # class and never looking at a price, so it is a measurement, not a choice,
    # and this is the measurement. It reads only `delisting_labels.csv`, which
    # is full: labels bought from here on land in `delisting_band.csv` and
    # cannot drag the registered null along behind them.
    in_band = set(f.loc[f["sign"] == "ambiguous", "stock_id"])
    seen = labels[labels["stock_id"].isin(in_band)]["label"]
    assert math.isclose(_GATE_NULL, seen.value_counts().max() / len(seen),
                        abs_tol=0.005), (
        f"_GATE_NULL is the majority-class rate among the {len(seen)} band "
        f"names already labelled, which is now "
        f"{seen.value_counts().max() / len(seen):.3f} against the registered "
        f"{_GATE_NULL}. The bar 0.50 has to clear was set by that rate"
    )

    # Why the halt rule is registered rather than dismissed: on the labelled
    # band it is now five ahead of 0.50, having been a point behind on the
    # smaller frame. Neither figure is a held-out score.
    scored = f.merge(labels[["stock_id", "label"]], on="stock_id")
    scored = scored[scored["sign"] == "ambiguous"]
    dd50 = int(((scored["drawdown"] > _DD_SINGLE).map(
        {True: "merger", False: "distress"}) == scored["label"]).sum())
    halt = int(((scored["has_tail"] | scored["long_suspension"]).map(
        {True: "distress", False: "merger"}) == scored["label"]).sum())
    assert (dd50, halt) == (20, 25), (
        f"README caveat 8 says the halt rule is right 25 times on the 28 "
        f"labelled band names against 0.50's 20, which is why both are "
        f"registered; they now score {dd50} and {halt} of {len(scored)}"
    )

    # How far `_LONG_SUSPENSION_DAYS` can move before one of the two facts above
    # moves with it, derived by walking the cut outwards from the value in force
    # rather than quoted from the docstrings that state it. The two bounds differ
    # and the difference is the point: no held-out name has a tail, so the
    # pre-registration's bound on each side is just the nearest halt length,
    # while the labelled band has tails and pins the cut far tighter.
    held = fresh[["stock_id"]].merge(
        f[["stock_id", "suspension_days", "has_tail"]], on="stock_id")
    registered = dict(zip(fresh["stock_id"], fresh["halt_call"]))
    # Bounded by the data, so a feature set on which the cut changed nothing
    # would report the whole range instead of walking forever.
    ceiling = int(f["suspension_days"].max()) + 1

    def widest(holds):
        lo = hi = _LONG_SUSPENSION_DAYS
        assert holds(lo), "the cut in force is the one the two facts were read at"
        while lo > 0 and holds(lo - 1):
            lo -= 1
        while hi < ceiling and holds(hi + 1):
            hi += 1
        return lo, hi

    blind = widest(lambda cut: registered == {
        sid: "distress" if tail or days > cut else "merger"
        for sid, days, tail in zip(held["stock_id"], held["suspension_days"],
                                   held["has_tail"])})
    seen = widest(lambda cut: halt == int(
        ((scored["has_tail"] | (scored["suspension_days"] > cut)).map(
            {True: "distress", False: "merger"}) == scored["label"]).sum()))
    assert (blind, seen) == ((14, 217), (16, 75)), (
        f"both docstrings say a move inside 14..217 leaves every held-out call "
        f"where it is, and that the labelled band's halt score holds only across "
        f"16..75 — so the cut is pinned to the narrower of the two. The held-out "
        f"suspensions are now {sorted(held['suspension_days'])} and the two "
        f"ranges derive as {blind[0]}..{blind[1]} and {seen[0]}..{seen[1]}. The "
        f"sentences are what is wrong here, not the data"
    )

    assert gate_threshold(_GATE_MIN_LABELS) < _GATE_MIN_LABELS, (
        f"the gate needs at least {_GATE_MIN_LABELS} labels because below that "
        f"only a perfect score can clear the null; at {_GATE_MIN_LABELS} it now "
        f"needs {gate_threshold(_GATE_MIN_LABELS)} of {_GATE_MIN_LABELS}"
    )
    below = _GATE_MIN_LABELS - 1
    assert gate_threshold(below) in (None, below), (
        f"_GATE_MIN_LABELS is meant to be the smallest sample the gate can "
        f"clear without a perfect score, but {below} labels would already do "
        f"it at {gate_threshold(below)} correct. The null or alpha moved and "
        f"the minimum did not follow"
    )

    g = single_cut_gate(band)
    blank = int((band["label"].fillna("") == "").sum())
    assert g["n"] + blank == len(band), "every held-out name is labelled or not"
    if g["need"] is None:
        status = (f"gate unread, {_GATE_MIN_LABELS - g['n']} of "
                  f"{_GATE_MIN_LABELS} labels short")
    else:
        status = (f"{g['correct']}/{g['n']} correct vs {g['need']} needed, "
                  f"{g['trivial']} constant, {g['halt']} halt — "
                  f"{'adopt' if g['adopt'] else 'decline'}")
    return (f"single cut {_DD_SINGLE} and the halt rule registered on "
            f"{len(band)} held-out names, {g['n']} labelled; {status}",
            len(band))


def test_taiwan_substitute_error_splits_by_deal_form():
    """README caveat 8: what the last close costs, and how it splits by form.

    The substitute a study books for a delisted payout name is its last traded
    close, and the question is how wrong that is. The answer is not one number,
    it is two, and the split is the finding because it decides which lookups are
    worth doing: a cash consideration lands the last close within 1.5 % every
    time across twelve deals, and a share swap misses it by anything from
    −13.9 % to +24.8 % across eleven.

    The check used to assert a bias — every deal one way — and that claim was
    true of the deals it could see. It could see two swaps, because the other
    ten state a ratio in conventions that disagree row to row and the direction
    had to come off a filing. `swap_ratios.py` went and got eight of them from
    the acquirer's own announcement, and the first thing the wider sample did
    was refute the direction: 4944 兆遠 was paid 0.02 of a 環球晶 share against a
    last close it had just run 32 % into, and sits at −13.9 %. What survives is
    the cash half, and the width of the swap half is now a fact rather than a
    two-point estimate.

    The staleness account moves the same way. It was dismissed on the ground
    that a holding-company successor has no price to drift against, which was a
    property of *which* swaps could be priced and not of swaps: the deals with
    an odd ratio are third-party acquisitions whose acquirer has traded for
    years, and six of them are now in the sample with `overlap` in the
    thousands. The gap spreads over six values instead of two and orders with
    the residual at +0.85, the sign staleness predicts — asserted here as a
    measurement, because it was read after the sample was assembled and the
    cash side still runs the other way at −0.70. Two forms ordering against the
    gap in opposite directions is what the pooled correlation was reporting all
    along.

    Seven in-frame swaps are still unpriced and the gate is one company over:
    five had a buyer that was itself later bought, and MOPS refuses a
    deregistered acquirer in the same words it refuses the targets; two went
    into a holding company that did not exist before the conversion, so it filed
    nothing to read. Those seven are what would move these numbers next, and
    which of them are out is recorded in `mops_acquirer_refusals.csv` rather
    than described here.
    """
    import numpy as np
    from finmind_data.delisting_sign import (
        band_holdout, features, substitute_error, terminal_value)

    f = features()
    e = substitute_error(f)
    cash = e.loc[e["kind"] == "cash", "residual"]
    swap = e.loc[e["kind"] == "swap", "residual"]

    assert (cash > 0).all() and cash.max() < 0.015, (
        f"README caveat 8 says a cash consideration is above the last close "
        f"every time and within 1.5 % of it, which is why cash deals need no "
        f"filing pulled; {len(cash)} deals now run "
        f"{cash.min():+.2%} to {cash.max():+.2%}"
    )
    # The refutation, pinned so it cannot quietly revert. A one-directional
    # claim is what the two-swap sample supported and what ten swaps overturned,
    # and an assertion that only bounded the spread would pass either way.
    assert swap.min() < 0, (
        f"README caveat 8 says the swap substitute is two-sided — 4944 兆遠 at "
        f"−13.9 % is paid *less* than its last close, which is what retired the "
        f"claim that the last close understates every deal. The worst swap is "
        f"now {swap.min():+.2%}, so either that row has left the sample or the "
        f"caveat's own history is wrong"
    )
    assert math.isclose(swap.min(), -0.139, abs_tol=0.01) and \
        math.isclose(swap.max(), 0.248, abs_tol=0.01), (
        f"README caveat 8 puts the swap residuals from −13.9 % to +24.8 % on "
        f"{len(swap)} deals; they now run {swap.min():+.1%} to {swap.max():+.1%}"
    )
    assert math.isclose(swap.median(), 0.099, abs_tol=0.02), (
        f"README caveat 8 puts the median swap residual near +10 %; it is now "
        f"{swap.median():+.1%}"
    )
    # The split is the finding, not either level: it is what decides that a swap
    # is worth a filing and a cash deal is not. Pinned on the typical swap
    # against the worst cash deal, in absolute value, because the swap side is
    # no longer signed.
    assert swap.abs().median() > 5 * cash.max(), (
        f"README caveat 8 rests on cash and swap errors being an order of "
        f"magnitude apart — {len(cash)} cash deals at most {cash.max():+.2%} "
        f"against a typical swap miss of {swap.abs().median():.1%}. They are "
        f"now within a factor of {swap.abs().median() / cash.max():.1f}, so the "
        f"lookup priority the caveat sets no longer follows from the measurement"
    )

    # Staleness, now that there is something to read it on. Within-cluster
    # ordering is the whole claim, so the two forms are asked separately and
    # neither is pooled with the other.
    rho_cash = float(e[e["kind"] == "cash"][["gap", "residual"]]
                     .corr(method="spearman").iloc[0, 1])
    rho_swap = float(e[e["kind"] == "swap"][["gap", "residual"]]
                     .corr(method="spearman").iloc[0, 1])
    assert rho_cash < -0.5 < 0.5 < rho_swap, (
        f"README caveat 8 says the two deal forms order against the gap in "
        f"opposite directions — cash at −0.70, where a close nine days old has "
        f"drifted less rather than more, and swaps at +0.85, the sign staleness "
        f"predicts. They are now {rho_cash:+.2f} and {rho_swap:+.2f}, so the "
        f"caveat's account of what the pooled figure was reporting is wrong"
    )
    # The two clusters are orders of magnitude apart on `overlap`, not adjacent,
    # so the cut between them is not a judgement: a third-party acquirer has
    # traded for years and a new holding company for none. 5854's single session
    # is 5880's pre-listing row of 2011-04-14, one of the twelve
    # `test_taiwan_pre_listing_sessions_are_one_vendor_day` pins, and it is why
    # the cut is drawn above a handful rather than above zero.
    acq = e[(e["kind"] == "swap") & (e["overlap"] > 100)]
    thin = e[(e["kind"] == "swap") & (e["overlap"] <= 100)]
    assert len(acq) == 7 and acq["overlap"].min() > 1000 and \
        thin["overlap"].max() <= 1, (
        f"README caveat 8 says the staleness account became testable because "
        f"reading the ratios off the filings put seven third-party acquisitions "
        f"into the sample, each with an acquirer that had traded for years "
        f"before the target left, against holding companies that had traded "
        f"for none. {len(acq)} now clear 100 sessions (thinnest "
        f"{acq['overlap'].min() if len(acq) else 0}) and the rest reach "
        f"{thin['overlap'].max()}"
    )
    assert e.loc[e["kind"] == "swap", "gap"].nunique() >= 5, (
        f"README caveat 8 says the gap spreads over six values across the "
        f"swaps where it took two before, which is what lets it be read at "
        f"all; it now takes {e.loc[e['kind'] == 'swap', 'gap'].nunique()}"
    )

    sign = f.set_index("stock_id")["sign"]
    in_band = int((e.loc[e["kind"] == "swap", "stock_id"].map(sign)
                   == "ambiguous").sum())
    assert in_band == 7, (
        f"README caveat 8 says seven of the eleven swaps are band names, so the "
        f"spread is measured mostly on names the cuts do not decide rather "
        f"than on classifier-confirmed payouts; {in_band} are now undecided"
    )

    t = terminal_value(f)
    undecided = t[t["basis"] == "undecided"]
    assert undecided["terminal"].isna().all(), (
        f"the undecided band has no sign, so it can carry no terminal value; "
        f"{int(undecided['terminal'].notna().sum())} names have been given one. "
        f"A number there is a guess at the direction, not at the size"
    )
    assert t.loc[t["basis"] != "undecided", "terminal"].notna().all(), (
        "README caveat 8 says the undecided band is the only missing terminal "
        "value, because that is what makes `basis` tell a caller which of two "
        "different jobs would supply the number; a second basis is now NaN too"
    )
    assert (t.loc[t["basis"] == "failed", "terminal"] == 0).all(), (
        "a failed delisting books zero"
    )
    # …by default, and the default is the rule rather than the arithmetic. A
    # backtest that liquidates a failure at some fraction of the last print
    # passes the fraction it does not recover, and gets the same 41 names on a
    # different basis — never a different set, which would make the haircut a
    # reclassification.
    for h in (0.0, 0.8):
        cut = terminal_value(f, failed_haircut=h)
        assert cut["basis"].equals(t["basis"]), (
            f"failed_haircut={h} moved a name between bases; it scales what a "
            f"failure returns and decides nothing about which names failed")
        booked = cut.loc[cut["basis"] == "failed", "terminal"]
        close = cut.loc[cut["basis"] == "failed", "last_close"]
        assert np.allclose(booked, close * (1 - h)), (
            f"failed_haircut={h} books {booked.sum():.2f} against the "
            f"{(close * (1 - h)).sum():.2f} its own definition gives — the "
            f"fraction of the last close a failure does not return")
        assert (cut.loc[cut["basis"] != "failed", "terminal"].fillna(-1)
                == t.loc[t["basis"] != "failed", "terminal"].fillna(-1)).all(), (
            f"failed_haircut={h} moved a value outside the failed basis, where "
            f"a consideration is what was paid and a substitute is the last "
            f"close; neither is a modelling choice")
    try:
        terminal_value(f, failed_haircut=1.5)
        raise AssertionError(
            "a haircut above 1.0 was accepted; it is the fraction of the last "
            "close a failure does not return, so it cannot exceed all of it")
    except ValueError:
        pass
    assert (t.loc[t["basis"] == "substituted", "terminal"]
            == t.loc[t["basis"] == "substituted", "last_close"]).all(), (
        "a payout books its last close, which is the substitute being measured"
    )
    # These four were quoted in the README off a run whose `failed` and
    # `substituted` were a name apart from what the code returns, and survived
    # because they were only ever printed in this check's message. Asserted now.
    basis = t["basis"].value_counts().to_dict()
    assert basis == {"substituted": 93, "failed": 41, "undecided": 7,
                     "consideration": 23}, (
        f"README caveat 8 says a study meets 41 failed, 23 consideration, 93 "
        f"substituted and 7 undecided; it now meets {basis}. Two movements "
        f"produce those, and only two: recording a consideration takes a name "
        f"from substituted to consideration, and reading a held-out band name's "
        f"filing takes it from undecided to substituted"
    )
    paid = e.set_index("stock_id")["paid"]
    booked = t[t["basis"] == "consideration"].set_index("stock_id")["terminal"]
    assert booked.to_dict() == paid.to_dict(), (
        f"README caveat 8 says a name whose consideration is recorded books "
        f"that consideration rather than the substitute it is measured "
        f"against; {sorted(set(paid.index) ^ set(booked.index))} disagree"
    )

    # A label outranks the shape, so the undecided rows are exactly the band
    # names nobody has looked up — the same nine the single cut is registered
    # against. Read off the label file rather than off a count, because a count
    # would still pass if the nine were a different nine.
    labels = pd.read_csv(Path(__file__).with_name("delisting_labels.csv"),
                         dtype={"stock_id": str})
    # Both label files, because settlement reads both. The band file's `label`
    # fills in as a held-out name's filing gets read for some other reason, and
    # a check that read only the drawn sample would pass while `terminal_value`
    # booked those names off a column no assertion had opened.
    band_file = pd.read_csv(Path(__file__).with_name("delisting_band.csv"),
                            dtype={"stock_id": str})
    hand = pd.concat([labels[["stock_id", "label"]],
                      band_file[["stock_id", "label"]]], ignore_index=True)
    labels = labels[labels["label"].fillna("") != ""]
    hand = hand[hand["label"].fillna("") != ""]
    expected = {"distress": "failed", "merger": "substituted"}
    off_label = t.merge(hand, on="stock_id")
    wrong = off_label[off_label["basis"].replace("consideration", "substituted")
                      != off_label["label"].map(expected)]
    assert not len(wrong), (
        f"README caveat 8 says a hand-read filing outranks the price shape "
        f"wherever one exists; {wrong['stock_id'].tolist()} book against their "
        f"own label instead"
    )
    band = int((f["sign"] == "ambiguous").sum())
    assert (band, len(undecided)) == (37, 7), (
        f"README caveat 8 says the labels empty 28 of the 37 band names and "
        f"two more have since been read, leaving 7 without a terminal value; "
        f"the cuts now leave {band} open and {len(undecided)} survive the "
        f"labels. An emptied label file lands here"
    )
    # The frozen nine do not change — the registration is what fixes them, and
    # `band_holdout` is passed the drawn sample alone so that filling a band
    # label cannot shrink the set the rules were registered against. What
    # changes is how many still owe a value, and the two are related by
    # subtraction rather than by a count either side could drift in.
    frozen = set(band_holdout(f, labels)["stock_id"])
    read = set(band_file.loc[band_file["label"].fillna("") != "", "stock_id"])
    assert len(frozen) == 9 and read <= frozen, (
        f"README caveat 8 says the single cut is registered against nine band "
        f"names and that their labels arrive from filings read for other "
        f"reasons; the holdout is now {len(frozen)} and {sorted(read - frozen)} "
        f"carry a band label without being in it"
    )
    assert set(undecided["stock_id"]) == frozen - read, (
        f"README caveat 8 says the names left without a terminal value are the "
        f"registered band less the ones whose filings have been read; "
        f"{sorted(set(undecided['stock_id']) ^ (frozen - read))} are on one "
        f"side and not the other, so the band a study is told to resolve is no "
        f"longer the band `delisting_band.csv` froze"
    )
    counts = t["basis"].value_counts().to_dict()
    return (f"last close off by {cash.median():+.1%} on {len(cash)} cash deals, "
            f"all one way and inside 1.5 %, against {swap.min():+.1%}.."
            f"{swap.max():+.1%} on {len(swap)} swaps; gap orders "
            f"{rho_cash:+.2f} cash / {rho_swap:+.2f} swap; terminal basis "
            f"{counts}",
            len(e))


def test_taiwan_cash_payouts_land_outside_the_band():
    """README caveat 8: the cash-deal clustering reading, and its refutation.

    This check was written around a zero. On the 18 payouts labelled before the
    2026-08-17 re-registration, nine of nine stated forms inside the band were
    share exchanges and no cash deal had ever been labelled there, which invited
    the reading that a conversion's discount is what drags a payout into the
    band. The reading came with a mechanism: a cash offer at a premium stops
    near its own high, so it should land above the band's upper cut. The check
    was written so that a cash deal arriving in the band would be the finding
    rather than a regression.

    It arrived. The corrected frame and the re-registered draw take the stated
    forms to 26, and four of the nine cash deals sit inside the band — 4965,
    8913, 6211 and 8266, at drawdowns of 0.56 to 0.63. The mechanism is what was
    wrong: the drawdown is measured against a trailing-year peak, and a cash
    offer at a premium to the *recent* price is routinely far below the price a
    year earlier. 商店街市集 was bought in at NT$44 after falling most of the way
    there from its own high; the offer was a premium and the drawdown was 0.56.

    So the zero is gone and the association with it: 12 of the 16 stated forms in
    the band are exchanges against 17 of 26 overall, and Fisher exact two-sided
    returns 0.234. What this now asserts is the refutation, so that a later
    re-registration cannot quietly restore the original reading.

    `form` is blank wherever the source names a merger without saying what was
    paid, and one name sits there: 8420's 股份轉換 with 明安國際 is announced
    without a consideration, and 股份轉換 permits shares, cash or other property
    alike. It is counted out of the stated-form table rather than read into it,
    because reading one in would invent the fact the column exists to count.
    """
    from finmind_data.delisting_sign import _DD_MERGER, features

    f = features()
    labels = pd.read_csv(Path(__file__).with_name("delisting_labels.csv"),
                         dtype={"stock_id": str})
    labels = labels[labels["label"].fillna("") != ""]
    m = labels[labels["label"] == "merger"].drop(columns=["sign", "drawdown"])
    m = m.merge(f[["stock_id", "sign", "drawdown"]], on="stock_id")
    assert not len(labels[(labels["label"] != "merger")
                          & (labels["form"].fillna("") != "")]), (
        "`form` is what a payout paid, so a failure cannot carry one"
    )

    # The live test first. A new label changes the counts too, so pinning those
    # ahead of it would answer the arrival of a cash deal in the band with a
    # message about column totals — the wrong sentence for the event this check
    # exists to catch.
    form = m["form"].fillna("unstated")
    in_band = m["sign"] == "ambiguous"
    cash_in_band = sorted(m.loc[in_band & (form == "cash"), "stock_id"])
    assert cash_in_band == ["4965", "6211", "8266", "8913"], (
        f"README caveat 8 records four labelled cash deals inside the band, "
        f"which is what refutes the clustering reading the earlier label set "
        f"supported; the band now holds {cash_in_band}. If this went back to "
        f"empty the refutation went with it and the paragraph has to be re-read"
    )
    assert m.loc[form == "cash", "drawdown"].min() < _DD_MERGER, (
        f"README caveat 8 retired the mechanical account — a cash offer at a "
        f"premium was said to stop near its own high, above the band's upper "
        f"cut of {_DD_MERGER}, and four cash deals sit below it because the "
        f"drawdown is measured against a trailing-year peak. The lowest "
        f"labelled cash deal is now at "
        f"{m.loc[form == 'cash', 'drawdown'].min():.3f}"
    )

    counts = form.value_counts().to_dict()
    assert (len(m), counts.get("swap"), counts.get("cash"),
            counts.get("unstated")) == (27, 17, 9, 1), (
        f"README caveat 8 says 27 labelled payouts in the frame split 17 share "
        f"exchanges, 9 cash and 8420 unstated; the label file now gives "
        f"{len(m)} and {counts}. A label arriving for one of the nine "
        f"held-out names lands here, and the paragraph is what has to be "
        f"re-read against the new table"
    )

    # Fisher exact on the stated forms, two-sided: sum every table at least as
    # extreme as the observed one. The single-term shortcut the old zero allowed
    # is gone with the zero.
    band_n = int((in_band & (form != "unstated")).sum())
    swap_n, stated_n = counts["swap"], counts["swap"] + counts["cash"]
    band_swap = int((in_band & (form == "swap")).sum())

    def _hyper(k):
        return (math.comb(swap_n, k) * math.comb(stated_n - swap_n, band_n - k)
                / math.comb(stated_n, band_n))

    obs = _hyper(band_swap)
    p = sum(_hyper(k) for k in range(max(0, band_n - (stated_n - swap_n)),
                                     min(band_n, swap_n) + 1)
            if _hyper(k) <= obs + 1e-12)
    assert math.isclose(p, 0.234, abs_tol=5e-4), (
        f"README caveat 8 reports Fisher exact two-sided at 0.234 on the "
        f"form-by-band table and reads it as no association; the exact test now "
        f"returns {p:.3f}"
    )
    return (f"{counts['cash']} labelled cash payouts, {len(cash_in_band)} of "
            f"them inside the band's {_DD_MERGER} cut; {band_swap} of {band_n} "
            f"stated forms inside it are share exchanges against "
            f"{swap_n}/{stated_n} overall, p={p:.3f}",
            len(m))


# Where `create_time` goes from a trickle to the rule (README caveat 9). Not a
# tuned cut: the reporting month before the frontier carries the stamp on under
# a hundredth of its rows and every month after on essentially all of them, so
# any value between the two clusters names the same month.
_STAMP_SPLIT = 0.5


def test_taiwan_fundamentals_are_fiscal_dated():
    """README caveat 9: fiscal period end, no announcement date.

    A look-ahead limit rather than a survivorship one, and invisible in the
    schema unless someone states what `date` means. `dividend/` carries
    `AnnouncementDate`, which is what makes the others' silence a gap rather
    than a convention of the source.
    """
    fin = _tree(REPO / "finmind_data/fin_is/2330.parquet")
    ends = set(pd.to_datetime(fin["date"]).dt.strftime("%m-%d"))
    assert ends <= {"03-31", "06-30", "09-30", "12-31"}, (
        f"README caveat 9 says fin_is dates are fiscal quarter ends; 2330 also "
        f"carries {sorted(ends - {'03-31', '06-30', '09-30', '12-31'})}"
    )
    for dset in ("fin_is", "fin_bs", "fin_cf"):
        c = set(pd.read_parquet(REPO / f"finmind_data/{dset}/2330.parquet").columns)
        assert not {"AnnouncementDate", "create_time", "announcement_date"} & c, (
            f"README caveat 9 says {dset}/ carries no announcement date; it now "
            f"has one, so the look-ahead caveat is obsolete and signals built "
            f"on it can be aligned point-in-time"
        )

    # `create_time` carries no announcement date for anything this package
    # answers about, and where its values fall is what rules it out. Read
    # unclipped on purpose: the claim is about the stamps landing outside the
    # window, and a clipped read would find none and asserting that zero would
    # verify nothing.
    #
    # The stamps are two different things either side of the window. On the
    # 2005-2010 backfill the lag from a period to its stamp runs to twenty
    # years, which is an ingest time for rows the vendor rewrote rather than a
    # release date. On the 2026 rows it is about ten days, which is what a
    # release date looks like under Taiwan's monthly-revenue deadline — so the
    # column is not uniformly meaningless, it is uniformly absent here. Neither
    # kind reaches the window, and that is the caveat: a signal built on
    # in-window monthly revenue has no announcement date to align to.
    tot = stamped = inwin_stamped = 0
    backfill_lag = []
    months = []
    for p in sorted(glob.glob(str(REPO / "finmind_data/month_rev/*.parquet"))):
        m = pd.read_parquet(p)
        if not len(m):
            continue
        tot += len(m)
        st = m["create_time"].astype(str).str.strip()
        d = pd.to_datetime(m["date"], errors="coerce")
        hit = st != ""
        stamped += int(hit.sum())
        inw = d.between(COVERAGE_START, COVERAGE_END)
        inwin_stamped += int((hit & inw).sum())
        months.append(pd.DataFrame({"date": d[inw], "hit": hit[inw]}))
        back = hit & (d < COVERAGE_START)
        if back.any():
            lag = (pd.to_datetime(st[back], errors="coerce") - d[back]).dt.days
            backfill_lag += list(lag.dropna())
    per = pd.concat(months, ignore_index=True).groupby("date")["hit"].mean()
    assert stamped, (
        "README caveat 9 argues from where create_time's values fall that it is "
        "not a release date for this window; no row in the tree carries one at "
        "all, so the argument has no population and the caveat is unsupported "
        "rather than confirmed"
    )
    # The frontier the caveat now turns on, read off the column rather than
    # written down: the reporting month from which the vendor stamps at
    # publication. Split at a half because the two sides are not near it — the
    # month before is stamped on well under a tenth of its rows and every month
    # after on essentially all of them — so any cut between the clusters names
    # the same month and this one is not a tuned boundary.
    above = per.index[per > _STAMP_SPLIT]
    assert len(above), (
        f"README caveat 9 says the vendor stamps monthly revenue at publication "
        f"from a reporting month inside the window; no month has {_STAMP_SPLIT:.0%} "
        f"of its rows stamped, so the point-in-time stretch the caveat offers "
        f"does not exist"
    )
    frontier = above.min()
    stragglers = sorted(per.index[(per.index > frontier) & (per <= _STAMP_SPLIT)])
    assert not stragglers, (
        f"README caveat 9 dates the point-in-time stretch from {frontier.date()} "
        f"onward, which requires every later reporting month to be stamped; "
        f"{len(stragglers)} are not ({[str(d.date()) for d in stragglers[:4]]}), "
        f"so the stretch is not contiguous and a study aligning on the stamp "
        f"would drop those months silently"
    )
    assert backfill_lag and min(backfill_lag) > 365, (
        f"README caveat 9 reads the pre-window stamps as the vendor's ingest "
        f"time because they post-date their own periods by years; the smallest "
        f"such lag is now {min(backfill_lag) if backfill_lag else None} days, "
        f"which is a release date's distance, not an ingest one"
    )

    div = _tree(REPO / "finmind_data/dividend/1101.parquet")
    assert "AnnouncementDate" in div.columns, (
        "README caveat 9 names dividend/ as the one dataset carrying "
        "AnnouncementDate; it no longer does"
    )
    return (f"fin_* dated on quarter ends with no announcement column; "
            f"month_rev create_time on {stamped:,} of {tot:,} rows, "
            f"{inwin_stamped:,} in-window and stamped at publication from "
            f"{frontier.date()} on, pre-window lag from {min(backfill_lag):,}d; "
            f"dividend has it"), tot


# ---- Taiwan: the statement trees are survivorship-incomplete ---------------
# Measured, not chosen: the latest delisting date whose income statement the
# vendor no longer serves. Every name that left after it has one, so the value
# is a property of the pull rather than a cut this file picked, and a refresh
# that moves it is the evidence that the retention rolls forward with the pull
# date (README caveat 10).
_STATEMENT_BREAK = pd.Timestamp("2020-11-20")


def test_taiwan_statement_trees_drop_old_delistings():
    """README caveat 10: prices keep the delisted names, statements do not.

    The universe overlay and the rebuild together make the *price* panel
    survivorship-complete, and a reader who stops there will assume the whole
    package is. It is not: the endpoints serving company filings answer for a
    company that still reports, so a name that failed a decade ago has prices
    and no income statement, and the missing names are exactly the failures a
    fundamentals study must not drop.

    Every number below is checked the way the caveat states it. The gap is
    absence at the source rather than clipping, so the file is read unclipped
    too and asserted empty. The break is one-sided, so the assertion is on the
    later side being whole rather than on a rate. And the contrast that
    localises it to the filing endpoints — the exchange's own daily series
    keeping the same names — is read from `per_pbr/`, which no part of the
    statement path touches.
    """
    u = pd.read_parquet(REPO / "finmind_data/universe.parquet")
    d = pd.read_parquet(REPO / "finmind_data/delisted_universe.parquet")
    uid = set(u["stock_id"].astype(str))
    d = d.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["sid"] = d["stock_id"].astype(str)
    inwin = d[(d["date"] >= COVERAGE_START) & (d["date"] <= COVERAGE_END)
              & d["sid"].isin(uid)]
    delist = dict(zip(inwin["sid"], inwin["date"]))
    assert len(delist) == 179, (
        f"README caveat 10 reports the statement coverage against 179 commons "
        f"delisted inside the window; the table now dates {len(delist)}"
    )

    have, empty_file, stale_only, last_row = [], 0, [], {}
    for sid in sorted(delist):
        whole = pd.read_parquet(REPO / f"finmind_data/fin_is/{sid}.parquet")
        clipped = _tree(REPO / f"finmind_data/fin_is/{sid}.parquet")
        if len(clipped):
            have.append(sid)
            last_row[sid] = pd.to_datetime(whole["date"]).max()
        elif len(whole):
            stale_only.append(sid)
        else:
            empty_file += 1
    assert len(have) == 78, (
        f"README caveat 10 says fin_is/ carries rows for 78 of the 179; it "
        f"now carries them for {len(have)}"
    )
    assert not stale_only, (
        f"README caveat 10 says the missing files are empty rather than "
        f"out-of-window, which is what makes this absence at the source and "
        f"not a window artifact; {len(stale_only)} now hold rows the window "
        f"excludes, so the caveat's argument no longer holds: {stale_only[:5]}"
    )
    assert empty_file == 101, (
        f"README caveat 10 pins 101 empty fin_is files; there are {empty_file}"
    )

    after = [s for s in delist if delist[s] > _STATEMENT_BREAK]
    before = [s for s in delist if delist[s] <= _STATEMENT_BREAK]
    kept_after = [s for s in after if s in last_row]
    kept_before = [s for s in before if s in last_row]
    assert len(after) == 62 and len(kept_after) == 62, (
        f"README caveat 10 rests on the break being one-sided — all "
        f"{len(after)} names delisted after {_STATEMENT_BREAK.date()} carry a "
        f"statement — and {len(after) - len(kept_after)} no longer do, so the "
        f"date is not where the retention ends any more"
    )
    assert (len(before), len(kept_before)) == (117, 16), (
        f"README caveat 10 says 16 of the 117 delisted on or before "
        f"{_STATEMENT_BREAK.date()} keep a statement; now "
        f"{len(kept_before)} of {len(before)}"
    )

    # The cut is a year and does no work: the names that kept filing after
    # leaving the board run 2,071 days past their delisting at the shortest,
    # and the ones that stopped run 48 days past it at the longest.
    still_filing = [s for s in kept_before
                    if (last_row[s] - delist[s]).days > 365]
    assert len(still_filing) == 12, (
        f"README caveat 10 explains the 16 as the vendor keeping the company "
        f"rather than the listing — 12 of them still filing long after they "
        f"left the board — and {len(still_filing)} now are, so the "
        f"explanation has lost the evidence it was read off"
    )

    daily = sum(bool(len(_tree(REPO / f"finmind_data/per_pbr/{s}.parquet")))
                for s in delist)
    assert daily == 177, (
        f"README caveat 10 localises the loss to the filing endpoints by "
        f"contrast with the exchange's daily series, which covers 177 of the "
        f"179; per_pbr/ now covers {daily}, and without the contrast the loss "
        f"could be a property of the delisted names themselves"
    )
    return (f"fin_is/ covers {len(have)}/{len(delist)} in-window delistings, "
            f"{empty_file} files empty at the source; all {len(kept_after)} "
            f"delisted after {_STATEMENT_BREAK.date()} kept against "
            f"{len(kept_before)}/{len(before)} before it ({len(still_filing)} "
            f"still filing); per_pbr/ keeps {daily}"), len(delist)


# ---- Taiwan: the holes with no event are checked against more than one source
def test_taiwan_no_event_holes_are_event_free_in_three_sources():
    """README, "The survivorship hole": none of the 17 has an event anywhere.

    `adjust.py` decides a hole has no corporate action from `div_result/` and
    `capital_reduction.parquet` — the two chains it would build a factor from —
    so re-reading those two would only restate the code. The claim the README
    makes is wider: the same names have no declaration in `dividend/` and no row
    in `exright_reference.parquet` either, and those two are independent of the
    factor path. A name with a dividend nobody filed a reference price for is a
    flat factor that should not be flat, and it is the one way a `rebuilt_noevent`
    stock can be wrong without any code here disagreeing with itself.

    The hole set is derived the way the decomposition derives it — raw prices in
    the window, no adjusted row in it — rather than listed, so a name that joins
    the hole arrives in this check too.
    """
    holes = []
    for sid in _panel_ids():
        raw = REPO / f"finmind_data/ohlcv/{sid}.parquet"
        if not raw.exists() or not len(_tree(raw)):
            continue
        if not len(_tree(REPO / f"finmind_data/price_adj/{sid}.parquet")):
            holes.append(sid)
    assert len(holes) == 54, (
        f"README counts 54 stocks with raw prices and no adjusted series in the "
        f"window; this tree has {len(holes)}. The split below is over that set"
    )

    cr = _tree(REPO / "finmind_data/capital_reduction.parquet")
    cr_ids = set(cr["stock_id"].astype(str))
    er = _tree(REPO / "finmind_data/exright_reference.parquet")
    er_ids = set(er["stock_id"].astype(str))

    noevent, offending = [], {}
    for sid in holes:
        dr = _tree(REPO / f"finmind_data/div_result/{sid}.parquet")
        if len(dr) or sid in cr_ids:
            continue                       # the factor path found an event
        noevent.append(sid)
        other = []
        dv = REPO / f"finmind_data/dividend/{sid}.parquet"
        if dv.exists() and len(_tree(dv)):
            other.append("dividend")
        if sid in er_ids:
            other.append("exright_reference")
        if other:
            offending[sid] = other

    assert len(noevent) == 17, (
        f"README splits the 54 holes into 37 with a factor chain and 17 with no "
        f"corporate action in window; the two event chains the factor is built "
        f"from leave {len(noevent)} without one"
    )
    assert not offending, (
        f"README says none of the 17 no-event holes has a declaration in "
        f"dividend/ or a row in exright_reference.parquet; {offending} does. A "
        f"distribution with no reference price behind it is a factor left flat "
        f"across an event that happened, and nothing in the factor path can see "
        f"it — both sources here are outside that path"
    )
    return (f"{len(noevent)} of {len(holes)} holes carry no event in "
            f"div_result/ or capital_reduction, and none of them in dividend/ "
            f"or exright_reference either"), len(holes)


# ---- consolidate_capred delivered artifact ---------------------------------
def test_capital_reduction_artifact_exists():
    fp = REPO / "finmind_data/capital_reduction.parquet"
    assert fp.exists(), "capital_reduction.parquet documented as delivered but missing"
    # Read it rather than stat it: a consolidation that wrote an empty frame
    # delivers the path and nothing else, and the runner's population guard is
    # what turns that into a failure.
    n = len(pd.read_parquet(fp))
    return f"capital_reduction.parquet present, {n:,} rows", n


# ---- Taiwan: ohlcv/ is raw, which is why price_adj/ is bought --------------
def test_taiwan_ohlcv_is_raw():
    """README, `ohlcv/` schema: the closes reflect no corporate action.

    The exchange publishes `before_price` per 除權息 event — the cum-session
    close it repriced from. If `ohlcv/close` on the session before the event
    equals it, the raw series carries the pre-event price and has had nothing
    removed. This is the premise the whole adjusted layer rests on: were
    `ohlcv/` already adjusted, joining `price_adj/` onto it would double-count.
    """
    import numpy as np

    frames = []
    for p in sorted(glob.glob(str(REPO / "finmind_data/div_result/*.parquet"))):
        d = _tree(p)
        if len(d):
            frames.append(d[["stock_id", "date", "before_price"]])
    assert frames, "div_result/ is empty — nothing to check ohlcv/ against"
    ev = pd.concat(frames, ignore_index=True)
    ev["stock_id"] = ev["stock_id"].astype(str)
    ev["date"] = pd.to_datetime(ev["date"])
    ev = ev[ev["before_price"] > 0]

    hit = tot = 0
    for sid, g in ev.groupby("stock_id"):
        fp = REPO / f"finmind_data/ohlcv/{sid}.parquet"
        if not fp.exists():
            continue
        px = _tree(fp)
        if not len(px):
            continue
        px = px.sort_values("date")
        dt, cl = px["date"].to_numpy(), px["close"].to_numpy(dtype=float)
        # -1 = the cum session, the last one before the event repriced it.
        i = np.searchsorted(dt, g["date"].to_numpy(), "left") - 1
        ok = i >= 0
        # atol is the exchange's own published precision: before_price carries
        # two decimals, so agreement there is agreement at full precision.
        good = np.isclose(cl[np.clip(i, 0, len(cl) - 1)],
                          g["before_price"].to_numpy(dtype=float),
                          atol=1e-2, rtol=0)
        hit += int((good & ok).sum())
        tot += int(ok.sum())

    frac = hit / max(tot, 1)
    assert frac >= 0.995, (
        f"README calls ohlcv/close 'raw/unadjusted' on the strength of it "
        f"matching the exchange's pre-event before_price on 99.83 % of 除權息 "
        f"events; it now matches {100 * frac:.2f} % of {tot:,}. A fall here "
        f"means the raw series is no longer raw, and price_adj/ would "
        f"double-count against it"
    )
    return (f"ohlcv/ is raw: {hit:,}/{tot:,} = {100 * frac:.2f} % vs "
            f"before_price"), tot


# ---- Taiwan: what the bought adjusted series is, and what it does not mark --
# The one day the vendor stamped a session onto codes that had not begun
# trading. Named rather than derived: the silence that follows those rows runs
# unbroken from a week to fourteen months, so no gap threshold separates them
# from a suspension, and the date is the only thing all of them share.
_PRE_LISTING_DAY = "2011-04-14"

# Every other series in the panel waits a median of one day between its first
# two sessions and exactly one waits longer than a month. A month is clear of
# both, and of the seven-day minimum inside the cohort.
_NORMAL_START_GAP_DAYS = 31


def test_taiwan_pre_listing_sessions_are_one_vendor_day():
    """README caveat 6: twelve series open on one day and then stop for months.

    A series that trades once and does not trade again for a year has not
    started trading, but no single row says so — the OHLCV is internally
    consistent, and `spread` reads −1.00 on all twelve, which on one row is an
    ordinary one-dollar fall and is that on 1.2 % of the panel. Twelve of twelve
    is not chance, but it is a property of the cohort rather than a test a row
    can be put to, so what this reads is the date they share and the silence
    after it.

    They are pinned rather than dropped because no vendor field says where a
    listing begins: `TaiwanStockInfo.date` is the day a stock left a market and
    `IPOYear` belongs to the US table, so a truncation rule would have to infer
    the boundary from the gap — and inferring it would reach the 56 series whose
    largest gap exceeds 180 days, 50 of them mid-series halts the name trades
    out of. A thirteenth series, or a second such day, fails here instead of
    arriving in a return.
    """
    import pyarrow.parquet as pq

    files = sorted((REPO / "finmind_data/ohlcv").glob("*.parquet"))
    if not files:
        raise Skipped("ohlcv/ not built — run `download.py`")
    day = pd.Timestamp(_PRE_LISTING_DAY)
    cohort, strays, empty = {}, {}, []
    for path in files:
        if "date" not in pq.ParquetFile(path).schema_arrow.names:
            empty.append(path.stem)
            continue
        dt = pd.to_datetime(pd.read_parquet(path, columns=["date"])["date"])
        if not len(dt):
            empty.append(path.stem)
            continue
        dt = dt.sort_values().reset_index(drop=True)
        if len(dt) < 2:
            continue
        gap = int((dt.iloc[1] - dt.iloc[0]).days)
        if dt.iloc[0] == day:
            cohort[path.stem] = gap
        elif gap > _NORMAL_START_GAP_DAYS:
            strays[path.stem] = gap

    assert sorted(cohort) == ["1337", "3665", "4141", "4144", "4935", "4984",
                              "5215", "5871", "5880", "5906", "5907", "8427"], (
        f"README caveat 6 names the twelve series that open on "
        f"{_PRE_LISTING_DAY}; they are now {sorted(cohort)}"
    )
    assert (min(cohort.values()), max(cohort.values())) == (7, 419), (
        f"caveat 6 says every one of the twelve then stops for 7 to 419 days, "
        f"which is what makes the row a pre-listing session rather than a "
        f"start; the run is now {min(cohort.values())} to {max(cohort.values())}"
    )
    assert sorted(strays) == ["2491"], (
        f"caveat 6 rests the cohort on a date because no gap threshold "
        f"separates it: outside {_PRE_LISTING_DAY} exactly one series waits "
        f"more than {_NORMAL_START_GAP_DAYS} days between its first two "
        f"sessions, and it is 2491. It is now {sorted(strays)}, so a gap rule "
        f"and a date rule no longer pick out different sets"
    )
    assert len(empty) == 3, (
        f"3 codes carry an OHLCV file the vendor never filled; "
        f"{len(empty)} do now ({sorted(empty)[:6]}), and an empty series reads "
        f"as an unlisted one here"
    )
    return (f"{len(cohort)} series open on {_PRE_LISTING_DAY} and then wait "
            f"{min(cohort.values())}-{max(cohort.values())} days, against one "
            f"series elsewhere in {len(files)} that waits over a month",
            len(cohort))


def test_taiwan_adjusted_series():
    """README "Adjusted prices", on the three things it claims.

    That the vendor series carries the exchange's own total-return factor; that
    a session the stock did not trade holds no adjusted price even though the
    vendor supplies one; and that a share cancellation the vendor did not price
    is marked rather than left in the series as a return.
    """
    sys.path.insert(0, str(REPO))
    if not (REPO / "finmind_data/unpriced_actions.parquet").exists():
        raise Skipped("unpriced_actions.parquet not built")
    import numpy as np

    from finmind_data.adjusted_loader import load_adjusted

    # (1) The factor is the exchange's. Each 除權息 event contributes
    # before_price/after_price; FinMind reaches the same number by subtracting
    # the declared distribution from the prior close instead, so the two agree
    # exactly on most events and closely on the rest.
    rel, cash = [], []
    for sid in ("2330", "2317", "1101", "2412", "1216", "2002"):
        ev = _tree(REPO / f"finmind_data/div_result/{sid}.parquet")
        ev = ev[(ev["before_price"] > 0) & (ev["after_price"] > 0)]
        d = load_adjusted(sid)
        f = d["tr_factor"].to_numpy(dtype=float)
        i = np.searchsorted(d["date"].to_numpy(),
                            pd.to_datetime(ev["date"]).to_numpy(), "left")
        ok = (i > 0) & (i < len(d))
        got = f[i[ok]] / f[i[ok] - 1]
        want = (ev["before_price"].to_numpy(dtype=float)
                / ev["after_price"].to_numpy(dtype=float))[ok]
        m = np.isfinite(got) & np.isfinite(want)
        rel.append(np.abs(got[m] / want[m] - 1.0))
        # 息 is cash only; 權 and 權息 carry stock, which moves the factor under
        # either convention and so says nothing about which one this is.
        is_cash = (ev["stock_or_cache_dividend"].astype(str) == "息").to_numpy()[ok][m]
        cash.append(np.abs(got[m][is_cash] - 1.0))
    rel = np.concatenate(rel)
    cash_dev = np.concatenate(cash)
    n_cash = len(cash_dev)
    within = float((rel < 1e-3).mean())
    assert within >= 0.98, (
        f"README claims price_adj/ carries the exchange's own total-return "
        f"factor, matching before_price/after_price within 1e-3 on 99.6 % of "
        f"events; on these {len(rel)} it now matches {100 * within:.1f} %. "
        f"Below that the series is adjusting for something else"
    )
    # A cash-only 除權息 moves the factor at all — this is what says the series
    # is total return and not price return, where a cash event has step 1. The
    # test is the step's *distance* from 1 on those events, not its agreement
    # with the exchange, which the bound above already covers: an agreement rate
    # is silent about which convention both sides agree on.
    assert (n_cash, float(cash_dev.min() > 1e-3)) == (98, 1.0), (
        f"README calls price_adj/ a total-return series, which means every one "
        f"of the 82 cash-only 除權息 across these six names steps the factor off "
        f"1; {n_cash} were found and the smallest step is "
        f"{cash_dev.min():.2e} from 1. Under price return every one would be 0"
    )

    # (2) A no-trade session is close == 0 in ohlcv/, and the vendor fills it
    # with the last traded price. Zero is not a price and neither is a carried
    # one, so the row must hold no adjusted close.
    d = load_adjusted("8934")
    z = d["close"] == 0
    vendor = _tree(REPO / "finmind_data/price_adj/8934.parquet")
    n_filled = int(d.loc[z, "date"].isin(vendor.loc[vendor["close"] > 0, "date"]).sum())
    # 8934 is the example because it barely trades: its zero-close rows are the
    # majority of its file. Both counts are pinned rather than tested for
    # presence — a single surviving zero-close row would satisfy `> 0` while the
    # encoding this check exists for had changed underneath it.
    #
    # The vendor prices 1,321 of the 1,326, not all of them. It used to price
    # all 1,321: `backfill_make_up_sessions` added six make-up sessions the raw
    # endpoint serves and the adjusted one does not, and five of them are
    # no-trade, so they are zero-close rows with no vendor price behind them
    # rather than zero-close rows the vendor carried a price across. The sixth,
    # 2016-06-04, traded, which is why the fill is counted on the zero-close
    # dates: a difference of positive-close counts reads one short. The NaN rule
    # below holds either way, which is the point of pinning both counts
    # separately.
    assert (int(z.sum()), n_filled) == (1326, 1321), (
        f"8934 is chosen for having 1,326 zero-close sessions, 1,321 of which "
        f"the vendor prices anyway; this tree has {int(z.sum())} and the "
        f"vendor fills {n_filled}. Either the raw zero encoding or the vendor's "
        f"carry changed, and the NaN rule below is written against both"
    )
    assert d.loc[z, "adj_close_tr"].isna().all(), (
        f"README claims a session the stock did not trade holds no adjusted "
        f"price; 8934 has {int(z.sum())} zero-close rows and "
        f"{int(d.loc[z, 'adj_close_tr'].notna().sum())} of them carry a number"
    )

    # (3) 2357 華碩 2010-06-24: an 85 % share cancellation six months before the
    # 減資 endpoint's first row. Nothing prices it — the vendor least of all —
    # and the history behind it was marked rather than carrying the jump. That
    # break is the case `COVERAGE_START` exists for, and the window now excludes
    # every row it invalidates. What is asserted is that the *window* is what
    # cleans 2357, not a marking that quietly stopped firing: move
    # `COVERAGE_START` back past the break and the first of these fails.
    d = load_adjusted("2357")
    brk = pd.Timestamp("2010-06-24")
    assert brk < COVERAGE_START <= d["date"].iloc[0], (
        f"2357's unpriced cancellation on {brk.date()} is excluded by a window "
        f"opening {COVERAGE_START.date()}; the panel now starts "
        f"{d['date'].iloc[0].date()}, so the break is inside it again and the "
        f"history behind it is unpriced rather than absent"
    )
    assert d["is_valid"].all(), (
        "README claims is_valid is False only *behind* the last break; 2357 "
        "has invalid rows on or after 2010-06-24"
    )

    # (4) The factor is re-anchored to this slice, so the last covered session
    # reads back its own raw close.
    cov = d["adj_close_tr"].notna()
    last = d.index[cov][-1]
    assert abs(d["adj_close_tr"].iloc[last] - d["close"].iloc[last]) < 1e-6, (
        "the loader re-anchors tr_factor to 1.0 on the last covered session, "
        f"so adj_close_tr should equal close there; 2357 gives "
        f"{d['adj_close_tr'].iloc[last]:.6f} vs {d['close'].iloc[last]:.6f}"
    )
    return (f"factor == exchange ratio on {100 * within:.1f} % of events "
            f"(<1e-3); 8934 {int(z.sum())} no-trade rows → NaN against "
            f"{n_filled} the vendor filled; 2357 step 1.0000 marked; "
            f"anchor exact"), len(rel)


# ---- Taiwan: the vendor's own events, graded against the exchange ----------
def test_taiwan_vendor_event_audit_is_current():
    """README, "Two conventions in one panel": the committed grade is this tree's.

    `vendor_event_audit.parquet` is what the README's 83.7 % / 99.6 % and the
    one patched event are quoted from, and `adjusted_loader` patches off it.
    A committed copy that no longer matches what the generator produces would
    publish an older run's grade while the loader patches a different set, so
    the file is regenerated here and compared rather than merely read.
    """
    sys.path.insert(0, str(REPO))
    from finmind_data.vendor_event_audit import OUT_PATH, audit

    assert OUT_PATH.exists(), (
        f"{OUT_PATH.name} is missing — run "
        f"`python -m finmind_data.vendor_event_audit`"
    )
    committed = pd.read_parquet(OUT_PATH)
    fresh = audit()
    # Datetime *unit* is the writer's, not the audit's: pandas 3 builds this
    # frame's `date` as datetime64[us] while the committed parquet was written
    # when the same construction gave ns, and every one of the 21,418 values is
    # equal across the two. Comparing units would report a pandas upgrade as a
    # changed grade, which is the opposite of what this check is for, so the
    # unit is pinned on both sides and everything else stays exact.
    for f in (committed, fresh):
        for col in f.columns:
            if pd.api.types.is_datetime64_any_dtype(f[col]):
                f[col] = f[col].astype("datetime64[ns]")
    pd.testing.assert_frame_equal(
        committed.reset_index(drop=True), fresh.reset_index(drop=True),
        check_exact=True, obj="vendor_event_audit.parquet")

    ck = committed[committed["checkable"]]
    assert (len(committed), len(ck)) == (21418, 21224), (
        f"README pins 21,418 filed 除權息 of which 21,224 are graded against "
        f"the exchange; this tree gives {len(committed):,} / {len(ck):,}"
    )
    # The two counts are one file and a column, not a filter that moved between
    # runs. Pin what the 34-row difference is made of so it stays that way.
    nc = committed[~committed["checkable"]]
    served = {p.stem for p in (REPO / "finmind_data/price_adj").glob("*.parquet")
              if len(_tree(p))}
    unserved = int((~nc["stock_id"].astype(str).isin(served)).sum())
    assert (len(nc), unserved) == (194, 174), (
        f"the 194 ungradable events should be 174 in stocks the vendor serves "
        f"nothing for and 20 with no adjacent bracketing session; this tree "
        f"gives {len(nc)} ungradable of which {unserved} are unserved"
    )
    w6, w3 = float((ck["rel"] < 1e-6).mean()), float((ck["rel"] < 1e-3).mean())
    assert abs(w6 - 0.8373) < 5e-4 and abs(w3 - 0.9958) < 5e-4, (
        f"README claims the vendor step matches the exchange's published "
        f"before_price/after_price to 1e-6 on 83.7 % of graded events and to "
        f"1e-3 on 99.6 %; this tree gives {100 * w6:.2f} % / {100 * w3:.2f} %. "
        f"A move here changes what the two conventions in the panel differ by"
    )
    defects = committed[committed["defect"] != ""].groupby("defect").size().to_dict()
    assert defects == {"malformed_twin": 1, "nonpositive_leg": 1}, (
        f"README claims 1 malformed-twin filing and 1 non-positive reference "
        f"leg inside the window, and no sign flip — the vendor's flips are all "
        f"2005-2008; this tree grades {defects}. A sign_flip appearing here is "
        f"the defect era reaching into the window and the patched set in "
        f"adjusted_loader is short"
    )

    # The defect is an era, not a rate: every flip the vendor makes is
    # 2005-2008, so the window opens after the last of them and holds none. The
    # era claim is about years this package does not answer for and is not
    # re-derived here; what is assertable inside the window is that the upward
    # reprices — the shape a flip takes — are all exact.
    up = ck[ck["exchange_step"] < 1.0]
    flipped = up[up["defect"] == "sign_flip"]
    assert (len(up), len(flipped)) == (16, 0), (
        f"the window holds {len(up)} upward reprices and the vendor's sign-flip "
        f"era ends in 2008, so none of them should be flipped; this tree flips "
        f"{len(flipped)}. A flip inside the window is the defect class returning "
        f"in years the loader's patch set was not built against"
    )
    assert not (up["defect"] != "").any(), (
        f"the docstring claims every upward reprice after the 2008 flips is "
        f"exact, and the window starts well past them, so a defect on one here "
        f"means the vendor's pipeline was not fixed and the search has to reopen"
    )
    return (f"{len(ck):,}/{len(committed):,} events graded; vendor == exchange "
            f"{100 * w6:.2f} % at 1e-6, {100 * w3:.2f} % at 1e-3; defects "
            f"{defects}, no sign flip in the window"), len(committed)


def test_taiwan_vendor_defects_are_patched():
    """README, "Seven vendor events carry the exchange's step instead".

    Each patched event should leave the loader's factor stepping by the
    exchange's published before_price/after_price across it, not the vendor's.
    The one inside the window moves the ex-date return from +4.19 % to +1.19 %,
    so an unpatched panel overstates that session by a factor of three.
    """
    sys.path.insert(0, str(REPO))
    import numpy as np

    from finmind_data.adjusted_loader import load_adjusted
    from finmind_data.vendor_event_audit import defective_events

    d = defective_events()
    assert len(d) == 1, (
        f"README claims 1 vendor event is replaced with the exchange's step; "
        f"the audit now marks {len(d)}. The sign-flip class the patch was built "
        f"for is confined to 2005-2008 and so falls outside the window entirely; "
        f"what is left inside it is 3454's malformed twin"
    )
    moved, spans = [], []
    for sid, g in d.groupby(d["stock_id"].astype(str)):
        df = load_adjusted(sid)
        assert df.attrs["events_patched"] == len(g), (
            f"{sid} carries {len(g)} defective event(s) that load_adjusted "
            f"patched {df.attrs['events_patched']} of"
        )
        dates = df["date"].to_numpy()
        cov = df["adj_covered"].to_numpy()
        f = df["tr_factor"].to_numpy()
        last = 0
        for _, e in g.iterrows():
            i = int(np.searchsorted(dates, np.datetime64(e["date"]), "left"))
            while i < len(df) and not cov[i]:
                i += 1
            got = f[i] / f[i - 1]
            assert abs(got / e["exchange_step"] - 1.0) < 1e-9, (
                f"{sid} {pd.Timestamp(e['date']).date()}: the patched factor "
                f"steps by {got:.6f} where the exchange published "
                f"{e['exchange_step']:.6f} ({e['before']} → {e['after']})"
            )
            moved.append(abs(e["rel"]))
            last = max(last, i)

        # The patch is not a one-day event. A factor anchored at the present
        # carries every step in the rows *behind* it, so replacing one rescales
        # the stock's history from the ex date back to its first session — the
        # ex-date return moves, and so does every level before it. A flag on the
        # ex row alone would tell a reader that one session differs from the
        # vendor's series when in fact the whole span does.
        lab = (df["adj_source"] == "vendor_patched").to_numpy()
        vend = df["adj_source"].isin(("vendor", "vendor_patched")).to_numpy()
        assert (lab[:last] == vend[:last]).all() and not lab[last:].any(), (
            f"{sid}: vendor_patched covers {int(lab.sum())} rows, but the patch "
            f"rescaled the {int(vend[:last].sum())} vendor rows before "
            f"{pd.Timestamp(dates[last]).date()} and nothing from it on"
        )
        spans.append(int(lab.sum()))

    assert sum(spans) == 120, (
        f"README claims the patch rescales 120 rows behind it; "
        f"this tree labels {sum(spans):,}"
    )
    return (f"{len(d)} event patched to the exchange's step; the patch moves the "
            f"ex-date factor by {100 * min(moved):.2f}-{100 * max(moved):.2f} % "
            f"and rescales {sum(spans):,} rows behind them"), sum(spans)


def test_taiwan_vendor_edges_are_carried():
    """README, "The edge of the vendor series": 493 first sessions carry the
    adjacent factor, and one is refused.

    A back-adjustment factor moves only on an ex date, so carrying it across a
    gap with no filing in it is exact rather than an interpolation — which is
    what makes the fill safe where a splice would not be. The guard is
    the part worth asserting: it is checked per row against every filed 除權息
    and 減資 plus the cancellations no filing explains, and it refuses 4141,
    whose first print sits 376 days before the vendor's first session with a
    cancellation on that session. A guard that never fires is indistinguishable
    from no guard.

    Only one edge is carried inside the window. The other — a name still quoted
    after its delisting — needs the vendor's series to stop before the raw one
    does, and no in-window name has that shape: the four names quoted past their
    delisting all left the market before `COVERAGE_START`, so the vendor never
    served them here and the rebuild does instead.
    """
    sys.path.insert(0, str(REPO))
    import numpy as np

    from finmind_data import adjust
    from finmind_data.adjusted_loader import _unpriced_dates, load_adjusted

    head = tail = 0
    refused, uncovered = [], []
    # 3271, 3142, 2479 and 3053 left this list when the window started being
    # enforced: their last quote is 2005-2008, so the package has no series for
    # them and `load_adjusted` refuses them rather than returning one. 1240
    # replaces the head carry they supplied — it listed inside the window, which
    # is now the only way a first session comes to be carried.
    for sid in ("1580", "3454", "1107", "2381", "2396", "2341", "1240",
                "4141", "2330"):
        df = load_adjusted(sid)
        s = df["adj_source"].to_numpy()
        carried = np.nonzero(s == "vendor_carried")[0]
        # The anchor is a session the vendor priced and the stock traded — not
        # merely one adj_covered, which is also True on the no-trade rows the
        # vendor filled with a carried close and which carry no factor.
        served = np.nonzero(np.isin(s, ("vendor", "vendor_patched")))[0]
        blocking = np.concatenate([adjust.filed_event_dates(sid),
                                   _unpriced_dates(sid)])
        dates = df["date"].to_numpy()
        f = df["tr_factor"].to_numpy()
        for i in carried:
            a = served[0] if i < served[0] else served[-1]
            lo, hi = sorted((dates[i], dates[a]))
            assert not ((blocking > lo) & (blocking <= hi)).any(), (
                f"{sid} {pd.Timestamp(dates[i]).date()}: the factor was carried "
                f"across a gap that holds a filing, so the level is spliced "
                f"rather than continuous"
            )
            assert abs(f[i] / f[a] - 1.0) < 1e-12, (
                f"{sid} {pd.Timestamp(dates[i]).date()}: carried factor "
                f"{f[i]:.10f} against its anchor's {f[a]:.10f}"
            )
            head += i < served[0]
            tail += i > served[-1]
        # A traded session the vendor does not serve and the guard would not
        # carry stays NaN rather than being filled from further away. Two
        # conditions land here and only one is the guard: a session *before*
        # the vendor's first served row is an edge it declined to carry, while
        # one *interior* to the series is a session the vendor's adjusted
        # product does not cover at all. The make-up sessions
        # `backfill_make_up_sessions` restored are the second — the raw
        # endpoint serves them and the adjusted endpoint does not — so they
        # reached the panel as traded rows with no adjusted price when the raw
        # tree was completed, and reading them as refusals would blame the
        # guard for the vendor's coverage.
        for i in np.nonzero((df["close"].to_numpy() > 0) & (s == ""))[0]:
            if i < served[0] or i > served[-1]:
                refused.append((sid, str(pd.Timestamp(dates[i]).date())))
            else:
                uncovered.append((sid, str(pd.Timestamp(dates[i]).date())))

    assert refused == [("4141", "2011-04-14")], (
        f"the carry guard should refuse exactly 4141's 2011-04-14 stub print "
        f"among these stocks; it refused {refused}"
    )
    assert uncovered == [("1240", "2017-09-30"), ("1240", "2018-03-31")], (
        f"among these stocks the only traded sessions interior to the vendor's "
        f"series that it prices nothing for are 1240's two restored make-up "
        f"Saturdays; this tree has {uncovered}"
    )
    assert (head, tail) == (1, 0), (
        f"these stocks hold 1 of the 493 carried first sessions, and no session "
        f"after a delisting is carried anywhere in the panel; this tree carries "
        f"{head} / {tail}"
    )
    return (f"{head} first session carried from the adjacent factor with no "
            f"filing in the gap, {tail} after a delisting; 4141 2011-04-14 "
            f"refused; {len(uncovered)} restored make-up sessions the vendor "
            f"prices nothing for"), head + len(refused) + len(uncovered)


def test_taiwan_post_delisting_sessions_are_marked():
    """README, "Which rows to trust": no session after a delisting is holdable.

    The exchange ended the listing on the date the delisting table carries, so
    whatever market the quotes that follow belong to, it is not the one a fill is
    assumed to come from. `is_valid` False with `invalid_reason`
    `post_delisting_emerging` is what keeps a backtest out while leaving the rows
    readable as terminal-value evidence, which is the one use they are good for.

    The population is derived from the delisting table rather than listed here,
    and that is the whole point of the check. It used to name seven stocks — the
    ones whose vendor series stops at the delisting, which was how the boundary
    was found. The rebuild gave 38 names no vendor series at all, so seven more
    acquired tails the boundary could not see, and this check went on passing
    because it was still looking at its original seven. A check that names its
    subjects cannot report the ones that arrive after it is written.

    Which leaves the other half of the same problem: what the check *classifies*
    on. Deciding a transfer by the vendor's coverage flag, as the loader does,
    would make this check a restatement of the loader rather than a test of it —
    the two would agree on a rebuilt name by construction, both of them silent.
    It reads the panel instead, and a disagreement is loud in both directions: a
    name still quoted at the panel's edge that the loader marked fails the
    assertion below, and one that stops being quoted but was left unmarked fails
    the `post == after` assertion further down.
    """
    sys.path.insert(0, str(REPO))
    import numpy as np
    import pyarrow.parquet as pq

    from finmind_data.adjusted_loader import _BREAK_GAP_DAYS, load_adjusted

    d = pd.read_parquet(REPO / "finmind_data/delisted_universe.parquet")
    d["date"] = pd.to_datetime(d["date"])

    # What separates a departure from an exit has to be something the loader did
    # not classify on, or the two cannot disagree and the check only restates the
    # code. The loader reads the vendor's coverage flag, which is False across
    # every rebuilt name and so cannot see a transfer among them; this reads the
    # market instead. A name still quoted on the panel's last session did not
    # leave the market whatever the delisting table says, and that is a fact
    # about the panel, defined for rebuilt and vendor-served names alike.
    last = {}
    for r in d.itertuples():
        f = REPO / f"finmind_data/ohlcv/{r.stock_id}.parquet"
        if not f.exists():
            continue
        c = _tree(f)
        if len(c):
            last[str(r.stock_id)] = c["date"].max()
    # Over the whole panel, not over `last`. Every name in `last` has left, so
    # the maximum among them belongs to whichever left last, which then equals
    # `panel_end` by construction and reads as never having left. It gave the
    # right answer here only because the delisting table carries names that
    # delisted after the download stopped, whose quotes run to the true edge —
    # an accident of the table's contents, not a property of the measurement.
    # `delisting_sign._panel_last_session` is the same anchor and had the same
    # drift; the fix is one fixed point, read the same way in both places — so
    # this reads it from there rather than recomputing it. A second copy of the
    # scan is what let the two answer differently in the first place, and the
    # window makes that sharper: the trees now run past `COVERAGE_END`, so an
    # unclipped scan answers with a session no check here is quoted on.
    from finmind_data.delisting_sign import _panel_last_session

    panel_end = _panel_last_session()

    marked = transferred = 0
    names = []
    moved = []
    reissued = []
    for r in d.itertuples():
        sid = str(r.stock_id)
        try:
            df = load_adjusted(sid)
        except (FileNotFoundError, ValueError):
            continue                      # no OHLCV file, or one with no rows
        after = (pd.to_datetime(df["date"]) > r.date).to_numpy()
        if not after.any():
            continue
        # A name still being quoted on the panel's last session did not leave the
        # market. Asserting that no such name picks up the reason is what stops
        # the boundary from being applied by date alone to a stock that is still
        # listed — the delisting table records departures from a board, and a
        # departure is not always an exit. The separation is not marginal: the
        # tails that end do so 12 to 18 years short of the panel, the shortest
        # after 8 sessions and the longest after 1,151.
        if last[sid] == panel_end:
            still = (df["invalid_reason"] == "post_delisting_emerging").to_numpy()
            assert not still[after].any(), (
                f"{sid}: it is still quoted on {panel_end.date()}, the panel's "
                f"last session, so its {r.date.date()} delisting was a departure "
                f"from a board and not from the market, but "
                f"{int(still[after].sum())} of its {int(after.sum())} later "
                f"sessions are marked as having followed an exit. The other "
                f"reasons may still claim rows here and should")
            # It kept being priced for one of two reasons, and the gap tells
            # them apart on the same threshold the break machinery uses: either
            # it never stopped, which is a board transfer the table records the
            # departure of and not the arrival, or it came back long after,
            # which is a different company on a reused code.
            gap = (pd.to_datetime(df["date"]).to_numpy()[after].min()
                   - r.date.to_datetime64()) / np.timedelta64(1, "D")
            if gap <= _BREAK_GAP_DAYS:
                transferred += int(after.sum())
                moved.append(sid)
            else:
                assert not df["is_valid"].to_numpy()[~after].any(), (
                    f"{sid}: its code was reissued {gap:.0f} days after the "
                    f"{r.date.date()} delisting, so the sessions before that "
                    f"date belong to a different company; "
                    f"{int(df['is_valid'].to_numpy()[~after].sum())} of them are "
                    f"still holdable, which splices two issuers into one series")
                reissued.append(sid)
            continue
        post = (df["invalid_reason"] == "post_delisting_emerging").to_numpy()
        assert (post == after).all(), (
            f"{sid}: {int(after.sum())} sessions follow its {r.date.date()} "
            f"delisting and {int(post.sum())} carry the reason. A session the "
            f"exchange delisted the name before is not a position, whether or "
            f"not the vendor served the name")
        assert not df["is_valid"].to_numpy()[post].any(), (
            f"{sid}: {int(df['is_valid'].to_numpy()[post].sum())} post-delisting "
            f"rows are still is_valid, so a backtest would trade them")
        # On the traded ones. A tail also holds sessions the stock did not trade,
        # and those carry no adjusted price anywhere in the panel — the segment
        # reason claims them from `no_trade`, it does not give them a level.
        priced = post & (df["close"].to_numpy() > 0)
        assert df.loc[priced, "adj_close_tr"].notna().all(), (
            f"{sid}: {int(df.loc[priced, 'adj_close_tr'].isna().sum())} of its "
            f"{int(priced.sum())} traded post-delisting rows carry no adjusted "
            f"price, so the terminal-value evidence they exist for is not there")
        marked += int(post.sum())
        names.append(sid)

    assert (len(names), marked) == (4, 1_134), (
        f"README claims 1,134 post-delisting sessions across 4 names; this "
        f"tree marks {marked:,} across {len(names)}")
    # Sorted, because the loop takes the delisting table's row order and a
    # re-collect that reorders it would fail this on nothing.
    assert (sorted(moved), sorted(reissued)) == ([], []), (
        f"README says the 2026-08-17 refresh left no board transfer and no "
        f"reused code in the table; this tree finds {moved} and {reissued}. A "
        f"new transfer is a name whose exit the table records and whose arrival "
        f"it does not, so a delisting return computed for it would be a loss it "
        f"never took")
    return (f"{marked:,} post-delisting sessions priced and marked invalid "
            f"across {len(names)} names; {len(moved)} board transfers and "
            f"{len(reissued)} reused codes, {transferred} transferred sessions "
            f"left holdable"), marked + transferred


# ---- Taiwan: no-trade sessions, and the closure of is_valid ----------------
def test_taiwan_no_trade_rows_are_not_holdable():
    """README, "Which rows to trust": the fourth `invalid_reason`, panel-wide.

    `close == 0` encodes a session the stock did not trade, and the vendor fills
    those rows with the last traded price — so the panel carries a level for a
    day on which nothing changed hands. Under "a position a study could have
    held" they are not positions, and they were the one class `is_valid` let
    through: the chain is intact, no cancellation is missing, the name had not
    delisted. A backtest filtering on the flag alone would have assumed a fill.

    Two things are asserted, and they fail on different mistakes. The counts pin
    *this* reason: dropping the mask leaves the 133,590 rows valid with no reason
    at all, which the reason split below catches and the closure below does not,
    because a row that is valid and unnamed is consistent. The closure pins the
    *next* one: every False row carries a reason and every True row carries none,
    across the whole panel, so a reason added later that marks `is_valid` without
    naming itself — or names itself without marking — fails here. That failure is
    invisible in any per-stock check, because each stock's own reasons look
    complete.

    The split between the segment reasons and this one is pinned too. It is a
    precedence choice rather than a fact about the data: a no-trade session
    behind a break keeps the break's name, because those rows would not have
    been holdable had they traded either.
    """
    sys.path.insert(0, str(REPO))
    import numpy as np

    from finmind_data.adjusted_loader import load_adjusted

    rows = invalid = mismatched = zero = zero_stocks = 0
    by_reason: dict[str, int] = {}
    no_trade_stocks = set()
    empty = []
    for sid in _panel_ids():
        try:
            df = load_adjusted(sid)
        except ValueError:
            # The stocks with no in-window sessions to load — one whose OHLCV
            # file holds no rows at all, the rest quoted only outside the window.
            # One more would push the count past the assertion below rather
            # than pass quietly.
            empty.append(sid)
            continue
        z = df["close"].to_numpy(dtype=float) == 0.0
        reason = df["invalid_reason"].to_numpy()
        valid = df["is_valid"].to_numpy()
        rows += len(df)
        invalid += int((~valid).sum())
        mismatched += int((valid != (reason == "")).sum())
        zero += int(z.sum())
        zero_stocks += int(z.any())
        for r in np.unique(reason[z]):
            by_reason[r] = by_reason.get(r, 0) + int((reason[z] == r).sum())
        nt = reason == "no_trade"
        if nt.any():
            no_trade_stocks.add(sid)
            assert (z[nt].all() and df.loc[nt, "adj_close_tr"].isna().all()
                    and not valid[nt].any()), (
                f"{sid}: a no_trade row must be a zero close, carry no adjusted "
                f"price and be is_valid False; "
                f"{int((~z[nt]).sum())}/{int(df.loc[nt, 'adj_close_tr'].notna().sum())}"
                f"/{int(valid[nt].sum())} of {int(nt.sum())} break one of those")

    assert len(empty) == 38, (
        f"README says load_adjusted refuses 38 of the universe's names — 1 whose "
        f"OHLCV file holds no rows at all and 37 quoted only outside the window; "
        f"{len(empty)} raised here, so this pass covered a "
        f"different panel than the counts below were measured on")
    assert (rows, zero, zero_stocks) == (6_676_903, 136_383, 1_208), (
        f"README quotes 136,383 no-trade sessions in 1,208 stocks over a "
        f"6,676,903-row panel; this tree has {zero:,} in {zero_stocks:,} over "
        f"{rows:,}. Every count below is a share of that population")
    assert mismatched == 0, (
        f"README claims is_valid alone is now enough — every False row carries "
        f"a reason and every True row carries none. {mismatched:,} of {rows:,} "
        f"rows break that, so invalid_reason no longer accounts for is_valid")
    assert by_reason == {"no_trade": 133_590,
                         "series_break": 1_941,
                         "unpriced_cancellation": 852}, (
        f"README claims 133,590 no-trade sessions take the new reason and the "
        f"2,793 behind a segment reason keep it; the split here is {by_reason}")
    assert len(no_trade_stocks) == 1_200, (
        f"README claims the 133,590 no_trade rows fall in 1,200 stocks — the "
        f"1,208 with a zero close, less the 8 whose zero closes all sit behind "
        f"a break; {len(no_trade_stocks):,} carry one here")
    return (f"{by_reason['no_trade']:,} no-trade sessions in "
            f"{len(no_trade_stocks):,} stocks marked invalid, "
            f"{zero - by_reason['no_trade']:,} more kept by a segment reason; "
            f"is_valid accounts for all {invalid:,} invalid rows of {rows:,}"
            ), rows


# ---- Taiwan: the make-up sessions ohlcv/ dropped ---------------------------
def test_taiwan_no_session_the_tape_holds_is_missing():
    """README, "The gap that runs the other way": the calendar, against the vendor.

    An absent session is not a missing row, it is an overstated return — the
    *next* session's return spans two sessions instead of one — and 1,940 of the
    1,941 sat on 14 holiday-adjacent Saturdays rather than anywhere at random,
    which is the shape a study reads as an effect.

    The hole used to be measured as the sessions ``price_adj/`` carries and
    ``ohlcv/`` does not: 303 rows in 96 stocks. That is a set difference between
    two local trees, so it could only ever see a session at least one of them
    held, and the number was read as the size of the hole rather than as the
    part of it one tree could still reach. Measured against the vendor instead,
    the hole was **1,941 rows in 507 stocks** — the 303 the loader could
    reconstruct, and 1,638 that neither tree held and nothing therefore
    reported. ``backfill_make_up_sessions`` read them from the date-keyed
    endpoint, which serves them today; the trees were behind a backfill.

    The assertion is therefore on the calendar and not on a recovery count: no
    session the tape holds is absent from the interior of a raw series. A date
    before a file's first row is the other condition entirely — the vendor's
    adjusted series opens one session after the raw one for ~500 stocks, which
    ``adjusted_loader`` handles by carrying the adjacent factor — and is not a
    gap in the calendar.
    """
    tape_dir = REPO / "finmind_data/tape"
    if not tape_dir.exists():
        raise Skipped("tape/ not built (python -m finmind_data.tape_universe)")
    tape = pd.concat([pd.read_parquet(q) for q in sorted(tape_dir.glob("*.parquet"))],
                     ignore_index=True)
    lo, hi = tape["date"].min(), tape["date"].max()
    by_code = {}
    for c, d in zip(tape["stock_id"], tape["date"]):
        by_code.setdefault(c, set()).add(d)

    interior, examined, offenders = 0, 0, []
    for q in sorted((REPO / "finmind_data/ohlcv").glob("*.parquet")):
        sid = q.stem
        if sid not in by_code:
            continue
        try:
            have = set(pd.read_parquet(q, columns=["date"])["date"].astype(str))
        except Exception:
            continue
        w = {d for d in have if lo <= d <= hi}
        if not w:
            continue
        first, last = min(w), max(w)
        gaps = [d for d in by_code[sid] - have if first < d < last]
        examined += len(by_code[sid])
        interior += len(gaps)
        if gaps and len(offenders) < 12:
            offenders.append((sid, sorted(gaps)[:3]))
    assert interior == 0, (
        f"{interior} sessions the vendor serves are absent from the interior of "
        f"a raw series, so the return after each one spans two sessions rather "
        f"than one: {offenders}")

    # The 303 were exactly the sessions price_adj/ held and ohlcv/ did not, and
    # they are what `adjusted_loader` used to reconstruct. With the raw tree
    # complete there is nothing to reconstruct, and `_require_raw_covers_vendor`
    # now raises rather than deriving one — this is the panel-wide version of
    # that guard, which per stock sees only what price_adj/ exposes.
    vendor_only = 0
    for q in sorted((REPO / "finmind_data/price_adj").glob("*.parquet")):
        sid = q.stem
        r = REPO / f"finmind_data/ohlcv/{sid}.parquet"
        if not r.exists():
            continue
        try:
            adj = set(pd.read_parquet(q, columns=["date"])["date"].astype(str))
            raw = set(pd.read_parquet(r, columns=["date"])["date"].astype(str))
        except Exception:
            continue
        vendor_only += len({d for d in adj - raw if lo <= d <= hi})
    assert vendor_only == 0, (
        f"{vendor_only} sessions price_adj/ carries are still absent from "
        f"ohlcv/, so the loader is reconstructing rows the raw tree should hold")
    return (f"no interior session gap across {examined:,} vendor-served "
            f"ticker-days; price_adj/ carries none ohlcv/ lacks"), examined


def test_taiwan_volume_repair_matches_the_tape():
    """README, "The gap that runs the other way": `volume_repair.py` wrote the
    vendor's raised count over the 5,925 rows where `ohlcv/` held its first one.

    The tape is the reference: the date-keyed endpoint, read later than the
    tree. It is a reference only if the per-stock endpoint the tree came from
    serves the same count, so the re-pull's Saturday rows are held against it
    too. The first counts are gone from the trees and kept in
    `volume_repair.parquet`, so the figures about the shortfall are read off
    it, and each tree must hold the record's `new` value on every row it names.
    """
    import pyarrow.parquet as pq

    tape_dir = REPO / "finmind_data/tape"
    if not tape_dir.exists():
        raise Skipped("tape/ not built (python -m finmind_data.tape_universe)")
    tape = pd.concat([pd.read_parquet(q) for q in sorted(tape_dir.glob("*.parquet"))],
                     ignore_index=True)
    tape["date"] = pd.to_datetime(tape["date"])
    sessions = pd.to_datetime(pd.read_parquet(
        REPO / "finmind_data/trading_sessions.parquet")["date"])
    saturdays = sessions[sessions.dt.dayofweek == 5]
    log = pd.read_parquet(REPO / "finmind_data/volume_repair.parquet")
    log["date"] = pd.to_datetime(log["date"])
    counts = ["Trading_Volume", "Trading_money", "Trading_turnover"]

    raw, adj = [], []
    for sid in _panel_ids():
        p = REPO / f"finmind_data/ohlcv/{sid}.parquet"
        if pq.ParquetFile(p).metadata.num_rows:
            raw.append(_tree(p, columns=["date", "stock_id"] + counts))
        q = REPO / f"finmind_data/price_adj/{sid}.parquet"
        if q.exists() and pq.ParquetFile(q).metadata.num_rows:
            adj.append(_tree(q, columns=["date", "stock_id"] + counts))
    raw = pd.concat(raw, ignore_index=True)
    adj = pd.concat(adj, ignore_index=True)

    m = raw.merge(tape, on=["date", "stock_id"], suffixes=("", "_tape"))
    off = int((m["Trading_Volume"].ne(m["Trading_Volume_tape"])
               | m["Trading_money"].ne(m["Trading_money_tape"])).sum())
    assert off == 0, (
        f"README says ohlcv/ now matches the tape on every in-window row the "
        f"tape holds; {off:,} of {len(m):,} rows differ on volume or value")

    o = log[log["tree"] == "ohlcv"]
    short = all((o[f"{c}_old"] < o[f"{c}_new"]).all()
                for c in ["Trading_Volume", "Trading_money"])
    got = (len(o), o["stock_id"].nunique(), o["date"].nunique(), len(saturdays),
           bool(o["date"].isin(saturdays).all()), short)
    assert got == (5925, 745, 12, 14, True, True), (
        f"README says that against the tape, ohlcv/'s volume and value fell "
        f"short on 5,925 rows in 745 stocks, all on 12 of the 14 Saturdays; "
        f"(rows the repair replaced, stocks, dates, calendar Saturdays, all on "
        f"a Saturday, short on both) now reads {got}")
    gap = 1 - o["Trading_Volume_old"] / o["Trading_Volume_new"]
    assert (math.isclose(gap.median(), 0.0042, abs_tol=0.00005)
            and math.isclose(gap.max(), 0.995, abs_tol=0.0005)), (
        f"README says the median row was short by 0.42 % of its volume, and the "
        f"worst by 99.5 %; the repair record gives {gap.median():.2%} and "
        f"{gap.max():.1%}")

    fresh = pd.read_parquet(REPO / "finmind_data/ohlcv_repull.parquet",
                            columns=["date", "stock_id", "Trading_Volume",
                                     "Trading_money"])
    fresh["date"] = pd.to_datetime(fresh["date"])
    fresh = fresh[fresh["date"].isin(saturdays)]
    f = fresh.merge(tape, on=["date", "stock_id"], suffixes=("", "_tape"))
    agree = bool(f["Trading_Volume"].eq(f["Trading_Volume_tape"]).all()
                 and f["Trading_money"].eq(f["Trading_money_tape"]).all())
    assert len(f) == len(fresh) > 0 and agree, (
        f"README says the re-pull under Provenance matches the tape on every "
        f"Saturday row of its sample; {len(f)} of its {len(fresh)} Saturday "
        f"rows are in the tape, all matching: {agree}")

    a = log[log["tree"] == "price_adj"]
    same = a.merge(o, on=["date", "stock_id"], suffixes=("", "_ohlcv"))
    first = all((same[f"{c}_old"] == same[f"{c}_old_ohlcv"]).all() for c in counts)
    rest = a[~a.set_index(["date", "stock_id"]).index.isin(
        same.set_index(["date", "stock_id"]).index)]
    others = [(r.stock_id, f"{r.date:%Y-%m-%d}", r.Trading_Volume_old < r.Trading_Volume_new)
              for r in rest.itertuples()]
    assert (len(same), first, others) == (3982, True, [("3713", "2020-02-27", True)]), (
        f"README says price_adj/ held the same first count on 3,982 of the rows, "
        f"and a lower count than ohlcv/'s on 3713's 2020-02-27; the repair "
        f"record gives {len(same):,} rows sharing ohlcv/'s entry, the same "
        f"first count on each: {first}, and beside them {others}")

    for name, tree in (("ohlcv", raw), ("price_adj", adj)):
        now = tree.merge(log[log["tree"] == name], on=["date", "stock_id"])
        wrong = int(sum((now[c] != now[f"{c}_new"]).sum() for c in counts))
        assert len(now) == int((log["tree"] == name).sum()) and wrong == 0, (
            f"README says volume_repair.parquet keeps every value the repair "
            f"replaced; {name}/ holds {len(now):,} of its rows, {wrong} of them "
            f"without the recorded new count")
    shared = raw.merge(adj, on=["date", "stock_id"], suffixes=("", "_adj"))
    differ = int(sum(shared[c].ne(shared[f"{c}_adj"]).sum() for c in counts))
    assert differ == 0, (
        f"README's sponsor-tier table says price_adj/'s three count columns equal "
        f"ohlcv/'s on every in-window row the two share; {differ:,} values of "
        f"{len(shared):,} rows differ")
    return (f"ohlcv/ matches the tape on {len(m):,} rows; the repair replaced "
            f"{len(o):,} ohlcv/ rows on {o['date'].nunique()} Saturdays and "
            f"{len(a):,} price_adj/ rows; the re-pull matches the tape on "
            f"{len(f)} Saturday rows"), len(m)


# ---- Taiwan: the survivorship hole is filled, and says so -------------------
def test_taiwan_survivorship_hole_is_rebuilt():
    """README, "The survivorship hole is filled": 50 stocks, 60,371 sessions.

    The universe carries a 57-name overlay of in-window delistings FinMind's
    live registry dropped, and `TaiwanStockPriceAdj` drops 50 of them too. A
    panel built by concatenating `load_adjusted` and dropping NaN used to
    reinstate the bias silently; it no longer can, but only while every one of
    the 50 comes back with a price. `adj_covered` stays False across them so
    the hole remains countable after it is filled.

    The invalid-reason split is what the rebuild is scored on, and moving the
    window start to 2011-01-25 emptied two of its three reasons. Both belonged
    entirely to holes that delisted in 2005-2007: 970 sessions behind an
    unpriced cancellation across 1207, 1462, 2544 and 2811, and 1,524 past a
    delisting across 1408, 1462, 1807, 2326, 2407, 2410 and 2811. None of those
    nine names is inside the window any more, and none is in the universe
    either — the overlay reinstates in-window delistings only. What is left is
    one reissued code: 4415's first occupant traded 2005-01-03 to 2011-11-07
    and 台原藥 took the code over after a 1,249-day gap, so the earlier
    company's 192 in-window traded sessions carry `series_break`, the tail of a
    history that straddles the window start.
    """
    sys.path.insert(0, str(REPO))
    from finmind_data.adjusted_loader import load_adjusted

    u = pd.read_parquet(REPO / "finmind_data/universe.parquet")
    d = pd.read_parquet(REPO / "finmind_data/delisted_universe.parquet")
    uid = set(u["stock_id"].astype(str))
    d = d.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["sid"] = d["stock_id"].astype(str)
    inwin = d[(d["date"] >= COVERAGE_START) & (d["date"] <= COVERAGE_END)
              & d["sid"].isin(uid)]

    # A hole is raw prices with no adjusted series *inside the window*. Read
    # unclipped, a name whose whole history predates `COVERAGE_START` counts as
    # one, and `load_adjusted` below then raises on it rather than measuring it.
    holes = [sid for sid in sorted(set(inwin["sid"]))
             if len(_tree(REPO / f"finmind_data/ohlcv/{sid}.parquet"))
             and not len(_tree(REPO / f"finmind_data/price_adj/{sid}.parquet"))]
    traded = priced = 0
    kinds = {}
    invalid = {}
    for sid in holes:
        df = load_adjusted(sid)
        t = df["close"] > 0
        traded += int(t.sum())
        priced += int((t & df["adj_close_tr"].notna()).sum())
        assert not df["adj_covered"].any(), (
            f"{sid} is one of the 50 the vendor serves nothing for, but "
            f"adj_covered is True somewhere — the hole is no longer countable"
        )
        for k in df.loc[df["adj_source"] != "", "adj_source"].unique():
            kinds[k] = kinds.get(k, 0) + 1
        # Over the traded sessions only, which is the population `invalid`
        # counts. Every stock also carries no-trade rows, and they are invalid
        # for a reason that has nothing to do with the rebuild.
        for k, c in df.loc[t & ~df["is_valid"], "invalid_reason"].value_counts().items():
            invalid[k] = invalid.get(k, 0) + int(c)

    assert (len(holes), traded, priced) == (50, 60371, 60371), (
        f"README claims all 50 vendor holes come back priced across their "
        f"60,371 traded sessions; this tree gives {len(holes)} stocks, "
        f"{traded:,} traded, {priced:,} priced. An unpriced session here is a "
        f"survivorship hole the panel build will drop"
    )
    assert kinds == {"rebuilt_factored": 37, "rebuilt_noevent": 13}, (
        f"README splits the 50 into 37 with a factor chain and 13 with no "
        f"corporate action in window; this tree gives {kinds}. The split is "
        f"what isolates the cumulative-product path from the flat one"
    )
    assert invalid == {"series_break": 192}, (
        f"README claims one of the 50 carries invalid traded sessions — 4415's "
        f"192 under the code's earlier occupant — and that the rebuild "
        f"leaves every other traded session holdable; this tree gives "
        f"{invalid}. A reason returning here is a hole the panel build will "
        f"drop rows from after paying to fill it"
    )
    return (f"{len(holes)} holes rebuilt over {priced:,} traded sessions "
            f"({kinds}); {invalid['series_break']:,} invalid, all one "
            f"reissued code's earlier occupant"), traded


def test_taiwan_rebuild_matches_vendor():
    """README, "Validated on the 131 covered in-window delistings".

    The rebuild is only trustworthy on the 50 if the same code path reproduces
    the vendor where the vendor exists. The gate set is the in-window
    delistings the vendor *does* cover — same era, same situation — and the
    statistic is the one research consumes: the daily adjusted return.
    """
    sys.path.insert(0, str(REPO))
    import numpy as np

    from finmind_data import adjust
    from finmind_data.adjusted_loader import load_adjusted

    d = pd.read_parquet(REPO / "finmind_data/delisted_universe.parquet")
    d["date"] = pd.to_datetime(d["date"])
    ids = sorted(set(d[(d["date"] >= COVERAGE_START)
                       & (d["date"] <= COVERAGE_END)]["stock_id"].astype(str)))
    n = ok6 = ok3 = stocks = 0
    for sid in ids:
        try:
            df = load_adjusted(sid)
        except (FileNotFoundError, ValueError):
            continue
        if not df["adj_covered"].any():
            continue
        f, _ = adjust.rebuild_tr_factor(sid, df[["date", "close"]])
        m = (df["adj_covered"].to_numpy() & (df["close"].to_numpy() > 0)
             & df["is_valid"].to_numpy())
        if m.sum() < 2:
            continue
        last = np.nonzero(m)[0][-1]
        c = np.where(m, df["close"].to_numpy(dtype=float), np.nan)
        vp, mp = c * df["tr_factor"].to_numpy(), c * (f / f[last])
        vr, mr = vp[1:] / vp[:-1] - 1, mp[1:] / mp[:-1] - 1
        g = np.isfinite(vr) & np.isfinite(mr)
        if not g.any():
            continue
        stocks += 1
        diff = np.abs(vr[g] - mr[g])
        n += int(g.sum())
        ok6 += int((diff < 1e-6).sum())
        ok3 += int((diff < 1e-3).sum())

    assert (stocks, n) == (131, 247422), (
        f"README quotes the gate on 131 covered in-window delistings and "
        f"247,422 daily adjusted returns; this tree gives {stocks} / {n:,}"
    )
    assert ok6 / n >= 0.9991 and ok3 / n >= 0.9999, (
        f"README claims the rebuild reproduces the vendor on 99.952 % of daily "
        f"adjusted returns to 1e-6 and 99.994 % to 1e-3; this tree gives "
        f"{100 * ok6 / n:.3f} % / {100 * ok3 / n:.3f} %. Below that the 50 "
        f"rebuilt names are no longer validated by anything"
    )
    return (f"{stocks} stocks, {n:,} returns: {100 * ok6 / n:.3f} % match to "
            f"1e-6, {100 * ok3 / n:.3f} % to 1e-3"), n


def test_taiwan_adj_source_partitions_the_panel():
    """README, "Which rows to trust": adj_source is present exactly where a
    price is, and adj_method follows from it.

    A row with a price and no source cannot be filtered by convention, and a
    source with no price is a label on nothing. Both would let a panel mix the
    declared-dividend and exchange-reference conventions without a way to split
    them again.
    """
    sys.path.insert(0, str(REPO))
    from finmind_data.adjusted_loader import _METHOD, load_adjusted

    seen = set()
    rows = 0
    # 2822 and 1207 last traded in 2006 and 2007, so the package has no series
    # for them; 1566 and 1240 replace the rebuilt_factored and vendor_carried
    # values they supplied, and 3454 carries the one patched event left in the
    # window.
    for sid in ("2330", "8934", "2396", "2357", "1566", "1240", "3454"):
        df = load_adjusted(sid)
        rows += len(df)
        has_px = df["adj_close_tr"].notna()
        has_src = df["adj_source"] != ""
        assert (has_px == has_src).all(), (
            f"{sid}: {int((has_px != has_src).sum())} rows carry a price "
            f"without a source or a source without a price"
        )
        assert (df["adj_method"] == df["adj_source"].map(_METHOD)).all(), (
            f"{sid}: adj_method does not follow adj_source"
        )
        seen |= set(df.loc[has_src, "adj_source"].unique())
    assert seen == {"vendor", "vendor_patched", "vendor_carried",
                    "rebuilt_factored", "rebuilt_noevent"}, (
        f"README documents five adj_source values; these stocks exercise {seen}"
    )
    return (f"adj_source present exactly where a price is; exercises "
            f"{sorted(seen)}"), rows


# ---- Taiwan: when a fundamental could first have been read ------------------
def test_taiwan_filing_deadline_table_covers_the_data():
    """README caveat 9: every period end in the tree resolves to a deadline.

    `available_date` raises rather than returning NaT for a period end no rule
    covers, which is only a safeguard if something exercises it against the
    whole tree — a NaT would otherwise surface as rows quietly dropped from a
    join. This also pins the 2012 regime boundary, which is the reason the
    deadlines are a versioned table instead of two constants.
    """
    sys.path.insert(0, str(REPO))
    import pyarrow.parquet as pq

    from finmind_data.available_date import available_date, with_available_date

    resolved = 0
    for sub, kind, n_ends in (("fin_is", "financial_statement", 62),
                              ("fin_bs", "financial_statement", 59),
                              ("fin_cf", "financial_statement", 62),
                              ("month_rev", "monthly_revenue", 188)):
        ends = set()
        for f in sorted(glob.glob(str(REPO / f"finmind_data/{sub}/*.parquet"))):
            if not pq.ParquetFile(f).metadata.num_rows:
                continue
            ends |= set(_tree(f, columns=["date"])["date"])
        # The count, not merely presence: this test's whole subject is that the
        # deadline table spans the tree, and a tree that had shrunk to one
        # period end would be spanned by any table at all.
        assert len(ends) == n_ends, (
            f"{sub}/ holds {len(ends)} distinct period ends against the {n_ends} "
            f"the deadline table was checked to span. A download that widened or "
            f"narrowed the tree owes filing_deadlines.csv a re-check"
        )
        got = available_date(sorted(ends), kind=kind)          # raises if unruled
        resolved += len(got)
        assert (got.to_numpy() > pd.Series(sorted(ends)).to_numpy()).all(), (
            f"{sub}: some rows are available on or before the period they "
            f"describe, which is look-ahead rather than a bound on it"
        )

    # 證交法 §36 as amended 2010-06-02, in force 2012-01-01: the annual report
    # goes from four months to three. The half-year goes from a 75-day
    # consolidated back-stop to 45 days a year later — §183 defers §36 I(2) to
    # 一百零二會計年度 — so the two rules break in different years and a constant
    # fitted to either side is wrong for a third of the window. 2012-06-30 is
    # the quarter that separates the two readings and is pinned for that.
    want = {"2010-12-31": "2011-04-30", "2011-06-30": "2011-09-13",
            "2011-12-31": "2012-03-31", "2012-06-30": "2012-09-13",
            "2013-06-30": "2013-08-14", "2024-12-31": "2025-03-31"}
    got = available_date(pd.to_datetime(list(want)))
    for (pe, exp), g in zip(want.items(), got):
        assert g == pd.Timestamp(exp), (
            f"README dates the {pe} period as available {exp}; "
            f"filing_deadlines.csv now gives {g.date()}"
        )

    # The lag is a research parameter, and `date` is never overwritten.
    d = _tree(REPO / "finmind_data/fin_is/2330.parquet")
    a = with_available_date(d)
    b = with_available_date(d, extra_days=15)
    assert (a["date"] == d["date"]).all() and (b["date"] == d["date"]).all(), (
        "with_available_date overwrote `date`, destroying the key that says "
        "which fiscal period a figure belongs to"
    )
    assert ((b["available_date"] - a["available_date"])
            == pd.Timedelta(days=15)).all(), "extra_days is not additive"

    # The result carries the caller's index. Without that, assigning it onto a
    # filtered frame aligns against a RangeIndex the frame no longer has and
    # fills NaN, which reads downstream as an unruled period rather than as a
    # join that silently missed.
    filtered = d[d["date"] >= "2015-01-01"].copy()
    assert filtered.index[0] != 0, "the case needs a frame whose index was cut"
    filtered["deadline"] = available_date(filtered["date"])
    assert filtered["deadline"].notna().all(), (
        f"available_date reindexed its input, so "
        f"{filtered['deadline'].isna().sum()} of {len(filtered)} deadlines "
        f"assigned onto a filtered frame came back NaT"
    )
    return (f"all {resolved} period ends in fin_is/fin_bs/fin_cf/month_rev "
            f"resolve; 2012 regime boundary holds; extra_days additive; the "
            f"result keeps the caller's index"), resolved


def test_taiwan_month_rev_date_is_the_following_month():
    """The premise the monthly-revenue deadline rests on.

    `month_rev.date` is the first of the month *after* the revenue month —
    2005-01-01 carries `revenue_month` 12 of 2004 — so the 10th-of-the-month
    deadline is nine days later, not a month and nine days. If FinMind ever
    re-keys the table on the revenue month, the deadline silently becomes a
    month too early and every monthly signal gains a month of look-ahead.
    """
    import pyarrow.parquet as pq

    rows = off = first = 0
    for f in sorted(glob.glob(str(REPO / "finmind_data/month_rev/*.parquet"))):
        if not pq.ParquetFile(f).metadata.num_rows:
            continue
        d = _tree(f, columns=["date", "revenue_month", "revenue_year"])
        dt = pd.to_datetime(d["date"])
        per = pd.to_datetime(dict(year=d["revenue_year"], month=d["revenue_month"],
                                  day=1))
        rows += len(d)
        first += int((dt.dt.day == 1).sum())
        off += int((((dt.dt.year * 12 + dt.dt.month)
                     - (per.dt.year * 12 + per.dt.month)) == 1).sum())
    assert rows and off == rows and first == rows, (
        f"README claims month_rev.date is the first of the month after the "
        f"revenue month on every row; {rows - off:,} of {rows:,} are a "
        f"different offset and {rows - first:,} are not the first of a month"
    )
    return (f"month_rev.date is the 1st of the month after revenue_month on "
            f"all {rows:,} rows"), rows



def test_taiwan_mops_covers_every_delisted_name():
    """README caveat 8: the 主旨 was pulled for all 164, not for the servable few.

    The two MOPS hosts disagree about delisted companies, and the legacy one
    answers for 14 of the 164. A pull that ran against it would return a corpus
    that looks complete — every file non-empty, every request answered — over a
    twelfth of the frame. This asserts the corpus spans the frame, so a rerun
    pointed at the wrong host fails here rather than shrinking the population a
    reason is later read from.
    """
    frame = pd.read_parquet(REPO / "finmind_data/delisting_sign.parquet")
    d = REPO / "finmind_data/mops_listing"
    if not d.exists():
        raise Skipped("mops_listing/ not built — run `mops_filings.py listings`")
    files = {p.stem for p in d.glob("*.parquet")}
    missing = sorted(set(frame.stock_id) - files)
    assert not missing, (
        f"README caveat 8 says 重大訊息 were pulled for every one of the "
        f"{len(frame)} in-window commons; {len(missing)} have no file "
        f"({missing[:5]}), so any reason read from this corpus is read over a "
        f"smaller frame than the caveat claims"
    )
    rows = pd.concat([pd.read_parquet(p) for p in d.glob("*.parquet")],
                     ignore_index=True)
    empty = sorted(f for f in files if not len(pd.read_parquet(d / f"{f}.parquet")))
    assert not empty, (
        f"a company with zero announcements cannot have its reason read; "
        f"{len(empty)} files are empty ({empty[:5]})"
    )
    assert len(rows) >= 19_000, (
        f"README caveat 8 puts 19,949 announcements in this corpus; it now "
        f"holds {len(rows)}. A pull that shrank means the host changed what it "
        f"serves, and the reasons downstream were read from more than survives"
    )
    return (f"{len(rows)} 主旨 across {len(files)} names, none empty", len(rows))


def test_taiwan_mops_detail_gate_is_registration_not_filing():
    """README caveat 8: 說明 is refused for a company that deregistered.

    The refusal is the coverage figure, so it is asserted rather than logged:
    if MOPS starts serving the bodies, the caveat's claim that a consideration
    must still be read one filing at a time is obsolete and the 說明 for 150
    names is sitting there unread.
    """
    path = REPO / "finmind_data/mops_detail_refusals.csv"
    if not path.exists():
        raise Skipped("mops_detail_refusals.csv not built — "
                      "run `mops_filings.py details`")
    ref = pd.read_csv(path, dtype={"stock_id": str})
    ref = ref[ref["stage"] == "details"]
    frame = pd.read_parquet(REPO / "finmind_data/delisting_sign.parquet")
    served = len(frame) - len(ref)
    assert served == 14, (
        f"README caveat 8 says MOPS serves the 說明 for 14 of the "
        f"{len(frame)} and refuses 150; it now serves {served}. If that grew, "
        f"the consideration is readable for more names than the caveat admits"
    )
    off_script = ref.loc[~ref["refusal"].str.contains(
        "不繼續公開發行|已下市", regex=True, na=False), "stock_id"]
    assert not len(off_script), (
        f"caveat 8 says the gate is the company's registration, in one of two "
        f"sentences; {len(off_script)} names were refused for some other "
        f"reason ({sorted(off_script)[:5]}), so the gate is not what is claimed"
    )
    return (f"{served} names serve a 說明, {len(ref)} refused on registration",
            len(ref))


def test_taiwan_swap_ratio_quotes_the_filing_it_names():
    """README caveat 8: every swap ratio read off a filing is still in it.

    The direction of a swap ratio is the thing this package cannot afford to
    get from the number itself — `0.3168568` and `3.1560` are the same deal and
    the wrong one is a 216 % error — so `swap_ratios.py` goes to the acquirer,
    whose filing states it in a sentence, and each row's `source` carries that
    sentence in 「」. This asserts the sentence is really there: the quote is
    matched against the cached body of a filing on one of the dates the source
    names, with whitespace flattened because MOPS wraps mid-clause.

    That is the whole binding. A ratio whose quote no longer resolves is a
    number with a citation and no source, which is the state the labels were in
    before this route existed and the one thing a plausible-looking table hides
    best.
    """
    quoted = re.compile("「([^」]+)」")
    roc = re.compile(r"\b\d{2,3}/\d{2}/\d{2}\b")
    flat = lambda s: re.sub(r"\s+", "", s or "")
    cons = pd.read_csv(REPO / "finmind_data/delisting_consideration.csv",
                       dtype={"stock_id": str, "successor": str})
    rows = [r for r in cons.itertuples() if quoted.search(r.source or "")]

    unresolved = []
    for r in rows:
        # `source` says whose filing it is: the target's own where MOPS still
        # serves it, the acquirer's otherwise. Reading the routing out of the
        # sentence keeps the two caches from being interchangeable by accident.
        sub = "mops_detail" if "own filing" in r.source else "mops_acquirer_detail"
        path = REPO / f"finmind_data/{sub}/{r.stock_id}.parquet"
        if not path.exists():
            raise Skipped(f"{sub}/{r.stock_id}.parquet not built — "
                          "run `swap_ratios.py`")
        det = pd.read_parquet(path)
        want = flat(quoted.search(r.source).group(1))
        on = {d for d in det.loc[det["body"].fillna("").map(
            lambda b: want in flat(b)), "spoke_date"]}
        if not (on & set(roc.findall(r.source))):
            unresolved.append(f"{r.stock_id} (quote on {sorted(on) or 'nothing'},"
                              f" source names {roc.findall(r.source)})")
    assert not unresolved, (
        f"README caveat 8 says each swap ratio's direction was read off the "
        f"filing its row quotes; {unresolved} no longer resolve to a cached "
        f"body on a date the row names, so their `per_share` is uncited"
    )

    # The route's boundary, asserted for the same reason the target-side gate
    # is: it is a coverage figure. An acquirer that was itself later bought is
    # refused in the same words as a target, and the five that are out are why
    # seven of the seventeen in-frame swaps still have no ratio.
    refused = pd.read_csv(REPO / "finmind_data/mops_acquirer_refusals.csv",
                          dtype=str)
    off_script = refused.loc[~refused["refusal"].str.contains(
        "不繼續公開發行|已下市", regex=True, na=False), "target_id"]
    assert len(refused) == 5 and not len(off_script), (
        f"caveat 8 says five deals are out because the buyer deregistered "
        f"after the deal, refused on the same registration sentence as a "
        f"target; there are now {len(refused)}, {len(off_script)} of them "
        f"refused for some other reason. Fewer means a ratio is readable that "
        f"the caveat calls unreachable"
    )
    served = {r.stock_id for r in rows if "own filing" not in r.source}
    assert not (served & set(refused["target_id"])), (
        f"{sorted(served & set(refused['target_id']))} are recorded as both "
        f"refused and quoted from the acquirer's body, so one of the two files "
        f"is stale"
    )
    return (f"{len(rows)} ratios quote a filing on a date they name, "
            f"{len(refused)} deals refused at the acquirer", len(rows))


def test_taiwan_mops_reason_empties_the_undecided_band():
    """README caveat 8: the filings decide 30 of the 37 the price shape did not.

    This is what the pull bought. The band is the set the single cut is
    registered against, and the claim is that a filing settles most of it
    without the cut — so if the reader shrinks, the cut is carrying names the
    caveat says it no longer has to.
    """
    path = REPO / "finmind_data/mops_reason.parquet"
    if not path.exists():
        raise Skipped("mops_reason.parquet not built — run `mops_reason.py`")
    r = pd.read_parquet(path)
    amb = r[r["price_shape_sign"] == "ambiguous"]
    decided = amb[amb["reason"] != "unknown"]
    assert len(amb) == 37, (
        f"README caveat 8 counts 37 names the shape left undecided; the frame "
        f"now holds {len(amb)}, so the band this claim is about has moved"
    )
    assert len(decided) == 30, (
        f"README caveat 8 says the filings decide 30 of the 37 undecided "
        f"names; they now decide {len(decided)}"
    )
    n_mer = int((decided["reason"] == "merger").sum())
    assert n_mer == 19, (
        f"README caveat 8 splits those 30 into 19 payouts and 11 failures; "
        f"the split is now {n_mer} and {len(decided) - n_mer}"
    )
    return (f"band {len(amb)} -> {len(decided)} decided "
            f"({n_mer} payout, {len(decided) - n_mer} failure)", len(amb))


def test_taiwan_mops_overturns_only_failures_the_tape_missed():
    """README caveat 8: two overturns, both the same error, one of them 1613.

    The caveat used to describe its error mode with one name because one name
    was labelled. The filings put two in the 127 the shape decided, both a
    removal the tape read as a payout and neither the other way. A third, or
    one running the other direction, means the described error mode is no
    longer the one the data shows — which is the same contract the labelled
    miss is held to. It stood at four until the statute behind 53-17 was read
    (`test_taiwan_exchange_provision_markers_match_what_they_govern`); two of
    the four were the rule misreading a share swap, not the tape missing a
    failure.
    """
    path = REPO / "finmind_data/mops_reason.parquet"
    if not path.exists():
        raise Skipped("mops_reason.parquet not built — run `mops_reason.py`")
    r = pd.read_parquet(path)
    d = r[(r["price_shape_sign"] != "ambiguous") & (r["reason"] != "unknown")]
    over = d[d["price_shape_sign"] != d["reason"]]
    wrong_way = over[over["reason"] != "distress"]
    assert not len(wrong_way), (
        f"README caveat 8 says every overturn runs the same way — a removal "
        f"the tape read as a payout; {len(wrong_way)} now run the other way "
        f"({sorted(wrong_way['stock_id'])}), so the error mode is not one-sided"
    )
    got = sorted(over["stock_id"])
    assert got == ["1613", "3562"], (
        f"README caveat 8 names the two overturns 1613 and 3562; they are now "
        f"{got}. The sentence describing what the shape gets wrong no longer "
        f"matches the filings"
    )
    return (f"{len(over)} overturns, all payout->failure: {got}", len(d))


def test_taiwan_exchange_provision_markers_match_what_they_govern():
    """README caveat 8: one exchange provision is a merger marker, the other is
    no marker at all, and the second is a gap this frame cannot afford to close.

    An article number is the one subject that says nothing on its face, so what
    it is worth has to come from the statute and not from the words around it.
    營業細則第五十三條之十七 governs a single transaction — a listed company
    swapping its shares to an unlisted existing company under 企業併購法第34條
    and delisting on the swap's record date — and was read here as a suspension
    removal until 2026-08-25, which is what put 5305 and 8497 among the
    overturns. Nothing in the rule's output could show that: a misread statute
    returns a verdict, not an error. So the reading is bound to the transaction
    it names, and a citer that files no swap fails here.

    The TPEx notice is not the analogue it was described as — it suspends
    trading or changes the trading method — and its counterfactual is asserted
    rather than described, because the prose version of it counted the
    companies filing a notice and printed that as the names adopting it would
    decide. Six file one and two would move, and both numbers were true of
    something.
    """
    sys.path.insert(0, str(REPO))
    path = REPO / "finmind_data/mops_reason.parquet"
    if not path.exists():
        raise Skipped("mops_reason.parquet not built — run `mops_reason.py`")
    from finmind_data import mops_reason as M

    r = pd.read_parquet(path).set_index("stock_id")
    subjects = {p.stem: pd.read_parquet(p)["subject"].fillna("")
                for p in sorted((REPO / "finmind_data/mops_listing").glob("*.parquet"))}
    cites = lambda pat: sorted(k for k, v in subjects.items()
                               if v.str.contains(pat, regex=True).any())

    # The provision applies to one transaction, so a company citing it has said
    # which one; the swap filing under its own name is that transaction on the
    # record. `_subjects` is the rule's own window rather than a second copy.
    twse = cites(r"五十三條之十七|53條之17")
    assert twse == ["5305", "8497"], (
        f"README caveat 8 names 5305 and 8497 as the two 53-17 citers; the "
        f"archive now cites it for {twse}"
    )
    for sid in twse:
        row = r.loc[sid]
        assert (row["reason"], row["basis"]) == ("merger", "anchor"), (
            f"README caveat 8 says 53-17 decides {sid} as a merger at the "
            f"anchor because the provision governs only a share swap; it now "
            f"reads {row['reason']} on the {row['basis']}"
        )
        w = M._subjects(sid, pd.Timestamp(row["delist_date"]))
        own = w["subject"].fillna("")
        own = own[~own.str.contains(M.SUBSIDIARY_PROXY, regex=True)]
        assert own.str.contains("股份轉換", regex=True).any(), (
            f"{sid} cites 53-17 but files no 股份轉換 of its own in the window. "
            f"The provision governs that transaction and no other, so either "
            f"the statute reading in `mops_reason.py` is wrong or this is a "
            f"citation to something the rule has never seen"
        )

    # The TPEx side, and why it stays out. Adopting the rule name would decide
    # names the score is read against, in the direction their labels already
    # say — fitting on the scoring set, which is what the order in
    # `mops_reason.py`'s docstring exists to prevent.
    tpex = r"證券商營業處所買賣有價證券業務規則"
    assert not re.search(tpex, M.MERGER) and not re.search(tpex, M.DISTRESS), (
        "the TPEx business rule has been adopted as a marker; caveat 8 records "
        "it as an open gap because adopting it fits the scoring set"
    )
    filers = cites(tpex)
    assert len(filers) == 6, (
        f"README caveat 8 says 6 companies file a TPEx business-rule notice; "
        f"{len(filers)} do now ({filers})"
    )
    lab = pd.read_csv(REPO / "finmind_data/delisting_labels.csv",
                      dtype={"stock_id": str}).set_index("stock_id")["label"]
    base = M.build().set_index("stock_id")["reason"]
    stated = M.DISTRESS
    M.DISTRESS = stated + "|" + tpex
    try:
        alt = M.build().set_index("stock_id")["reason"]
    finally:
        M.DISTRESS = stated
    alt = alt.reindex(base.index)
    moved = sorted(base.index[base != alt])
    assert moved == ["1333", "6497"], (
        f"README caveat 8 says adopting the TPEx notice moves 1333 and 6497; "
        f"it now moves {moved}, so the sentence pricing the gap is wrong"
    )
    unlabelled = [s for s in moved if s not in lab.index]
    assert not unlabelled, (
        f"caveat 8 declines the TPEx notice because every name it decides is "
        f"one the score is read against; {unlabelled} now carry no label, so "
        f"the gap could be closed on names the score does not spend"
    )
    fitted = [s for s in moved if alt[s] == lab[s]]
    assert fitted == moved, (
        f"caveat 8 calls adopting the notice a recalibration on the scoring "
        f"set — it decides labelled names into their own labels; {sorted(set(moved) - set(fitted))} "
        f"would now be decided against the label, which is a different finding"
    )
    return (f"{len(twse)} names cite 53-17 and file the swap it governs, "
            f"{len(filers)} cite the TPEx rule that stays out because adopting "
            f"it decides {len(moved)} labelled names into their labels",
            len(twse) + len(filers))


def test_taiwan_mops_reason_scored_against_the_hand_labels():
    """README caveat 8: the subject rule against the corrected hand labels.

    The labels were read off announcements by hand and the rule reads the same
    filings mechanically, so this is the rule's error rate against the best
    reading the package owns. It is not an independent one, and caveat 8 says
    so: the two parted on 8420, the parting is what sent the filings to be
    read, and the label was the side that moved. 41 of 42 against the sheet as
    drawn is the number with provenance. What this asserts is that nothing
    parts now, so a rule that drifts arrives here by name.
    """
    path = REPO / "finmind_data/mops_reason.parquet"
    if not path.exists():
        raise Skipped("mops_reason.parquet not built — run `mops_reason.py`")
    r = pd.read_parquet(path)
    lab = pd.read_csv(REPO / "finmind_data/delisting_labels.csv",
                      dtype={"stock_id": str})[["stock_id", "label"]]
    m = r.merge(lab, on="stock_id", how="inner")
    dec = m[m["reason"] != "unknown"]
    assert len(dec) >= 40, (
        f"the rate needs names the rule decided *and* a hand label reads; "
        f"only {len(dec)} qualify now, so the score is over a sample too "
        f"small for the caveat's sentence"
    )
    miss = sorted(dec.loc[dec["reason"] != dec["label"], "stock_id"])
    assert miss == [], (
        f"README caveat 8 says the rule and the corrected labels agree on all "
        f"{len(dec)}; they now part on {miss}. 8420 was the one parting and it "
        f"closed by correcting the label, so a name here is the rule drifting "
        f"rather than a label left to re-read"
    )
    return (f"{len(dec)}/{len(dec)} agree with the hand labels, one of them "
            f"(8420) because the label was corrected to match", len(dec))



def test_taiwan_anchor_overrides_agree_with_their_own_window():
    """README caveat 8: the decision path the hand-label score is blind to.

    `read_one` lets a naming anchor outrank the window vote, on the ground that
    the filing about this exit outranks anything counted around it. That is the
    rule's strongest move and its least witnessed one: 14 of the 17 names it
    decides carry no hand label, against 39 of the 129 the window decides. So
    the score above is computed over a set that mostly excludes the path most
    able to be wrong, and labels are the scarce input, so it cannot be fixed by
    spending them here.

    What needs no labels is the rule's own second opinion. Where an anchor
    decides *against* the window it sits in, one of the two readings is wrong
    and a reader is owed the name whether or not anyone has labelled it. A
    silent window abstains rather than dissents — that is the case the anchor
    exists to decide — so only a window carrying markers the other way counts.

    Empty is the shape of a check that verifies nothing, so the detector is
    exercised rather than trusted. Restoring 五十三條之十七 to the distress
    pattern, where it sat until it was read against the statute, makes this
    return 5305 and 8497: the two names the label score could not reach,
    because neither carries a label. Both halves are asserted, so an empty
    result stays evidence.
    """
    sys.path.insert(0, str(REPO))
    path = REPO / "finmind_data/mops_reason.parquet"
    if not path.exists():
        raise Skipped("mops_reason.parquet not built — run `mops_reason.py`")
    from finmind_data import mops_reason as M

    def contradicted(frame):
        """Anchor-decided names whose own window votes the other way."""
        out = []
        for t in frame[frame["basis"] == "anchor"].itertuples():
            w = ("merger" if t.n_merger_subjects > t.n_distress_subjects else
                 "distress" if t.n_distress_subjects > t.n_merger_subjects else
                 "silent")
            if w not in (t.reason, "silent"):
                out.append(t.stock_id)
        return sorted(out)

    r = pd.read_parquet(path)
    lab = set(pd.read_csv(REPO / "finmind_data/delisting_labels.csv",
                          dtype={"stock_id": str})["stock_id"])
    anchors = r[r["basis"] == "anchor"]
    unwitnessed = sorted(set(anchors["stock_id"]) - lab)

    split = contradicted(r)
    assert split == [], (
        f"README caveat 8 says every anchor override agrees with the window it "
        f"sits in; {split} now decide against their own window, so one of the "
        f"two readings is wrong. Read the filings for these before the frame is "
        f"quoted again — {sorted(set(split) - lab)} carry no hand label, so "
        f"nothing else in this file is looking at them"
    )

    # The detector is the claim here, so it is run against the defect it was
    # written from rather than trusted for having returned nothing.
    mer, dis = M.MERGER, M.DISTRESS
    M.MERGER = mer.replace(r"五十三條之十七|53條之17|", "")
    M.DISTRESS = dis + r"|五十三條之十七|53條之17"
    try:
        premove = contradicted(M.build())
    finally:
        M.MERGER, M.DISTRESS = mer, dis
    assert premove == ["5305", "8497"], (
        f"with 53-17 read as distress, the window contradiction is what names "
        f"5305 and 8497; it now names {premove}, so an empty result above is no "
        f"longer evidence that the anchors agree"
    )
    assert not (set(premove) & lab), (
        f"this check earns its place by reaching names the labels cannot, and "
        f"{sorted(set(premove) & lab)} are labelled now — the demonstration "
        f"needs a defect the label score still could not see"
    )

    return (f"{len(anchors)} anchor overrides all agree with their own window, "
            f"{len(unwitnessed)} of them carrying no hand label; the same test "
            f"names 5305 and 8497 under the statute misreading", len(anchors))



def test_taiwan_silent_names_keep_their_unknown():
    """README caveat 8: why the 18 silent names are not a pattern gap to close.

    Silence here is never missing data — every one of the 18 carries between 18
    and 191 filings in its window, so the rule read them and matched nothing.
    That invites filling the gap with the vocabulary those filings do use, and
    the two words a reader reaches for first are measured here instead, because
    both fail in ways their own hit rate hides.

    繼續經營 is a real auditor's finding and a weak delisting marker: it sits in
    13 of the 164 windows, and among the names already decided it splits 8
    distress to 3 merger. A company can be doubted as a going concern and then
    be bought. Adopting it decides two names on 73 % precision, which is the
    likelier of two guesses the module docstring declines to make.

    保留意見 is worse, and its counterfactual is the reason this check exists
    rather than a sentence. Adopting it naively moves three names and one of
    them, 3536, lands on its own hand label — so the sheet certifies it. The
    match is on 無保留意見, an *un*qualified opinion, which is the auditor
    saying the accounts are clean. Requiring the negation to be absent drops
    3536 back out, which is the proof the agreement was luck: the label was
    right about the company and had no way to be wrong about the rule. A marker
    scored only where it fires cannot show this, and neither can the hand-label
    score above.
    """
    sys.path.insert(0, str(REPO))
    path = REPO / "finmind_data/mops_reason.parquet"
    if not path.exists():
        raise Skipped("mops_reason.parquet not built — run `mops_reason.py`")
    from finmind_data import mops_reason as M

    r = pd.read_parquet(path)
    lab = pd.read_csv(REPO / "finmind_data/delisting_labels.csv",
                      dtype={"stock_id": str}).set_index("stock_id")["label"]
    silent = r[r["basis"] == "silent"]
    span = (int(silent["n_subjects_in_window"].min()),
            int(silent["n_subjects_in_window"].max()))
    assert span == (18, 191), (
        f"README caveat 8 says the silent names carry 18 to 191 filings each, "
        f"so their silence is the rule matching nothing rather than there being "
        f"nothing to match; the span is {span} now, and a low end at zero would "
        f"make this a coverage hole instead"
    )

    def moves(add, where="DISTRESS"):
        """Names whose reason changes when a candidate marker is adopted."""
        base = M.build().set_index("stock_id")["reason"]
        saved = getattr(M, where)
        setattr(M, where, saved + "|" + add)
        try:
            alt = M.build().set_index("stock_id")["reason"]
        finally:
            setattr(M, where, saved)
        alt = alt.reindex(base.index)
        return sorted(base.index[base != alt])

    # A going-concern paragraph is evidence about the company, not about the
    # exit: the names carrying it are already decided both ways.
    carriers = {t.stock_id: t.reason for t in r.itertuples()
                if M._subjects(t.stock_id, pd.Timestamp(t.delist_date))
                     ["subject"].fillna("").str.contains("繼續經營", regex=True).any()}
    decided = pd.Series([v for v in carriers.values() if v != "unknown"])
    split = (int((decided == "distress").sum()), int((decided == "merger").sum()))
    assert (len(carriers), split) == (13, (8, 3)), (
        f"README caveat 8 keeps 繼續經營 out on 13 windows splitting 8 distress "
        f"to 3 merger; it is {len(carriers)} windows at {split} now, and a split "
        f"this rule could act on would change that paragraph rather than pass here"
    )

    # The trap: the naive form matches 無保留意見, and the label rewards it.
    naive, negated = moves(r"保留意見"), moves(r"(?<!無)保留意見")
    assert naive == ["3536", "4408", "6131"], (
        f"caveat 8 names 3536, 4408 and 6131 as what the naive 保留意見 moves; "
        f"it moves {naive} now"
    )
    assert "3536" not in negated and lab.get("3536") == "distress", (
        f"the argument is that 3536 agreed with its label on a match inside "
        f"無保留意見: excluding the negation has to drop it, and it stays in "
        f"{negated} with label {lab.get('3536')!r}"
    )
    assert not (set(negated) & set(lab.index)), (
        f"neither name the negated form still moves carries a hand label, which "
        f"is why the sheet could not have caught this; {sorted(set(negated) & set(lab.index))} "
        f"do now, so the counterfactual needs restating"
    )

    return (f"{len(silent)} silent names carry {span[0]}-{span[1]} filings each; "
            f"繼續經營 splits {split[0]}/{split[1]} across decided names and "
            f"保留意見 wins its one labelled name by matching 無保留意見",
            len(silent))


def test_taiwan_reason_frame_is_frozen():
    """README Provenance: the composition downstream work is built against.

    The frame's shape is what a model inherits, and a population count does not
    hold it: the counts move against each other inside a constant 164. Which
    part of the shape was actually unwatched was measured rather than assumed,
    by moving three names and running the other checks.

    `reason` turned out to be guarded from the side. Flipping three merger names
    to distress trips `test_taiwan_mops_overturns_only_failures_the_tape_missed`
    whether or not they carry hand labels, because a reason that now contradicts
    its price shape is a new overturn — so that margin was never the gap.

    `basis` is. Re-basing three names from window to anchor with `reason`
    untouched leaves every other check green, because nothing else reads the
    column. It is also the cell that matters most: `basis` is what says how much
    of the frame rests on the anchor path, which the hand labels barely witness
    (caveat 8), so it can grow without a single assertion noticing that the
    least-checked rule is deciding more of the data.

    The label denominators are pinned here for a different reason. The obvious
    join, 68 labels against 164 names, scores the rule at 42/68 and is wrong
    three ways at once: 20 of the labels are pre-window `prior` rows that were
    never in the frame, and 6 of the 48 that are in it name a company the rule
    declines to decide, which is an abstention and not a miss. The published
    42/42 is over the 42 the rule commits on. Asserting the identity means the
    two files cannot drift apart silently — a label added without a frame name
    behind it, or a frame name that loses its label, breaks the arithmetic
    rather than quietly re-basing a percentage nobody recomputes.
    """
    path = REPO / "finmind_data/mops_reason.parquet"
    if not path.exists():
        raise Skipped("mops_reason.parquet not built — run `mops_reason.py`")
    r = pd.read_parquet(path)

    span = (r["delist_date"].min().date().isoformat(),
            r["delist_date"].max().date().isoformat())
    assert span == ("2011-05-02", "2024-11-29"), (
        f"README Provenance freezes this frame over 2011-05-02..2024-11-29; it "
        f"now spans {span[0]}..{span[1]}, so the frame is not the one the "
        f"baseline was recorded for"
    )

    # The joint, not the two margins: the README reads the cells off it — that
    # silence and `unknown` are the same 18 names, that the anchor decides 15
    # mergers against 2 distress — and a pair of marginal counts is satisfied by
    # arrangements where neither holds.
    cells = {f"{a}/{b}": int(n) for (a, b), n
             in r.groupby(["reason", "basis"]).size().items()}
    assert cells == {"distress/anchor": 2, "distress/window": 32,
                     "merger/anchor": 15, "merger/window": 97,
                     "unknown/silent": 18}, (
        f"README Provenance freezes this frame at 112 merger / 34 distress / 18 "
        f"unknown, decided 129 window / 17 anchor / 18 silent; the joint is now "
        f"{cells}. A downstream split conditioned on `reason` is conditioned on "
        f"a different population, and a moved anchor cell changes how much of "
        f"the frame rests on the path the hand labels barely witness"
    )
    reason = r["reason"].value_counts().to_dict()
    basis = r["basis"].value_counts().to_dict()

    lab = pd.read_csv(REPO / "finmind_data/delisting_labels.csv",
                      dtype={"stock_id": str})
    got = r.set_index("stock_id")["reason"].reindex(lab["stock_id"])
    # `pre_window` here is frame membership, not the sheet's own `purpose`
    # column — that carries a value spelled `prior` which tags 27 rows for a
    # different reason and does not partition the frame.
    pre_window_n = int(got.isna().sum())
    declined = int((got == "unknown").sum())
    scored = len(lab) - pre_window_n - declined
    assert (len(lab), scored, declined, pre_window_n) == (68, 42, 6, 20), (
        f"README Provenance freezes the label sheet as 68 = 42 scored + 6 the "
        f"rule declines + 20 pre-window; it is now {len(lab)} = {scored} + "
        f"{declined} + {pre_window_n}. The published 42/42 has a denominator of "
        f"42, not {len(lab)} — re-derive it before quoting the score again"
    )
    # Why those 20 are absent, asserted as an identity rather than assumed: the
    # frame opens on its first delisting, and they predate it. A label naming an
    # in-window company the frame does not carry is a hole in the frame, not a
    # stale label, and only the two-way form tells them apart.
    absent = set(lab["stock_id"]) - set(r["stock_id"])
    pre_window = set(lab.loc[pd.to_datetime(lab["delist_date"], format="ISO8601")
                             < r["delist_date"].min(), "stock_id"])
    assert absent == pre_window, (
        f"every label with no frame name should be one that predates the frame; "
        f"{sorted(absent - pre_window)} delisted in-window and are missing from "
        f"it, and {sorted(pre_window - absent)} predate it and are in it"
    )

    return (f"frame frozen at {len(r)} names {span[0]}..{span[1]}: "
            f"{reason['merger']} merger / {reason['distress']} distress / "
            f"{reason['unknown']} unknown, decided {basis['window']} window / "
            f"{basis['anchor']} anchor / {basis['silent']} silent; labels "
            f"{len(lab)} = {scored} scored + {declined} declined + "
            f"{pre_window_n} pre-window",
            len(r))

def test_taiwan_filing_dates_cover_the_statement_trees():
    """README caveat 9: every company holding a statement is dated.

    The panel exists to say when a figure became public, so a company missing
    from it silently falls back on the deadline — the very bound the caveat says
    is wrong for one quarter in fifteen. Asserting the frames match means a tree
    added later fails here rather than being dated by a rule nobody chose.

    The first assertion ranges over the companies whose tree carries rows, not
    over the tree files. A file is written for every name in the universe and
    182 of them are empty, so the two sets differ by whether the vendor served
    a statement — and a company with no statement has nothing that could fall
    back on a deadline, which is the whole failure this looks for. 181 of the
    182 are dated anyway, because the document server carries filings FinMind
    does not serve; the exception is 3718, a holding company listed on
    2026-09-10 whose page is empty on both the plain and the holdco route while
    its delisted predecessor's carries 382 documents. Requiring a filing date
    for a company that has filed nothing asks the server for a date that does
    not exist.

    The second assertion still ranges over every tree file, because it asks the
    opposite question: a dated code with no tree at all is a page answered for
    someone else, and narrowing that set would turn the 181 into failures.
    """
    import pyarrow.parquet as pq

    path = REPO / "finmind_data/filing_dates.parquet"
    if not path.exists():
        raise Skipped("filing_dates.parquet not built — "
                      "run `filing_dates.py` then `--consolidate`")
    d = pd.read_parquet(path)
    trees, holding = set(), set()
    for f in (REPO / "finmind_data/fin_is").glob("*.parquet"):
        trees.add(f.stem)
        if pq.read_metadata(f).num_rows:
            holding.add(f.stem)
    missing = sorted(holding - set(d["stock_id"]))
    assert not missing, (
        f"README caveat 9 dates all {len(holding)} companies whose statement "
        f"tree carries rows; {len(missing)} have no filing dates "
        f"({missing[:5]}), so their statements would be dated by the deadline "
        f"the caveat says is a bound and not a date"
    )
    extra = sorted(set(d["stock_id"]) - trees)
    assert not extra, (
        f"{len(extra)} companies carry filing dates but no statement tree "
        f"({extra[:5]}); the panel is keyed on the code its page was asked "
        f"for, so a stray code means a page answered for someone else"
    )
    undated = int(d["first_public"].isna().sum())
    assert not undated, f"{undated} rows carry no 上傳日期 and date nothing"
    assert len(d) == 164029, (
        f"README caveat 9 consolidates the documents to 164,029 "
        f"company-quarters; the panel holds {len(d):,}")

    # `other` marks the rows the server returns on a company's page under
    # another code. The README calls the four-digit ones earlier codes, which is
    # a claim about order: each company filed under them before it first filed
    # under its own.
    other = d["filed_as"] != d["stock_id"]
    six = other & d["filed_as"].str.fullmatch(r"\d{6}")
    four = other & d["filed_as"].str.fullmatch(r"\d{4}")
    counts = (int(other.sum()), int(six.sum()), int(four.sum()))
    assert counts == (1055, 603, 452), (
        f"README caveat 9 says 1,055 rows are filed under a code other than the "
        f"company's own, 603 under a six-digit registration number and 452 "
        f"under an earlier four-digit code; the panel has {counts}")
    own_first = d[~other].groupby("stock_id")["first_public"].min()
    four_last = d[four].groupby("stock_id")["first_public"].max()
    after = sorted(four_last.index[
        ~(four_last < own_first.reindex(four_last.index))])
    assert not after, (
        f"README caveat 9 calls the four-digit codes earlier ones, and {after} "
        f"filed under another four-digit code after first filing under its own")
    return (f"{len(d):,} company-quarters over {d['stock_id'].nunique():,} "
            f"companies, none undated; {len(holding):,} of {len(trees):,} "
            f"trees carry a statement and every one of them is dated", len(d))


def test_taiwan_filing_dates_drop_reports_filed_before_their_quarter():
    """README caveat 9: 98 documents from 13 companies were uploaded on or
    before the last day of the quarter their filename names, and the panel
    drops them.

    Counted off the collected histories, because the panel no longer holds
    them, and asserted on the panel as well: a panel consolidated without the
    drop fails there while the count still holds. That no observed date moved
    is a claim about the statements, so it ranges over every quarter the three
    trees hold, not only the window's.
    """
    import pyarrow.parquet as pq
    from finmind_data.filing_dates import documents

    path = REPO / "finmind_data/filing_dates.parquet"
    if not path.exists() or not any(
            (REPO / "finmind_data/filing_dates").glob("*.parquet")):
        raise Skipped("filing_dates.parquet or the filing_dates/ histories "
                      "not built")
    d = pd.read_parquet(path)
    bad = d[d["first_public"].dt.normalize() <= d["period_end"]]
    assert not len(bad), (
        f"README caveat 9 says the panel drops every report uploaded on or "
        f"before the last day of its quarter; {len(bad)} rows are, first "
        f"{bad[['stock_id', 'period_end']].head(3).values.tolist()}")

    docs = documents()
    early = docs[docs["upload_ts"].dt.normalize() <= docs["period_end"]]
    got = (len(early), early["stock_id"].nunique())
    assert got == (98, 13), (
        f"README caveat 9 says 98 documents from 13 companies were uploaded on "
        f"or before the last day of the quarter their filename names; the "
        f"histories hold {got}")
    q1 = docs.loc[(docs["stock_id"] == "3087")
                  & (docs["period_end"].dt.month == 3)
                  & (docs["period_end"].dt.year >= 2005), "upload_ts"]
    assert (len(q1) and (q1.dt.month == 2).all()
            and q1.dt.day.between(22, 27).all()), (
        f"README caveat 9 says 3087 uploaded every report it numbered as a "
        f"first quarter from 2005 on between 22 and 27 February; the uploads "
        f"are {sorted(q1.dt.strftime('%Y-%m-%d'))}")
    inwin = sorted(early.loc[early["period_end"].between(COVERAGE_START,
                                                         COVERAGE_END),
                             "stock_id"].unique())
    assert inwin == ["3087", "9104"], (
        f"README caveat 9 says only 3087 and 9104 filed such a report inside "
        f"the window; {inwin} did")

    lost = set(zip(early["stock_id"], early["period_end"]))
    held = []
    for sid in sorted(early["stock_id"].unique()):
        for tree in ("fin_is", "fin_bs", "fin_cf"):
            f = REPO / "finmind_data" / tree / f"{sid}.parquet"
            if not f.exists() or not pq.read_metadata(f).num_rows:
                continue
            dates = pd.to_datetime(pd.read_parquet(f, columns=["date"])["date"])
            held += sorted((tree, sid, str(t.date())) for t in set(dates)
                           if (sid, t) in lost)
    assert not held, (
        f"README caveat 9 says no statement tree holds a quarter one of the 98 "
        f"was filed under, so no statement's observed date moved; {held[:3]}")

    years = set(zip(early["stock_id"], early["period_end"].dt.year))
    frame = d[d["period_end"].between(pd.Timestamp("2011-12-31"),
                                      _LATE_FRAME_END)]
    stay = sorted((s, str(p.date()))
                  for s, p in zip(frame["stock_id"], frame["period_end"])
                  if (s, p.year) in years)
    assert stay == [("3087", "2011-12-31"), ("3087", "2012-12-31")], (
        f"README caveat 9 says the frame keeps two reports from the years these "
        f"were filed in, 3087's under 2011-12-31 and 2012-12-31; it keeps "
        f"{stay}")
    return (f"{got[0]} documents from {got[1]} companies dropped, none of "
            f"their quarters in a statement tree; the panel holds none uploaded "
            f"by its quarter's end, and the frame keeps {len(stay)} from the "
            f"same years", len(docs))


# Caveat 9's late-filing figures are quoted on period ends through 2024-12-31,
# where coverage ended when they were measured. The end does not follow
# `COVERAGE_END`: an end that moved with coverage would move every figure
# quoted on the frame. The move would be large, because the late rate falls
# from the frame's last year on. Right-censoring biases the newest years down,
# since a report enters `filing_dates.parquet` only once it is uploaded.
# `test_taiwan_late_rate_falls_after_the_frame` bounds that bias and finds it
# small next to the fall.
_LATE_FRAME_END = pd.Timestamp("2024-12-31")


def test_taiwan_statements_are_published_after_their_deadline():
    """README caveat 9: 6.56 % of the frame's quarters were published late.

    This is the number the caveat's claim rests on — that joining `fin_is` on
    `available_date` hands a trader one figure in fifteen before it existed. It
    is computed here against the deadline the module actually returns, so a
    change to `filing_deadlines.csv` moves it and this check says by how much.

    Scored on whatever `filing_deadlines.csv` returns, with no correction
    applied here. There used to be one: the table put the 第二季 45-day rule a
    year early, this check patched the FY2012 half-year back to 75 days so a
    table error would not be reported as a market fact, and the rate below was
    always the corrected one. The table now carries §183's deferral itself, so
    the patch is gone and the number is unchanged — which is the evidence that
    it was the same correction in both places.
    """
    from finmind_data.available_date import available_date

    path = REPO / "finmind_data/filing_dates.parquet"
    if not path.exists():
        raise Skipped("filing_dates.parquet not built")
    d = pd.read_parquet(path)
    w = d[(d["period_end"] >= pd.Timestamp("2011-12-31"))
          & (d["period_end"] <= _LATE_FRAME_END)].reset_index(drop=True)
    dl = available_date(w["period_end"])
    late = (w["first_public"].dt.normalize() - dl).dt.days
    n_late = int((late > 0).sum())
    rate = n_late / len(w)
    got = (len(w), n_late, w.loc[late > 0, "stock_id"].nunique(),
           int(late[late > 0].quantile(0.9)), int(late.max()))
    assert got == (93520, 6138, 1421, 234, 1665), (
        f"README caveat 9 says 6,138 of the frame's 93,520 company-quarters, "
        f"across 1,421 companies, were published late, 234 days late at the "
        f"90th percentile and 1,665 at the worst; the panel gives {got}")
    assert math.isclose(rate, 0.0656, abs_tol=0.005), (
        f"README caveat 9 says 6.56 % of the frame's company-quarters were "
        f"published after the deadline; the rate is now {rate:.2%} "
        f"({n_late:,} of {len(w):,})"
    )
    med = int(late[late > 0].median())
    assert med == 15, (
        f"README caveat 9 puts the median lateness at 15 days; it is now {med}"
    )
    on_time = int(-late[late <= 0].median())
    assert on_time == 3, (
        f"README caveat 9 says an on-time filing lands a median 3 days ahead "
        f"of the deadline, which is what makes the deadline a tight bound; "
        f"it is now {on_time}"
    )
    return (f"{n_late:,}/{len(w):,} = {rate:.2%} published late, median "
            f"{med}d; on-time filings land {on_time}d early", len(w))


def test_taiwan_late_rate_falls_after_the_frame():
    """README caveat 9: the late rate falls from the frame's last year on, and
    right-censoring is a small part of the fall.

    A report enters `filing_dates.parquet` only once it is uploaded, so a
    period near the pull is short of the late reports still to come. The bound
    divides a period's late reports by the smallest share of late reports that
    the same period of any year in the frame had uploaded within as many days
    of its deadline as the file now reaches past this one's. A year nearer the
    pull holds no report later than its own reach and so scores a share of
    one, which lets every year in the frame take part without a special case.
    """
    from finmind_data.available_date import available_date

    path = REPO / "finmind_data/filing_dates.parquet"
    if not path.exists():
        raise Skipped("filing_dates.parquet not built")
    d = pd.read_parquet(path)
    last = d["first_public"].max().normalize()
    assert last == pd.Timestamp("2026-08-31"), (
        f"README caveat 9 puts the file's last upload at 2026-08-31; it is now "
        f"{last.date()}")
    d = d[d["period_end"] >= pd.Timestamp("2011-12-31")].reset_index(drop=True)
    deadline = available_date(d["period_end"])
    d["late"] = (d["first_public"].dt.normalize() - deadline).dt.days
    d["reach"] = (last - deadline).dt.days
    frame = d[d["period_end"] <= _LATE_FRAME_END]
    late_days = [(p, g.loc[g["late"] > 0, "late"])
                 for p, g in frame.groupby("period_end")]

    def censored(g):
        """Observed late reports, and how many more the bound allows."""
        share = min((l <= g["reach"].iloc[0]).mean()
                    for p, l in late_days
                    if p.month == g.name.month and len(l))
        n_late = int((g["late"] > 0).sum())
        return pd.Series({"n": len(g), "late": n_late,
                          "missing": n_late * (1 / share - 1)})

    per = d[(d["period_end"] <= _LATE_FRAME_END)
            | (d["period_end"] == pd.Timestamp("2025-12-31"))].groupby(
        "period_end")[["late", "reach"]].apply(censored)

    annual = per[per.index.month == 12]
    annual.index = annual.index.year
    rate = annual["late"] / annual["n"]
    bound = ((annual["late"] + annual["missing"])
             / (annual["n"] + annual["missing"]))
    reach = d[d["period_end"].dt.month == 12].groupby(
        d["period_end"].dt.year)["reach"].first()
    before = rate.loc[2019:2023]
    quoted = {"FY2024": 0.0311, "FY2025": 0.0085, "FY2019-FY2023 min": 0.0666,
              "FY2019-FY2023 max": 0.0768}
    got = {"FY2024": rate[2024], "FY2025": rate[2025],
           "FY2019-FY2023 min": before.min(), "FY2019-FY2023 max": before.max()}
    off = {k: f"{got[k]:.2%}" for k, q in quoted.items()
           if not math.isclose(got[k], q, abs_tol=0.00005)}
    assert not off, (
        f"README caveat 9 says FY2024's annual reports read 3.11 % late and "
        f"FY2025's 0.85 %, against 6.66-7.68 % for FY2019-FY2023; the file "
        f"gives {off}")
    assert (reach[2025], reach[2024]) == (153, 518), (
        f"README caveat 9 says the last upload is 153 days past FY2025's annual "
        f"deadline and 518 days past FY2024's; it is {reach[2025]} and "
        f"{reach[2024]}")

    # A bound is quoted rounded up, since a rounded-down one is false.
    def ceil(x, places):
        return math.ceil(x * 10 ** places) / 10 ** places

    fr = per[per.index <= _LATE_FRAME_END]
    head = fr["late"].sum() / fr["n"].sum()
    lifted = ((fr["late"].sum() + fr["missing"].sum())
              / (fr["n"].sum() + fr["missing"].sum()))
    got = (ceil(bound[2025], 3), ceil(bound[2024], 3), ceil(lifted - head, 4))
    assert got == (0.015, 0.037, 0.0011), (
        f"README caveat 9 says FY2025 will read at most 1.5 % late and FY2024 "
        f"at most 3.7 % on the upload pattern of any year in the frame, and "
        f"that the same bound lifts the frame's 6.56 % by at most 0.11 points; "
        f"the bound gives {bound[2025]:.3%}, {bound[2024]:.3%} and "
        f"{lifted - head:.4%}")

    lag = (d["first_public"].dt.normalize() - d["period_end"]).dt.days
    med = lag[d["period_end"].dt.month == 12].groupby(
        d["period_end"].dt.year).median()
    early = med.loc[2011:2019]
    assert (early.min(), early.max(), med[2024]) == (87, 89, 72), (
        f"README caveat 9 says the annual reports' median upload came 87-89 "
        f"days after year end for FY2011-FY2019 and 72 days after for FY2024; "
        f"it is {early.min():.0f}-{early.max():.0f} and {med[2024]:.0f}")

    short = d[d["period_end"] <= pd.Timestamp("2023-12-31")]
    alt = (short["late"] > 0).mean()
    assert math.isclose(alt, 0.0681, abs_tol=0.00005), (
        f"README caveat 9 says a frame ending at 2023-12-31 reads 6.81 %; it "
        f"reads {alt:.2%}")
    return (f"annual late {before.min():.2%}-{before.max():.2%} FY2019-FY2023, "
            f"{rate[2024]:.2%} FY2024, {rate[2025]:.2%} FY2025; censoring bounds "
            f"FY2024 <= {bound[2024]:.3%}, FY2025 <= {bound[2025]:.3%}, frame "
            f"+{lifted - head:.3%}; median upload {early.min():.0f}-"
            f"{early.max():.0f}d -> {med[2024]:.0f}d; 2023-12-31 frame "
            f"{alt:.2%}", int(per["n"].sum()))


def test_taiwan_filing_deadline_q2_boundary_is_fy2013():
    """README caveat 9: the 第二季 rule starts a year after the rest of §36.

    The 2010-06-02 amendment to 證交法 §36 is in force 一百零一年一月一日 and the
    annual rule bites exactly there. The 第二季 rule does not, and §183 is where
    it says so: 一百零一年一月四日修正公布之第三十六條第一項第二款、自一百零二會計
    年度施行. That is the clause naming a 第二季財務報告, so through FY2012 the
    mid-year document is still the 半年度財務報告 on pre-2012 terms, and
    `filing_deadlines.csv` carries the two as separate rows.

    Read as a deadline the table was wrong for exactly one quarter and wrong by
    a lot — it scored 98 % of the FY2012 half-years late. What keeps this a
    check rather than a correction already banked is that the statute and the
    filings have to agree about *where* the boundary falls: FY2012 must score
    like FY2011 and FY2013 must not. A table edited until one quarter passed
    would still fail here if it put the break in the wrong year.
    """
    from finmind_data.available_date import available_date
    from finmind_data.filing_dates import CLASS_CONSOLIDATED

    path = REPO / "finmind_data/filing_dates.parquet"
    if not path.exists():
        raise Skipped("filing_dates.parquet not built")
    d = pd.read_parquet(path)

    def half(year):
        q = d[d["period_end"] == pd.Timestamp(f"{year}-06-30")]
        late = ((q["first_public"].dt.normalize()
                 - available_date(q["period_end"])).dt.days > 0)
        lag = int((q["first_public"].dt.normalize()
                   - q["period_end"]).dt.days.median())
        return len(q), float(late.mean()), lag

    n11, late11, lag11 = half(2011)
    n12, late12, lag12 = half(2012)
    n13, late13, lag13 = half(2013)
    assert late11 < 0.05 and late12 < 0.05 and lag11 == lag12 == 61, (
        f"README caveat 9 puts the FY2012 half-year under the same 75-day rule "
        f"as FY2011 — §183 defers §36 I(2) to 一百零二會計年度 — so the two should "
        f"score alike; FY2011 is {late11:.1%} late at a median {lag11}d and "
        f"FY2012 is {late12:.1%} at {lag12}d"
    )
    assert lag13 == 44 and late13 > 2 * max(late11, late12), (
        f"README caveat 9 reads the regime break off the filings at FY2013, "
        f"where the median lag drops to the 45-day rule; FY2013 files at a "
        f"median {lag13}d and is {late13:.1%} late against FY2012's {late12:.1%}"
    )
    # What the old row scored: FY2012's half-years against the 45-day rule the
    # table now starts at FY2013.
    q45 = (available_date(pd.Series([pd.Timestamp("2013-06-30")])).iloc[0]
           - pd.Timestamp("2013-06-30"))
    h = d[d["period_end"] == pd.Timestamp("2012-06-30")]
    old = int(((h["first_public"].dt.normalize() - h["period_end"]) > q45).sum())
    assert (old, len(h)) == (1592, 1619), (
        f"README caveat 9 says the 45-day rule scored 1,592 of the 1,619 FY2012 "
        f"half-years late; it scores {old:,} of {len(h):,}")
    # The lag is the symptom; the report type is the cause the paragraph names.
    was = d[d["period_end"] == pd.Timestamp("2012-06-30")]["class_code"].value_counts().idxmax()
    now = d[d["period_end"] == pd.Timestamp("2013-06-30")]["class_code"].value_counts().idxmax()
    assert was != CLASS_CONSOLIDATED and now == CLASS_CONSOLIDATED, (
        f"README caveat 9 reads the FY2012 boundary off the document as well as "
        f"the statute: the mid-year filing is a 我國GAAP 半年度財務報告 through "
        f"FY2012 and the IFRSs consolidated report ({CLASS_CONSOLIDATED}) from "
        f"FY2013. The modal class is {was} then {now}, so that corroboration is "
        f"gone and the boundary rests on §183 alone"
    )
    return (f"FY2011/FY2012 half-years {late11:.1%}/{late12:.1%} late at a "
            f"median {lag12}d under the 75-day rule; FY2013 {late13:.1%} at "
            f"{lag13}d under the 45-day one; modal report {was} then "
            f"{now}"), n11 + n12 + n13


def test_taiwan_observed_date_leaves_the_undatable_undated():
    """README caveat 9: the observed date covers `fin_is` bar 19 quarters.

    `observed_date` is only usable as a default if what it cannot date is both
    small and known, and the caveat claims it is: 19 of the window's 106,472
    `fin_is` company-quarters carry no filing, 15 of them an annual report from
    outside the span the document server holds for that company — filed before
    it listed, or after it stopped filing. Pinning the count means a panel that
    quietly loses coverage fails here, rather than dropping those rows out of a
    join that still looks like it ran.

    That they come back `NaT` rather than as the deadline is the other half of
    the claim, and the half that would be invisible if it broke: a substituted
    bound fills the column, and the rows then trade on a date nobody observed.
    """
    from finmind_data.available_date import observed_date

    if not (REPO / "finmind_data/filing_dates.parquet").exists():
        raise Skipped("filing_dates.parquet not built")
    frames = []
    for f in sorted((REPO / "finmind_data/fin_is").glob("*.parquet")):
        d = _tree(f)
        if not len(d) or "date" not in d.columns:
            continue
        frames.append(pd.DataFrame({"stock_id": f.stem,
                                    "period_end": d["date"].drop_duplicates()}))
    p = pd.concat(frames, ignore_index=True)
    obs = observed_date(p["stock_id"], p["period_end"])
    undated = p[obs.isna()]
    assert len(undated) == 19, (
        f"README caveat 9 says 19 of the window's {len(p):,} fin_is "
        f"company-quarters have no observed filing date; {len(undated)} do. "
        f"A drop means the panel gained coverage and the caveat undersells it; "
        f"a rise means it lost some, and the rows it lost leave a join silently"
    )
    assert undated["stock_id"].nunique() == 18, (
        f"README caveat 9 spreads the 19 over 18 companies; they now fall on "
        f"{undated['stock_id'].nunique()}"
    )

    # The caveat explains them as periods outside what the server holds for the
    # company, not as a collector that missed rows. Asserted, because the two
    # have the same count and only one of them is a reason to go back.
    span = (pd.read_parquet(REPO / "finmind_data/filing_dates.parquet")
              .groupby("stock_id")["period_end"].agg(["min", "max"]))
    j = undated.join(span, on="stock_id")
    outside = int(((j["period_end"] < j["min"])
                   | (j["period_end"] > j["max"])).sum())
    assert outside == 15, (
        f"README caveat 9 puts 15 of the 19 outside the span the document "
        f"server holds for their company — a pre-listing or post-delisting "
        f"report the vendor kept and the server never carried; {outside} are "
        f"now. The rest sit inside the span and are absent from it, which is a "
        f"collection gap rather than a structural one"
    )
    return (f"{len(p) - len(undated):,}/{len(p):,} in-window fin_is quarters "
            f"carry an observed date; the {len(undated)} that do not are NaT, "
            f"{outside} of them outside their company's filing span", len(p))


def test_taiwan_observed_date_rolls_past_the_session_close():
    """README caveat 9: 14.66 % are untradable by the deadline, not 6.56 %.

    Three quarters of reports are uploaded after TWSE's 13:30 close, so a
    filing that lands *on* its deadline is not tradable until the next session
    and the deadline is a look-ahead for it. That is why `observed_date` rolls
    rather than truncating, and it is the difference between the 6.56 % of
    quarters filed late and the 14.66 % that could not be traded on in time —
    more than double, on the same frame and the same deadline.

    Scored on whatever `filing_deadlines.csv` returns, with no correction
    applied here — for the reason the check above it gives.
    """
    from finmind_data.available_date import (available_date, observed_date,
                                             SESSION_CLOSE)

    path = REPO / "finmind_data/filing_dates.parquet"
    if not path.exists():
        raise Skipped("filing_dates.parquet not built")
    d = pd.read_parquet(path)
    w = d[(d["period_end"] >= pd.Timestamp("2011-12-31"))
          & (d["period_end"] <= _LATE_FRAME_END)].reset_index(drop=True)
    rolled = (w["first_public"] - w["first_public"].dt.normalize()) > SESSION_CLOSE
    assert math.isclose(rolled.mean(), 0.749, abs_tol=0.02), (
        f"README caveat 9 says three quarters of filings land after the 13:30 "
        f"close, which is what makes the roll worth doing; the share is now "
        f"{rolled.mean():.1%} ({int(rolled.sum()):,} of {len(w):,})"
    )

    dl = available_date(w["period_end"])
    untradable = ((observed_date(w["stock_id"], w["period_end"]) - dl).dt.days > 0)
    late = ((w["first_public"].dt.normalize() - dl).dt.days > 0)
    rate = untradable.mean()
    assert math.isclose(rate, 0.1466, abs_tol=0.005), (
        f"README caveat 9 says 14.66 % of the frame's company-quarters could "
        f"not be traded on by their deadline; the rate is now {rate:.2%} "
        f"({int(untradable.sum()):,} of {len(w):,})"
    )
    assert untradable.sum() > 2 * late.sum(), (
        f"README caveat 9 says the untradable share is more than double the "
        f"{late.mean():.2%} filed late, which is the whole reason the observed "
        f"date rolls; it is now {untradable.sum():,} against {late.sum():,}. If "
        f"the two have converged, the close-time roll is no longer load-bearing"
    )
    return (f"{int(rolled.sum()):,}/{len(w):,} = {rolled.mean():.1%} filed after "
            f"the close; {int(untradable.sum()):,} = {rate:.2%} untradable by "
            f"their deadline against {int(late.sum()):,} = {late.mean():.2%} "
            f"filed after it", len(w))


def test_taiwan_booked_tender_offers_opened_on_the_delisting_date():
    """README caveat 8: a tender is the exit only if it opened after the tape did.

    `tender_offers.parquet` is the exchange's own 公開收購申報資料彙總表, and it is
    reachable for names whose 說明 MOPS refuses because it is filed by the
    offeror and served by period rather than by company. It states a per-share
    price, which is the amount the caveat says is still missing — but a tender
    price is the terminal consideration only where the tender *was* the exit.

    Eight of the fifteen offers made on a name in this frame were the first step
    of a two-step deal, and the price a holder who did not tender received is
    the squeeze-out's, which this table does not carry. The three that are
    booked opened on the day the shares stopped trading and ran the 50 days
    公開收購管理辦法 §18 allows at most, so nothing later can have been their exit:
    there was no market left for it to precede. That rule is asserted here
    because the column the offeror files — 被收購公司於收購後是否終止上市 — does not
    carry it, being marked 是 on two of the three and 不適用 on the third.
    """
    from finmind_data.delisting_sign import considerations, features

    path = REPO / "finmind_data/tender_offers.parquet"
    if not path.exists():
        raise Skipped("tender_offers.parquet not built — "
                      "run `python -m finmind_data.tender_offers`")
    d = pd.read_parquet(path)
    f = features()
    on_frame = d[d["target_id"].isin(f["stock_id"])].merge(
        f[["stock_id", "delist_date", "last_trade"]],
        left_on="target_id", right_on="stock_id")
    assert len(on_frame) == 15, (
        f"README caveat 8 counts 15 tender offers made on the 164; there are "
        f"now {len(on_frame)}. The table starts at ROC 105/11, so a fall means "
        f"the source moved and a rise means it reaches further back"
    )

    c = pd.read_csv(REPO / "finmind_data/delisting_consideration.csv",
                    dtype={"stock_id": str})
    booked = c[c["source"].str.contains("公開收購申報資料彙總表", na=False)]
    assert len(booked) == 3, (
        f"README caveat 8 books 3 tender offers as the consideration paid; the "
        f"sheet now cites the table on {len(booked)}"
    )
    off = on_frame.set_index("target_id")
    for r in booked.itertuples():
        o = off.loc[r.stock_id]
        assert o["start_ts"] == o["delist_date"], (
            f"{r.stock_id} is booked at its tender price, which only holds "
            f"because the offer opened on the delisting date "
            f"({o['delist_date'].date()}); it opened {o['start_ts'].date()}, so "
            f"a later transaction could have been the exit instead"
        )
        assert (o["end_ts"] - o["start_ts"]).days == 49, (
            f"{r.stock_id}'s offer ran {(o['end_ts'] - o['start_ts']).days + 1} "
            f"days, not the 50 公開收購管理辦法 §18 allows at most — the ceiling "
            f"is what makes the going-private offer's dates readable as a rule"
        )
        assert math.isclose(o["per_share"], r.per_share, abs_tol=0.005), (
            f"{r.stock_id} is booked at {r.per_share} against the table's "
            f"{o['per_share']}; the sheet is a copy of the parquet here and a "
            f"copy that no longer matches publishes an older pull"
        )

    # The other twelve stay out, and the eight two-step ones are why the caveat
    # still says the amount is open: their price is the squeeze-out's.
    two_step = on_frame[on_frame["start_ts"] < on_frame["last_trade"]]
    assert len(two_step) == 12 and not set(two_step["target_id"]) & set(booked["stock_id"]), (
        f"README caveat 8 leaves the 12 offers that opened while the shares "
        f"still traded unbooked; {len(two_step)} are now pre-tape and "
        f"{sorted(set(two_step['target_id']) & set(booked['stock_id']))} are "
        f"booked anyway, which would assert a squeeze-out price nobody read"
    )

    # What the exclusion costs, which is the half of it a policy has to know.
    # `linkage` is the offeror's own 終止上市 answer and the module warns it does
    # not decide which transaction was the exit; it is used here only for what
    # the README claims with it — that four of the twelve are offers *the table
    # itself* says ended nothing. The eight are the ones it says did.
    linked = two_step[two_step["linkage"] == "yes"].copy()
    assert len(linked) == 8, (
        f"README caveat 8 splits the twelve into eight first steps and four the "
        f"table says ended no listing; it now reads {len(linked)} and "
        f"{len(two_step) - len(linked)}"
    )
    linked["gap"] = (linked["delist_date"] - linked["end_ts"]).dt.days
    assert (linked["gap"].min(), linked["gap"].max()) == (99, 648), (
        f"README caveat 8 dates the second step 99 to 648 days after the offer "
        f"closed; the span is now {linked['gap'].min()}..{linked['gap'].max()}"
    )
    last = {}
    for tid in linked["target_id"]:
        px = pd.read_parquet(REPO / f"finmind_data/ohlcv/{tid}.parquet")
        last[tid] = float(px.loc[pd.to_datetime(px["date"]).idxmax(), "close"])
    # Signed the way the README quotes it: the tender price against the last
    # close, so 5820's +11.1 % means the offer was above the tape.
    linked["err"] = [r.per_share / last[r.target_id] - 1
                     for r in linked.itertuples()]
    lo, hi = linked["err"].min(), linked["err"].max()
    assert math.isclose(lo, -0.0576, abs_tol=5e-4) and \
        math.isclose(hi, 0.1111, abs_tol=5e-4), (
        f"README caveat 8 puts the eight tender prices from −5.8 % (3144) to "
        f"+11.1 % (5820) against the last close; they now run {lo:+.1%}..{hi:+.1%}"
    )
    # The shape of that spread is what decides the policy, and it is not the
    # swaps'. There the error is a bias — the gap orders the signed residual at
    # +0.85. Here the gap orders the *absolute* one and leaves the sign alone,
    # so the last close is unbiased and only gets noisier the longer the second
    # step takes. A tender price booked in its place would trade a wide unbiased
    # substitute for a narrow one that is the wrong holder's, so the eight stay
    # out on a reason that does not move when the spread does.
    rho_abs = linked["gap"].corr(linked["err"].abs(), method="spearman")
    rho_signed = linked["gap"].corr(linked["err"], method="spearman")
    assert rho_abs > 0.5 > abs(rho_signed), (
        f"README caveat 8 reads the two-step residual as dispersion that grows "
        f"with the wait rather than as a bias — the gap orders |error| at +0.86 "
        f"and the signed error at +0.36. They are now {rho_abs:+.2f} and "
        f"{rho_signed:+.2f}, so the account of why a tender price is not a "
        f"better substitute than the last close is wrong"
    )
    # Reachability, which is what makes the exclusion temporary rather than a
    # rule: an offeror the sheet marks 上市 is still 公開發行 and files the second
    # step the way `swap_ratios.py` reads a swap. Counted off the sheet's own
    # 上市/上櫃 marking, so a buyer that was itself later bought still counts and
    # the figure is an upper bound on what the route can reach.
    listed = linked["offeror"].str.contains("上市|上櫃", na=False)
    assert int(listed.sum()) == 3, (
        f"README caveat 8 says three of the eight were bought by a company "
        f"whose own filings are served — 6422 by 國巨 2327, 4725 by 台泥 1101 "
        f"and 5820 by 富邦金 2881; {int(listed.sum())} now carry a 上市/上櫃 "
        f"offeror, so the count of deals the route could still price has moved"
    )
    # Those three have since been priced, and the point of asserting it here is
    # that the reason the eight were excluded was one of *kind* — the tender
    # price belongs to the holders who tendered — and a reason of kind is only
    # worth what it predicts. It predicted that the second step need not equal
    # the first, and on the three the route reaches, twice it does and once it
    # does not: 5820's NT$13 was cut to 12.41 for the 109 dividend and to 11.71
    # for the 110 one, so booking the tender would have been 11.0 % high on the
    # residual the README calls the largest of the eight.
    paid = considerations(features()).set_index("stock_id")["paid"]
    second = {t: float(paid[t]) for t in ("6422", "4725", "5820")
              if t in paid.index}
    assert len(second) == 3, (
        f"README caveat 8 says the three reachable two-step residuals are "
        f"booked from the buyer's own filing of the second step; "
        f"{sorted({'6422', '4725', '5820'} - set(second))} carry no "
        f"consideration, so the route's own output has gone missing"
    )
    off_tender = {t: second[t] / float(linked.set_index("target_id")
                                       .loc[t, "per_share"]) - 1
                  for t in second}
    assert all(abs(v) < 1e-9 for k, v in off_tender.items() if k != "5820"), (
        f"README caveat 8 says 6422 and 4725 restate the tender price exactly "
        f"— 「與公開收購對價一致」 and 「每股現金新台幣18元予信昌化公司其餘股東」 — "
        f"which is what makes 5820 a difference in the deal rather than in the "
        f"reading; they now sit at {off_tender}"
    )
    assert math.isclose(off_tender["5820"], -0.0992, abs_tol=5e-4), (
        f"README caveat 8 says 5820's merger consideration was adjusted twice "
        f"for dividends and settled 9.9 % below its NT$13 tender; it is now "
        f"{off_tender['5820']:+.2%}, so either the filing was reread or the "
        f"one case that pays for the exclusion has moved"
    )
    # The half that decides the policy: against the same three exits, the last
    # close is the better substitute, and it is better *because* the tender is
    # exact only when nothing intervened between the two steps.
    worst_close = max(abs(second[t] / last[t] - 1) for t in second)
    assert worst_close < abs(off_tender["5820"]), (
        f"README caveat 8 declines the tender price as a substitute on the "
        f"ground that it is the wrong holder's; on the three exits where both "
        f"can be scored the last close is off by at most {worst_close:.2%} and "
        f"the tender by {abs(off_tender['5820']):.2%}. That ordering has "
        f"reversed, so the decline now costs accuracy rather than buying it"
    )
    return (f"{len(d)} tender offers from ROC105/11, {len(on_frame)} on the "
            f"frame; 3 booked because they opened on the delisting date, "
            f"{len(two_step)} left because the tender preceded the exit — 8 of "
            f"them first steps at {lo:+.1%}..{hi:+.1%}, |error| ordered by the "
            f"gap at {rho_abs:+.2f} and the sign at {rho_signed:+.2f}, 3 with a "
            f"listed offeror", len(on_frame))


def test_taiwan_short_sale_series_has_no_regime_gap():
    """README "Two regime facts": a hole in margin_short is a failed download.

    Several markets suspended short selling in March 2020 and Taiwan did not,
    which is what lets a caller read a missing stretch here as a fetch to retry
    rather than a rule to model around. That reading is only safe while the
    tape has no gap in it, so the gap is counted rather than argued from the
    statute. March 2020 is held to being *busier* than normal on top of that: a
    suspension the monthly totals survived at some reduced level would clear a
    bare zero-count while being exactly the regime the README says is absent.
    """
    import pyarrow.parquet as pq

    frames = []
    for f in sorted(glob.glob(str(REPO / "finmind_data/margin_short/*.parquet"))):
        if not pq.ParquetFile(f).metadata.num_rows:
            continue
        frames.append(_tree(f, columns=["date", "ShortSaleSell",
                                        "ShortSaleTodayBalance"]))
    d = pd.concat(frames)
    m = d.groupby(pd.to_datetime(d["date"]).dt.to_period("M")).agg(
        sell=("ShortSaleSell", "sum"), bal=("ShortSaleTodayBalance", "sum"))
    dead = int((m["sell"] == 0).sum())
    flat = int((m["bal"] == 0).sum())
    assert len(m) == 189 and len(frames) == 2082 and not dead and not flat, (
        f"README claims 'across the 189 in-window months, on 2,082 names, not "
        f"one month has zero short-sale volume and not one has zero short "
        f"balance'; {len(m):,} months on {len(frames):,} names, {dead} with no "
        f"volume and {flat} with no balance")
    ratio = m.loc["2020-03", "sell"] / m.loc["2019", "sell"].mean()
    assert math.isclose(ratio, 1.66, abs_tol=0.02), (
        f"README claims March 2020 carries '1.66x' the 2019 monthly mean of "
        f"short-sale volume; it carries {ratio:.2f}x")
    return (f"{len(m)} in-window months on {len(frames):,} names, none with "
            f"zero short-sale volume or zero balance; 2020-03 at "
            f"{ratio:.2f}x the 2019 mean"), len(d)


def test_taiwan_par_value_changes_are_priced():
    """README caveat 5: the rebuild steps across a 面額變更 rather than through it.

    A 面額變更 divides the quoted price and multiplies the share count by the
    same factor, so it moves a price as mechanically as a 減資 — and it sat in
    neither of the two chains the factor was built from. The gate that certifies
    the rebuild (`test_taiwan_rebuild_matches_vendor`) could not see it: that one
    scores on in-window *delistings*, and a par value change is what a healthy
    company with an expensive share does, so the validation set is
    anti-correlated with the failure. This check scores the same statistic on
    the event dates themselves, which is the population that was missing.

    The raw leg is asserted too. Without it a chain that silently stopped
    carrying these events would still pass, by matching a vendor series that had
    also stopped — the raw drop is what makes the event's presence checkable
    from outside either adjusted series.
    """
    sys.path.insert(0, str(REPO))
    from finmind_data import adjust

    sp = pd.read_parquet(REPO / "finmind_data/split_reference.parquet")
    uni = set(pd.read_parquet(REPO / "finmind_data/universe.parquet")["stock_id"])
    ev = sp[sp["date"].between(COVERAGE_START, COVERAGE_END)
            & sp["stock_id"].isin(uni)]
    raw_drop = matched = 0
    for r in ev.itertuples():
        px = _tree(REPO / f"finmind_data/ohlcv/{r.stock_id}.parquet",
                   columns=["date", "close"]).sort_values("date")
        px = px.reset_index(drop=True)
        i = px.index[px["date"] >= r.date]
        a = _tree(REPO / f"finmind_data/price_adj/{r.stock_id}.parquet",
                  columns=["date", "close"]).sort_values("date")
        a = a.reset_index(drop=True)
        j = a.index[a["date"] >= r.date]
        if not len(i) or not i[0] or not len(j) or not j[0]:
            continue
        i, j = i[0], j[0]
        raw_drop += int(px["close"][i] / px["close"][i - 1] - 1 < -0.30)
        f, _ = adjust.rebuild_tr_factor(r.stock_id, px)
        rebuilt = (px["close"][i] * f[i]) / (px["close"][i - 1] * f[i - 1]) - 1
        vendor = a["close"][j] / a["close"][j - 1] - 1
        matched += int(abs(rebuilt - vendor) < 1e-3)
    # Counted off `split_reference.parquet` rather than fixed at what it held
    # when this was written: coverage moves with the download and the exchange
    # files more of these every year, so a literal would fail the next extension
    # for being right about the old panel. An event the loop could not score
    # stays in `n` and shows up as a shortfall, which is the loud version of the
    # `continue` above.
    n = len(ev)
    assert n and raw_drop == n, (
        f"README caveat 5 claims every in-window 面額變更 is a raw drop past "
        f"-30 %; {n - raw_drop} of the {n} in split_reference.parquet are not — "
        f"either the event is not the mechanical reprice the caveat describes, "
        f"or the price tree does not hold the session it fell on"
    )
    assert matched == n, (
        f"README caveat 5 claims the rebuild reproduces the vendor on every "
        f"in-window 面額變更; it does on {matched} of {n}. A shortfall means the "
        f"chain in split_reference.parquet is no longer reaching the factor, "
        f"and the rebuilt names carry the whole par change as a return"
    )
    return (f"{n} in-window 面額變更 events, all {raw_drop} a raw drop past "
            f"-30 %, all {matched} rebuilt to the vendor within 1e-3"), n


CHECKS = [
    test_taiwan_tree_readers_import_the_window,
    test_taiwan_coverage_does_not_outrun_the_data,
    test_taiwan_tape_years_are_whole,
    test_taiwan_loader_takes_the_callers_span,
    test_taiwan_delisting_frame_does_not_follow_coverage,
    test_taiwan_dataset_names_in_code_resolve,
    test_taiwan_ohlcv_one_per_universe,
    test_taiwan_universe_excludes_the_instruments_it_claims_to,
    test_taiwan_price_adj_one_per_universe,
    test_taiwan_overlay_covers_the_window,
    test_taiwan_universe_holds_every_common_the_tape_shows,
    test_taiwan_pit_universe_is_dated_and_keeps_its_delistings,
    test_taiwan_listing_spans_reconcile_with_the_tape,
    test_taiwan_universe_bridges_a_halt_only_when_asked,
    test_taiwan_adjusted_survivorship_hole,
    test_taiwan_adjusted_coverage_decomposition,
    test_taiwan_vendor_event_audit_is_current,
    test_taiwan_vendor_defects_are_patched,
    test_taiwan_vendor_edges_are_carried,
    test_taiwan_post_delisting_sessions_are_marked,
    test_taiwan_no_trade_rows_are_not_holdable,
    test_taiwan_no_session_the_tape_holds_is_missing,
    test_taiwan_volume_repair_matches_the_tape,
    test_taiwan_survivorship_hole_is_rebuilt,
    test_taiwan_rebuild_matches_vendor,
    test_taiwan_adj_source_partitions_the_panel,
    test_taiwan_adj_covered_survives_concat,
    test_taiwan_open_outside_session_range,
    test_taiwan_repull_returns_the_stored_prices,
    test_taiwan_short_sale_series_has_no_regime_gap,
    test_taiwan_delisting_table_has_no_reason,
    test_taiwan_mops_covers_every_delisted_name,
    test_taiwan_mops_detail_gate_is_registration_not_filing,
    test_taiwan_swap_ratio_quotes_the_filing_it_names,
    test_taiwan_mops_reason_empties_the_undecided_band,
    test_taiwan_mops_overturns_only_failures_the_tape_missed,
    test_taiwan_exchange_provision_markers_match_what_they_govern,
    test_taiwan_mops_reason_scored_against_the_hand_labels,
    test_taiwan_anchor_overrides_agree_with_their_own_window,
    test_taiwan_silent_names_keep_their_unknown,
    test_taiwan_reason_frame_is_frozen,
    test_taiwan_filing_dates_cover_the_statement_trees,
    test_taiwan_filing_dates_drop_reports_filed_before_their_quarter,
    test_taiwan_statements_are_published_after_their_deadline,
    test_taiwan_late_rate_falls_after_the_frame,
    test_taiwan_filing_deadline_q2_boundary_is_fy2013,
    test_taiwan_observed_date_leaves_the_undatable_undated,
    test_taiwan_observed_date_rolls_past_the_session_close,
    test_taiwan_delisting_sign_sample_is_preregistered,
    test_taiwan_delisting_sign_accuracy,
    test_taiwan_single_cut_is_registered_unscored,
    test_taiwan_substitute_error_splits_by_deal_form,
    test_taiwan_booked_tender_offers_opened_on_the_delisting_date,
    test_taiwan_cash_payouts_land_outside_the_band,
    test_taiwan_fundamentals_are_fiscal_dated,
    test_taiwan_statement_trees_drop_old_delistings,
    test_taiwan_filing_deadline_table_covers_the_data,
    test_taiwan_month_rev_date_is_the_following_month,
    test_taiwan_no_event_holes_are_event_free_in_three_sources,
    test_capital_reduction_artifact_exists,
    test_taiwan_par_value_changes_are_priced,
    test_taiwan_ohlcv_is_raw,
    test_taiwan_pre_listing_sessions_are_one_vendor_day,
    test_taiwan_adjusted_series,
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
    # The bound is per check because a population clipped to coverage moves only
    # when coverage does, while one open past it grows every time the vendor is
    # re-pulled — a single rule would either fail every refresh or catch nothing.
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
                    f"coverage changed, which a re-pull does only by moving "
                    f"COVERAGE_END. Re-seed with --write-populations once the "
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
