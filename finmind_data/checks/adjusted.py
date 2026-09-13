"""The adjusted panel: the vendor's series, the rebuild, the patches, the edges, the validity flags."""
from __future__ import annotations
import pandas as pd

from finmind_data.window import COVERAGE_END, COVERAGE_START
from finmind_data.paths import DATA, TREES
from ._common import Skipped, _panel_ids, _tree


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
    u = pd.read_parquet(DATA / "universe.parquet")
    d = pd.read_parquet(DATA / "delisted_universe.parquet")
    uid = set(u["stock_id"].astype(str))
    d = d.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["sid"] = d["stock_id"].astype(str)
    inwin = d[(d["date"] >= COVERAGE_START) & (d["date"] <= COVERAGE_END)
              & d["sid"].isin(uid)]

    hole = []
    for sid in sorted(set(inwin["sid"])):
        raw = _tree(TREES / f"ohlcv/{sid}.parquet")
        adj = _tree(TREES / f"price_adj/{sid}.parquet")
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
    u = pd.read_parquet(DATA / "universe.parquet")
    traded = covered = hole = tail = first = makeup = gap = 0
    vendor_only = []
    gaps = []
    heads = {}
    for sid in sorted(set(u["stock_id"].astype(str))):
        fp = TREES / f"ohlcv/{sid}.parquet"
        if not fp.exists():
            continue
        raw = _tree(fp)
        if not len(raw):
            continue
        tr = raw[raw["close"] > 0].copy()
        tr["date"] = pd.to_datetime(tr["date"])
        tr = tr.sort_values("date").reset_index(drop=True)
        traded += len(tr)

        adj = _tree(TREES / f"price_adj/{sid}.parquet")
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
        # the raw file kept printing through. The head edge is the run of traded
        # sessions before the vendor's first covered one, which
        # `test_taiwan_vendor_edges_are_carried` covers. Read as a run of dates
        # rather than as the row at position 0: the re-pull fill put a listing-day
        # Saturday in front of two series whose first session was already ahead of
        # the vendor's (caveat 15), so the edge is no longer one row per stock.
        # The vendor's own file may open on an earlier *date* than the raw series'
        # first traded session, because a raw series can open on a no-trade row the
        # vendor still carries a price for; what it never does is open before the
        # raw file does, which the `lead` count below pins.
        tail += int((miss & (tr["date"] > adj_dates.max())).sum())
        inner = miss & (tr["date"] <= adj_dates.max())
        # The reverse gap runs both ways, and only one direction was known. The
        # 303 sessions below were Saturday 補行交易日 the vendor prices and the
        # raw endpoint had no row for; these are the same Saturdays traded in
        # `ohlcv/` and absent from the vendor series. The panel marks every one
        # of them `adj_covered=False` rather than carrying a price across, so
        # they are a disclosed hole and counted as one.
        mk = inner & (tr["date"].dt.dayofweek == 5) & (tr.index > 0)
        makeup += int(mk.sum())
        covered_from = tr.loc[~miss, "date"].min() if (~miss).any() else tr["date"].max()
        lead = inner & ~mk & (tr["date"] < covered_from)
        first += int(lead.sum())
        if lead.any():
            heads[sid] = int(lead.sum())
        # The fifth kind, and the only one that is the vendor being short rather
        # than the vendor's product being shaped that way: a weekday inside a
        # live series the adjusted endpoint has no row for. Both are a lone
        # traded day inside a suspension, and asking the endpoint for the stretch
        # directly returns the same short answer, so the tree records what is
        # served. Counted rather than forbidden — the coverage ratio asserted
        # below is what bounds it, and an outage large enough to matter moves it.
        g = inner & ~mk & ~lead
        gap += int(g.sum())
        gaps += [(sid, d.strftime("%Y-%m-%d")) for d in tr.loc[g, "date"]]

    assert (traded, covered) == (6540524, 6477647), (
        f"README pins adjusted coverage at 6,477,647 of the 6,540,524 traded "
        f"sessions in ohlcv/ (99.04 %); this tree gives {covered:,} of "
        f"{traded:,} ({100 * covered / max(traded, 1):.2f} %)"
    )
    assert (hole, tail, first, makeup, gap) == (61505, 0, 498, 872, 2), (
        f"README splits the {traded - covered:,} missing sessions into 61,505 "
        f"in the 54 stocks with no adjusted series, none past the end of a "
        f"vendor series that stopped at a delisting, 498 sessions ahead of the "
        f"vendor's first, 872 make-up sessions the vendor's adjusted product "
        f"does not cover and 2 weekdays inside a live series it is simply short "
        f"of; this tree gives {hole:,} / {tail:,} / {first:,} / {makeup} / "
        f"{gap}. The first number is the survivorship hole — if it moved, so did "
        f"the bias"
    )
    assert (len(heads), sum(n > 1 for n in heads.values())) == (496, 2), (
        f"README says the 498 sessions ahead of the vendor's first sit in 496 "
        f"stocks, two of them carrying the listing-day Saturday the re-pull fill "
        f"added in front of a session already ahead of it (caveat 15); they sit "
        f"in {len(heads)}, {sum(n > 1 for n in heads.values())} with more than one"
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
    from finmind_data.derive.adjusted_loader import load_adjusted
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


# ---- Taiwan: the coverage flag has to survive a panel build -----------------
def test_taiwan_adj_covered_survives_concat():
    """README, "The adjusted panel is survivorship-biased": `adj_covered`.

    Coverage rides on a column rather than `df.attrs` because `attrs` survives
    `pd.concat` only when every frame agrees. That makes it present on a panel
    of uniformly covered stocks, which needs no warning, and absent on one that
    mixes covered with uncovered, which is the only panel that does. This pins
    both halves: that `attrs` really does drop, and that the column does not.
    """
    if not (DATA / "unpriced_actions.parquet").exists():
        raise Skipped("unpriced_actions.parquet not built")
    from finmind_data.derive.adjusted_loader import load_adjusted

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
        raw = TREES / f"ohlcv/{sid}.parquet"
        if not raw.exists() or not len(_tree(raw)):
            continue
        if not len(_tree(TREES / f"price_adj/{sid}.parquet")):
            holes.append(sid)
    assert len(holes) == 54, (
        f"README counts 54 stocks with raw prices and no adjusted series in the "
        f"window; this tree has {len(holes)}. The split below is over that set"
    )

    cr = _tree(DATA / "capital_reduction.parquet")
    cr_ids = set(cr["stock_id"].astype(str))
    er = _tree(DATA / "exright_reference.parquet")
    er_ids = set(er["stock_id"].astype(str))

    noevent, offending = [], {}
    for sid in holes:
        dr = _tree(TREES / f"div_result/{sid}.parquet")
        if len(dr) or sid in cr_ids:
            continue                       # the factor path found an event
        noevent.append(sid)
        other = []
        dv = TREES / f"dividend/{sid}.parquet"
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
    fp = DATA / "capital_reduction.parquet"
    assert fp.exists(), "capital_reduction.parquet documented as delivered but missing"
    # Read it rather than stat it: a consolidation that wrote an empty frame
    # delivers the path and nothing else, and the runner's population guard is
    # what turns that into a failure.
    n = len(pd.read_parquet(fp))
    return f"capital_reduction.parquet present, {n:,} rows", n


def test_taiwan_adjusted_series():
    """ADJUSTED_PRICES.md, on the three things it claims.

    That the vendor series carries the exchange's own total-return factor; that
    a session the stock did not trade holds no adjusted price even though the
    vendor supplies one; and that a share cancellation the vendor did not price
    is marked rather than left in the series as a return.
    """
    if not (DATA / "unpriced_actions.parquet").exists():
        raise Skipped("unpriced_actions.parquet not built")
    import numpy as np

    from finmind_data.derive.adjusted_loader import load_adjusted

    # (1) The factor is the exchange's. Each 除權息 event contributes
    # before_price/after_price; FinMind reaches the same number by subtracting
    # the declared distribution from the prior close instead, so the two agree
    # exactly on most events and closely on the rest.
    rel, cash = [], []
    for sid in ("2330", "2317", "1101", "2412", "1216", "2002"):
        ev = _tree(TREES / f"div_result/{sid}.parquet")
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
    vendor = _tree(TREES / "price_adj/8934.parquet")
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

    `vendor_event_audit.parquet` is what the README's 81.4 % / 99.6 % and the
    one patched event are quoted from, and `adjusted_loader` patches off it.
    A committed copy that no longer matches what the generator produces would
    publish an older run's grade while the loader patches a different set, so
    the file is regenerated here and compared rather than merely read.
    """
    from finmind_data.derive.vendor_event_audit import OUT_PATH, audit

    assert OUT_PATH.exists(), (
        f"{OUT_PATH.name} is missing — run "
        f"`python -m finmind_data.derive.vendor_event_audit`"
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
    served = {p.stem for p in (TREES / "price_adj").glob("*.parquet")
              if len(_tree(p))}
    unserved = int((~nc["stock_id"].astype(str).isin(served)).sum())
    assert (len(nc), unserved) == (194, 174), (
        f"the 194 ungradable events should be 174 in stocks the vendor serves "
        f"nothing for and 20 with no adjacent bracketing session; this tree "
        f"gives {len(nc)} ungradable of which {unserved} are unserved"
    )
    w6, w3 = float((ck["rel"] < 1e-6).mean()), float((ck["rel"] < 1e-3).mean())
    assert abs(w6 - 0.8138) < 5e-4 and abs(w3 - 0.9961) < 5e-4, (
        f"README claims the vendor step matches the exchange's published "
        f"before_price/after_price to 1e-6 on 81.4 % of graded events and to "
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
    import numpy as np

    from finmind_data.derive.adjusted_loader import load_adjusted
    from finmind_data.derive.vendor_event_audit import defective_events

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
    import numpy as np

    from finmind_data.derive import adjust
    from finmind_data.derive.adjusted_loader import _unpriced_dates, load_adjusted

    head = tail = 0
    refused, uncovered = [], []
    # 3271, 3142, 2479 and 3053 left this list when the window started being
    # enforced: their last quote is 2005-2008, so the package has no series for
    # them and `load_adjusted` refuses them rather than returning one. 1240
    # replaces the head carry they supplied — it listed inside the window, which
    # is now the only way a first session comes to be carried. 1338 holds a
    # restored make-up Saturday the vendor still does not price; 1240's two
    # were that until the whole re-pull of `price_adj/` brought them in.
    for sid in ("1580", "3454", "1107", "2381", "2396", "2341", "1240",
                "1338", "4141", "2330"):
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
        # product does not cover at all. Most make-up sessions
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
    assert uncovered == [("1338", "2012-02-04")], (
        f"among these stocks the only traded session interior to the vendor's "
        f"series that it prices nothing for is 1338's restored 2012-02-04 "
        f"make-up Saturday; this tree has {uncovered}"
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


def test_taiwan_adjusted_factor_moves_only_on_events():
    """README, "One pull per adjusted file": the factor steps only where
    something was filed.

    `price_adj/` over the raw close is the vendor's back-adjustment factor, and
    a factor moves only on the first session at or after an event: a 除權息, 減資
    or 面額變更 filing, or a share cancellation no filing explains. That set is
    the one `adjusted_loader` refuses to carry a factor across. A step is a
    move past `_VINTAGE_TOL`, the bound `backfill_make_up_sessions` separates
    the vendor's rounding from a second vintage with.

    A file assembled from two pulls steps once more. Each pull is anchored at
    its own date, so the earlier pull's rows lack every event filed between the
    two, and the factor steps on the first session of the later pull, where
    nothing was filed. `download.py --extend` built the tree that way until it
    re-pulled back-adjusted files whole: 232 steps, on 2025-01-02 in 10 files
    and on 2026-08-03 or the session after in 222. `vendor_event_audit` graded
    every event and passed, because on an event's own session both sides of the
    step already sit at the later anchor.

    One step off an event is left, found by position rather than by list: the
    step into a series' second session. On all but one of those series the
    vendor serves the first row at its own anchor, so its adjusted close is the
    raw close.
    """
    import numpy as np
    import pyarrow.parquet as pq

    from finmind_data.derive import adjust
    from finmind_data.derive.adjusted_loader import _unpriced_dates
    from finmind_data.repair.backfill_make_up_sessions import _VINTAGE_TOL

    steps = 0
    second, stray = [], []
    for sid in _panel_ids():
        a = TREES / f"price_adj/{sid}.parquet"
        r = TREES / f"ohlcv/{sid}.parquet"
        # A zero-row file is written without a schema, so it has no column to read.
        if not pq.ParquetFile(a).metadata.num_rows or not pq.ParquetFile(r).metadata.num_rows:
            continue
        adj = _tree(a, columns=["date", "close"])
        raw = _tree(r, columns=["date", "close"])
        m = raw.merge(adj, on="date", suffixes=("", "_adj")).sort_values("date")
        m = m[m["close"] > 0]
        if len(m) < 2:
            continue
        f = m["close_adj"].to_numpy(dtype=float) / m["close"].to_numpy(dtype=float)
        moved = np.flatnonzero(np.abs(f[1:] / f[:-1] - 1.0) > _VINTAGE_TOL) + 1
        steps += len(moved)
        dates = m["date"].to_numpy()
        events = np.concatenate([adjust.filed_event_dates(sid), _unpriced_dates(sid)])
        seat = np.searchsorted(dates, events, "left")
        for i in moved[~np.isin(moved, seat)]:
            if i == 1:
                second.append((sid, bool(f[0] == 1.0)))
            else:
                stray.append((sid, str(pd.Timestamp(dates[i]).date()),
                              round(float(f[i] / f[i - 1]), 6)))

    assert not stray, (
        f"README says the adjusted factor steps only on an event's first session "
        f"or into a series' second session; {len(stray)} steps in "
        f"{len({s for s, _, _ in stray})} files fall on neither, most on "
        f"{pd.Series([d for _, d, _ in stray]).value_counts().head(3).to_dict()}. "
        f"Many files stepping on one date is an append that spliced two pulls; "
        f"re-pull them whole with `download.py --extend --datasets price_adj`: "
        f"{stray[:5]}")
    unadjusted = sum(u for _, u in second)
    assert (steps, len(second), unadjusted) == (22_017, 116, 115), (
        f"README counts 22,017 factor steps in the universe's files, 116 of "
        f"them into a series' second session, and 115 of those after a first "
        f"row the vendor left at the raw close; this tree gives {steps:,}, "
        f"{len(second)} and {unadjusted}")
    return (f"{steps:,} factor steps, all on an event's first session but "
            f"{len(second)} into a series' second session ({unadjusted} after "
            f"an unadjusted first row)"), steps


def test_taiwan_unadjusted_first_sessions_are_carried():
    """README, "One pull per adjusted file": a first session the vendor serves at
    the raw close takes the second session's factor.

    The vendor's factor on such a session is exactly 1.0 and steps into the
    second session with no filing under it, so kept, the step would be the
    second session's return. `load_adjusted` drops that factor and the edge carry
    replaces it: the row is `vendor_carried`, and `adj_covered` stays True
    because the vendor did serve it. The sessions are read off the trees and held
    against the loader's carries in both directions. A carry the trees do not
    call for overwrote a price the vendor served, and a first row they call for
    that the loader kept puts the step back into a return.

    The same pass counts every carried row in the panel, which the README's
    `adj_source` table quotes.
    """
    import numpy as np
    import pyarrow.parquet as pq

    from finmind_data.derive.adjusted_loader import load_adjusted
    from finmind_data.repair.backfill_make_up_sessions import _VINTAGE_TOL

    want, got = set(), set()
    edge = 0
    for sid in _panel_ids():
        a = TREES / f"price_adj/{sid}.parquet"
        r = TREES / f"ohlcv/{sid}.parquet"
        # A zero-row file is written without a schema, so it has no column to read.
        if not pq.ParquetFile(r).metadata.num_rows:
            continue
        if pq.ParquetFile(a).metadata.num_rows:
            adj = _tree(a, columns=["date", "close"])
            raw = _tree(r, columns=["date", "close"])
            m = raw.merge(adj, on="date", suffixes=("", "_adj")).sort_values("date")
            m = m[m["close"] > 0]
            if len(m) > 1:
                f = m["close_adj"].to_numpy(dtype=float) / m["close"].to_numpy(dtype=float)
                if f[0] == 1.0 and abs(f[1] - 1.0) > _VINTAGE_TOL:
                    want.add((sid, str(pd.Timestamp(m["date"].iloc[0]).date())))
        try:
            df = load_adjusted(sid)
        except ValueError:
            # No in-window session to load: the 38 names
            # test_taiwan_no_trade_rows_are_not_holdable counts.
            continue
        carried = df["adj_source"].to_numpy() == "vendor_carried"
        served = df["adj_covered"].to_numpy()
        edge += int((carried & ~served).sum())
        f = df["tr_factor"].to_numpy()
        priced = np.flatnonzero(np.isfinite(f))
        for i in np.flatnonzero(carried & served):
            day = str(pd.Timestamp(df["date"].iloc[i]).date())
            got.add((sid, day))
            nxt = priced[priced > i]
            assert i == priced[0] and len(nxt) and abs(f[i] / f[nxt[0]] - 1.0) < 1e-12, (
                f"{sid} {day}: a vendor-served session was carried, and it is not "
                f"the first priced session taking the next one's factor")

    assert got == want, (
        f"README says load_adjusted carries the second session's factor onto "
        f"each first session the vendor serves at the raw close; the trees show "
        f"{len(want)} such sessions and the loader carried {len(got)}. Not "
        f"carried: {sorted(want - got)[:5]}; carried without the shape: "
        f"{sorted(got - want)[:5]}")
    assert (edge, len(got)) == (501, 115), (
        f"README's adj_source table counts 616 vendor_carried rows: 497 "
        f"sessions ahead of the vendor series, the Saturday make-up session "
        f"right after it in four of those stocks, and 115 first sessions the "
        f"vendor serves unadjusted. That is 501 the vendor does not serve and "
        f"115 it does; this panel gives {edge} and {len(got)}")
    return (f"{len(got)} unadjusted first sessions carried from the second, "
            f"exactly the {len(want)} the trees show; {edge} carried ahead of "
            f"the vendor series"), edge + len(got)


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
    import numpy as np
    import pyarrow.parquet as pq

    from finmind_data.derive.adjusted_loader import _BREAK_GAP_DAYS, load_adjusted

    d = pd.read_parquet(DATA / "delisted_universe.parquet")
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
        f = TREES / f"ohlcv/{r.stock_id}.parquet"
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
    from finmind_data.delisting.delisting_sign import _panel_last_session

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
    import numpy as np

    from finmind_data.derive.adjusted_loader import load_adjusted

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
    assert (rows, zero, zero_stocks) == (6_676_907, 136_383, 1_208), (
        f"README quotes 136,383 no-trade sessions in 1,208 stocks over a "
        f"6,676,907-row panel; this tree has {zero:,} in {zero_stocks:,} over "
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
    from finmind_data.derive.adjusted_loader import load_adjusted

    u = pd.read_parquet(DATA / "universe.parquet")
    d = pd.read_parquet(DATA / "delisted_universe.parquet")
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
             if len(_tree(TREES / f"ohlcv/{sid}.parquet"))
             and not len(_tree(TREES / f"price_adj/{sid}.parquet"))]
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
    import numpy as np

    from finmind_data.derive import adjust
    from finmind_data.derive.adjusted_loader import load_adjusted

    d = pd.read_parquet(DATA / "delisted_universe.parquet")
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
    from finmind_data.derive.adjusted_loader import _METHOD, load_adjusted

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


def test_taiwan_par_value_changes_are_priced():
    """CAVEATS.md 5: the rebuild steps across a 面額變更 rather than through it.

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
    from finmind_data.derive import adjust

    sp = pd.read_parquet(DATA / "split_reference.parquet")
    uni = set(pd.read_parquet(DATA / "universe.parquet")["stock_id"])
    ev = sp[sp["date"].between(COVERAGE_START, COVERAGE_END)
            & sp["stock_id"].isin(uni)]
    raw_drop = matched = 0
    for r in ev.itertuples():
        px = _tree(TREES / f"ohlcv/{r.stock_id}.parquet",
                   columns=["date", "close"]).sort_values("date")
        px = px.reset_index(drop=True)
        i = px.index[px["date"] >= r.date]
        a = _tree(TREES / f"price_adj/{r.stock_id}.parquet",
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
        f"CAVEATS.md 5 claims every in-window 面額變更 is a raw drop past "
        f"-30 %; {n - raw_drop} of the {n} in split_reference.parquet are not — "
        f"either the event is not the mechanical reprice the caveat describes, "
        f"or the price tree does not hold the session it fell on"
    )
    assert matched == n, (
        f"CAVEATS.md 5 claims the rebuild reproduces the vendor on every "
        f"in-window 面額變更; it does on {matched} of {n}. A shortfall means the "
        f"chain in split_reference.parquet is no longer reaching the factor, "
        f"and the rebuilt names carry the whole par change as a return"
    )
    return (f"{n} in-window 面額變更 events, all {raw_drop} a raw drop past "
            f"-30 %, all {matched} rebuilt to the vendor within 1e-3"), n


CHECKS = [
    test_taiwan_adjusted_survivorship_hole,
    test_taiwan_adjusted_coverage_decomposition,
    test_taiwan_adj_covered_survives_concat,
    test_taiwan_no_event_holes_are_event_free_in_three_sources,
    test_capital_reduction_artifact_exists,
    test_taiwan_adjusted_series,
    test_taiwan_vendor_event_audit_is_current,
    test_taiwan_vendor_defects_are_patched,
    test_taiwan_vendor_edges_are_carried,
    test_taiwan_adjusted_factor_moves_only_on_events,
    test_taiwan_unadjusted_first_sessions_are_carried,
    test_taiwan_post_delisting_sessions_are_marked,
    test_taiwan_no_trade_rows_are_not_holdable,
    test_taiwan_survivorship_hole_is_rebuilt,
    test_taiwan_rebuild_matches_vendor,
    test_taiwan_adj_source_partitions_the_panel,
    test_taiwan_par_value_changes_are_priced,
]
