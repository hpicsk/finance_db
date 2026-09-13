"""The window and the package's own source: coverage, the calendar, the import rules, the client."""
from __future__ import annotations
import ast
import math
import re
from pathlib import Path
import pandas as pd

from finmind_data.window import COVERAGE_START, COVERAGE_END, clip
from finmind_data.paths import DATA, PKG, TAPE, TREES
from ._common import Skipped


def _sources() -> list[Path]:
    """The package's own modules: what the source-level checks read.

    Every `.py` under the package except this suite, the check modules and
    `_internal/`, which holds run state rather than code the package runs.
    """
    return sorted(p for p in PKG.rglob("*.py")
                  if "_internal" not in p.parts and "checks" not in p.parts
                  and not p.name.startswith("test_"))


# ---- Taiwan: every reader of the trees goes through the window -------------
def test_taiwan_tree_readers_import_the_window():
    """`window`'s own docstring: every module that reads the trees imports it.

    The trees hold sessions on both sides of `COVERAGE_START..COVERAGE_END`, so
    a module that reads one without clipping does not fail — it measures a wider
    panel than it reports, and that number is the kind that gets published. The
    invariant was written in prose and nothing enforced it, which is the state
    every figure in this suite was in before it was asserted.

    A module reads the trees when it imports `TREES` from `paths`, the one
    spelling of where they are. Four are excepted, and named here rather than
    skipped by pattern, so adding a fifth is a change to this list and not a
    silent one. `download.py` writes the trees — writing them short is what the
    window is not for, since a wider tree costs nothing and a narrower one
    cannot be widened without a re-download. `filing_dates.py` reads which files
    exist and the newest quarter each holds, to decide what to collect;
    `fin_bs_vintage.py` grades whole files against a snapshot whose own periods
    bound the comparison; `available_date.py` opens one file in its
    demonstration block. None of the three publishes a figure over the trees.

    The import is what is checked, not the call, because that is what the
    docstring claims and a module may legitimately hold the dates rather than
    clip a frame. A reader that imports and then forgets to clip is caught by
    the population guard instead: its count moves against `populations.json`.
    """
    readers = [(p.name, p.read_text()) for p in _sources()]
    readers = [(n, t) for n, t in readers
               if re.search(r"^from (\.\.?|finmind_data\.)paths import .*\bTREES\b", t, re.M)]
    assert readers, (
        "no module in the package imports `paths.TREES` at all, so this check "
        "has no population — the trees moved, or the path spelling did, and "
        "the invariant is unverified rather than held"
    )
    excepted = {"download.py", "filing_dates.py", "fin_bs_vintage.py", "available_date.py"}
    names = {n for n, _ in readers}
    assert excepted <= names, (
        f"this check excepts {sorted(excepted)} from the import rule; "
        f"{sorted(excepted - names)} no longer reads the trees, so the "
        f"exception is stale and names a file that is not there"
    )
    missing = sorted(n for n, t in readers
                     if n not in excepted
                     and not re.search(r"^from (\.\.?|finmind_data\.)window import", t, re.M))
    assert not missing, (
        f"window.py's docstring claims every module that reads the trees "
        f"imports the window from it, the writers and whole-file readers "
        f"excepted; {missing} reads them and does not. An unclipped read "
        f"measures the sessions outside "
        f"{COVERAGE_START.date()}..{COVERAGE_END.date()} into a figure the "
        f"package publishes as being about the window"
    )
    return (f"{len(readers)} modules read the trees; "
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
    cal_path = DATA / "trading_sessions.parquet"
    spans_path = DATA / "listing_spans.parquet"
    tape_path = TAPE / f"{COVERAGE_END.year}.parquet"
    if not cal_path.exists() or not spans_path.exists() or not tape_path.exists():
        raise Skipped("trading_sessions.parquet / listing_spans.parquet / the "
                      "tape year coverage ends in are not built — run "
                      "`python -m finmind_data.collect.tape_universe` then "
                      "`python -m finmind_data.derive.pit_universe`")
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
                       (PKG / "collect/download.py").read_text()))
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
        DATA / "universe.parquet", columns=["stock_id"])["stock_id"])
    on_last = sorted(universe & set(
        tape.loc[tape["date"].astype(str) == hi, "stock_id"]))
    assert on_last, (
        f"the tape carries {hi} and shows no universe name trading on it, so "
        f"coverage ends on a day the package holds no price for")
    silent = [s for s in on_last
              if hi not in set(pd.read_parquet(
                  TREES / f"ohlcv/{s}.parquet",
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

    from finmind_data.collect.tape_universe import _YEAR_END_SLACK

    files = sorted((TAPE).glob("*.parquet"))
    if not files:
        raise Skipped("tape/ not built (python -m finmind_data.collect.tape_universe)")
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
    from finmind_data.delisting import delisting_sign

    frozen = pd.read_parquet(DATA / "delisting_sign.parquet")
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

    from finmind_data.derive.adjusted_loader import load_adjusted, available_stocks

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
        f = TREES / f"div_result/{sid}.parquet"
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
    comment that nothing re-checks. `catalogue.KNOWN_ABSENT` registers two.

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
    for f in _sources():
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for t in token.findall(node.value):
                    seen.setdefault(t, set()).add(f.name)
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


def test_taiwan_token_travels_in_a_header():
    """README, "Provenance": every collector sends the token in a header.

    One request loop, `client.get`, is how: it sends `auth.headers()` and never
    puts the token in the query string, which `requests` writes into the errors
    a collector logs. The collectors are the modules that import that loop,
    found by reading the package rather than listed, and the rest of the check
    is that no module but the client spells the endpoint itself — a request
    loop written beside the client is where a token goes back into a URL.
    """
    host = "api.finmindtrade.com"
    client = (PKG / "client.py").read_text()
    assert "headers=headers()" in client and not re.search(
        r"""["']token["']\s*(?::|\]\s*=)""", client), (
        "README says every collector sends the token in an Authorization: "
        "Bearer header; client.py, the one request loop, does not")
    bypass = sorted(p.name for p in _sources()
                    if p.name != "client.py" and host in p.read_text())
    assert not bypass, (
        f"README says every collector requests through client.get; {bypass} "
        f"spell the endpoint themselves, so their token handling is their own")
    users = sorted(p.name for p in _sources() if re.search(
        r"^from (\.\.?|finmind_data\.)client import .*\bget\b", p.read_text(), re.M))
    assert users, ("no module imports client.get, so nothing collects through "
                   "the loop this check is about")
    return (f"{len(users)} collectors request through client.get, which sends "
            f"the token in a header"), len(users)


CHECKS = [
    test_taiwan_tree_readers_import_the_window,
    test_taiwan_coverage_does_not_outrun_the_data,
    test_taiwan_tape_years_are_whole,
    test_taiwan_delisting_frame_does_not_follow_coverage,
    test_taiwan_loader_takes_the_callers_span,
    test_taiwan_dataset_names_in_code_resolve,
    test_taiwan_token_travels_in_a_header,
]
