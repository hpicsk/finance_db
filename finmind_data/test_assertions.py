"""Integrity assertions for the claims `finmind_data`'s documentation makes.

This repo has no CI; verification is ad-hoc. Run with the data trees populated,
from anywhere:

    python finmind_data/test_assertions.py

or run every package's assertions at once with `./run_assertions.sh` from the
repo root. Each check prints PASS/FAIL; the script exits non-zero if any fail.
"""
from __future__ import annotations

import glob
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
    return f"Taiwan universe = {len(u)}; all have OHLCV"


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
    return f"all {len(uid)} ids fetched; {empty} empty, {len(uid) - empty} with data"


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
            f"adjusted series, all delisted {yrs.min()}-{yrs.max()}")


def test_taiwan_adjusted_coverage_decomposition():
    """README, "The adjusted panel is survivorship-biased": 99.80 %, and why.

    The figure has to be quoted against every traded session in `ohlcv/`. Drop
    the 38 uncovered delistings from the denominator and the same files report
    99.95 % — the coverage of a panel the survivorship bias has already been
    taken out of, which is the one number a reader must not cite. This asserts
    the honest denominator and the split of what it misses, so the two cannot
    drift back into each other.
    """
    u = pd.read_parquet(REPO / "finmind_data/universe.parquet")
    traded = covered = hole = tail = first = 0
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
        miss = ~tr["date"].isin(set(adj_dates))
        covered += int((~miss).sum())
        # A session past the vendor's last is the series stopping at a delisting
        # the raw file kept printing through; anything else is the first-session
        # offset the vendor series starts on.
        tail += int((miss & (tr["date"] > adj_dates.max())).sum())
        first += int((miss & (tr["date"] <= adj_dates.max())).sum())

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
    return (f"{covered:,}/{traded:,} = {100 * covered / traded:.2f} % "
            f"(vs {100 * covered / (traded - hole):.2f} % on the bias-removed "
            f"denominator); missing = {hole:,} hole + {tail:,} tail + {first:,} first")


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
    return "2005-2014 commons fully covered; 42-name overlay present"


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
        return "SKIP (unpriced_actions.parquet not built)"
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
            f"{frac:.4f} where attrs carries {dict(panel.attrs) or 'nothing'}")


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
            f"({100 * bad / tot:.2f} %) in {stocks} stocks; close on 0")


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
    return f"delisting table = {sorted(cols)}; no reason, no terminal value"


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
            f"month_rev create_time blank {blank:,}/{tot:,}; dividend has it")


# ---- consolidate_capred delivered artifact ---------------------------------
def test_capital_reduction_artifact_exists():
    fp = REPO / "finmind_data/capital_reduction.parquet"
    assert fp.exists(), "capital_reduction.parquet documented as delivered but missing"
    return "capital_reduction.parquet present"


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
    return f"ohlcv/ is raw: {hit:,}/{tot:,} = {100 * frac:.2f} % vs before_price"


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
        return "SKIP (unpriced_actions.parquet not built)"
    import numpy as np

    from finmind_data.adjusted_loader import load_adjusted

    # (1) The factor is the exchange's. Each 除權息 event contributes
    # before_price/after_price; FinMind reaches the same number by subtracting
    # the declared distribution from the prior close instead, so the two agree
    # exactly on most events and closely on the rest.
    rel = []
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
    rel = np.concatenate(rel)
    within = float((rel < 1e-3).mean())
    assert within >= 0.98, (
        f"README claims price_adj/ carries the exchange's own total-return "
        f"factor, matching before_price/after_price within 1e-3 on 99.6 % of "
        f"events; on these {len(rel)} it now matches {100 * within:.1f} %. "
        f"Below that the series is adjusting for something else"
    )
    # A cash-only 除權息 moves the factor at all — this is what says the series
    # is total return and not price return, where a cash event has step 1.
    assert rel.size and float(np.median(rel)) < 1e-3 and (rel < 1e-3).sum() > 0, (
        "the factor does not track the cash-inclusive reference-price ratio"
    )

    # (2) A no-trade session is close == 0 in ohlcv/, and the vendor fills it
    # with the last traded price. Zero is not a price and neither is a carried
    # one, so the row must hold no adjusted close.
    d = load_adjusted("8934")
    z = d["close"] == 0
    vendor = pd.read_parquet(REPO / "finmind_data/price_adj/8934.parquet")
    n_filled = int((vendor["close"] > 0).sum() - (d["close"] > 0).sum())
    assert z.sum() > 0 and d.loc[z, "adj_close_tr"].isna().all(), (
        f"README claims a session the stock did not trade holds no adjusted "
        f"price; 8934 has {int(z.sum())} zero-close rows and "
        f"{int(d.loc[z, 'adj_close_tr'].notna().sum())} of them carry a number"
    )
    assert n_filled > 0, (
        "README claims the vendor fills no-trade sessions with a carried "
        "price — the failure the NaN above prevents; 8934's vendor file now "
        "prices no more sessions than actually traded, so either the vendor "
        "changed or the raw zero encoding did"
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
            f"anchor exact")


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
    return (f"{len(ck):,}/{len(committed):,} events graded; vendor == exchange "
            f"{100 * w6:.2f} % at 1e-6, {100 * w3:.2f} % at 1e-3; defects {defects}")


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
    moved = []
    for _, e in d.iterrows():
        df = load_adjusted(e["stock_id"])
        assert df.attrs["events_patched"] >= 1, (
            f"{e['stock_id']} carries a {e['defect']} on "
            f"{pd.Timestamp(e['date']).date()} that load_adjusted did not patch"
        )
        dates = df["date"].to_numpy()
        i = int(np.searchsorted(dates, np.datetime64(e["date"]), "left"))
        while i < len(df) and not df["adj_covered"].iloc[i]:
            i += 1
        f = df["tr_factor"].to_numpy()
        got = f[i] / f[i - 1]
        assert abs(got / e["exchange_step"] - 1.0) < 1e-9, (
            f"{e['stock_id']} {pd.Timestamp(e['date']).date()}: the patched "
            f"factor steps by {got:.6f} where the exchange published "
            f"{e['exchange_step']:.6f} ({e['before']} → {e['after']})"
        )
        assert (df.loc[:i - 1, "adj_source"] == "vendor_patched").any(), (
            f"{e['stock_id']}: rows behind the patched event are not labelled "
            f"vendor_patched, so the panel cannot be split on it"
        )
        moved.append(abs(e["rel"]))
    return (f"7 events patched to the exchange's step; the patch moves the "
            f"ex-date factor by {100 * min(moved):.2f}-{100 * max(moved):.2f} %")


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
    traded = priced = invalid = 0
    kinds = {}
    reasons = set()
    for sid in holes:
        df = load_adjusted(sid)
        t = df["close"] > 0
        traded += int(t.sum())
        priced += int((t & df["adj_close_tr"].notna()).sum())
        invalid += int((t & ~df["is_valid"]).sum())
        assert not df["adj_covered"].any(), (
            f"{sid} is one of the 38 the vendor serves nothing for, but "
            f"adj_covered is True somewhere — the hole is no longer countable"
        )
        for k in df.loc[df["adj_source"] != "", "adj_source"].unique():
            kinds[k] = kinds.get(k, 0) + 1
        reasons |= set(df.loc[~df["is_valid"], "invalid_reason"].unique())

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
    assert (invalid, reasons) == (970, {"unpriced_cancellation"}), (
        f"README claims 970 of those sessions sit behind an unpriced share "
        f"cancellation in 4 of the 38; this tree gives {invalid:,} for "
        f"{sorted(reasons)}"
    )
    return (f"{len(holes)} holes rebuilt over {priced:,} traded sessions "
            f"({kinds}); {invalid:,} behind an unpriced cancellation")


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

    assert (stocks, n) == (134, 268485), (
        f"README quotes the gate on 134 covered in-window delistings and "
        f"268,485 daily adjusted returns; this tree gives {stocks} / {n:,}"
    )
    assert ok6 / n >= 0.9993 and ok3 / n >= 0.9999, (
        f"README claims the rebuild reproduces the vendor on 99.93 % of daily "
        f"adjusted returns to 1e-6 and 99.997 % to 1e-3; this tree gives "
        f"{100 * ok6 / n:.3f} % / {100 * ok3 / n:.3f} %. Below that the 38 "
        f"rebuilt names are no longer validated by anything"
    )
    return (f"{stocks} stocks, {n:,} returns: {100 * ok6 / n:.3f} % match to "
            f"1e-6, {100 * ok3 / n:.3f} % to 1e-3")


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
    for sid in ("2330", "8934", "2396", "2822", "1207", "2357"):
        df = load_adjusted(sid)
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
    assert seen == {"vendor", "vendor_patched", "rebuilt_factored",
                    "rebuilt_noevent"}, (
        f"README documents four adj_source values; these stocks exercise {seen}"
    )
    return f"adj_source present exactly where a price is; exercises {sorted(seen)}"


CHECKS = [
    test_taiwan_ohlcv_one_per_universe,
    test_taiwan_price_adj_one_per_universe,
    test_taiwan_overlay_covers_2005_2014,
    test_taiwan_adjusted_survivorship_hole,
    test_taiwan_adjusted_coverage_decomposition,
    test_taiwan_vendor_event_audit_is_current,
    test_taiwan_vendor_defects_are_patched,
    test_taiwan_survivorship_hole_is_rebuilt,
    test_taiwan_rebuild_matches_vendor,
    test_taiwan_adj_source_partitions_the_panel,
    test_taiwan_adj_covered_survives_concat,
    test_taiwan_open_outside_session_range,
    test_taiwan_delisting_table_has_no_reason,
    test_taiwan_fundamentals_are_fiscal_dated,
    test_capital_reduction_artifact_exists,
    test_taiwan_ohlcv_is_raw,
    test_taiwan_adjusted_series,
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
