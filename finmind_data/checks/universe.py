"""The universe: membership, the survivorship overlay, the dated spans."""
from __future__ import annotations
import glob
import os
import pandas as pd

from finmind_data.window import COVERAGE_START, COVERAGE_END, clip
from finmind_data.paths import DATA, TAPE, TREES
from ._common import Skipped, _EXCLUDED_INSTRUMENTS, _INNOVATION_BOARD_SUFFIX, _NON_COMMON_CODE_BLOCK, _tape_universe, _tree


# ---- Taiwan: one OHLCV file per universe id --------------------------------
def _tw_ids():
    u = pd.read_parquet(DATA / "universe.parquet")
    d = pd.read_parquet(DATA / "delisted_universe.parquet")
    uid = set(u["stock_id"].astype(str))
    files = {os.path.basename(p).split(".")[0]
             for p in glob.glob(str(TREES / "ohlcv/*"))}
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
    from finmind_data.derive.pit_universe import sessions

    cal = sessions()
    _, d, uid, _ = _tw_ids()
    d = d[d["stock_id"].isin(uid) & (d["date"] >= cal[0]) & (d["date"] <= cal[-1])]
    rows = []
    for r in d.itertuples():
        p = _tree(TREES / f"ohlcv/{r.stock_id}.parquet",
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
    rows. What is checkable offline is the signatures a leak leaves in the
    file itself, and each is enumerated over every row rather than looked up
    for the names this bug happened to involve.

    The first signature reads `industry_category`, which the 57 overlay rows
    leave empty. The second reads the -創 suffix, which marks only the
    Innovation Board. The third signature is the code, which every row has. The
    first two alone passed a copy of the file with 0015 added as an overlay row.
    The other checks that failed on that copy pinned a count or needed a price
    file for 0015. A common added to the overlay fails them the same way.
    """
    u = pd.read_parquet(DATA / "universe.parquet")
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

    code = u["stock_id"].astype(str)
    off = u[~code.str.fullmatch(r"\d{4}") | code.str.fullmatch(_NON_COMMON_CODE_BLOCK)]
    assert off.empty, (
        f"README 'Universe' counts common stocks by 4-digit ticker code and "
        f"excludes ETFs and TDRs, whose 4-digit codes are 00xx and 91xx, but "
        f"{len(off)} ids are not a 4-digit code outside those blocks: "
        f"{sorted(off['stock_id'].astype(str))[:10]}"
    )

    assert u["stock_id"].is_unique, (
        f"universe.parquet has {len(u) - u['stock_id'].nunique()} duplicate "
        f"stock_id — taiwan_stock_info returns one row per classification, not "
        f"per stock, and a duplicate means the reduction to one row per stock "
        f"did not happen"
    )
    return (f"{len(u)} ids, all 4-digit codes outside 00xx/91xx, none carrying "
            f"an excluded instrument type or the Innovation Board -創 suffix"), len(u)


def test_taiwan_price_adj_one_per_universe():
    """Every universe id was fetched, and the empty ones are the known 92.

    `adjusted_loader.load_adjusted` raises when the file is absent, so a partial
    download is a hole in the panel rather than a degraded mode. An *empty* file
    is different: the vendor served nothing, and the README names how many.
    """
    _, _, uid, _ = _tw_ids()
    adj = {os.path.basename(p).split(".")[0]
           for p in glob.glob(str(TREES / "price_adj/*"))}
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
                    TREES / f"price_adj/{sid}.parquet")))
    assert empty == 92, (
        f"README pins 92 empty adjusted series — 50 in-window delistings and 42 "
        f"pre-window, and none of the third kind the shorter window had, a name "
        f"listed too recently for the vendor to carry an adjusted history yet; "
        f"the tree now has {empty}. A change here moves the survivorship hole "
        f"the README quantifies"
    )
    return (f"all {len(uid)} ids fetched; {empty} empty, {len(uid) - empty} "
            f"with data"), len(uid)


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


def test_taiwan_universe_holds_every_common_the_tape_shows():
    """README, "Survivorship": the universe checked against the trade record.

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
    from finmind_data.derive.pit_universe import universe_at, sessions

    spans = pd.read_parquet(DATA / "listing_spans.parquet")
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

    tape_dir = TAPE
    if not tape_dir.exists():
        raise Skipped("tape/ not built (python -m finmind_data.collect.tape_universe)")
    spans = pd.read_parquet(DATA / "listing_spans.parquet")
    cal = list(pd.read_parquet(DATA / "trading_sessions.parquet")["date"])
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
        f"`python -m finmind_data.derive.pit_universe`")
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
    from finmind_data.derive.pit_universe import _bridged, sessions, universe_at

    cal = sessions()
    at = {d: i for i, d in enumerate(cal)}
    spans = _bridged(0)
    committed = pd.read_parquet(DATA / "listing_spans.parquet")
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


CHECKS = [
    test_taiwan_ohlcv_one_per_universe,
    test_taiwan_universe_excludes_the_instruments_it_claims_to,
    test_taiwan_price_adj_one_per_universe,
    test_taiwan_overlay_covers_the_window,
    test_taiwan_universe_holds_every_common_the_tape_shows,
    test_taiwan_pit_universe_is_dated_and_keeps_its_delistings,
    test_taiwan_listing_spans_reconcile_with_the_tape,
    test_taiwan_universe_bridges_a_halt_only_when_asked,
]
