"""The delisting study: the frame, the labels, the reasons, the terminal values."""
from __future__ import annotations
import math
import re
import pandas as pd

from finmind_data.paths import DATA, TREES
from ._common import Skipped


# ---- Taiwan: the biases the delisting table does *not* fix -----------------
def test_taiwan_delisting_table_has_no_reason():
    """CAVEATS.md 8: the delisting table dates the exit and says nothing else.

    The universe overlay built from this table removes survivorship bias from
    the price panel — the names are all present, and caveat 10 is where that
    stops. It cannot touch delisting-return bias either, because nothing here
    separates a bankruptcy from a merger and no column records what a holder
    was paid. This asserts the absence, so that a vendor backfill
    retires the caveat instead of leaving it to contradict the data quietly.
    """
    d = pd.read_parquet(DATA / "delisted_universe.parquet")
    cols = set(d.columns)
    assert cols == {"date", "stock_id", "stock_name", "year"}, (
        f"CAVEATS.md 8 says TaiwanStockDelisting carries date, stock_id, "
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
    from finmind_data.delisting.delisting_sign import (
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
    labels = pd.read_csv(DATA / "delisting_labels.csv",
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
    """CAVEATS.md 8: the price shape is right on 99 % of the names it decides.

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
    from finmind_data.delisting.delisting_sign import accuracy, features

    f = features()
    labels = pd.read_csv(DATA / "delisting_labels.csv",
                         dtype={"stock_id": str})
    blank = labels.loc[labels["label"].fillna("") == "", "stock_id"]
    assert not len(blank), (
        f"CAVEATS.md 8 reports a rate over all {len(labels)} labelled "
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
        f"CAVEATS.md 8 says the one miss is 1613 台一, a forced delisting "
        f"for non-filing that never collapsed; the misses are now "
        f"{r['missed']}. The described error mode no longer matches the data"
    )
    assert math.isclose(r["accuracy"], 0.987, abs_tol=0.005), (
        f"CAVEATS.md 8 claims the shape is right on 99 % of the names "
        f"carrying a verdict; the weighted rate is now {r['accuracy']:.1%}"
    )
    assert math.isclose(r["n_verdict"], 126, abs_tol=3), (
        f"CAVEATS.md 8 puts 127 names under a verdict (29 + 98); the "
        f"stratum-weighted estimate is {r['n_verdict']:.0f}, so the sample no "
        f"longer reconstructs the population it is weighted to"
    )
    assert math.isclose(r["n_ambiguous_merger"], 24, abs_tol=3), (
        f"CAVEATS.md 8 says ~24 of the ~38 undecided names are payouts; "
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
    from finmind_data.delisting.delisting_sign import (
        _DD_SINGLE, _GATE_MIN_LABELS, _GATE_NULL, _LONG_SUSPENSION_DAYS,
        band_holdout, features, gate_threshold, single_cut_gate)

    f = features()
    labels = pd.read_csv(DATA / "delisting_labels.csv",
                         dtype={"stock_id": str})
    band = pd.read_csv(DATA / "delisting_band.csv",
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
        f"CAVEATS.md 8 says the halt rule is right 25 times on the 28 "
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
    """CAVEATS.md 8: what the last close costs, and how it splits by form.

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
    from finmind_data.delisting.delisting_sign import (
        band_holdout, features, substitute_error, terminal_value)

    f = features()
    e = substitute_error(f)
    cash = e.loc[e["kind"] == "cash", "residual"]
    swap = e.loc[e["kind"] == "swap", "residual"]

    assert (cash > 0).all() and cash.max() < 0.015, (
        f"CAVEATS.md 8 says a cash consideration is above the last close "
        f"every time and within 1.5 % of it, which is why cash deals need no "
        f"filing pulled; {len(cash)} deals now run "
        f"{cash.min():+.2%} to {cash.max():+.2%}"
    )
    # The refutation, pinned so it cannot quietly revert. A one-directional
    # claim is what the two-swap sample supported and what ten swaps overturned,
    # and an assertion that only bounded the spread would pass either way.
    assert swap.min() < 0, (
        f"CAVEATS.md 8 says the swap substitute is two-sided — 4944 兆遠 at "
        f"−13.9 % is paid *less* than its last close, which is what retired the "
        f"claim that the last close understates every deal. The worst swap is "
        f"now {swap.min():+.2%}, so either that row has left the sample or the "
        f"caveat's own history is wrong"
    )
    assert math.isclose(swap.min(), -0.139, abs_tol=0.01) and \
        math.isclose(swap.max(), 0.248, abs_tol=0.01), (
        f"CAVEATS.md 8 puts the swap residuals from −13.9 % to +24.8 % on "
        f"{len(swap)} deals; they now run {swap.min():+.1%} to {swap.max():+.1%}"
    )
    assert math.isclose(swap.median(), 0.099, abs_tol=0.02), (
        f"CAVEATS.md 8 puts the median swap residual near +10 %; it is now "
        f"{swap.median():+.1%}"
    )
    # The split is the finding, not either level: it is what decides that a swap
    # is worth a filing and a cash deal is not. Pinned on the typical swap
    # against the worst cash deal, in absolute value, because the swap side is
    # no longer signed.
    assert swap.abs().median() > 5 * cash.max(), (
        f"CAVEATS.md 8 rests on cash and swap errors being an order of "
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
        f"CAVEATS.md 8 says the two deal forms order against the gap in "
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
        f"CAVEATS.md 8 says the staleness account became testable because "
        f"reading the ratios off the filings put seven third-party acquisitions "
        f"into the sample, each with an acquirer that had traded for years "
        f"before the target left, against holding companies that had traded "
        f"for none. {len(acq)} now clear 100 sessions (thinnest "
        f"{acq['overlap'].min() if len(acq) else 0}) and the rest reach "
        f"{thin['overlap'].max()}"
    )
    assert e.loc[e["kind"] == "swap", "gap"].nunique() >= 5, (
        f"CAVEATS.md 8 says the gap spreads over six values across the "
        f"swaps where it took two before, which is what lets it be read at "
        f"all; it now takes {e.loc[e['kind'] == 'swap', 'gap'].nunique()}"
    )

    sign = f.set_index("stock_id")["sign"]
    in_band = int((e.loc[e["kind"] == "swap", "stock_id"].map(sign)
                   == "ambiguous").sum())
    assert in_band == 7, (
        f"CAVEATS.md 8 says seven of the eleven swaps are band names, so the "
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
        "CAVEATS.md 8 says the undecided band is the only missing terminal "
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
        f"CAVEATS.md 8 says a study meets 41 failed, 23 consideration, 93 "
        f"substituted and 7 undecided; it now meets {basis}. Two movements "
        f"produce those, and only two: recording a consideration takes a name "
        f"from substituted to consideration, and reading a held-out band name's "
        f"filing takes it from undecided to substituted"
    )
    paid = e.set_index("stock_id")["paid"]
    booked = t[t["basis"] == "consideration"].set_index("stock_id")["terminal"]
    assert booked.to_dict() == paid.to_dict(), (
        f"CAVEATS.md 8 says a name whose consideration is recorded books "
        f"that consideration rather than the substitute it is measured "
        f"against; {sorted(set(paid.index) ^ set(booked.index))} disagree"
    )

    # A label outranks the shape, so the undecided rows are exactly the band
    # names nobody has looked up — the same nine the single cut is registered
    # against. Read off the label file rather than off a count, because a count
    # would still pass if the nine were a different nine.
    labels = pd.read_csv(DATA / "delisting_labels.csv",
                         dtype={"stock_id": str})
    # Both label files, because settlement reads both. The band file's `label`
    # fills in as a held-out name's filing gets read for some other reason, and
    # a check that read only the drawn sample would pass while `terminal_value`
    # booked those names off a column no assertion had opened.
    band_file = pd.read_csv(DATA / "delisting_band.csv",
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
        f"CAVEATS.md 8 says a hand-read filing outranks the price shape "
        f"wherever one exists; {wrong['stock_id'].tolist()} book against their "
        f"own label instead"
    )
    band = int((f["sign"] == "ambiguous").sum())
    assert (band, len(undecided)) == (37, 7), (
        f"CAVEATS.md 8 says the labels empty 28 of the 37 band names and "
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
        f"CAVEATS.md 8 says the single cut is registered against nine band "
        f"names and that their labels arrive from filings read for other "
        f"reasons; the holdout is now {len(frozen)} and {sorted(read - frozen)} "
        f"carry a band label without being in it"
    )
    assert set(undecided["stock_id"]) == frozen - read, (
        f"CAVEATS.md 8 says the names left without a terminal value are the "
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
    """CAVEATS.md 8: the cash-deal clustering reading, and its refutation.

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
    from finmind_data.delisting.delisting_sign import _DD_MERGER, features

    f = features()
    labels = pd.read_csv(DATA / "delisting_labels.csv",
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
        f"CAVEATS.md 8 records four labelled cash deals inside the band, "
        f"which is what refutes the clustering reading the earlier label set "
        f"supported; the band now holds {cash_in_band}. If this went back to "
        f"empty the refutation went with it and the paragraph has to be re-read"
    )
    assert m.loc[form == "cash", "drawdown"].min() < _DD_MERGER, (
        f"CAVEATS.md 8 retired the mechanical account — a cash offer at a "
        f"premium was said to stop near its own high, above the band's upper "
        f"cut of {_DD_MERGER}, and four cash deals sit below it because the "
        f"drawdown is measured against a trailing-year peak. The lowest "
        f"labelled cash deal is now at "
        f"{m.loc[form == 'cash', 'drawdown'].min():.3f}"
    )

    counts = form.value_counts().to_dict()
    assert (len(m), counts.get("swap"), counts.get("cash"),
            counts.get("unstated")) == (27, 17, 9, 1), (
        f"CAVEATS.md 8 says 27 labelled payouts in the frame split 17 share "
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
        f"CAVEATS.md 8 reports Fisher exact two-sided at 0.234 on the "
        f"form-by-band table and reads it as no association; the exact test now "
        f"returns {p:.3f}"
    )
    return (f"{counts['cash']} labelled cash payouts, {len(cash_in_band)} of "
            f"them inside the band's {_DD_MERGER} cut; {band_swap} of {band_n} "
            f"stated forms inside it are share exchanges against "
            f"{swap_n}/{stated_n} overall, p={p:.3f}",
            len(m))


def test_taiwan_mops_covers_every_delisted_name():
    """CAVEATS.md 8: the 主旨 was pulled for all 164, not for the servable few.

    The two MOPS hosts disagree about delisted companies, and the legacy one
    answers for 14 of the 164. A pull that ran against it would return a corpus
    that looks complete — every file non-empty, every request answered — over a
    twelfth of the frame. This asserts the corpus spans the frame, so a rerun
    pointed at the wrong host fails here rather than shrinking the population a
    reason is later read from.
    """
    frame = pd.read_parquet(DATA / "delisting_sign.parquet")
    d = DATA / "mops_listing"
    if not d.exists():
        raise Skipped("mops_listing/ not built — run `mops_filings.py listings`")
    files = {p.stem for p in d.glob("*.parquet")}
    missing = sorted(set(frame.stock_id) - files)
    assert not missing, (
        f"CAVEATS.md 8 says 重大訊息 were pulled for every one of the "
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
        f"CAVEATS.md 8 puts 19,949 announcements in this corpus; it now "
        f"holds {len(rows)}. A pull that shrank means the host changed what it "
        f"serves, and the reasons downstream were read from more than survives"
    )
    return (f"{len(rows)} 主旨 across {len(files)} names, none empty", len(rows))


def test_taiwan_mops_detail_gate_is_registration_not_filing():
    """CAVEATS.md 8: 說明 is refused for a company that deregistered.

    The refusal is the coverage figure, so it is asserted rather than logged:
    if MOPS starts serving the bodies, the caveat's claim that a consideration
    must still be read one filing at a time is obsolete and the 說明 for 150
    names is sitting there unread.
    """
    path = DATA / "mops_detail_refusals.csv"
    if not path.exists():
        raise Skipped("mops_detail_refusals.csv not built — "
                      "run `mops_filings.py details`")
    ref = pd.read_csv(path, dtype={"stock_id": str})
    ref = ref[ref["stage"] == "details"]
    frame = pd.read_parquet(DATA / "delisting_sign.parquet")
    served = len(frame) - len(ref)
    assert served == 14, (
        f"CAVEATS.md 8 says MOPS serves the 說明 for 14 of the "
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
    """CAVEATS.md 8: every swap ratio read off a filing is still in it.

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
    cons = pd.read_csv(DATA / "delisting_consideration.csv",
                       dtype={"stock_id": str, "successor": str})
    rows = [r for r in cons.itertuples() if quoted.search(r.source or "")]

    unresolved = []
    for r in rows:
        # `source` says whose filing it is: the target's own where MOPS still
        # serves it, the acquirer's otherwise. Reading the routing out of the
        # sentence keeps the two caches from being interchangeable by accident.
        sub = "mops_detail" if "own filing" in r.source else "mops_acquirer_detail"
        path = DATA / f"{sub}/{r.stock_id}.parquet"
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
        f"CAVEATS.md 8 says each swap ratio's direction was read off the "
        f"filing its row quotes; {unresolved} no longer resolve to a cached "
        f"body on a date the row names, so their `per_share` is uncited"
    )

    # The route's boundary, asserted for the same reason the target-side gate
    # is: it is a coverage figure. An acquirer that was itself later bought is
    # refused in the same words as a target, and the five that are out are why
    # seven of the seventeen in-frame swaps still have no ratio.
    refused = pd.read_csv(DATA / "mops_acquirer_refusals.csv",
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
    """CAVEATS.md 8: the filings decide 30 of the 37 the price shape did not.

    This is what the pull bought. The band is the set the single cut is
    registered against, and the claim is that a filing settles most of it
    without the cut — so if the reader shrinks, the cut is carrying names the
    caveat says it no longer has to.
    """
    path = DATA / "mops_reason.parquet"
    if not path.exists():
        raise Skipped("mops_reason.parquet not built — run `mops_reason.py`")
    r = pd.read_parquet(path)
    amb = r[r["price_shape_sign"] == "ambiguous"]
    decided = amb[amb["reason"] != "unknown"]
    assert len(amb) == 37, (
        f"CAVEATS.md 8 counts 37 names the shape left undecided; the frame "
        f"now holds {len(amb)}, so the band this claim is about has moved"
    )
    assert len(decided) == 30, (
        f"CAVEATS.md 8 says the filings decide 30 of the 37 undecided "
        f"names; they now decide {len(decided)}"
    )
    n_mer = int((decided["reason"] == "merger").sum())
    assert n_mer == 19, (
        f"CAVEATS.md 8 splits those 30 into 19 payouts and 11 failures; "
        f"the split is now {n_mer} and {len(decided) - n_mer}"
    )
    return (f"band {len(amb)} -> {len(decided)} decided "
            f"({n_mer} payout, {len(decided) - n_mer} failure)", len(amb))


def test_taiwan_mops_overturns_only_failures_the_tape_missed():
    """CAVEATS.md 8: two overturns, both the same error, one of them 1613.

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
    path = DATA / "mops_reason.parquet"
    if not path.exists():
        raise Skipped("mops_reason.parquet not built — run `mops_reason.py`")
    r = pd.read_parquet(path)
    d = r[(r["price_shape_sign"] != "ambiguous") & (r["reason"] != "unknown")]
    over = d[d["price_shape_sign"] != d["reason"]]
    wrong_way = over[over["reason"] != "distress"]
    assert not len(wrong_way), (
        f"CAVEATS.md 8 says every overturn runs the same way — a removal "
        f"the tape read as a payout; {len(wrong_way)} now run the other way "
        f"({sorted(wrong_way['stock_id'])}), so the error mode is not one-sided"
    )
    got = sorted(over["stock_id"])
    assert got == ["1613", "3562"], (
        f"CAVEATS.md 8 names the two overturns 1613 and 3562; they are now "
        f"{got}. The sentence describing what the shape gets wrong no longer "
        f"matches the filings"
    )
    return (f"{len(over)} overturns, all payout->failure: {got}", len(d))


def test_taiwan_exchange_provision_markers_match_what_they_govern():
    """CAVEATS.md 8: one exchange provision is a merger marker, the other is
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
    path = DATA / "mops_reason.parquet"
    if not path.exists():
        raise Skipped("mops_reason.parquet not built — run `mops_reason.py`")
    from finmind_data.delisting import mops_reason as M

    r = pd.read_parquet(path).set_index("stock_id")
    subjects = {p.stem: pd.read_parquet(p)["subject"].fillna("")
                for p in sorted((DATA / "mops_listing").glob("*.parquet"))}
    cites = lambda pat: sorted(k for k, v in subjects.items()
                               if v.str.contains(pat, regex=True).any())

    # The provision applies to one transaction, so a company citing it has said
    # which one; the swap filing under its own name is that transaction on the
    # record. `_subjects` is the rule's own window rather than a second copy.
    twse = cites(r"五十三條之十七|53條之17")
    assert twse == ["5305", "8497"], (
        f"CAVEATS.md 8 names 5305 and 8497 as the two 53-17 citers; the "
        f"archive now cites it for {twse}"
    )
    for sid in twse:
        row = r.loc[sid]
        assert (row["reason"], row["basis"]) == ("merger", "anchor"), (
            f"CAVEATS.md 8 says 53-17 decides {sid} as a merger at the "
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
        f"CAVEATS.md 8 says 6 companies file a TPEx business-rule notice; "
        f"{len(filers)} do now ({filers})"
    )
    lab = pd.read_csv(DATA / "delisting_labels.csv",
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
        f"CAVEATS.md 8 says adopting the TPEx notice moves 1333 and 6497; "
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
    """CAVEATS.md 8: the subject rule against the corrected hand labels.

    The labels were read off announcements by hand and the rule reads the same
    filings mechanically, so this is the rule's error rate against the best
    reading the package owns. It is not an independent one, and caveat 8 says
    so: the two parted on 8420, the parting is what sent the filings to be
    read, and the label was the side that moved. 41 of 42 against the sheet as
    drawn is the number with provenance. What this asserts is that nothing
    parts now, so a rule that drifts arrives here by name.
    """
    path = DATA / "mops_reason.parquet"
    if not path.exists():
        raise Skipped("mops_reason.parquet not built — run `mops_reason.py`")
    r = pd.read_parquet(path)
    lab = pd.read_csv(DATA / "delisting_labels.csv",
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
        f"CAVEATS.md 8 says the rule and the corrected labels agree on all "
        f"{len(dec)}; they now part on {miss}. 8420 was the one parting and it "
        f"closed by correcting the label, so a name here is the rule drifting "
        f"rather than a label left to re-read"
    )
    return (f"{len(dec)}/{len(dec)} agree with the hand labels, one of them "
            f"(8420) because the label was corrected to match", len(dec))


def test_taiwan_anchor_overrides_agree_with_their_own_window():
    """CAVEATS.md 8: the decision path the hand-label score is blind to.

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
    path = DATA / "mops_reason.parquet"
    if not path.exists():
        raise Skipped("mops_reason.parquet not built — run `mops_reason.py`")
    from finmind_data.delisting import mops_reason as M

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
    lab = set(pd.read_csv(DATA / "delisting_labels.csv",
                          dtype={"stock_id": str})["stock_id"])
    anchors = r[r["basis"] == "anchor"]
    unwitnessed = sorted(set(anchors["stock_id"]) - lab)

    split = contradicted(r)
    assert split == [], (
        f"CAVEATS.md 8 says every anchor override agrees with the window it "
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
    """CAVEATS.md 8: why the 18 silent names are not a pattern gap to close.

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
    path = DATA / "mops_reason.parquet"
    if not path.exists():
        raise Skipped("mops_reason.parquet not built — run `mops_reason.py`")
    from finmind_data.delisting import mops_reason as M

    r = pd.read_parquet(path)
    lab = pd.read_csv(DATA / "delisting_labels.csv",
                      dtype={"stock_id": str}).set_index("stock_id")["label"]
    silent = r[r["basis"] == "silent"]
    span = (int(silent["n_subjects_in_window"].min()),
            int(silent["n_subjects_in_window"].max()))
    assert span == (18, 191), (
        f"CAVEATS.md 8 says the silent names carry 18 to 191 filings each, "
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
        f"CAVEATS.md 8 keeps 繼續經營 out on 13 windows splitting 8 distress "
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
    path = DATA / "mops_reason.parquet"
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

    lab = pd.read_csv(DATA / "delisting_labels.csv",
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


def test_taiwan_booked_tender_offers_opened_on_the_delisting_date():
    """CAVEATS.md 8: a tender is the exit only if it opened after the tape did.

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
    from finmind_data.delisting.delisting_sign import considerations, features

    path = DATA / "tender_offers.parquet"
    if not path.exists():
        raise Skipped("tender_offers.parquet not built — "
                      "run `python -m finmind_data.delisting.tender_offers`")
    d = pd.read_parquet(path)
    f = features()
    on_frame = d[d["target_id"].isin(f["stock_id"])].merge(
        f[["stock_id", "delist_date", "last_trade"]],
        left_on="target_id", right_on="stock_id")
    assert len(on_frame) == 15, (
        f"CAVEATS.md 8 counts 15 tender offers made on the 164; there are "
        f"now {len(on_frame)}. The table starts at ROC 105/11, so a fall means "
        f"the source moved and a rise means it reaches further back"
    )

    c = pd.read_csv(DATA / "delisting_consideration.csv",
                    dtype={"stock_id": str})
    booked = c[c["source"].str.contains("公開收購申報資料彙總表", na=False)]
    assert len(booked) == 3, (
        f"CAVEATS.md 8 books 3 tender offers as the consideration paid; the "
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
        f"CAVEATS.md 8 leaves the 12 offers that opened while the shares "
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
        f"CAVEATS.md 8 splits the twelve into eight first steps and four the "
        f"table says ended no listing; it now reads {len(linked)} and "
        f"{len(two_step) - len(linked)}"
    )
    linked["gap"] = (linked["delist_date"] - linked["end_ts"]).dt.days
    assert (linked["gap"].min(), linked["gap"].max()) == (99, 648), (
        f"CAVEATS.md 8 dates the second step 99 to 648 days after the offer "
        f"closed; the span is now {linked['gap'].min()}..{linked['gap'].max()}"
    )
    last = {}
    for tid in linked["target_id"]:
        px = pd.read_parquet(TREES / f"ohlcv/{tid}.parquet")
        last[tid] = float(px.loc[pd.to_datetime(px["date"]).idxmax(), "close"])
    # Signed the way the README quotes it: the tender price against the last
    # close, so 5820's +11.1 % means the offer was above the tape.
    linked["err"] = [r.per_share / last[r.target_id] - 1
                     for r in linked.itertuples()]
    lo, hi = linked["err"].min(), linked["err"].max()
    assert math.isclose(lo, -0.0576, abs_tol=5e-4) and \
        math.isclose(hi, 0.1111, abs_tol=5e-4), (
        f"CAVEATS.md 8 puts the eight tender prices from −5.8 % (3144) to "
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
        f"CAVEATS.md 8 reads the two-step residual as dispersion that grows "
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
        f"CAVEATS.md 8 says three of the eight were bought by a company "
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
        f"CAVEATS.md 8 says the three reachable two-step residuals are "
        f"booked from the buyer's own filing of the second step; "
        f"{sorted({'6422', '4725', '5820'} - set(second))} carry no "
        f"consideration, so the route's own output has gone missing"
    )
    off_tender = {t: second[t] / float(linked.set_index("target_id")
                                       .loc[t, "per_share"]) - 1
                  for t in second}
    assert all(abs(v) < 1e-9 for k, v in off_tender.items() if k != "5820"), (
        f"CAVEATS.md 8 says 6422 and 4725 restate the tender price exactly "
        f"— 「與公開收購對價一致」 and 「每股現金新台幣18元予信昌化公司其餘股東」 — "
        f"which is what makes 5820 a difference in the deal rather than in the "
        f"reading; they now sit at {off_tender}"
    )
    assert math.isclose(off_tender["5820"], -0.0992, abs_tol=5e-4), (
        f"CAVEATS.md 8 says 5820's merger consideration was adjusted twice "
        f"for dividends and settled 9.9 % below its NT$13 tender; it is now "
        f"{off_tender['5820']:+.2%}, so either the filing was reread or the "
        f"one case that pays for the exclusion has moved"
    )
    # The half that decides the policy: against the same three exits, the last
    # close is the better substitute, and it is better *because* the tender is
    # exact only when nothing intervened between the two steps.
    worst_close = max(abs(second[t] / last[t] - 1) for t in second)
    assert worst_close < abs(off_tender["5820"]), (
        f"CAVEATS.md 8 declines the tender price as a substitute on the "
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


CHECKS = [
    test_taiwan_delisting_table_has_no_reason,
    test_taiwan_delisting_sign_sample_is_preregistered,
    test_taiwan_delisting_sign_accuracy,
    test_taiwan_single_cut_is_registered_unscored,
    test_taiwan_substitute_error_splits_by_deal_form,
    test_taiwan_cash_payouts_land_outside_the_band,
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
    test_taiwan_booked_tender_offers_opened_on_the_delisting_date,
]
