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

import glob
import json
import math
import os
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from finmind_data.window import COVERAGE_START, COVERAGE_END, clip  # noqa: E402

# The study window every package's figures are quoted on. Duplicated in each
# assertion file because the container holds no shared module to import it from;
# `run_assertions.sh` fails if the copies ever disagree.
WIN_START = pd.Timestamp("2005-01-01")
WIN_END = pd.Timestamp("2024-12-31")
# This package answers questions about less of it than the others do, for a
# reason `window.py` states: the event log a price series has to be read
# against does not exist before 2011-01-25 and cannot be made to. Every check
# below is quoted on `COVERAGE_START`..`COVERAGE_END`, and the study window is
# here to be the thing that contains it.
assert WIN_START <= COVERAGE_START <= COVERAGE_END <= WIN_END, (
    f"the package's coverage {COVERAGE_START.date()}..{COVERAGE_END.date()} "
    f"is not inside the study window {WIN_START.date()}..{WIN_END.date()}"
)
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
        f"2011-01-25..2024-12-31 into a figure the package publishes as being "
        f"about the window"
    )
    return (f"{len(readers)} modules name the trees; "
            f"{len(readers) - len(excepted)} of them import the window, "
            f"{sorted(excepted)} excepted"), len(readers)


# ---- Taiwan: one OHLCV file per universe id --------------------------------
def _tw_ids():
    u = pd.read_parquet(REPO / "finmind_data/universe.parquet")
    d = pd.read_parquet(REPO / "finmind_data/delisted_universe.parquet")
    uid = set(u["stock_id"].astype(str))
    files = {os.path.basename(p).split(".")[0]
             for p in glob.glob(str(REPO / "finmind_data/ohlcv/*"))}
    return u, d, uid, files


def test_taiwan_ohlcv_one_per_universe():
    u, _, uid, files = _tw_ids()
    missing = uid - files
    assert len(u) == 2158, f"Taiwan universe = {len(u)}, README pins 2,158"
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
        f"{sorted(inn['stock_id'].astype(str))}. The 2005-2024 window closes "
        f"before any of these graduated to the ordinary board"
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
    """Every universe id was fetched, and the empty ones are the known 51.

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
    assert empty == 113, (
        f"README pins 113 empty adjusted series (50 of them in-window "
        f"delistings, 42 pre-window, 21 names listed too recently to have an "
        f"adjusted history); the tree now has {empty}. "
        f"A change here moves the survivorship hole the README quantifies"
    )
    return (f"all {len(uid)} ids fetched; {empty} empty, {len(uid) - empty} "
            f"with data"), len(uid)


def test_taiwan_adjusted_survivorship_hole():
    """README, "The adjusted panel is survivorship-biased": 50 of 164.

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

    assert len(inwin["sid"].unique()) == 164, (
        f"README counts 164 in-window universe delistings; found "
        f"{len(inwin['sid'].unique())}"
    )
    assert len(hole) == 50, (
        f"README claims 50 of the 164 in-window delistings have raw prices and "
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
    return (f"{len(hole)} of 164 in-window delistings have raw prices and no "
            f"adjusted series, delisted {yrs.min()}-{yrs.max()}"
            ), len(inwin["sid"].unique())


def test_taiwan_adjusted_coverage_decomposition():
    """README, "The adjusted panel is survivorship-biased": 98.92 %, and why.

    The figure has to be quoted against every traded session in `ohlcv/`. Drop
    the 54 uncovered stocks from the denominator and the same files report
    99.99 % — the coverage of a panel the survivorship bias has already been
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
    traded = covered = hole = tail = first = makeup = 0
    vendor_only = []
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
        first += int((inner & ~mk).sum())
        assert not (inner & ~mk & (tr.index > 0)).any(), (
            f"{sid}: a session other than the first is missing from the vendor "
            f"series inside its own date range, and is not a Saturday make-up "
            f"session either, so it is a hole rather than the documented offset "
            f"and is not what the carry fills"
        )

    assert (traded, covered) == (5754275, 5692266), (
        f"README pins adjusted coverage at 5,692,266 of the 5,754,275 traded "
        f"sessions in ohlcv/ (98.92 %); this tree gives {covered:,} of "
        f"{traded:,} ({100 * covered / max(traded, 1):.2f} %)"
    )
    assert (hole, tail, first, makeup) == (61505, 0, 493, 11), (
        f"README splits the {traded - covered:,} missing sessions into 61,505 "
        f"in the 54 stocks with no adjusted series, none past the end of a "
        f"vendor series that stopped at a delisting, 493 first sessions and 11 "
        f"Saturday make-up sessions; this tree gives {hole:,} / {tail:,} / "
        f"{first:,} / {makeup}. The first number is the survivorship hole — if "
        f"it moved, so did the bias"
    )

    vo = pd.DataFrame(vendor_only, columns=["stock_id", "date", "lead", "trail"])
    assert (len(vo), vo["stock_id"].nunique(), vo["date"].nunique()) == (303, 96, 14), (
        f"README puts the reverse gap at 303 sessions in 96 stocks on 14 dates; "
        f"this tree gives {len(vo):,} in {vo['stock_id'].nunique()} on "
        f"{vo['date'].nunique()}. These are sessions `ohlcv/` has no row for, so "
        f"unlike the missing adjusted ones they cannot be filled from the panel"
    )
    # Every one is a Saturday 補行交易日, which is the whole content of the
    # finding: the raw endpoint serves those Saturdays for a thousand-odd stocks
    # each and drops the row for a few dozen. An ordinary weekday appearing here
    # would be a different defect wearing the same count.
    assert set(vo["date"].dt.dayofweek) == {5}, (
        f"README calls all 303 make-up Saturdays; this tree has vendor-only "
        f"sessions on {sorted(set(vo['date'].dt.day_name()))}"
    )
    assert not vo["lead"].any() and not vo["trail"].any(), (
        f"{int(vo['lead'].sum())} vendor-only sessions fall before the raw "
        f"series opens and {int(vo['trail'].sum())} after it closes. Both are "
        f"interior in this tree, which is what makes the head fill's anchor the "
        f"raw first traded session rather than a date the raw file never reaches"
    )
    return (f"{covered:,}/{traded:,} = {100 * covered / traded:.2f} % "
            f"(vs {100 * covered / (traded - hole):.2f} % on the bias-removed "
            f"denominator); missing = {hole:,} hole + {tail:,} tail + {first:,} "
            f"first; {len(vo)} the other way, all interior make-up Saturdays"
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
    """README caveat 10: `open` sits outside [min, max] on 2.2 % of rows.

    `close` never does, which is what makes this a property of the `open` field
    rather than of the sessions. Asserted because the caveat is the only thing
    standing between the panel and a backtest that enters at the open.
    """
    import pyarrow.parquet as pq

    bad = tot = stocks = bad_close = 0
    for sid in _panel_ids():
        p = REPO / f"finmind_data/ohlcv/{sid}.parquet"
        # Some files hold no rows and carry no schema, so a column-projected
        # read would fail on them; the row count comes from the footer instead.
        if pq.ParquetFile(p).metadata.num_rows == 0:
            continue
        r = _tree(p, columns=["date", "open", "max", "min", "close"])
        r = r[r["close"] > 0]
        tot += len(r)
        n = int(((r["open"] > r["max"]) | (r["open"] < r["min"])).sum())
        bad += n
        stocks += n > 0
        bad_close += int(((r["close"] > r["max"]) | (r["close"] < r["min"])).sum())

    assert bad_close == 0, (
        f"README caveat 10 rests on close being consistent with its own session "
        f"bar on every row; {bad_close:,} rows now break that, so the problem is "
        f"no longer confined to the open field"
    )
    assert (bad, stocks) == (125114, 669), (
        f"README caveat 10 pins 125,114 rows across 669 stocks with open "
        f"outside [min, max]; this tree gives {bad:,} across {stocks}"
    )
    return (f"open outside [min,max] on {bad:,}/{tot:,} rows "
            f"({100 * bad / tot:.2f} %) in {stocks} stocks; close on 0"), tot


# ---- Taiwan: the biases the delisting table does *not* fix -----------------
def test_taiwan_delisting_table_has_no_reason():
    """README caveat 8: the delisting table dates the exit and says nothing else.

    The universe overlay built from this table removes survivorship bias — the
    names are all present. It cannot touch delisting-return bias, because
    nothing here separates a bankruptcy from a merger and no column records what
    a holder was paid. This asserts the absence, so that a vendor backfill
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
    # from two sides — so `test_taiwan_adjusted_survivorship_hole`'s 164 and this
    # 164 are the same delistings, and a divergence is a real disagreement
    # rather than a documented offset.
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
    assert math.isclose(r["n_ambiguous_merger"], 22, abs_tol=3), (
        f"README caveat 8 says ~22 of the ~38 undecided names are payouts; "
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
    and the null it has to beat rose from 0.55 to 0.571 at the same time. That is
    reported rather than repaired — the repair is a wider held-out set, and
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
    200, so `_LONG_SUSPENSION_DAYS` can be moved anywhere inside 15..217
    without moving a call, and that move passes here. The claim is bounded to
    what it can see, and the alternative — asserting the constants themselves —
    would only restate them.
    """
    from finmind_data.delisting_sign import (
        _DD_SINGLE, _GATE_MIN_LABELS, _GATE_NULL, band_holdout, features,
        gate_threshold, single_cut_gate)

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
    assert (dd50, halt) == (19, 24), (
        f"README caveat 8 says the halt rule is right 24 times on the 28 "
        f"labelled band names against 0.50's 19, which is why both are "
        f"registered; they now score {dd50} and {halt} of {len(scored)}"
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


def test_taiwan_delisting_substitute_is_biased_low():
    """README caveat 8: the last close understates a payout, and by how much.

    The substitute a study books for a delisted payout name is its last traded
    close, and the question is not whether that is imprecise but whether it is
    wrong in a fixed direction — noise averages out of a portfolio, a bias does
    not. It is one-directional here on every deal measured, which is what the
    assertion pins; the size splits by deal type and the split is the finding,
    because it decides which lookups are worth doing.

    Four deals is few, and the direction is the part that survives that. Two of
    the original six delisted before the coverage start and left the frame with
    the window; they stay in `delisting_consideration.csv` as the record of what
    was read. The sample can be grown — the re-registered draw added 23 payout
    labels whose `source` already states a price or a ratio — and any addition
    to that file moves these numbers on purpose.

    The `overlap` assertion is the one that will fire on such an addition, and
    it should. Zero acquirer sessions before the target's last trade is what
    makes the caveat's "not staleness" claim true, and it holds because a swap
    stated without a ratio convention is a holding-company conversion. A
    third-party acquisition for stock would break it, and that is the deal the
    staleness account could finally be tested on — so the failure is an
    instruction to measure, not a regression.
    """
    from finmind_data.delisting_sign import (
        band_holdout, features, substitute_error, terminal_value)

    f = features()
    e = substitute_error(f)
    assert (e["residual"] > 0).all(), (
        f"README caveat 8 says the last close understates the consideration on "
        f"every deal measured, so the substitute is a downward bias rather "
        f"than noise; "
        f"{e.loc[e['residual'] <= 0, 'stock_id'].tolist()} now sit at or above "
        f"what was paid"
    )
    cash = e.loc[e["kind"] == "cash", "residual"]
    swap = e.loc[e["kind"] == "swap", "residual"]
    assert cash.max() < 0.01, (
        f"README caveat 8 says a cash consideration is within 1 % of the last "
        f"close, which is why cash deals need no lookup; the worst is now "
        f"{cash.max():+.1%}"
    )
    assert math.isclose(swap.median(), 0.112, abs_tol=0.02), (
        f"README caveat 8 puts the share-swap understatement near 11 %; the "
        f"median is now {swap.median():+.1%}. That number is what makes a "
        f"swap worth resolving and a cash deal not"
    )
    assert (e.loc[e["kind"] == "swap", "overlap"] == 0).all(), (
        f"README caveat 8 says the understatement is not the last close going "
        f"stale, because the successor of every swap measured first trades on "
        f"the day the target leaves — no acquirer price to drift against. "
        f"{e.loc[e['overlap'] > 0, 'stock_id'].tolist()} now overlap, which "
        f"makes the staleness account testable and the caveat's dismissal of "
        f"it stale in turn"
    )
    sign = f.set_index("stock_id")["sign"]
    in_band = int((e.loc[e["kind"] == "swap", "stock_id"].map(sign)
                   == "ambiguous").sum())
    assert in_band == 1, (
        f"README caveat 8 says one of the two swaps is a band name, so the "
        f"+11 % is measured on a mix rather than on classifier-confirmed "
        f"payouts alone; {in_band} are now undecided by the cuts"
    )
    assert e.loc[e["kind"] == "swap", "gap"].nunique() <= 2, (
        f"README caveat 8 says the gap cannot price the bias because it barely "
        f"varies across the swaps; it now takes "
        f"{e.loc[e['kind'] == 'swap', 'gap'].nunique()} values, so the check "
        f"the caveat rules out may now have something to read"
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
    assert (t.loc[t["basis"] == "substituted", "terminal"]
            == t.loc[t["basis"] == "substituted", "last_close"]).all(), (
        "a payout books its last close, which is the substitute being measured"
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
    labels = labels[labels["label"].fillna("") != ""]
    expected = {"distress": "failed", "merger": "substituted"}
    off_label = t.merge(labels[["stock_id", "label"]], on="stock_id")
    wrong = off_label[off_label["basis"].replace("consideration", "substituted")
                      != off_label["label"].map(expected)]
    assert not len(wrong), (
        f"README caveat 8 says a hand-read filing outranks the price shape "
        f"wherever one exists; {wrong['stock_id'].tolist()} book against their "
        f"own label instead"
    )
    band = int((f["sign"] == "ambiguous").sum())
    assert (band, len(undecided)) == (37, 9), (
        f"README caveat 8 says the labels empty 28 of the 37 band names and "
        f"leave 9 without a terminal value; the cuts now leave {band} open and "
        f"{len(undecided)} survive the labels. An emptied label file lands here"
    )
    assert set(undecided["stock_id"]) == set(
        band_holdout(f, labels)["stock_id"]), (
        "README caveat 8 says the nine names left without a terminal value "
        "are the nine the single cut is registered against; they have come "
        "apart, so the band a study is told to resolve is no longer the band "
        "`delisting_band.csv` froze"
    )
    counts = t["basis"].value_counts().to_dict()
    return (f"last close understates by {cash.median():+.1%} on {len(cash)} cash "
            f"deals and {swap.median():+.1%} on {len(swap)} swaps, all one way; "
            f"not staleness ({int(e['overlap'].sum())} acquirer sessions before "
            f"the last trade); terminal basis {counts}",
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
    paid; there are none left in the frame, and reading one in would invent the
    fact the column exists to count.
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
            counts.get("unstated")) == (26, 17, 9, None), (
        f"README caveat 8 says 26 labelled payouts in the frame split 17 share "
        f"exchanges and 9 cash, with none left unstated; the label file now "
        f"gives {len(m)} and {counts}. A label arriving for one of the nine "
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
    for p in sorted(glob.glob(str(REPO / "finmind_data/month_rev/*.parquet")))[:200]:
        m = pd.read_parquet(p)
        if not len(m):
            continue
        tot += len(m)
        st = m["create_time"].astype(str).str.strip()
        d = pd.to_datetime(m["date"], errors="coerce")
        hit = st != ""
        stamped += int(hit.sum())
        inwin_stamped += int((hit & d.between(COVERAGE_START, COVERAGE_END)).sum())
        back = hit & (d < COVERAGE_START)
        if back.any():
            lag = (pd.to_datetime(st[back], errors="coerce") - d[back]).dt.days
            backfill_lag += list(lag.dropna())
    assert stamped, (
        "README caveat 9 argues from where create_time's values fall that it is "
        "not a release date for this window; no row in the tree carries one at "
        "all, so the argument has no population and the caveat is unsupported "
        "rather than confirmed"
    )
    assert inwin_stamped == 0, (
        f"README caveat 9 says no in-window row carries a create_time, which is "
        f"what makes the look-ahead limit a fact about the window rather than "
        f"about the column; {inwin_stamped:,} of the {stamped:,} stamped rows "
        f"now fall inside it, so monthly revenue may be alignable point-in-time"
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
            f"month_rev create_time on {stamped:,} of {tot:,} rows and none of "
            f"them in-window, pre-window lag from {min(backfill_lag):,}d; "
            f"dividend has it"), tot


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
        f"matching the exchange's pre-event before_price on 99.84 % of 除權息 "
        f"events; it now matches {100 * frac:.2f} % of {tot:,}. A fall here "
        f"means the raw series is no longer raw, and price_adj/ would "
        f"double-count against it"
    )
    return (f"ohlcv/ is raw: {hit:,}/{tot:,} = {100 * frac:.2f} % vs "
            f"before_price"), tot


# ---- Taiwan: what the bought adjusted series is, and what it does not mark --
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
    assert (n_cash, float(cash_dev.min() > 1e-3)) == (82, 1.0), (
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
    n_filled = int((vendor["close"] > 0).sum() - (d["close"] > 0).sum())
    # 8934 is the example because it barely trades: its zero-close rows are the
    # majority of its file. Both counts are pinned rather than tested for
    # presence — a single surviving zero-close row would satisfy `> 0` while the
    # encoding this check exists for had changed underneath it.
    assert (int(z.sum()), n_filled) == (1321, 1321), (
        f"8934 is chosen for having 1,321 zero-close sessions, every one of "
        f"which the vendor prices anyway; this tree has {int(z.sum())} and the "
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

    `vendor_event_audit.parquet` is what the README's 84.2 % / 99.5 % and the
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
    pd.testing.assert_frame_equal(
        committed.reset_index(drop=True), fresh.reset_index(drop=True),
        check_exact=True, obj="vendor_event_audit.parquet")

    ck = committed[committed["checkable"]]
    assert (len(committed), len(ck)) == (18277, 18087), (
        f"README pins 18,277 filed 除權息 of which 18,087 are graded against "
        f"the exchange; this tree gives {len(committed):,} / {len(ck):,}"
    )
    # The two counts are one file and a column, not a filter that moved between
    # runs. Pin what the 34-row difference is made of so it stays that way.
    nc = committed[~committed["checkable"]]
    served = {p.stem for p in (REPO / "finmind_data/price_adj").glob("*.parquet")
              if len(_tree(p))}
    unserved = int((~nc["stock_id"].astype(str).isin(served)).sum())
    assert (len(nc), unserved) == (190, 174), (
        f"the 190 ungradable events should be 174 in stocks the vendor serves "
        f"nothing for and 16 with no adjacent bracketing session; this tree "
        f"gives {len(nc)} ungradable of which {unserved} are unserved"
    )
    w6, w3 = float((ck["rel"] < 1e-6).mean()), float((ck["rel"] < 1e-3).mean())
    assert abs(w6 - 0.8425) < 5e-4 and abs(w3 - 0.9951) < 5e-4, (
        f"README claims the vendor step matches the exchange's published "
        f"before_price/after_price to 1e-6 on 84.2 % of graded events and to "
        f"1e-3 on 99.5 %; this tree gives {100 * w6:.2f} % / {100 * w3:.2f} %. "
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
    assert (len(up), len(flipped)) == (14, 0), (
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
    """README, "The edge of the vendor series": 492 first sessions carry the
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
    refused = []
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
        # carry stays NaN rather than being filled from further away.
        for i in np.nonzero((df["close"].to_numpy() > 0) & (s == ""))[0]:
            refused.append((sid, str(pd.Timestamp(dates[i]).date())))

    assert refused == [("4141", "2011-04-14")], (
        f"the carry guard should refuse exactly 4141's 2011-04-14 stub print "
        f"among these stocks; it refused {refused}"
    )
    assert (head, tail) == (1, 0), (
        f"these stocks hold 1 of the 492 carried first sessions, and no session "
        f"after a delisting is carried anywhere in the panel; this tree carries "
        f"{head} / {tail}"
    )
    return (f"{head} first session carried from the adjacent factor with no "
            f"filing in the gap, {tail} after a delisting; "
            f"4141 2011-04-14 refused"), head + len(refused)


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
    *this* reason: dropping the mask leaves the 125,055 rows valid with no reason
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
            # The 59 stocks with no in-window sessions to load — one whose OHLCV
            # file holds no rows at all and 58 quoted only outside the window; a
            # 60th would push the count past the assertion below rather than
            # pass quietly.
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

    assert len(empty) == 59, (
        f"README says load_adjusted refuses 59 of the universe's names — 1 whose "
        f"OHLCV file holds no rows at all and 58 quoted only outside the window; "
        f"{len(empty)} raised here, so this pass covered a "
        f"different panel than the counts below were measured on")
    assert (rows, zero, zero_stocks) == (5_882_323, 127_838, 1_150), (
        f"README quotes 127,838 no-trade sessions in 1,150 stocks over a "
        f"5,882,323-row panel; this tree has {zero:,} in {zero_stocks:,} over "
        f"{rows:,}. Every count below is a share of that population")
    assert mismatched == 0, (
        f"README claims is_valid alone is now enough — every False row carries "
        f"a reason and every True row carries none. {mismatched:,} of {rows:,} "
        f"rows break that, so invalid_reason no longer accounts for is_valid")
    assert by_reason == {"no_trade": 125_055,
                         "series_break": 1_931,
                         "unpriced_cancellation": 852}, (
        f"README claims 125,055 no-trade sessions take the new reason and the "
        f"2,783 behind a segment reason keep it; the split here is {by_reason}")
    assert len(no_trade_stocks) == 1_141, (
        f"README claims the 125,055 no_trade rows fall in 1,141 stocks — the "
        f"1,150 with a zero close, less the 9 whose zero closes all sit behind "
        f"a break; {len(no_trade_stocks):,} carry one here")
    return (f"{by_reason['no_trade']:,} no-trade sessions in "
            f"{len(no_trade_stocks):,} stocks marked invalid, "
            f"{zero - by_reason['no_trade']:,} more kept by a segment reason; "
            f"is_valid accounts for all {invalid:,} invalid rows of {rows:,}"
            ), rows


# ---- Taiwan: the make-up sessions ohlcv/ dropped ---------------------------
def test_taiwan_make_up_sessions_are_recovered():
    """README, "The gap that runs the other way": 303 sessions, and 303 returns.

    The cost of a dropped session is not the row. It is that the *next* session's
    return spans two sessions instead of one, so the 303 sessions `ohlcv/` has no
    row for were 303 overstated returns — and not scattered, but clustered on 14
    holiday-adjacent Saturdays, which is the shape a study would read as an
    effect. That contamination is invisible to the coverage decomposition, which
    counts rows and not the gaps between them, so it is asserted here.

    The assertion is on the return path rather than on the count: after the
    recovery no session `price_adj/` carries is absent from the panel, which is
    what makes every return a one-session return.

    The reconstruction is then checked against a source it did not use. The
    loader takes the nearer earlier anchor; this recomputes from the following
    one, a different session in the opposite direction, and the two must give the
    same price. That is a real check because it would fail on exactly what the
    method assumes away — a factor that moved inside the interval.
    """
    sys.path.insert(0, str(REPO))
    import numpy as np

    from finmind_data.adjusted_loader import load_adjusted

    # Which stocks could be short a session at all — a set difference over the
    # files, so the expensive pass runs on the 159 that can fail rather than the
    # 2,103 that cannot.
    want = {}
    for sid in _panel_ids():
        raw = _tree(REPO / f"finmind_data/ohlcv/{sid}.parquet")
        adj = _tree(REPO / f"finmind_data/price_adj/{sid}.parquet")
        if not len(raw) or not len(adj):
            continue
        only = set(pd.to_datetime(adj["date"])) - set(pd.to_datetime(raw["date"]))
        if only:
            want[sid] = (only, adj)

    n_traded = n_flat = n_both = 0
    dev = []
    for sid, (only, adj) in want.items():
        df = load_adjusted(sid)
        assert df.attrs["vendor_only_sessions"] == len(only), (
            f"{sid}: attrs reports {df.attrs['vendor_only_sessions']} vendor-only "
            f"sessions against {len(only)} in the files")
        panel = set(df["date"])
        assert not (only - panel), (
            f"{sid}: {len(only - panel)} sessions price_adj/ carries are still "
            f"absent from the panel, so the return after each of them spans two "
            f"sessions rather than one")
        rec = df[~df["raw_covered"]]
        assert set(rec["date"]) == only, (
            f"{sid}: raw_covered is False on {len(rec)} rows against {len(only)} "
            f"sessions ohlcv/ has no row for, so the flag no longer marks what "
            f"was reconstructed")

        a = adj.assign(date=pd.to_datetime(adj["date"])).sort_values("date")
        priced = a.set_index("date")["close"].astype(float).to_dict()
        vol = a.set_index("date")["Trading_Volume"].to_dict()
        d8 = list(df["date"])
        seat = np.nonzero((df["raw_covered"].to_numpy())
                          & (df["close"].to_numpy(dtype=float) > 0)
                          & np.array([priced.get(x, 0.0) > 0 for x in d8]))[0]
        for _, r in rec.iterrows():
            if vol[r["date"]] == 0:
                # ohlcv/ writes a session with no volume as a zero row and never
                # with a close, so that is what a reconstruction of one holds.
                n_flat += 1
                assert r["close"] == 0 and not r["is_valid"], (
                    f"{sid} {r['date'].date()}: the vendor reports no volume, so "
                    f"the row should read as the no-trade row ohlcv/ would have "
                    f"written and be unholdable; it carries close {r['close']} "
                    f"and is_valid {r['is_valid']}")
                continue
            n_traded += 1
            # Reconstruct from the anchor on each side and hold the loader's
            # price to both. Checking only the side it did not take would leave
            # the check trivial whenever it fell back to the other one.
            k = int(np.searchsorted([d8[j] for j in seat], r["date"], "left"))
            js = [j for j in (k - 1, k) if 0 <= j < len(seat)]
            n_both += len(js) == 2
            for i in (seat[j] for j in js):
                f = priced[d8[i]] / float(df["close"].to_numpy()[i])
                dev.append(abs(priced[r["date"]] / f / r["close"] - 1.0))

    assert (len(want), n_traded + n_flat, n_traded) == (96, 303, 210), (
        f"README claims 303 make-up sessions in 96 stocks, 210 of them traded; "
        f"this tree recovers {n_traded + n_flat} in {len(want)}, {n_traded} traded")
    dev = np.array(dev)
    assert (len(dev), n_both) == (419, 209) and dev.max() < 1e-5, (
        f"209 of the 210 traded make-up sessions have a usable anchor on both "
        f"sides, and the price the loader wrote has to be reproducible from "
        f"either — a disagreement is a factor that moved inside the interval the "
        f"carry assumes it did not. {len(dev)} reconstructions were run over "
        f"{n_both} two-sided sessions, and the worst differs from the loader's "
        f"price by {dev.max():.2e}")
    return (f"{n_traded + n_flat} make-up sessions recovered in {len(want)} "
            f"stocks ({n_traded} traded, {n_flat} written as no-trade rows); "
            f"no return spans two sessions; the two anchors agree to "
            f"{dev.max():.1e}"), n_traded + n_flat


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
    """README, "Validated on the 116 covered in-window delistings".

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

    assert (stocks, n) == (116, 203671), (
        f"README quotes the gate on 116 covered in-window delistings and "
        f"203,671 daily adjusted returns; this tree gives {stocks} / {n:,}"
    )
    assert ok6 / n >= 0.9991 and ok3 / n >= 0.9999, (
        f"README claims the rebuild reproduces the vendor on 99.954 % of daily "
        f"adjusted returns to 1e-6 and 99.998 % to 1e-3; this tree gives "
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
    for sub, kind, n_ends in (("fin_is", "financial_statement", 56),
                              ("fin_bs", "financial_statement", 53),
                              ("fin_cf", "financial_statement", 56),
                              ("month_rev", "monthly_revenue", 167)):
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
    # goes from four months to three and the half-year from a 75-day
    # consolidated back-stop to 45 days. A constant fitted to either side is
    # wrong for a third of the window.
    want = {"2010-12-31": "2011-04-30", "2011-06-30": "2011-09-13",
            "2011-12-31": "2012-03-31", "2012-06-30": "2012-08-14",
            "2024-12-31": "2025-03-31"}
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
    return (f"all {resolved} period ends in fin_is/fin_bs/fin_cf/month_rev "
            f"resolve; 2012 regime boundary holds; extra_days additive"), resolved


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


CHECKS = [
    test_taiwan_tree_readers_import_the_window,
    test_taiwan_ohlcv_one_per_universe,
    test_taiwan_universe_excludes_the_instruments_it_claims_to,
    test_taiwan_price_adj_one_per_universe,
    test_taiwan_overlay_covers_the_window,
    test_taiwan_adjusted_survivorship_hole,
    test_taiwan_adjusted_coverage_decomposition,
    test_taiwan_vendor_event_audit_is_current,
    test_taiwan_vendor_defects_are_patched,
    test_taiwan_vendor_edges_are_carried,
    test_taiwan_post_delisting_sessions_are_marked,
    test_taiwan_no_trade_rows_are_not_holdable,
    test_taiwan_make_up_sessions_are_recovered,
    test_taiwan_survivorship_hole_is_rebuilt,
    test_taiwan_rebuild_matches_vendor,
    test_taiwan_adj_source_partitions_the_panel,
    test_taiwan_adj_covered_survives_concat,
    test_taiwan_open_outside_session_range,
    test_taiwan_delisting_table_has_no_reason,
    test_taiwan_delisting_sign_sample_is_preregistered,
    test_taiwan_delisting_sign_accuracy,
    test_taiwan_single_cut_is_registered_unscored,
    test_taiwan_delisting_substitute_is_biased_low,
    test_taiwan_cash_payouts_land_outside_the_band,
    test_taiwan_fundamentals_are_fiscal_dated,
    test_taiwan_filing_deadline_table_covers_the_data,
    test_taiwan_month_rev_date_is_the_following_month,
    test_taiwan_no_event_holes_are_event_free_in_three_sources,
    test_capital_reduction_artifact_exists,
    test_taiwan_ohlcv_is_raw,
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
    # The bound is per check because a population clipped to the study window
    # cannot legitimately move at all, while one open past the window grows every
    # time the vendor is re-pulled — a single rule would either fail every
    # refresh or catch nothing.
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
