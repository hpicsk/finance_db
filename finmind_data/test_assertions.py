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
# The study window every package's figures are quoted on. Duplicated in each
# assertion file because the container holds no shared module to import it from;
# `run_assertions.sh` fails if the copies ever disagree.
WIN_START = pd.Timestamp("2005-01-01")
WIN_END = pd.Timestamp("2024-12-31")
# Each check's population, recorded so a tree that lost rows fails rather
# than passing on a smaller one. Per package, not per repo: the root is a
# container and holds no package's numbers.
POPULATIONS = Path(__file__).with_name("populations.json")


class Skipped(Exception):
    """A prerequisite artifact is absent, so this check verified nothing.

    Distinct from a pass because it is: it used to print as one, which is the
    same confusion the population guard below exists to remove.
    """


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
    assert len(u) == 2154, f"Taiwan universe = {len(u)}, README pins 2,154"
    assert not missing, f"{len(missing)} universe ids have no OHLCV file"
    return f"Taiwan universe = {len(u)}; all have OHLCV", len(u)


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
    empty = sum(1 for sid in uid
                if not len(pd.read_parquet(
                    REPO / f"finmind_data/price_adj/{sid}.parquet")))
    assert empty == 51, (
        f"README pins 51 empty adjusted series (38 of them 2005-2007 "
        f"delistings, 13 post-window listings); the tree now has {empty}. "
        f"A change here moves the survivorship hole the README quantifies"
    )
    return (f"all {len(uid)} ids fetched; {empty} empty, {len(uid) - empty} "
            f"with data"), len(uid)


def test_taiwan_adjusted_survivorship_hole():
    """README, "The adjusted panel is survivorship-biased": 38 of 173.

    The universe carries a 42-name overlay of 2005-2007 delistings that
    FinMind's live `taiwan_stock_info` no longer returns (see
    `test_taiwan_overlay_covers_2005_2014`). `TaiwanStockPriceAdj` drops the
    same names, so the raw panel is survivorship-free and the adjusted one is
    not. This asserts the size of that hole, because a panel built by dropping
    NaN reinstates the bias without saying so.
    """
    u = pd.read_parquet(REPO / "finmind_data/universe.parquet")
    d = pd.read_parquet(REPO / "finmind_data/delisted_universe.parquet")
    uid = set(u["stock_id"].astype(str))
    d = d.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["sid"] = d["stock_id"].astype(str)
    inwin = d[(d["date"] >= WIN_START) & (d["date"] <= WIN_END) & d["sid"].isin(uid)]

    hole = []
    for sid in sorted(set(inwin["sid"])):
        raw = pd.read_parquet(REPO / f"finmind_data/ohlcv/{sid}.parquet")
        adj = pd.read_parquet(REPO / f"finmind_data/price_adj/{sid}.parquet")
        if len(raw) and not len(adj):
            hole.append(sid)

    assert len(inwin["sid"].unique()) == 173, (
        f"README counts 173 in-window universe delistings; found "
        f"{len(inwin['sid'].unique())}"
    )
    assert len(hole) == 38, (
        f"README claims 38 of the 173 in-window delistings have raw prices and "
        f"no adjusted series; found {len(hole)}. If this shrank the vendor has "
        f"backfilled and the caveat is overstated; if it grew the hole is wider "
        f"than the paragraph says"
    )
    yrs = inwin.set_index("sid").loc[hole, "date"].dt.year
    assert yrs.max() <= 2007, (
        f"README claims every one of them delisted in 2005-2007, which is what "
        f"makes the hole an edge rather than a scatter; the latest is {yrs.max()}"
    )
    return (f"{len(hole)} of 173 in-window delistings have raw prices and no "
            f"adjusted series, all delisted {yrs.min()}-{yrs.max()}"
            ), len(inwin["sid"].unique())


def test_taiwan_adjusted_coverage_decomposition():
    """README, "The adjusted panel is survivorship-biased": 99.80 %, and why.

    The figure has to be quoted against every traded session in `ohlcv/`. Drop
    the 38 uncovered delistings from the denominator and the same files report
    99.95 % — the coverage of a panel the survivorship bias has already been
    taken out of, which is the one number a reader must not cite. This asserts
    the honest denominator and the split of what it misses, so the two cannot
    drift back into each other.

    Coverage has two directions and only one of them is repairable. The
    sessions `price_adj/` is short of are filled from `ohlcv/`; the sessions
    `ohlcv/` is short of have no source behind them, so they are counted here
    beside the ones that do rather than left to a per-stock `attrs` field
    nobody sums.
    """
    u = pd.read_parquet(REPO / "finmind_data/universe.parquet")
    traded = covered = hole = tail = first = 0
    vendor_only = []
    for sid in sorted(set(u["stock_id"].astype(str))):
        fp = REPO / f"finmind_data/ohlcv/{sid}.parquet"
        if not fp.exists():
            continue
        raw = pd.read_parquet(fp)
        if not len(raw):
            continue
        tr = raw[raw["close"] > 0].copy()
        tr["date"] = pd.to_datetime(tr["date"])
        tr = tr.sort_values("date").reset_index(drop=True)
        traded += len(tr)

        adj = pd.read_parquet(REPO / f"finmind_data/price_adj/{sid}.parquet")
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
        first += int((miss & (tr["date"] <= adj_dates.max())).sum())
        assert not (miss & (tr["date"] <= adj_dates.max())
                    & (tr.index > 0)).any(), (
            f"{sid}: a session other than the first is missing from the vendor "
            f"series inside its own date range, which is a hole rather than the "
            f"documented offset and is not what the carry fills"
        )

    assert (traded, covered) == (7509555, 7494582), (
        f"README pins adjusted coverage at 7,494,582 of the 7,509,555 traded "
        f"sessions in ohlcv/ (99.80 %); this tree gives {covered:,} of "
        f"{traded:,} ({100 * covered / max(traded, 1):.2f} %)"
    )
    assert (hole, tail, first) == (10981, 3089, 903), (
        f"README splits the {traded - covered:,} missing sessions into 10,981 "
        f"in the 38 delistings with no adjusted series, 3,089 past the end of a "
        f"vendor series that stopped at a delisting, and 903 first sessions; "
        f"this tree gives {hole:,} / {tail:,} / {first:,}. The first number is "
        f"the survivorship hole — if it moved, so did the bias"
    )

    vo = pd.DataFrame(vendor_only, columns=["stock_id", "date", "lead", "trail"])
    assert (len(vo), vo["stock_id"].nunique(), vo["date"].nunique()) == (600, 159, 22), (
        f"README puts the reverse gap at 600 sessions in 159 stocks on 22 dates; "
        f"this tree gives {len(vo):,} in {vo['stock_id'].nunique()} on "
        f"{vo['date'].nunique()}. These are sessions `ohlcv/` has no row for, so "
        f"unlike the missing adjusted ones they cannot be filled from the panel"
    )
    # Every one is a Saturday 補行交易日, which is the whole content of the
    # finding: the raw endpoint serves those Saturdays for a thousand-odd stocks
    # each and drops the row for a few dozen. An ordinary weekday appearing here
    # would be a different defect wearing the same count.
    assert set(vo["date"].dt.dayofweek) == {5}, (
        f"README calls all 600 make-up Saturdays; this tree has vendor-only "
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


def test_taiwan_overlay_covers_2005_2014():
    """Survivorship invariant.

    The 42-name overlay must cover every 2005-2014 4-digit common delisting
    FinMind purged. Codes are restricted to 4-digit numeric (the universe's own
    filter); pre-2005 names never trade in-window and 2015+ absentees are
    ETF/TDR instruments the universe excludes. The naive "all delisted ids have
    OHLCV" form was a false alarm.
    """
    u, d, uid, _ = _tw_ids()
    d = d.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["sid"] = d["stock_id"].astype(str)
    d4 = d[d["sid"].str.fullmatch(r"\d{4}")]
    in_2005_2014 = d4[(d4["date"] >= WIN_START) & (d4["date"] <= pd.Timestamp("2014-12-31"))]
    missing = sorted(set(in_2005_2014["sid"]) - uid)
    assert not missing, (
        f"{len(missing)} 2005-2014 4-digit common delistings absent from "
        f"universe.parquet (overlay gap): {missing}"
    )
    n_overlay = int(u[u["type"].isna()]["stock_id"].astype(str).str.fullmatch(r"\d{4}").sum())
    assert n_overlay == 42, f"4-digit type=NaN overlay ids = {n_overlay}, expected 42"
    return ("2005-2014 commons fully covered; 42-name overlay present",
            len(in_2005_2014))


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
    hole = load_adjusted("1204")       # one of the 38, covered nowhere
    assert full.attrs["adj_coverage"] == 1.0 and hole.attrs["adj_coverage"] == 0.0, (
        f"2330/1204 chosen as the covered/uncovered pair; they now report "
        f"{full.attrs['adj_coverage']} and {hole.attrs['adj_coverage']}"
    )
    assert hole["adj_covered"].any() is not True and not hole["adj_covered"].any(), (
        "1204 has no adjusted series, so no row may be marked adj_covered"
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
    for p in sorted(glob.glob(str(REPO / "finmind_data/ohlcv/*.parquet"))):
        # 13 files hold no rows and carry no schema, so a column-projected read
        # would fail on them; the row count comes from the footer instead.
        if pq.ParquetFile(p).metadata.num_rows == 0:
            continue
        r = pd.read_parquet(p, columns=["open", "max", "min", "close"])
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
    assert (bad, stocks) == (167930, 836), (
        f"README caveat 10 pins 167,930 rows across 836 stocks with open "
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
    # 173 in-window delistings have prices; `test_taiwan_adjusted_survivorship_hole`
    # counts those. This counts the ones that left the *market* — the same set
    # less 6446, which changed boards and goes on trading, so it has no
    # shareholder outcome to classify.
    assert exited == 172, (
        f"README's delisting-sign section counts 172 in-window delistings that "
        f"exited the market, the 173 priced less the one board transfer; "
        f"features() now returns {exited}"
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
    assert r["n_scored"] == 18, (
        f"the rate rests on 18 labelled names that carry a verdict; "
        f"{r['n_scored']} do now. The estimate is weighted by stratum, so a "
        f"change in which names are decided changes what the 99 % is over"
    )
    assert r["missed"] == ["1613"], (
        f"README caveat 8 says the one miss is 1613 台一, a forced delisting "
        f"for non-filing that never collapsed; the misses are now "
        f"{r['missed']}. The described error mode no longer matches the data"
    )
    assert math.isclose(r["accuracy"], 0.993, abs_tol=0.005), (
        f"README caveat 8 claims the shape is right on 99 % of the names "
        f"carrying a verdict; the weighted rate is now {r['accuracy']:.1%}"
    )
    assert math.isclose(r["n_verdict"], 140, abs_tol=3), (
        f"README caveat 8 puts 140 names under a verdict (41 + 99); the "
        f"stratum-weighted estimate is {r['n_verdict']:.0f}, so the sample no "
        f"longer reconstructs the population it is weighted to"
    )
    assert math.isclose(r["n_ambiguous_merger"], 18, abs_tol=3), (
        f"README caveat 8 says ~18 of the ~32 undecided names are payouts; "
        f"the weighted estimate is now {r['n_ambiguous_merger']:.0f}"
    )
    return (f"{r['accuracy']:.1%} of {r['n_verdict']:.0f} verdicts correct "
            f"from {r['n_scored']} labelled, miss = {r['missed']}; "
            f"undecided band ~{r['n_ambiguous']:.0f}, "
            f"~{r['n_ambiguous_merger']:.0f} payouts",
            len(labels))


def test_taiwan_fundamentals_are_fiscal_dated():
    """README caveat 9: fiscal period end, no announcement date.

    A look-ahead limit rather than a survivorship one, and invisible in the
    schema unless someone states what `date` means. `dividend/` carries
    `AnnouncementDate`, which is what makes the others' silence a gap rather
    than a convention of the source.
    """
    fin = pd.read_parquet(REPO / "finmind_data/fin_is/2330.parquet")
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

    tot = blank = 0
    for p in sorted(glob.glob(str(REPO / "finmind_data/month_rev/*.parquet")))[:200]:
        m = pd.read_parquet(p)
        if not len(m):
            continue
        tot += len(m)
        blank += int((m["create_time"].astype(str).str.strip() == "").sum())
    assert tot and blank == tot, (
        f"README caveat 9 says month_rev's create_time is empty on every row "
        f"(40,735 of 40,735 over the first 200 files); {tot - blank:,} of "
        f"{tot:,} now carry a stamp, which would make monthly revenue the "
        f"second dataset alignable point-in-time"
    )

    div = pd.read_parquet(REPO / "finmind_data/dividend/1101.parquet")
    assert "AnnouncementDate" in div.columns, (
        "README caveat 9 names dividend/ as the one dataset carrying "
        "AnnouncementDate; it no longer does"
    )
    return (f"fin_* dated on quarter ends with no announcement column; "
            f"month_rev create_time blank {blank:,}/{tot:,}; dividend has it"
            ), tot


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
        d = pd.read_parquet(p)
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
        px = pd.read_parquet(fp)
        if not len(px):
            continue
        px["date"] = pd.to_datetime(px["date"])
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
        f"matching the exchange's pre-event before_price on 99.82 % of 除權息 "
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
        ev = pd.read_parquet(REPO / f"finmind_data/div_result/{sid}.parquet")
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
    assert (n_cash, float(cash_dev.min() > 1e-3)) == (89, 1.0), (
        f"README calls price_adj/ a total-return series, which means every one "
        f"of the 89 cash-only 除權息 across these six names steps the factor off "
        f"1; {n_cash} were found and the smallest step is "
        f"{cash_dev.min():.2e} from 1. Under price return every one would be 0"
    )

    # (2) A no-trade session is close == 0 in ohlcv/, and the vendor fills it
    # with the last traded price. Zero is not a price and neither is a carried
    # one, so the row must hold no adjusted close.
    d = load_adjusted("8934")
    z = d["close"] == 0
    vendor = pd.read_parquet(REPO / "finmind_data/price_adj/8934.parquet")
    n_filled = int((vendor["close"] > 0).sum() - (d["close"] > 0).sum())
    # 8934 is the example because it barely trades: its zero-close rows are the
    # majority of its file. Both counts are pinned rather than tested for
    # presence — a single surviving zero-close row would satisfy `> 0` while the
    # encoding this check exists for had changed underneath it.
    assert (int(z.sum()), n_filled) == (2441, 2441), (
        f"8934 is chosen for having 2,441 zero-close sessions, every one of "
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
    # so the history behind it is marked instead of carrying the jump.
    d = load_adjusted("2357")
    brk = pd.Timestamp("2010-06-24")
    i = int(d.index[d["date"] == brk][0])
    step = d["tr_factor"].iloc[i] / d["tr_factor"].iloc[i - 1]
    assert abs(step - 1.0) < 1e-6, (
        f"README claims the vendor carries 2357's pre-2011 reduction through "
        f"at a factor step of exactly 1; the step is now {step:.6f}, so the "
        f"vendor has started pricing it and is_valid may be over-marking"
    )
    assert not d.loc[d["date"] < brk, "is_valid"].any(), (
        "README claims 2357's pre-2010-06-24 history is marked is_valid=False "
        "(unpriced capital reduction); some of it is still flagged valid"
    )
    assert d.loc[d["date"] >= brk, "is_valid"].all(), (
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

    `vendor_event_audit.parquet` is what the README's 83.3 % / 99.5 % and the
    seven patched events are quoted from, and `adjusted_loader` patches off it.
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
    assert (len(committed), len(ck)) == (22370, 22336), (
        f"README pins 22,370 filed 除權息 of which 22,336 are graded against "
        f"the exchange; this tree gives {len(committed):,} / {len(ck):,}"
    )
    # The two counts are one file and a column, not a filter that moved between
    # runs. Pin what the 34-row difference is made of so it stays that way.
    nc = committed[~committed["checkable"]]
    served = {p.stem for p in (REPO / "finmind_data/price_adj").glob("*.parquet")
              if len(pd.read_parquet(p))}
    unserved = int((~nc["stock_id"].astype(str).isin(served)).sum())
    assert (len(nc), unserved) == (34, 12), (
        f"the 34 ungradable events should be 12 in stocks the vendor serves "
        f"nothing for and 22 with no adjacent bracketing session; this tree "
        f"gives {len(nc)} ungradable of which {unserved} are unserved"
    )
    w6, w3 = float((ck["rel"] < 1e-6).mean()), float((ck["rel"] < 1e-3).mean())
    assert abs(w6 - 0.8328) < 5e-4 and abs(w3 - 0.9946) < 5e-4, (
        f"README claims the vendor step matches the exchange's published "
        f"before_price/after_price to 1e-6 on 83.3 % of graded events and to "
        f"1e-3 on 99.5 %; this tree gives {100 * w6:.2f} % / {100 * w3:.2f} %. "
        f"A move here changes what the two conventions in the panel differ by"
    )
    defects = committed[committed["defect"] != ""].groupby("defect").size().to_dict()
    assert defects == {"malformed_twin": 1, "nonpositive_leg": 1, "sign_flip": 6}, (
        f"README claims 6 sign-flipped events, 1 malformed-twin filing and 1 "
        f"non-positive reference leg; this tree grades {defects}. If sign_flip "
        f"shrank the vendor has fixed them and the patch is now a no-op; if it "
        f"grew the patched set in adjusted_loader is short"
    )

    # The defect is an era, not a rate. Every flip is 2005-2008 and every upward
    # reprice after the last of them is exact, which is what makes the next
    # search of this kind cheap — and what makes a rate measured on the
    # 2005-2007 delisting sample the wrong thing to extrapolate.
    up = ck[ck["exchange_step"] < 1.0]
    flipped = up[up["defect"] == "sign_flip"]["date"]
    clean = up[up["defect"] != "sign_flip"]["date"]
    assert len(up) == 24 and len(flipped) == 6, (
        f"the sign-flip class is defined against the {len(up)} upward reprices "
        f"in the graded set, of which {len(flipped)} are flipped; the module "
        f"docstring says 24 and 6"
    )
    assert flipped.max() == pd.Timestamp("2008-09-16"), (
        f"the docstring localises every flip to 2005-2008, last on 2008-09-16; "
        f"this tree flips one on {flipped.max().date()}"
    )
    assert (clean > flipped.max()).sum() == 16, (
        f"the docstring counts 16 exact upward reprices after the last flip, "
        f"and 2 more inside the defective window; this tree has "
        f"{int((clean > flipped.max()).sum())} after it"
    )
    assert not ((up["date"] > flipped.max()) & (up["defect"] != "")).any(), (
        f"the docstring claims every upward reprice after 2008-09-16 is exact, "
        f"so a defect past it means the vendor's pipeline was not fixed and the "
        f"search window has to reopen"
    )
    return (f"{len(ck):,}/{len(committed):,} events graded; vendor == exchange "
            f"{100 * w6:.2f} % at 1e-6, {100 * w3:.2f} % at 1e-3; defects "
            f"{defects}, every flip in {flipped.min().date()}.."
            f"{flipped.max().date()}"), len(committed)


def test_taiwan_vendor_defects_are_patched():
    """README, "Seven vendor events carry the exchange's step instead".

    Each patched event should leave the loader's factor stepping by the
    exchange's published before_price/after_price across it, not the vendor's.
    Six of the seven reverse the direction of the move, so an unpatched panel
    puts a return of the wrong sign on those sessions.
    """
    sys.path.insert(0, str(REPO))
    import numpy as np

    from finmind_data.adjusted_loader import load_adjusted
    from finmind_data.vendor_event_audit import defective_events

    d = defective_events()
    assert len(d) == 7, (
        f"README claims 7 vendor events are replaced with the exchange's step; "
        f"the audit now marks {len(d)}"
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

    assert sum(spans) == 3641, (
        f"README claims the seven patches rescale 3,641 rows between them; "
        f"this tree labels {sum(spans):,}"
    )
    return (f"7 events patched to the exchange's step; the patch moves the "
            f"ex-date factor by {100 * min(moved):.2f}-{100 * max(moved):.2f} % "
            f"and rescales {sum(spans):,} rows behind them"), sum(spans)


def test_taiwan_vendor_edges_are_carried():
    """README, "The two edges of the vendor series": 902 first sessions and
    3,089 post-delisting ones carry the adjacent factor, and one is refused.

    A back-adjustment factor moves only on an ex date, so carrying it across a
    gap with no filing in it is exact rather than an interpolation — which is
    what makes these two fills safe where a splice would not be. The guard is
    the part worth asserting: it is checked per row against every filed 除權息
    and 減資 plus the cancellations no filing explains, and it refuses 4141,
    whose first print sits 376 days before the vendor's first session with a
    cancellation on that session. A guard that never fires is indistinguishable
    from no guard.
    """
    sys.path.insert(0, str(REPO))
    import numpy as np

    from finmind_data import adjust
    from finmind_data.adjusted_loader import _unpriced_dates, load_adjusted

    head = tail = 0
    refused = []
    for sid in ("1580", "3271", "3454", "1107", "2381", "2396", "2341",
                "3142", "2479", "3053", "4141", "2330"):
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
    assert (head, tail) == (3, 3089), (
        f"these stocks hold 3 of the 902 carried first sessions and all 3,089 "
        f"post-delisting ones; this tree carries {head} / {tail}"
    )
    return (f"{head} first sessions and {tail} post-delisting sessions carried "
            f"from the adjacent factor with no filing in the gap; "
            f"4141 2011-04-14 refused"), head + tail


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
        c = pd.read_parquet(f)
        if len(c):
            last[str(r.stock_id)] = pd.to_datetime(c["date"]).max()
    panel_end = max(last.values())

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

    assert (len(names), marked) == (14, 4_632), (
        f"README claims 4,632 post-delisting sessions across 14 names; this "
        f"tree marks {marked:,} across {len(names)}")
    # Sorted, because the loop takes the delisting table's row order and a
    # re-collect that reorders it would fail this on nothing.
    assert (sorted(moved), sorted(reissued)) == (["6446"], ["2301", "2432"]), (
        f"README names 6446 as the one delisting that is a board transfer and "
        f"2301 and 2432 as the two reused codes; this tree finds {moved} and "
        f"{reissued}. A new transfer is a name whose exit the table records and "
        f"whose arrival it does not, so a delisting return computed for it "
        f"would be a loss it never took")
    return (f"{marked:,} post-delisting sessions priced and marked invalid "
            f"across {len(names)} names; {transferred} sessions of {moved[0]}'s "
            f"board transfer left holdable, {len(reissued)} reused codes cut "
            f"behind their reissue"), marked + transferred


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
    *this* reason: dropping the mask leaves the 167,162 rows valid with no reason
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
    for p in sorted(glob.glob(str(REPO / "finmind_data/ohlcv/*.parquet"))):
        sid = Path(p).stem
        try:
            df = load_adjusted(sid)
        except ValueError:
            # The 13 stocks whose OHLCV file holds no rows at all; a 14th would
            # push the count past the assertion below rather than pass quietly.
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

    assert len(empty) == 13, (
        f"README says 13 stocks have a zero-row OHLCV file and load_adjusted "
        f"raises on them; {len(empty)} raised here, so this pass covered a "
        f"different panel than the counts below were measured on")
    assert (rows, zero, zero_stocks) == (7_689_904, 179_930, 1_325), (
        f"README quotes 179,930 no-trade sessions in 1,325 stocks over a "
        f"7,689,904-row panel; this tree has {zero:,} in {zero_stocks:,} over "
        f"{rows:,}. Every count below is a share of that population")
    assert mismatched == 0, (
        f"README claims is_valid alone is now enough — every False row carries "
        f"a reason and every True row carries none. {mismatched:,} of {rows:,} "
        f"rows break that, so invalid_reason no longer accounts for is_valid")
    assert by_reason == {"no_trade": 167_162,
                         "post_delisting_emerging": 19,
                         "series_break": 3_244,
                         "unpriced_cancellation": 9_505}, (
        f"README claims 167,162 no-trade sessions take the new reason and the "
        f"12,768 behind a segment reason keep it; the split here is {by_reason}")
    assert len(no_trade_stocks) == 1_309, (
        f"README claims the 167,162 no_trade rows fall in 1,309 stocks — the "
        f"1,325 with a zero close, less the 16 whose zero closes all sit behind "
        f"a break; {len(no_trade_stocks):,} carry one here")
    return (f"{by_reason['no_trade']:,} no-trade sessions in "
            f"{len(no_trade_stocks):,} stocks marked invalid, "
            f"{zero - by_reason['no_trade']:,} more kept by a segment reason; "
            f"is_valid accounts for all {invalid:,} invalid rows of {rows:,}"
            ), rows


# ---- Taiwan: the make-up sessions ohlcv/ dropped ---------------------------
def test_taiwan_make_up_sessions_are_recovered():
    """README, "The gap that runs the other way": 600 sessions, and 600 returns.

    The cost of a dropped session is not the row. It is that the *next* session's
    return spans two sessions instead of one, so the 600 sessions `ohlcv/` has no
    row for were 600 overstated returns — and not scattered, but clustered on 22
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
    for p in sorted(glob.glob(str(REPO / "finmind_data/ohlcv/*.parquet"))):
        sid = Path(p).stem
        raw = pd.read_parquet(p)
        adj = pd.read_parquet(REPO / f"finmind_data/price_adj/{sid}.parquet")
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

    assert (len(want), n_traded + n_flat, n_traded) == (159, 600, 419), (
        f"README claims 600 make-up sessions in 159 stocks, 419 of them traded; "
        f"this tree recovers {n_traded + n_flat} in {len(want)}, {n_traded} traded")
    dev = np.array(dev)
    assert (len(dev), n_both) == (837, 418) and dev.max() < 1e-5, (
        f"418 of the 419 traded make-up sessions have a usable anchor on both "
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
    """README, "The survivorship hole is filled": 38 stocks, 10,981 sessions.

    The universe carries a 42-name overlay of 2005-2007 delistings FinMind's
    live registry dropped, and `TaiwanStockPriceAdj` drops 38 of them too. A
    panel built by concatenating `load_adjusted` and dropping NaN used to
    reinstate the bias silently; it no longer can, but only while every one of
    the 38 comes back with a price. `adj_covered` stays False across them so
    the hole remains countable after it is filled.
    """
    sys.path.insert(0, str(REPO))
    from finmind_data.adjusted_loader import load_adjusted

    u = pd.read_parquet(REPO / "finmind_data/universe.parquet")
    d = pd.read_parquet(REPO / "finmind_data/delisted_universe.parquet")
    uid = set(u["stock_id"].astype(str))
    d = d.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["sid"] = d["stock_id"].astype(str)
    inwin = d[(d["date"] >= WIN_START) & (d["date"] <= WIN_END) & d["sid"].isin(uid)]

    holes = [sid for sid in sorted(set(inwin["sid"]))
             if len(pd.read_parquet(REPO / f"finmind_data/ohlcv/{sid}.parquet"))
             and not len(pd.read_parquet(REPO / f"finmind_data/price_adj/{sid}.parquet"))]
    traded = priced = 0
    kinds = {}
    invalid = {}
    for sid in holes:
        df = load_adjusted(sid)
        t = df["close"] > 0
        traded += int(t.sum())
        priced += int((t & df["adj_close_tr"].notna()).sum())
        assert not df["adj_covered"].any(), (
            f"{sid} is one of the 38 the vendor serves nothing for, but "
            f"adj_covered is True somewhere — the hole is no longer countable"
        )
        for k in df.loc[df["adj_source"] != "", "adj_source"].unique():
            kinds[k] = kinds.get(k, 0) + 1
        # Over the traded sessions only, which is the population `invalid`
        # counts. Every stock also carries no-trade rows, and they are invalid
        # for a reason that has nothing to do with the rebuild.
        for k, c in df.loc[t & ~df["is_valid"], "invalid_reason"].value_counts().items():
            invalid[k] = invalid.get(k, 0) + int(c)

    assert (len(holes), traded, priced) == (38, 10981, 10981), (
        f"README claims all 38 vendor holes come back priced across their "
        f"10,981 traded sessions; this tree gives {len(holes)} stocks, "
        f"{traded:,} traded, {priced:,} priced. An unpriced session here is a "
        f"survivorship hole the panel build will drop"
    )
    assert kinds == {"rebuilt_factored": 11, "rebuilt_noevent": 27}, (
        f"README splits the 38 into 11 with a factor chain and 27 with no "
        f"corporate action in window; this tree gives {kinds}. The split is "
        f"what isolates the cumulative-product path from the flat one"
    )
    assert invalid == {"unpriced_cancellation": 970,
                       "post_delisting_emerging": 1_524}, (
        f"README claims 970 of those sessions sit behind an unpriced share "
        f"cancellation in 4 of the 38, and 1,524 follow a delisting in 7 of "
        f"them; this tree gives {invalid}. The second number is the one the "
        f"rebuild itself created: these stocks have no vendor series, so the "
        f"delisting boundary had nothing to read until it was moved onto the "
        f"delisting table"
    )
    return (f"{len(holes)} holes rebuilt over {priced:,} traded sessions "
            f"({kinds}); {invalid['unpriced_cancellation']:,} behind an "
            f"unpriced cancellation, "
            f"{invalid['post_delisting_emerging']:,} past a delisting"), traded


def test_taiwan_rebuild_matches_vendor():
    """README, "Validated on the 134 covered in-window delistings".

    The rebuild is only trustworthy on the 38 if the same code path reproduces
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
    ids = sorted(set(d[(d["date"] >= WIN_START)
                       & (d["date"] <= WIN_END)]["stock_id"].astype(str)))
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

    assert (stocks, n) == (134, 268503), (
        f"README quotes the gate on 134 covered in-window delistings and "
        f"268,503 daily adjusted returns; this tree gives {stocks} / {n:,}"
    )
    assert ok6 / n >= 0.9993 and ok3 / n >= 0.9999, (
        f"README claims the rebuild reproduces the vendor on 99.93 % of daily "
        f"adjusted returns to 1e-6 and 99.997 % to 1e-3; this tree gives "
        f"{100 * ok6 / n:.3f} % / {100 * ok3 / n:.3f} %. Below that the 38 "
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
    for sid in ("2330", "8934", "2396", "2822", "1207", "2357"):
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
    for sub, kind, n_ends in (("fin_is", "financial_statement", 80),
                              ("fin_bs", "financial_statement", 53),
                              ("fin_cf", "financial_statement", 65),
                              ("month_rev", "monthly_revenue", 240)):
        ends = set()
        for f in sorted(glob.glob(str(REPO / f"finmind_data/{sub}/*.parquet"))):
            if not pq.ParquetFile(f).metadata.num_rows:
                continue
            ends |= set(pd.to_datetime(pd.read_parquet(f, columns=["date"])["date"]))
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
    d = pd.read_parquet(REPO / "finmind_data/fin_is/2330.parquet")
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
        d = pd.read_parquet(f, columns=["date", "revenue_month", "revenue_year"])
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
    test_taiwan_ohlcv_one_per_universe,
    test_taiwan_price_adj_one_per_universe,
    test_taiwan_overlay_covers_2005_2014,
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
    test_taiwan_fundamentals_are_fiscal_dated,
    test_taiwan_filing_deadline_table_covers_the_data,
    test_taiwan_month_rev_date_is_the_following_month,
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
