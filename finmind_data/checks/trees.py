"""The raw trees and their repairs: prices, counts, flows, the fills and what each record pins."""
from __future__ import annotations
import glob
import math
import pandas as pd

from finmind_data.window import COVERAGE_START, COVERAGE_END, clip
from finmind_data.paths import DATA, RECORDS, TAPE, TREES
from ._common import Skipped, _NORMAL_START_GAP_DAYS, _PRE_LISTING_DAY, _panel_ids, _tape_universe, _tree


# ---- Taiwan: the open field disagrees with its own session bar -------------
def test_taiwan_open_outside_session_range():
    """CAVEATS.md 11: `open` sits outside [min, max] on 2.0 % of rows.

    `close` never does, which is what makes this a property of the `open` field
    rather than of the sessions. Asserted because the caveat is the only thing
    standing between the panel and a backtest that enters at the open.

    The shares the caveat prints after the count are measured on the sessions
    `pit_universe.py` keeps, read off the spans `universe_at` reads. The board
    is `type` in `universe.parquet`, the column the Universe table counts. The
    per-year claims range over every year of the window.
    """
    import pyarrow.parquet as pq
    from finmind_data.derive.pit_universe import _spans

    spans = {s: list(zip(pd.to_datetime(g["start"]), pd.to_datetime(g["end"])))
             for s, g in _spans().groupby("stock_id")}
    u = pd.read_parquet(DATA / "universe.parquet")
    board = dict(zip(u["stock_id"].astype(str), u["type"]))
    until = pd.to_datetime(_tape_universe().set_index("stock_id")["emerging_until"])

    bad = tot = stocks = bad_close = gone = gone_emerging = 0
    kept = []
    for sid in _panel_ids():
        p = TREES / f"ohlcv/{sid}.parquet"
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
        f"CAVEATS.md 11 rests on close being consistent with its own session "
        f"bar on every row; {bad_close:,} rows now break that, so the problem is "
        f"no longer confined to the open field"
    )
    assert (bad, stocks) == (131261, 684), (
        f"CAVEATS.md 11 pins 131,261 rows across 684 stocks with open "
        f"outside [min, max]; this tree gives {bad:,} across {stocks}"
    )
    # The rows `pit_universe.py` removes, each on or before the day its name
    # left 興櫃.
    assert (gone, gone_emerging) == (29651, 29651), (
        f"CAVEATS.md 11 says 29,651 of the 131,261 fall on 興櫃 sessions, "
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
        f"CAVEATS.md 11 says the share on the sessions pit_universe.py keeps "
        f"is 1.57 %, 2.18 % for the names the Universe table counts under TPEx "
        f"against 1.12 % for those under TWSE, and falls from 3.33 % of 2011's "
        f"rows to 0.06 % of 2024's; the tree gives {off}")

    window = list(range(COVERAGE_START.year, COVERAGE_END.year + 1))
    last = int(by_year.index[by_year["bad"] > 0].max())
    assert list(by_year.index) == window and last == 2024, (
        f"CAVEATS.md 11 says no session pit_universe.py keeps from 2025 on "
        f"carries such an open; kept sessions fall in {list(by_year.index)} "
        f"and the last such open is in {last}")
    g = k.groupby(["year", "board"])[["bad", "rows"]].sum()
    yearly = (g["bad"] / g["rows"]).unstack("board")
    lower = [y for y in range(COVERAGE_START.year, last + 1)
             if not yearly.loc[y, "tpex"] > yearly.loc[y, "twse"]]
    assert not lower, (
        f"CAVEATS.md 11 says the TPEx share is the higher of the two in every "
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
    from finmind_data.collect.ohlcv_repull import draw, strata

    fresh = pd.read_parquet(DATA / "ohlcv_repull.parquet")
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

    stored = pd.concat([_tree(TREES / f"ohlcv/{s}.parquet")
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
    log = pd.read_parquet(RECORDS / "volume_repair.parquet")
    log = log[log["tree"] == "ohlcv"].assign(date=lambda x: pd.to_datetime(x["date"]))
    hit = m.merge(log, on=["date", "stock_id"])
    higher = all(((hit[f"{c}_old"] < hit[f"{c}_f"])
                  & (hit[f"{c}_new"] == hit[f"{c}_f"])).all() for c in counts)
    sessions = pd.to_datetime(pd.read_parquet(
        DATA / "trading_sessions.parquet")["date"])
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
    for p in sorted(glob.glob(str(TREES / "div_result/*.parquet"))):
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
        fp = TREES / f"ohlcv/{sid}.parquet"
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


def test_taiwan_pre_listing_sessions_are_one_vendor_day():
    """CAVEATS.md 6: twelve series open on one day and then stop for months.

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

    files = sorted((TREES / "ohlcv").glob("*.parquet"))
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
        f"CAVEATS.md 6 names the twelve series that open on "
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


def test_taiwan_repull_fill_is_in_the_trees():
    """CAVEATS.md 15: some rows of the daily trees come from the whole re-pull
    of 2026-09-13, and `repull_fill/` records what it found in both directions.

    The fill adds a row only where the tree held none under its key, so the
    recorded rows are read back: the rows the tree holds under those keys are the
    recorded ones and no others, value for value. A row under one of those keys
    that the record lacks would mean the fill wrote into a row the tree held,
    which caveat 13 found is a revision and not a correction.

    Where each added row sat is read back against the tree minus the record,
    which is the file as the fill found it: a `before` row precedes every row of
    its stock the fill did not add, an `interior` row sits between two of them, a
    `same-day` row shares its date with one, and an `empty` row belongs to a
    stock that had none. That is what carries the caveat's reading of the hole —
    a vendor backfill `--extend` cannot reach — rather than a count of rows.

    The record holds one file per tree the re-pull covered, so a tree the fill
    found nothing in is an empty file rather than an absent one, and
    `unserved.parquet` holds the stock-dates the re-pull no longer carries. Those
    rows are asserted to be in the trees still: what the caveat claims about them
    is that none was dropped.
    """
    from finmind_data.repair.repull_fill import KEY, RECORD, _keys

    names = set(_panel_ids())
    lo, hi = COVERAGE_START.strftime("%Y-%m-%d"), COVERAGE_END.strftime("%Y-%m-%d")
    sessions = set(pd.read_parquet(DATA / "trading_sessions.parquet")
                   ["date"].astype(str).str[:10])
    saturdays = {d for d in sessions if pd.Timestamp(d).dayofweek == 5}
    got, loose, merged, misplaced, off_session = {}, [], [], [], []
    flow, nonzero, on_saturday = {}, 0, {}
    for p in sorted(RECORD.glob("*.parquet")):
        if p.stem not in KEY:
            continue
        tree, key = p.stem, KEY[p.stem]
        r = pd.read_parquet(p)
        out = r[~r["stock_id"].isin(names) | ~r["date"].between(lo, hi)]
        loose += [(tree, s, d) for s, d in zip(out["stock_id"], out["date"])]
        off_session += [(tree, s, d) for s, d in zip(r["stock_id"], r["date"])
                        if d not in sessions]
        on_saturday[tree] = int(r["date"].isin(saturdays).sum()) if len(r) else 0
        if tree == "instflow":
            nonzero = int(((r["buy"] != 0) | (r["sell"] != 0)).sum())
            for s, d in zip(r["stock_id"], r["date"]):
                flow.setdefault(s, set()).add(d)
        for sid, x in r.groupby("stock_id"):
            x = x.reset_index(drop=True)
            # Read as written rather than through `_tree`: the claim is that the
            # file holds these rows, and each of them is inside the window already.
            f = pd.read_parquet(TREES / f"{tree}/{sid}.parquet")
            added = _keys(f, key).isin(_keys(x, key))
            if not f[added].reset_index(drop=True).equals(x.drop(columns="place")):
                merged.append((tree, sid))
                continue
            before = set(f.loc[~added, "date"])
            for d, place in zip(x["date"], x["place"]):
                sits = {"empty": not before,
                        "same-day": d in before,
                        "before": bool(before) and d < min(before),
                        "after": bool(before) and d > max(before),
                        "interior": bool(before) and min(before) < d < max(before)
                                    and d not in before}[place]
                if not sits:
                    misplaced.append((tree, sid, d, place))
        got[tree] = (len(r), r["stock_id"].nunique(), r["place"].value_counts().to_dict())
    assert not loose, (
        f"CAVEATS.md 15 says the fill added rows for universe names inside "
        f"the window only; {len(loose)} recorded rows are not: {loose[:5]}")
    assert not merged, (
        f"CAVEATS.md 15 says a row the tree held keeps its own values and "
        f"each added key holds the pull's row alone; in {len(merged)} files the "
        f"recorded keys read back otherwise: {merged[:5]}")
    assert not misplaced, (
        f"CAVEATS.md 15 counts the added rows by where each sat against the "
        f"span its file held; {len(misplaced)} sit elsewhere: {misplaced[:5]}")
    assert not off_session, (
        f"CAVEATS.md 15 says every added row falls on a session the exchange "
        f"held; {len(off_session)} do not: {off_session[:5]}")
    assert got == {
        "instflow": (111_056, 805, {"before": 105_528, "interior": 5_513, "same-day": 15}),
        "margin_short": (682, 311, {"interior": 682}),
        "ohlcv": (4, 4, {"before": 4}),
        "per_pbr": (8_399, 757, {"interior": 8_399}),
        "sec_lending": (0, 0, {}),
        "shares": (0, 0, {})}, (
        f"CAVEATS.md 15 says the fill added 111,056 rows to instflow/ for 805 "
        f"names, 8,399 to per_pbr/ for 757, 682 to margin_short/ for 311 and 4 to "
        f"ohlcv/ for 4, none to shares/ or sec_lending/, and 105,528 of the "
        f"instflow/ rows before their file's first row; repull_fill/ gives "
        f"(rows, names, places) {got}")
    assert nonzero == 40_162, (
        f"CAVEATS.md 15 says 40,162 of the instflow/ rows carry a buy or a "
        f"sell that is not zero; {nonzero:,} do")
    assert (on_saturday["per_pbr"], on_saturday["ohlcv"]) == (8_399, 4), (
        f"CAVEATS.md 15 says all 8,399 per_pbr/ rows and all 4 ohlcv/ rows "
        f"sit on a make-up Saturday; "
        f"{on_saturday['per_pbr']:,} and {on_saturday['ohlcv']} do")
    priced = sum(len(d & set(pd.read_parquet(
        TREES / f"ohlcv/{s}.parquet", columns=["date"])["date"]))
        for s, d in flow.items())
    want = sum(len(d) for d in flow.values())
    assert priced == want, (
        f"CAVEATS.md 15 says ohlcv/ carries a price on every one of the "
        f"{want:,} stock-dates the instflow/ fill reached; it carries one on "
        f"{priced:,}")

    left = pd.read_parquet(RECORD / "unserved.parquet")
    dropped = []
    for (tree, sid), x in left.groupby(["tree", "stock_id"]):
        n = pd.read_parquet(TREES / f"{tree}/{sid}.parquet",
                            columns=["date"])["date"].value_counts()
        dropped += [(tree, sid, d) for d, rows in zip(x["date"], x["rows"])
                    if n.get(d, 0) != rows]
    assert not dropped, (
        f"CAVEATS.md 15 says a row the re-pull no longer serves is kept; "
        f"{len(dropped)} recorded ones are gone or hold another count now: "
        f"{dropped[:5]}")
    by_tree = left.groupby("tree").size().to_dict()
    assert (by_tree, len(left), int(left["rows"].sum())) == (
        {"instflow": 3_179, "margin_short": 3_807, "ohlcv": 1_135, "per_pbr": 872,
         "sec_lending": 3_463, "shares": 44_271}, 56_727, 68_135), (
        f"CAVEATS.md 15 says the re-pull carries no row for 56,727 stock-dates "
        f"the trees hold 68,135 rows on — 44,271 in shares/, 3,807 in "
        f"margin_short/, 3,463 in sec_lending/, 3,179 in instflow/, 1,135 in "
        f"ohlcv/ and 872 in per_pbr/; unserved.parquet gives {by_tree}, "
        f"{len(left):,} stock-dates, {int(left['rows'].sum()):,} rows")
    on_session = left[left["date"].isin(sessions)]
    assert (len(on_session), on_session.groupby("tree").size().to_dict()) == (
        1_914, {"instflow": 779, "ohlcv": 1_135}), (
        f"CAVEATS.md 15 says 1,914 of the unserved stock-dates fall on a "
        f"session the exchange held, 1,135 of them in ohlcv/ and 779 in "
        f"instflow/; {len(on_session):,} do, "
        f"{on_session.groupby('tree').size().to_dict()}")
    quotes = set(on_session.loc[on_session["tree"] == "ohlcv", "stock_id"])
    assert quotes == {"1107", "2341", "2381", "2396", "2910"}, (
        f"CAVEATS.md 15 says the ohlcv/ rows on a session belong to 1107, "
        f"2341, 2381 and 2396, which left the board before the window, and to "
        f"2910's one all-zero row; they belong to {sorted(quotes)}")
    return (f"{sum(n for n, _, _ in got.values()):,} rows added from the re-pull, "
            f"{len(left):,} stock-dates it no longer serves kept"), (
        sum(n for n, _, _ in got.values()) + len(left))


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
    tape_dir = TAPE
    if not tape_dir.exists():
        raise Skipped("tape/ not built (python -m finmind_data.collect.tape_universe)")
    tape = pd.concat([pd.read_parquet(q) for q in sorted(tape_dir.glob("*.parquet"))],
                     ignore_index=True)
    lo, hi = tape["date"].min(), tape["date"].max()
    by_code = {}
    for c, d in zip(tape["stock_id"], tape["date"]):
        by_code.setdefault(c, set()).add(d)

    interior, examined, offenders = 0, 0, []
    for q in sorted((TREES / "ohlcv").glob("*.parquet")):
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
    for q in sorted((TREES / "price_adj").glob("*.parquet")):
        sid = q.stem
        r = TREES / f"ohlcv/{sid}.parquet"
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

    # The adjusted tree against the same tape, over the universe's files. Each
    # file is the per-stock endpoint's whole answer, so a session the tape holds
    # and the file does not is one that endpoint does not serve for the stock.
    import pyarrow.parquet as pq
    before = inside = after = 0
    for sid in _panel_ids():
        q = TREES / f"price_adj/{sid}.parquet"
        if sid not in by_code or not pq.ParquetFile(q).metadata.num_rows:
            continue
        have = set(pd.read_parquet(q, columns=["date"])["date"].astype(str).str[:10])
        w = {d for d in have if lo <= d <= hi}
        if not w:
            continue
        first, last = min(w), max(w)
        miss = by_code[sid] - have
        before += sum(d < first for d in miss)
        inside += sum(first < d < last for d in miss)
        after += sum(d > last for d in miss)
    assert (before, inside, after) == (501, 1384, 0), (
        f"README, \"Why the adjusted tree was not repaired the same way\": the "
        f"tape holds 1,384 sessions inside a universe name's price_adj/ series "
        f"that the file does not, and 501 before a file's first session; this "
        f"tree gives {inside:,} inside, {before:,} before and {after:,} after")
    return (f"no interior session gap across {examined:,} vendor-served "
            f"ticker-days; price_adj/ carries none ohlcv/ lacks, and lacks "
            f"{inside:,} tape sessions inside its series and {before} before "
            f"them"), examined


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

    tape_dir = TAPE
    if not tape_dir.exists():
        raise Skipped("tape/ not built (python -m finmind_data.collect.tape_universe)")
    tape = pd.concat([pd.read_parquet(q) for q in sorted(tape_dir.glob("*.parquet"))],
                     ignore_index=True)
    tape["date"] = pd.to_datetime(tape["date"])
    sessions = pd.to_datetime(pd.read_parquet(
        DATA / "trading_sessions.parquet")["date"])
    saturdays = sessions[sessions.dt.dayofweek == 5]
    log = pd.read_parquet(RECORDS / "volume_repair.parquet")
    log["date"] = pd.to_datetime(log["date"])
    counts = ["Trading_Volume", "Trading_money", "Trading_turnover"]

    raw, adj = [], []
    for sid in _panel_ids():
        p = TREES / f"ohlcv/{sid}.parquet"
        if pq.ParquetFile(p).metadata.num_rows:
            raw.append(_tree(p, columns=["date", "stock_id"] + counts))
        q = TREES / f"price_adj/{sid}.parquet"
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

    fresh = pd.read_parquet(DATA / "ohlcv_repull.parquet",
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


def test_taiwan_sec_lending_pairs_are_disclosed():
    """CAVEATS.md 12: `sec_lending` carries 86,002 rows twice, all between
    2017-12-18 and 2020-10-27.

    The pairs stay in the tree, because nothing here can tell a repeated load
    from two identical transactions. What makes `drop_duplicates()` safe is
    their shape, so the shape is what is pinned: every group is a pair, the span
    is closed, and no row outside it has a twin.
    """
    import pyarrow.parquet as pq

    rows = paired = stocks = 0
    sizes: dict[int, int] = {}
    days = set()
    for sid in _panel_ids():
        p = TREES / f"sec_lending/{sid}.parquet"
        # A zero-row file is written without a schema, so it has no column to read.
        if not pq.ParquetFile(p).metadata.num_rows:
            continue
        d = _tree(p)
        rows += len(d)
        twin = d.duplicated(keep=False)
        if not twin.any():
            continue
        stocks += 1
        paired += int(twin.sum())
        for k, c in d[twin].groupby(list(d.columns), dropna=False).size().value_counts().items():
            sizes[int(k)] = sizes.get(int(k), 0) + int(c)
        days |= set(pd.to_datetime(d.loc[twin, "date"]).dt.date.astype(str))

    span = (min(days), max(days)) if days else None
    assert (rows, paired, stocks, sizes) == (1_541_802, 172_004, 989, {2: 86_002}), (
        f"CAVEATS.md 12 counts 172,004 of the 1,541,802 in-window sec_lending "
        f"rows in 86,002 identical pairs, across 989 stocks; this tree gives "
        f"{paired:,} of {rows:,} in {stocks} stocks, groups by size {sizes}")
    assert span == ("2017-12-18", "2020-10-27"), (
        f"CAVEATS.md 12 says every pair falls between 2017-12-18 and "
        f"2020-10-27; this tree's pairs span {span}")
    return (f"{sizes.get(2, 0):,} identical pairs in {stocks} stocks, "
            f"{span[0]}..{span[1]}, none larger"), rows


def test_taiwan_fin_bs_revision_follows_the_filing():
    """CAVEATS.md 13: `fin_bs/` takes FinMind's revision of a balance sheet
    only where the filing sides with it.

    The company-periods written are derived from the committed grade, not
    listed, and held against the record in both directions. A record entry the
    grade does not call for is a revision taken without the filing behind it.
    A company-period the filing sides with and the record lacks is a statement
    left at a vintage its filing contradicts. Each row the record names is then
    read back from the tree: a changed or added row holds the revision's value
    and label, and a kept row, one the revision does not carry, holds the
    tree's. Every amount graded in a revised company-period the filing does not
    side with is read back as well, and holds the value the grade read.
    """
    from finmind_data.repair.fin_bs_vintage import GRADE, KEY, RECORD, verdicts

    g = pd.read_parquet(GRADE)
    v = verdicts(g)
    rec = pd.read_parquet(RECORD)
    rev = v[v["kind"] == "revised"]
    take = rev[rev["verdict"] == "revision"]
    want = set(zip(take["period"], take["stock_id"]))
    got = set(zip(rec["date"], rec["stock_id"]))
    assert got == want, (
        f"CAVEATS.md 13 says fin_bs/ takes the revision in exactly the "
        f"company-periods whose filing sides with it; the grade calls for "
        f"{len(want):,} and the record holds {len(got):,}. Not taken: "
        f"{sorted(want - got)[:5]}; taken without the filing: {sorted(got - want)[:5]}")

    stay = (g[(g["kind"] == "revised") & g["type"].notna()]
            .merge(rev.loc[rev["verdict"] != "revision", ["period", "stock_id"]],
                   on=["period", "stock_id"])
            .rename(columns={"period": "date"}))
    stay["date"] = pd.to_datetime(stay["date"])
    rec["date"] = pd.to_datetime(rec["date"])
    kept = rec["change"] == "kept"
    rec["value_want"] = rec["value_old"].where(kept, rec["value_new"])
    rec["name_want"] = rec["origin_name_old"].where(kept, rec["origin_name_new"])
    wrong, moved = [], []
    for sid in sorted(set(rec["stock_id"]) | set(stay["stock_id"])):
        f = _tree(TREES / f"fin_bs/{sid}.parquet")
        m = rec[rec["stock_id"] == sid].merge(f, on=KEY, how="left")
        ok = (((m["value"] == m["value_want"]) | (m["value"].isna() & m["value_want"].isna()))
              & (m["origin_name"] == m["name_want"]))
        wrong += [(sid, str(d.date()), t) for d, t in zip(m.loc[~ok, "date"], m.loc[~ok, "type"])]
        k = stay[stay["stock_id"] == sid].merge(f, on=KEY, how="left")
        off = ~((k["value"] == k["ours"]) | (k["value"].isna() & k["ours"].isna()))
        moved += [(sid, str(d.date()), t) for d, t in zip(k.loc[off, "date"], k.loc[off, "type"])]
    assert not wrong, (
        f"CAVEATS.md 13 says fin_bs/ holds the revision's value and label on "
        f"every row the revision carries in those company-periods, and the "
        f"tree's value on every row it does not; {len(wrong):,} rows of "
        f"fin_bs_vintage.parquet read back otherwise: {wrong[:5]}")
    assert not moved, (
        f"CAVEATS.md 13 says every other company-period keeps the tree's "
        f"rows; {len(moved):,} graded amounts there no longer hold the value "
        f"the grade read: {moved[:5]}")

    sides = rev["verdict"].value_counts().to_dict()
    ungraded = rev.loc[rev["verdict"] == "ungraded", "status"].value_counts().to_dict()
    assert (g["period"].min(), rev["period"].nunique(), sides, ungraded) == (
            "2013-03-31", 41,
            {"tree": 3_697, "revision": 3_498, "mixed": 25, "neither": 7, "ungraded": 99},
            {"no_label": 91, "no_report": 6, "refused": 2}), (
        f"CAVEATS.md 13 grades 7,326 company-periods in 41 quarters from "
        f"2013 Q1: the filing sides with the tree in 3,697 and with the "
        f"revision in 3,498, neither vintage agrees with every graded amount "
        f"in 32 more (with none in 7), and 99 are ungraded (91 matching no "
        f"line, 6 without a filing, 2 refused); this grade starts at "
        f"{g['period'].min()}, spans {rev['period'].nunique()} quarters and "
        f"gives {sides}, ungraded {ungraded}")

    by_q = (rev[rev["verdict"].isin(["tree", "revision"])]
            .groupby("period")["verdict"].agg(lambda s: "/".join(sorted(set(s)))))
    whole = {k: sorted(by_q.index[by_q == k]) for k in ("revision", "tree")}
    split = int((by_q == "revision/tree").sum())
    assert (whole, split) == ({
            "revision": ["2014-03-31", "2014-06-30", "2014-09-30", "2014-12-31",
                         "2019-03-31", "2019-06-30", "2019-09-30", "2019-12-31",
                         "2024-03-31", "2024-06-30", "2024-09-30",
                         "2026-03-31", "2026-06-30"],
            "tree": ["2013-03-31", "2013-06-30", "2013-09-30",
                     "2016-03-31", "2016-06-30", "2016-09-30", "2020-09-30",
                     "2022-03-31", "2022-06-30", "2022-09-30", "2025-06-30"]}, 17), (
        f"CAVEATS.md 13 says the filing sides with the revision in every "
        f"company-period it decides in 2014, 2019, 2024 Q1-Q3 and 2026 Q1-Q2, "
        f"with the tree in every one in 2013 Q1-Q3, 2016 Q1-Q3, 2020 Q3, 2022 "
        f"Q1-Q3 and 2025 Q2, and splits the other 17 quarters; this grade "
        f"gives {whole} and {split} split")

    blind = g.merge(take[["period", "stock_id"]], on=["period", "stock_id"])
    blind = blind[blind["status"] == "no_label"]
    changes = rec["change"].value_counts().to_dict()
    kept_in = rec.loc[kept, ["date", "stock_id"]].drop_duplicates()
    assert (len(blind), blind[["period", "stock_id"]].drop_duplicates().shape[0],
            changes, len(kept_in)) == (
            122, 117, {"changed": 31_514, "kept": 2_875, "added": 7}, 869), (
        f"CAVEATS.md 13 says 122 revised amounts in 117 of the company-periods "
        f"taken match no single filing line, and fin_bs_vintage.parquet records 31,514 "
        f"rows changed, 2,875 kept in 869 company-periods and 7 added; there are "
        f"{len(blind)} in {blind[['period', 'stock_id']].drop_duplicates().shape[0]}, "
        f"and the record gives {changes}, kept in {len(kept_in)}")

    ctl = v[v["kind"] == "control"]
    per = ctl.groupby("period").size()
    ctrl = ctl["verdict"].value_counts().to_dict()
    off = int((ctl["items"] - ctl["tree"]).sum())
    assert (len(per), set(per), ctrl, off) == (
            54, {4}, {"both": 193, "mixed": 16, "ungraded": 7}, 64), (
        f"CAVEATS.md 13 draws four agreeing company-periods per quarter, 216 "
        f"in all: the filing agrees with every graded amount in 193, both pulls "
        f"disagree with it on 64 amounts in 16, and 7 are ungraded; the grade "
        f"holds {len(per)} quarters of {sorted(set(per))} and gives {ctrl}, "
        f"{off} amounts off")
    return (f"{len(got):,} company-periods take the revision the filing sides "
            f"with, {len(rec):,} rows recorded; {len(stay):,} graded amounts "
            f"elsewhere keep the tree's value"), len(rec) + len(stay)


def test_taiwan_date_keyed_fill_is_in_the_trees():
    """CAVEATS.md 14: some company-periods come from FinMind's date-keyed
    query, and `date_keyed_fill/` records every row added.

    The fill adds a company-period only where the tree held no row of it, so
    each recorded company-period is read back whole: its rows in the tree are
    the recorded rows and no others, value for value. A tree row inside one
    that the record lacks means the fill merged into a company-period the tree
    held, which caveat 13 found is a revision and not a correction. A `fin_is/`
    or `fin_cf/` file that holds nothing but recorded rows was empty before.

    The record carries no per-stock answer, so the kinds are read off the
    vendor's stamp on `month_rev`. It splits them the way the per-stock query
    of 2026-09-13 did: no stamp on each row that query did not return, one
    stamp on each row it did, and September stamps on the edge month.
    """
    from finmind_data.repair.date_keyed_fill import RECORD, STATEMENT_TREES

    names = set(_panel_ids())
    d = pd.read_parquet(DATA / "delisted_universe.parquet")
    gone = names & set(d.loc[pd.to_datetime(d["date"]).between(
        COVERAGE_START, COVERAGE_END), "stock_id"].astype(str))
    lo, hi = COVERAGE_START.strftime("%Y-%m-%d"), COVERAGE_END.strftime("%Y-%m-%d")
    rec, got, only, loose, merged = {}, {}, {}, [], []
    for tree in STATEMENT_TREES:
        r = pd.read_parquet(RECORD / f"{tree}.parquet")
        rec[tree] = r
        out = r[~r["stock_id"].isin(names) | ~r["date"].between(lo, hi)]
        loose += [(tree, s, x) for s, x in zip(out["stock_id"], out["date"])]
        only[tree] = set()
        for sid, x in r.groupby("stock_id"):
            # Read as written rather than through `_tree`: the claim is that the
            # file holds exactly these rows, and each of them is in the window.
            f = pd.read_parquet(TREES / f"{tree}/{sid}.parquet")
            # A zero-row file is written without a schema, so it has no column to read.
            held = f[f["date"].isin(set(x["date"]))].reset_index(drop=True) if len(f) else f
            if not held.equals(x.reset_index(drop=True)):
                merged.append((tree, sid))
            if len(f) == len(x):
                only[tree].add(sid)
        cps = r[["stock_id", "date"]].drop_duplicates()
        got[tree] = (len(cps), cps["stock_id"].nunique(), len(r))
    assert not loose, (
        f"CAVEATS.md 14 says the fill added rows for universe names inside "
        f"the window only; {len(loose)} recorded rows are not: {loose[:5]}")
    assert not merged, (
        f"CAVEATS.md 14 says a company-period the tree held keeps its rows "
        f"and each added one holds the pull's rows alone; in {len(merged)} "
        f"files the recorded company-periods read back otherwise: {merged[:5]}")
    assert got == {"fin_is": (199, 6, 3_338), "fin_bs": (7, 4, 525),
                   "fin_cf": (467, 15, 9_761), "month_rev": (3_483, 719, 3_483)}, (
        f"CAVEATS.md 14 says the fill added 199 company-periods to fin_is/ "
        f"for 6 names, 467 to fin_cf/ for 15, 7 to fin_bs/ for 4 and 3,483 "
        f"company-months to month_rev/ for 719; date_keyed_fill/ gives "
        f"(company-periods, names, rows) {got}")
    for tree in ("fin_is", "fin_cf"):
        ids = set(rec[tree]["stock_id"])
        assert ids <= gone and ids == only[tree], (
            f"CAVEATS.md 14 says every {tree}/ row added belongs to a name "
            f"delisted inside the window whose file was empty; "
            f"{sorted(ids - gone)} were not delisted inside it and "
            f"{sorted(ids - only[tree])} hold rows the fill did not add")

    m = rec["month_rev"]
    stamp = m["create_time"].astype(str).str.strip().str[:10]
    edge = m["date"] == m["date"].max()
    none, some = (stamp == "") & ~edge, (stamp != "") & ~edge
    kinds = {"unstamped": (int(none.sum()), m.loc[none, "stock_id"].nunique(),
                           len(set(m.loc[none, "stock_id"]) & gone)),
             "stamped": (int(some.sum()), m.loc[some, "stock_id"].nunique(),
                         sorted(set(stamp[some])), m.loc[some, "date"].min(),
                         m.loc[some, "date"].max()),
             "edge": (m["date"].max(), int(edge.sum()), stamp[edge].min(),
                      stamp[edge].max())}
    assert kinds == {"unstamped": (1_454, 20, 18),
                     "stamped": (1_409, 104, ["2026-05-19"], "2011-02-01", "2013-01-01"),
                     "edge": ("2026-09-01", 620, "2026-09-10", "2026-09-12")}, (
        f"CAVEATS.md 14 splits the month_rev/ rows three ways: 1,454 for 20 "
        f"names, 18 of them delisted inside the window, that the per-stock "
        f"query does not return; 1,409 for 104 names, dated 2011-02-01 to "
        f"2013-01-01 and stamped 2026-05-19, that the vendor added after the "
        f"tree was pulled; and 620 dated 2026-09-01, stamped 2026-09-10 to "
        f"2026-09-12. The record gives {kinds}")

    last = m["date"].max()
    month = [f.loc[f["date"] == last, "create_time"] for f in (
        pd.read_parquet(TREES / f"month_rev/{sid}.parquet")
        for sid in sorted(names)) if len(f)]
    month = pd.concat(month, ignore_index=True).astype(str).str.strip().str[:10]
    counts = (len(month) - int(edge.sum()), len(month), int((month > hi).sum()))
    assert counts == (1_306, 1_926, 858), (
        f"CAVEATS.md 14 says the {last} month held 1,306 companies before "
        f"the fill and holds 1,926 after it, 858 of them stamped after "
        f"COVERAGE_END; month_rev/ gives {counts}")
    return (f"{sum(len(r) for r in rec.values()):,} recorded rows read back "
            f"whole from their trees: {got}; month_rev kinds {kinds}"), \
        sum(len(r) for r in rec.values())


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
    for f in sorted(glob.glob(str(TREES / "margin_short/*.parquet"))):
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
    assert math.isclose(ratio, 1.59, abs_tol=0.02), (
        f"README claims March 2020 carries '1.59x' the 2019 monthly mean of "
        f"short-sale volume; it carries {ratio:.2f}x")
    return (f"{len(m)} in-window months on {len(frames):,} names, none with "
            f"zero short-sale volume or zero balance; 2020-03 at "
            f"{ratio:.2f}x the 2019 mean"), len(d)


def test_taiwan_short_sale_flows_match_the_balances():
    """CAVEATS.md 16: `margin_short`'s two short-sale flows were crossed in
    the rows the first pull wrote, and `short_sale_repair.parquet` records every
    row exchanged.

    A short sale raises the short balance and buying the position back lowers
    it, so a row's flows and its balances are one identity. That identity is
    what convicts the pair, rather than a second pull disagreeing with the
    first, and it is read back in both directions: no in-window row contradicts
    its balances now, and putting each recorded row's values back the way the
    tree held them contradicts them on every one. That is what makes the record
    the set that was wrong rather than a list of rows someone picked.

    The margin flows carry the same identity with the buy and the sell the other
    way round, and it held before the repair, so asserting it here fails a
    repair that wrote into the wrong pair of columns. The rows the re-pull no
    longer serves are repaired on the balances alone, so the record keeps which
    of the two answers each row had.

    Both identities are read over every file the tree holds rather than over the
    universe: they are a property of a row, not a panel figure, and the 72 files
    outside the universe carry rows a caller can still open.
    """
    import pyarrow.parquet as pq

    from finmind_data.repair.short_sale_repair import BUY, RECORD, SELL, crossed

    names = set(_panel_ids())
    rec = pd.read_parquet(RECORD)
    lo, hi = COVERAGE_START.strftime("%Y-%m-%d"), COVERAGE_END.strftime("%Y-%m-%d")
    loose = rec[~rec["stock_id"].isin(names) | ~rec["date"].between(lo, hi)]
    rows = bad = margin = 0
    unrepaired = []
    by_stock = dict(tuple(rec.groupby("stock_id")))
    for p in sorted((TREES / "margin_short").glob("*.parquet")):
        sid = p.stem
        if not pq.ParquetFile(p).metadata.num_rows:
            continue
        f = pd.read_parquet(p)
        f = f[f["date"].between(lo, hi)]
        rows += len(f)
        bad += int(crossed(f).sum())
        margin += int((f["MarginPurchaseTodayBalance"]
                       != f["MarginPurchaseYesterdayBalance"] + f["MarginPurchaseBuy"]
                       - f["MarginPurchaseSell"] - f["MarginPurchaseCashRepayment"]).sum())
        x = by_stock.get(sid)
        if x is None:
            continue
        m = f.merge(x[["date", BUY, SELL]], on="date", how="right", suffixes=("", "_was"))
        was = m.assign(**{BUY: m[f"{BUY}_was"], SELL: m[f"{SELL}_was"]})
        undone = (m[BUY] == m[f"{SELL}_was"]) & (m[SELL] == m[f"{BUY}_was"]) & crossed(was)
        if not undone.all():
            unrepaired.append((sid, int((~undone).sum())))
    assert bad == 0, (
        f"CAVEATS.md 16 says every in-window row's short-sale flows agree "
        f"with the balances beside them after the repair; {bad:,} of {rows:,} "
        f"contradict them")
    assert margin == 0, (
        f"CAVEATS.md 16 rests on the margin flows carrying the same identity "
        f"the other way round, which is what fixes the direction; {margin:,} "
        f"in-window rows now break the margin identity")
    assert loose.empty, (
        f"CAVEATS.md 16 says the repair touched universe names inside the "
        f"window only; {len(loose)} recorded rows are not: "
        f"{list(zip(loose['stock_id'], loose['date']))[:5]}")
    assert not unrepaired, (
        f"CAVEATS.md 16 says each recorded row now holds the two values the "
        f"other way round and contradicted its balances before; "
        f"{len(unrepaired)} names hold rows that do not: {unrepaired[:5]}")
    span = (rec["date"].min(), rec["date"].max())
    assert (len(rec), rec["stock_id"].nunique(), rec["repull"].value_counts().to_dict()) == (
        761_472, 750, {"exchanged": 759_918, "absent": 1_554}), (
        f"CAVEATS.md 16 says the repair exchanged 761,472 rows in 750 names, "
        f"759,918 of them confirmed by the re-pull and 1,554 rows it no longer "
        f"serves, none served the way the tree had them; the record gives "
        f"{len(rec):,} rows in {rec['stock_id'].nunique()} names, "
        f"{rec['repull'].value_counts().to_dict()}")
    assert span[0][:4] == "2011" and span[1][:4] == "2024", (
        f"CAVEATS.md 16 says every crossed row is dated 2011 to 2024, the "
        f"rows the 2026-04-27 build wrote, against none of those appended on "
        f"2026-09-10; the record spans {span[0]}..{span[1]}")
    return (f"{len(rec):,} crossed short-sale pairs exchanged in "
            f"{rec['stock_id'].nunique()} names, {span[0]}..{span[1]}; "
            f"{rows:,} in-window rows agree with their balances"), rows


CHECKS = [
    test_taiwan_open_outside_session_range,
    test_taiwan_repull_returns_the_stored_prices,
    test_taiwan_ohlcv_is_raw,
    test_taiwan_pre_listing_sessions_are_one_vendor_day,
    test_taiwan_repull_fill_is_in_the_trees,
    test_taiwan_no_session_the_tape_holds_is_missing,
    test_taiwan_volume_repair_matches_the_tape,
    test_taiwan_sec_lending_pairs_are_disclosed,
    test_taiwan_fin_bs_revision_follows_the_filing,
    test_taiwan_date_keyed_fill_is_in_the_trees,
    test_taiwan_short_sale_series_has_no_regime_gap,
    test_taiwan_short_sale_flows_match_the_balances,
]
