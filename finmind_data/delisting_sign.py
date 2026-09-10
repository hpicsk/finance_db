"""Separate a delisting that took shareholders to zero from one that paid them.

``delisted_universe.parquet`` records that a name left a board and on what date.
It does not record *why*, and the two whys have opposite signs: a company that
failed is a total loss, one that was acquired or folded into a holding company
pays out at something near its last price. A study that drops delisted names
loses both; one that marks them all -100 % is wrong on the larger half. The
exchange publishes the reason only for TPEx names delisted from 2021 — 46 of
the 164 priced in-window delistings are dated 2021 or later, and only the TPEx
ones among them are covered — so the reason has to be read off the panel
instead.

It is legible there because the price paths differ in shape. An acquisition is
announced, jumps to a premium, then converges flat to the consideration and
stops at its own high. A failure collapses. The ratio of the last traded close
to the highest close of the preceding year separates them without needing the
level, the currency, or any adjustment — raw and adjusted closes give the same
ratio to four decimals (median |log difference| 0.0000, correlation 0.984), so
this runs on every name with a price history rather than the 114 the vendor's
adjusted series covers.

**The cuts below were fixed before any label was collected, and this file is
that record.** They are not tuned to the labels and must not be: an accuracy
measured at a cut chosen after seeing the answers is an accuracy of the choosing.
``delisting_labels.csv`` is drawn here, filled in by hand from the exchange and
the filings, and read back by this same script to report how often the shape was
right. The labels are in, and at the cuts as committed the shape is right on
98.7 % of the 126 names carrying a verdict — an estimate from 15 labelled
verdicts, weighted by stratum, turning on the single miss 1613.

The cut inside the band was registered on the frame this package answered about
before 2026-08-17, on the reading that the truth turns over near a drawdown of
0.50. That boundary was read off the same labels any rate at it would be scored
against, so it was never adopted here — it is *registered* here, which is the
second half of this file. On the corrected frame the reading has weakened and
the alternative registered beside it has overtaken it: 0.50 is right on 20 of
the 28 labelled band names and the free halt rule on 25.

``_DD_SINGLE`` and the gate below are committed before the labels that will test
them exist, exactly as the two cuts were. Twenty-eight of the 37 undecided names
are already labelled and are what suggested 0.50, so they cannot test it; the
other nine have never been looked up, and ``delisting_band.csv`` records what
0.50 calls each of them while that is still true — beside the call of the free
rule it has to beat, registered on the same terms so the comparison is not
assembled afterwards. Those nine are the whole test set, and they are as many as
there will ever be, because the band does not grow — which is also why the gate
can no longer be read at all: ``_GATE_MIN_LABELS`` is eleven. The work that would produce
their labels is the payout lookup — an announcement states its own reason, so a
name looked up for its consideration returns a reason for free — which is why
this is committed first. Registered after that work begins, it would be
registered against labels already seen, and there is no third batch to fall
back on.

That mechanism has since fired twice. 3561 and 6298 were both targets of
three-way transactions whose *other* targets were being looked up for a ratio,
so their filings named their reason without either name being sought: the
labels are in ``delisting_band.csv``, each beside the sentence it came from.
The registration is unaffected — the nine were frozen with the calls already
committed, and a label arriving afterwards is what a held-out set is *for*.
What it changes is the settlement, where a name whose filing has been read no
longer books NaN, and ``band_holdout`` is deliberately not shown these two, so
that filling a label cannot shrink the set the rules were registered against.

Labels are two-valued by construction, and the question they answer is whether a
transaction paid holders — cash, or shares in a surviving company — or the
listing simply ended. A compulsory delisting for non-filing is a failure by that
test even where the company kept trading elsewhere, because no payout occurred.

Parameters, per the repo's degrees-of-freedom convention:

``_PEAK_WINDOW_DAYS``
    CHOSEN, structural. One year of trading is the window an acquisition's
    announcement-to-close normally fits inside, and short enough that an
    unrelated earlier peak does not set the denominator.
``_DD_DISTRESS`` / ``_DD_MERGER``
    CHOSEN, pre-registered. Two cuts on the drawdown, placed by inspection of
    the distribution before labels existed. Their cost is measured, not argued:
    99 % of the verdicts they issue, against the labels.
``_LONG_SUSPENSION_DAYS``
    CHOSEN, structural, and pre-registered since it also sets the halt rule's
    calls. The routine gap between a last trade and the formal date is 7-14 days
    for 73 of the priced delistings; anything past a month is a halt, not
    paperwork. The held-out names' halts run 3, 14, 14 days and then past 200,
    so a move anywhere inside 14..217 leaves every held-out call where it is —
    the registration binds where it can see, which is where a call moves. What
    sees the rest of that interval is the labelled band, whose halt score holds
    only across 16..75, so between the two the cut is pinned to the narrower
    range. Both bounds are recomputed from the features in the assertion and
    compared against this sentence, because the sentence is the part with nothing
    else holding it — the cut moved once already and the range around it did not.
``_STRATUM_BRACKET``
    CHOSEN, structural. How far either side of a cut the draw treats as its
    boundary. Its value matters less than its being applied to both cuts, which
    is what ties the sample to them.
``_DD_SINGLE``
    CHOSEN, pre-registered, unscored. One cut proposed to replace the undecided
    band, read off the band names already labelled and therefore testable only
    on the nine that are not.
``_GATE_NULL``
    MEASURED, by this script, from the labelled band: the larger label class is
    17 of 28. It is what a reader gets inside the band for free by calling every
    name a payout, so it is the rate 0.50 has to beat rather than 0.50 %.
``_GATE_ALPHA``, ``_GATE_MIN_LABELS``
    CHOSEN, pre-registered; the second DERIVED from the first two rather than
    picked. Below eleven labels the criterion can only be met by a perfect
    score, which is not a test of a rule but of whether it ever errs; eleven is
    the smallest sample at which ten of eleven clears the null. ``gate_threshold``
    derives it, and the assertion re-derives it, so it moves if the other two
    do — as it did, from ten to eleven, when the 8420 correction lifted the null.
    On this frame the held-out set is nine, two short, which is why the gate
    reports itself unreadable instead of returning a threshold.
``_SAMPLE_SEED``, ``_ALLOCATION``
    CHOSEN, pre-registered. Stratified because a uniform draw would spend most
    of its labels in the ``clear`` band where the shape is least in doubt; the
    strata are sized so the boundaries and the undecided middle carry the
    labels, and weighted back up by stratum size to recover a panel-wide rate.
    The seed is the one committed with the first draw and is not re-rolled here:
    the frame changed underneath it, which changes the draw on its own, and a
    fresh seed on top would be a second thing moved at the same time.

BASELINE: price-shape classification | obvious alternative: the exchange's own
stated reason, published for TPEx names from 2021 | discharge: the reason was
read by hand for 41 names in the frame and the shape agrees with it on all but
one, so the objection is answered by measurement rather than by argument. The
names the exchange does state a reason for are in the draw on the same footing
as the rest and carry no special weight, since they cover neither the TWSE side
nor anything before 2021.

Not every row of the delisting table is an exit. A name that changes boards is
recorded as leaving the one it left and goes on trading, so it has no sign to
classify and is dropped here; a 4-digit code reissued years later to a different
company did exit, and keeps its row with the successor's sessions discounted.
Both are found by asking whether the name is still quoted on the panel's last
session — a fact about the market rather than about the delisting table, and
binary, with the tails that really end doing so 12 to 18 years short of it.

Classifying the exit is most of the work but not the number a study books, and
``terminal_value`` is the rest of it: zero for a failure unless the caller
states a haircut short of one, the consideration itself where one was recorded,
the last traded close where one was not, and nothing at all for the names whose
sign is still open. The substitute is
not free — measured against those recorded considerations, the last close
understates what was paid on every deal, by a rounding on a cash offer and by
around a tenth on a share swap. ``substitute_error`` measures it and the README
quotes it, so the gap is a known bias rather than an unknown one. What it is
*not* is a stale price: the obvious correction, scaling the error by the days
between the last trade and the formal date, fails because that gap is a
settlement calendar rather than a deal characteristic, and because the swaps
measured are conversions whose successor had no price during it at all. What is
left is a direction without a mechanism — a discount, revised terms, or four
deals falling one way, and nothing here separates them — so the bias is
reported and never corrected for.

Those four bases are the column a caller reads, and they are cut so that each
names a different piece of work: none for a failure or a recorded payout, one
filing for a substituted one, and the band's own question for an undecided one.
A single missing value covering the last two would say a number is absent
without saying which of two very different things would supply it.

Two things this file deliberately does not use. Balance-sheet equity, because
the vendor's statement history begins 2012-03-31 and nine of the 164 delisted
before it — the coverage is absent by construction rather than by non-filing
for those, and where it exists it is a quarter stale by the time the failure
lands. And a
shared delisting date, which marks a correlated event but not its direction:
2018-04-30 retires 日月光 and 矽品 into one holding company while 2007-04-11 and
2007-06-20 retire three names of the 力霸 group into bankruptcy. It is recorded
below as corroboration and never as a verdict.

    python -m finmind_data.delisting_sign
"""
from __future__ import annotations

from math import comb
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .adjusted_loader import _BREAK_GAP_DAYS
from .window import clip

HERE = Path(__file__).resolve().parent

# The frame the sample was drawn from, frozen here and deliberately not
# `window.py`'s. `COVERAGE_END` is the package's own constant and moves for the
# package's own reasons, which are not this registration's — and the draw below
# is a function of the frame, not merely reported over it: the strata bracket
# the cuts and
# `_SAMPLE_SEED` picks inside them, so a frame that grows re-strata a sample
# whose labels are already collected. That is the one edit the pre-registration
# above exists to forbid, and following a constant that moves for a data reason
# would have made it silently, with the labels still on disk and the accuracy
# still printing. These two dates are the span the package answered for on
# 2026-08-17, the day the draw was registered. Names that delisted afterwards
# sit outside them on purpose: an event later than the registration cannot join
# the sample it would have changed.
_WIN_START = pd.Timestamp("2011-01-25")
_WIN_END = pd.Timestamp("2024-12-31")

_PEAK_WINDOW_DAYS = 365
_DD_DISTRESS = 0.30
_DD_MERGER = 0.70
_LONG_SUSPENSION_DAYS = 30

# Stratum edges on the drawdown, and how many labels each stratum gets.
# The edges are *derived from the cuts* rather than written out, and that is what
# makes the pre-registration enforceable instead of merely stated: a cut moved
# after the labels are in moves the stratum boundaries, moves which names were
# drawn, and fails the assertion that redraws against the committed CSV. Written
# as five literal pairs they would not, and the edit would land silently.
_STRATUM_BRACKET = 0.05
_STRATA = [
    ("deep", 0.00, _DD_DISTRESS - _STRATUM_BRACKET),
    ("edge_lo", _DD_DISTRESS - _STRATUM_BRACKET, _DD_DISTRESS + _STRATUM_BRACKET),
    ("mid", _DD_DISTRESS + _STRATUM_BRACKET, _DD_MERGER - _STRATUM_BRACKET),
    ("edge_hi", _DD_MERGER - _STRATUM_BRACKET, _DD_MERGER + _STRATUM_BRACKET),
    ("clear", _DD_MERGER + _STRATUM_BRACKET, 1.01),
]
# The draw was stratified by era as well, on the ground that the composition
# moved hard across the window — 25 of the 65 names delisted 2005-2008 were
# distress-shaped against 0 of the 22 delisted 2011-2014 — so a sample drawn
# only from recent names would have measured the wrong mix. The window now
# starts in 2011 and every name in the frame is a recent one, which leaves the
# era dimension one non-empty cell and nothing to balance. The per-stratum
# totals are the old design's two cells added together, so what is retired is
# the split and not the shape.
_ALLOCATION = {"deep": 4, "edge_lo": 8, "mid": 10, "edge_hi": 5, "clear": 6}
_SAMPLE_SEED = 20260817

# The single cut that would close the undecided band, and the gate it has to
# clear before it may. Registered unscored: the labels that can test it do not
# exist yet, and the nine names that can supply them are listed in
# `delisting_band.csv` with 0.50's call on each already committed.
_DD_SINGLE = 0.50
_GATE_NULL = 0.607           # 17 of the 28 labelled band names are payouts
_GATE_ALPHA = 0.05
# Derived from the null and alpha, not chosen: the smallest sample at which
# something short of a perfect score clears. The band holds nine, two below it,
# so the gate cannot be read on the held-out set that exists — see the note in
# `single_cut_gate`.
_GATE_MIN_LABELS = 11

_LABEL_FILE = HERE / "delisting_labels.csv"
_BAND_FILE = HERE / "delisting_band.csv"
_CONSIDERATION_FILE = HERE / "delisting_consideration.csv"
_OUT_FILE = HERE / "delisting_sign.parquet"


def _price(stock_id: str) -> pd.DataFrame | None:
    """Raw closes for one name, positive rows only, in date order.

    Deliberately *not* clipped, unlike every other read of the trees here. The
    window decides which delistings this study answers for, and `features()`
    already applies it to the event date. It does not bound how far back a
    feature may look to characterise an event that is inside it: `drawdown`
    divides by the peak of the trailing `_PEAK_WINDOW_DAYS`, so clipping the
    lookback would leave a name whose last trade sits near `_WIN_START`
    dividing by a partial window while every other name divides by a full one —
    the same number measured over different spans.

    It costs 4408 its stratum. Its last trade is 2011-08-08 after a 266-day
    suspension, so 120 of the 248 sessions in its peak window are pre-window
    and the peak is among them: clipped, the drawdown rises 0.249 -> 0.378 and
    crosses `_DD_DISTRESS`. The pre-window half is not the contamination
    `window.COVERAGE_START` exists to exclude — no capital reduction is filed
    for it, and no session in the frame moves more than the 7 % daily limit, so
    there is no unexplained cut hiding in it. Clipping here would move a
    pre-registered draw on an artefact of the truncation.
    """
    f = HERE / f"ohlcv/{stock_id}.parquet"
    if not f.exists():
        return None
    p = pd.read_parquet(f)
    if not len(p) or "date" not in p.columns:
        return None
    p = p[["date", "close"]].copy()
    p["date"] = pd.to_datetime(p["date"])
    p = p[p["close"] > 0].sort_values("date")
    return p if len(p) else None


def _panel_last_session() -> pd.Timestamp:
    """The last session anywhere in the price panel.

    Read across the whole panel rather than the delisted frame, and rather than
    taken from a constant: this is the measurement `features()` compares a
    name's last quote against, so it has to be a session the panel really has,
    not the date the download was asked to stop on. Those two came to the same
    thing while the trees ended where the frame did; `--extend` separated them,
    and an unclipped scan now answers 2026 to a question asked about the frame.
    It is the last session the panel really has *inside* the frame, and the
    frame is `_WIN_START.._WIN_END` rather than coverage — a name's
    `quoted_through` is compared against this, so the two have to be bounded
    alike or a still-quoted name stops matching the day the trees grow.

    Stocks the endpoint returned nothing for are written as zero-row files with
    no schema at all, so the column projection is guarded instead of pushed down
    blind — same guard `_price` applies after its read.
    """
    last = None
    for f in sorted(HERE.glob("ohlcv/*.parquet")):
        if "date" not in pq.read_schema(f).names:
            continue
        d = pd.read_parquet(f, columns=["date"])
        d["date"] = pd.to_datetime(d["date"])
        d = clip(d, start=_WIN_START, end=_WIN_END)
        if not len(d):
            # Every session this stock has sits outside the frame; it
            # contributes no candidate rather than a NaT that would swallow
            # the running maximum on the first file that hits it.
            continue
        m = d["date"].max()
        last = m if last is None or m > last else last
    assert last is not None, "no priced sessions in ohlcv/ inside the frame"
    return last


def features() -> pd.DataFrame:
    """One row per in-window delisted common stock with a price history."""
    d = pd.read_parquet(HERE / "delisted_universe.parquet")
    d["date"] = pd.to_datetime(d["date"])
    d["stock_id"] = d["stock_id"].astype(str)
    d = d[(d["date"] >= _WIN_START) & (d["date"] <= _WIN_END)]
    # The target is common stock, and the universe is where that is decided. A
    # 4-digit code was standing in for it and is not the same test: Taiwan
    # numbers its ETFs 00xx and its depositary receipts 91xx, and the refreshed
    # delisting table carries 11 of them inside the window. Under the regex all
    # 11 entered the frame and left it again for want of a price file, which is
    # the right answer for a reason that expires the day the file is downloaded.
    u = set(pd.read_parquet(HERE / "universe.parquet")["stock_id"].astype(str))
    d = d[d["stock_id"].isin(u)]

    rows = []
    for r in d.itertuples():
        p = _price(r.stock_id)
        if p is None:
            continue
        pre = p[p["date"] <= r.date]
        if not len(pre):
            continue
        last_date = pre["date"].iloc[-1]
        window = pre[pre["date"] > last_date - pd.Timedelta(days=_PEAK_WINDOW_DAYS)]
        after = p[p["date"] > r.date]
        rows.append({
            "stock_id": r.stock_id,
            "stock_name": r.stock_name,
            "delist_date": r.date,
            "last_trade": last_date,
            "suspension_days": (r.date - last_date).days,
            "last_close": pre["close"].iloc[-1],
            "drawdown": pre["close"].iloc[-1] / window["close"].max(),
            "tail_sessions": int(len(after)),
            "quoted_through": p["date"].max(),
            "resume_gap": (after["date"].min() - r.date).days if len(after) else -1,
        })
    f = pd.DataFrame(rows)

    # A name still quoted on the panel's last session did not leave the market,
    # whatever the delisting table says, and the sessions after its date are not
    # its own tail. A short gap means it changed boards — no exit, so no sign to
    # classify, and it leaves the population. A long one means the 4-digit code
    # was reissued to a different company, whose sessions are in the same file:
    # the original did exit and keeps its row, with a tail of zero.
    #
    # The last session is the panel's, and reading it off this frame instead was
    # a rule that deleted its own most recent case. Every name here has left,
    # so the latest quote among them belongs to whichever left last: that name
    # matches `panel_end` by construction, is read as never having left, and —
    # having no tail — is dropped as a board transfer. It stayed hidden because
    # the frame held 6446, which the vendor dated as a delisting and never
    # delisted, so its quotes ran to the true panel end and pinned the maximum
    # there. The 2026-08-17 refresh retracts that row, and the rule immediately
    # ate 8420, the last exit in the window.
    panel_end = _panel_last_session()
    still_quoted = f["quoted_through"] == panel_end
    transferred = still_quoted & (f["resume_gap"] <= _BREAK_GAP_DAYS)
    f.loc[still_quoted & ~transferred, "tail_sessions"] = 0
    f = f[~transferred].drop(columns=["quoted_through", "resume_gap"])

    cohort = f.groupby("delist_date")["stock_id"].transform("size")
    f["shared_date"] = cohort > 1
    f["long_suspension"] = f["suspension_days"] > _LONG_SUSPENSION_DAYS
    f["has_tail"] = f["tail_sessions"] > 0

    f["sign"] = np.where(f["drawdown"] <= _DD_DISTRESS, "distress",
                         np.where(f["drawdown"] > _DD_MERGER, "merger", "ambiguous"))
    # Corroboration is recorded, never promoted to a verdict — a tail and a long
    # halt both point at failure, a shared date points only at a common cause.
    f["corroborated"] = f["has_tail"] | f["long_suspension"] | f["shared_date"]
    f["needs_lookup"] = (f["sign"] == "ambiguous") & ~f["corroborated"]

    f["stratum"] = pd.cut(f["drawdown"],
                          [e[1] for e in _STRATA] + [_STRATA[-1][2]],
                          labels=[e[0] for e in _STRATA], include_lowest=True)
    return f


def draw_sample(f: pd.DataFrame) -> pd.DataFrame:
    """The stratified label draw, fixed by ``_SAMPLE_SEED``."""
    rng = np.random.default_rng(_SAMPLE_SEED)
    picked = []
    for stratum, want in _ALLOCATION.items():
        pool = f[f["stratum"] == stratum]
        take = min(want, len(pool))
        if take:
            picked.extend(rng.choice(pool["stock_id"].to_numpy(),
                                     take, replace=False))
    s = f[f["stock_id"].isin(picked)].copy()
    s["purpose"] = "measure"
    return s


def band_holdout(f: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """The undecided names the registered rules have not been shown, and their calls.

    An undecided name that already carries a label is evidence the rules were
    read off and cannot test them; what is left is the held-out set, and it is
    the entire held-out set, because the band does not grow.

    Two calls, not one. ``halt_call`` is the rule a reader gets without the
    drawdown at all — a name whose quotation stopped a month before the formal
    date, or that went on trading after it, failed — and on the 28 labelled band
    names it is right 25 times against 0.50's 20. It was read off the same 28, so
    it is registered on the same footing rather than offered as a foil, and it
    disagrees with 0.50 on three of the nine held-out names: whatever the labels
    say, they say it about both.

    The two were level when the band was scored on 20 labelled names drawn from
    a frame that was missing 57 delistings; on the corrected frame the free rule
    is five ahead. Neither number was measured on held-out labels, so what this
    licenses is registering both, which is what happens here — not a ranking.
    """
    labelled = set(labels.loc[labels["label"].fillna("") != "", "stock_id"])
    b = f[(f["sign"] == "ambiguous") & ~f["stock_id"].isin(labelled)].copy()
    b["call"] = np.where(b["drawdown"] <= _DD_SINGLE, "distress", "merger")
    b["halt_call"] = np.where(b["has_tail"] | b["long_suspension"],
                              "distress", "merger")
    return b.sort_values("drawdown")[
        ["stock_id", "stock_name", "delist_date", "drawdown", "call",
         "halt_call"]]


def gate_threshold(n: int) -> int | None:
    """Correct calls needed at ``n`` labels to clear ``_GATE_NULL`` one-sided.

    ``None`` where no attainable count does. A binomial tail rather than a
    fixed rate because the sample size is not ours to pick: the labels arrive
    as a byproduct of looking a name up for its payout, so ``n`` is however
    many of the twelve a study turns out to hold.
    """
    p = _GATE_NULL
    for k in range(n + 1):
        if sum(comb(n, i) * p ** i * (1 - p) ** (n - i)
               for i in range(k, n + 1)) <= _GATE_ALPHA:
            return k
    return None


def single_cut_gate(band: pd.DataFrame) -> dict:
    """Where the registered cut stands against whatever labels have arrived.

    Three bars, all pre-registered, and 0.50 is adopted only by clearing every
    one. The binomial bar asks whether it beats the rate a reader gets by naming
    the band's larger class without looking at a price at all. ``trivial`` asks
    the same of the best constant predictor on these particular names, which is
    that objection in the form a referee can make once the labels are visible.
    ``halt`` asks whether the drawdown earned its place against the free rule
    that reads the halt instead — the one comparison that says whether the price
    path is doing the work, and the reason the labels are worth collecting even
    if 0.50 fails. On the labelled band that comparison has now gone the other
    way, which is what registering the alternative was for.

    The gate is unreadable as things stand and the arithmetic says so rather than
    the prose: nine names are held out and ``_GATE_MIN_LABELS`` is eleven, so
    ``need`` is ``None`` however many of the nine get labelled. Closing the band
    on the registered cut is not available on this frame, and the way back is a
    larger held-out set, not a lower bar.
    """
    scored = band[band["label"].fillna("") != ""]
    n = len(scored)
    need = gate_threshold(n) if n >= _GATE_MIN_LABELS else None
    correct = int((scored["call"] == scored["label"]).sum())
    halt = int((scored["halt_call"] == scored["label"]).sum())
    trivial = int(scored["label"].value_counts().max()) if n else 0
    return {"n": n, "correct": correct, "halt": halt, "need": need,
            "trivial": trivial,
            "adopt": need is not None and correct >= need
            and correct > trivial and correct > halt}


def considerations(f: pd.DataFrame) -> pd.DataFrame:
    """What was actually paid per share, for the deals that state it plainly.

    Only the deals whose consideration is stated in a form no convention has to
    be applied to are here — cash per share, and swaps quoted as a number of
    successor shares. A ratio written ``2.45:1`` has two readings, and picking
    the reading that lands nearer the last close would measure the picking.
    Those deals are excluded rather than resolved by inspection.

    A swap is worth the successor's price, so it is priced on the panel at the
    delisting date rather than taken from the filing.

    Twenty-three deals are recorded here, twelve of them cash; nineteen carry
    one of the 35 payout labels and four do not, because a consideration is a
    fact about a transaction and does not wait on a label. Four were read during
    labelling; three are the going-private tender offers in
    ``tender_offers.parquet``, where the exchange's own filing summary states a
    per-share price and the offer opened on the day the shares stopped trading,
    so no later transaction can have been the exit; four more were transcribed
    from ``delisting_labels.csv``, whose ``source`` already carried a per-share
    cash price read at labelling; and three are second steps, below.

    The swap side is where the direction had to be bought, and ``swap_ratios.py``
    is what bought it: the target deregistered on the way out and MOPS seals its
    說明, but the buyer is still 公開發行 and files the same ratio in a sentence
    that fixes which side is which — 「每3.1560股雷凌科技普通股股票換發1股本公司
    增資普通股股票」. Seven of the eleven in-frame swaps are read there. One more, 5854,
    is read from its own filing, because a bank converting into a holding company
    keeps its registration and is among the few MOPS still serves; and 5491 is a
    1:1, which reads the same in both directions and needs no filing to settle.
    Every ``source`` here quotes the sentence it came from, so the convention is
    auditable per row rather than assumed per file.

    Three rows are the *second* step of a two-step deal, and they are the
    reason the same route was pointed at a buyer who paid cash. A tender is paid
    to whoever tendered; the rest are squeezed out at the second step's terms,
    and those terms are in the buyer's own filing rather than in the offer
    table. 2327 states 6422's as 「合併對價為每股現金新台幣73元，與公開收購對價一致」
    and 1101 states 4725's as 「每股現金新台幣18元予信昌化公司其餘股東」 — 其餘股東 is
    the holders who did not tender, named as such. 2881 states 5820's
    differently: NT$13 at the tender, cut to 12.41 for the 109 dividend and to
    11.71 for the 110 one, so the exit is 9.9 % below the offer. Two restate the
    tender and one does not, which is why none of the three was taken from the
    offer table.

    Seven in-frame swaps are still out, and the reason is the same gate one
    company over. Five had a buyer that was itself later bought — 2448, 3698,
    2456, 5317 — and are refused in the words the targets are refused in; two
    went into a holding company that did not exist until the conversion, so
    there is no earlier filing of its to read. Their labels do state a ratio, in
    the conventions that disagree row to row, and those stay unread: for the odd
    ratios the reading that lands nearer the last close is off by an order of
    magnitude either way, but for a ratio near 1 — ``0.93:1``, ``1.07:1`` — the
    two readings are close and picking between them is fitting the answer to the
    hypothesis ``substitute_error`` below exists to test. The shortcut is safe
    exactly where it is not needed. The tender table cannot help either: a
    tender is paid in cash.
    """
    c = pd.read_csv(_CONSIDERATION_FILE,
                    dtype={"stock_id": str, "successor": str})
    c["delist_date"] = pd.to_datetime(c["delist_date"])
    # Two of the six were looked up when the package still answered about 2005
    # onward and delisted before `_WIN_START`. They stay in the file as the
    # record of what was read, and are dropped here because the frame no longer
    # reaches them. Only that reason is allowed to drop a row: a name inside the
    # window that is not one priced exit is still the assertion below.
    outside = c["delist_date"] < _WIN_START
    c = c[~outside]
    rows = []
    for r in c.itertuples():
        assert (f["stock_id"] == r.stock_id).sum() == 1, \
            f"{r.stock_id} is not one priced market exit"
        # The sheet's own date prices a swap and decides whether a row is inside
        # the window, and nothing else reads it — so a mistyped one is applied
        # rather than caught. Held against the frame, which derives its date from
        # the delisting table rather than from whoever transcribed the filing.
        formal = f.loc[f["stock_id"] == r.stock_id, "delist_date"].iloc[0]
        assert formal == r.delist_date, (
            f"{r.stock_id} is recorded in {_CONSIDERATION_FILE.name} as "
            f"delisting {r.delist_date.date()} and the frame has "
            f"{formal.date()}")
        paid = r.per_share
        overlap = 0
        if r.kind == "swap":
            p = _price(r.successor)
            assert p is not None, f"successor {r.successor} has no prices"
            on_or_before = p[p["date"] <= r.delist_date]
            assert len(on_or_before), f"successor {r.successor} not yet trading"
            paid = r.per_share * on_or_before["close"].iloc[-1]
            last_trade = f.loc[f["stock_id"] == r.stock_id, "last_trade"].iloc[0]
            overlap = int((p["date"] <= last_trade).sum())
        rows.append({"stock_id": r.stock_id, "stock_name": r.stock_name,
                     "kind": r.kind, "paid": float(paid), "overlap": overlap})
    return pd.DataFrame(rows)


def substitute_error(f: pd.DataFrame) -> pd.DataFrame:
    """How far the last traded close sits from the consideration actually paid.

    A study that holds a payout name through its delisting has to book
    *something*, and the cheapest something is the last close. Whether that is
    adequate is measurable without opening a single filing: the considerations
    are already recorded for the names looked up during labelling, and the
    successors are already priced in the panel.

    ``gap`` is the days between the last trade and the formal date, and it used
    to be here to be ruled out. The obvious reading of a one-sided error is that
    the last close is *stale* — a swap's value goes on moving with the acquirer
    while the target no longer trades, so a longer gap should carry a larger
    error. On two swaps that account could not be tested: ``overlap`` counts the
    successor's sessions on or before the target's last trade, it was zero on
    both, and a successor that has never traded cannot have drifted. Both were
    holding-company conversions, which is what a 1:1 or a flat share count is,
    and the third-party acquisitions that carry an odd ratio were the ones
    excluded for want of a direction.

    Reading those directions off the filings put seven such acquisitions into
    the sample and the account is now testable on the deals it was always about.
    ``overlap`` runs to thousands of sessions on those seven, the gap spreads
    over 7 to 16 days instead of 13 and 14, and the rank correlation of gap
    against residual across the eleven swaps is +0.86 — the sign staleness
    predicts. Read it as a measurement and not as a mechanism: it is eleven
    deals, the reading was adopted after the sample was assembled rather than
    before, and the same correlation on the twelve cash deals is −0.84, which is
    the sign staleness forbids. What can be said is that the two forms order against the
    gap in opposite directions, and that pooling them reports the deal form back
    under another name — the pooled figure read 0.80 at n=4, 0.51 with the
    tender offers, 0.10 with the label transcriptions, and moves again now,
    because it was never one relationship.

    What the wider sample did settle is the direction, by refuting it. Eleven
    swaps do not fall one way: 4944 兆遠 was paid 0.02 of a 環球晶 share, worth NT$9.99
    against a last close of NT$11.60, and it is −13.9 % rather than short of the
    mark. The name ran from 9.62 to 12.75 in its final five sessions on a float
    that was about to disappear, and pricing the swap on the last trade date
    instead of the formal one puts it at −17.8 %, so the sign is not an artefact
    of the seven-day gap. A liquidity discount, terms revised between
    announcement and effect, and a squeeze into a closing float all fit
    somewhere in these residuals, and no caller should read a cause into the
    column: ``residual`` is an error to disclose, not a factor to divide out.
    """
    c = considerations(f)
    e = f[["stock_id", "last_close", "suspension_days"]].merge(c, on="stock_id")
    return e.rename(columns={"suspension_days": "gap"}).assign(
        residual=lambda d: d["paid"] / d["last_close"] - 1)[
        ["stock_id", "stock_name", "kind", "gap", "overlap", "last_close",
         "paid", "residual"]]


def _hand_labels() -> pd.DataFrame:
    """Every hand-read label the package holds, from both files that carry one.

    ``delisting_labels.csv`` is the drawn sample and ``delisting_band.csv`` the
    nine held out from it, whose ``label`` fills in as a filing gets read for
    some other reason — two are in already, transcribed off the acquirer filings
    of the three-way mergers those names belonged to. Settlement reads both,
    because a read filing is a read filing whichever file it landed in, and
    booking NaN for a name whose sign the package has already established
    refuses an answer it owns.

    ``accuracy`` reads only the first, and gets that for free by filtering on
    ``purpose``, which the band file does not carry. The asymmetry is the point:
    booking a label is not scoring a rule against it, and the band's labels are
    held out from the rate, not from the settlement.
    """
    cols = ["stock_id", "label"]
    return pd.concat(
        [pd.read_csv(path, dtype={"stock_id": str})[cols]
         for path in (_LABEL_FILE, _BAND_FILE)], ignore_index=True)


def terminal_value(f: pd.DataFrame, labels: pd.DataFrame | None = None,
                   *, failed_haircut: float = 1.0) -> pd.DataFrame:
    """What a holder books when the series stops, and on what basis.

    A hand-read filing outranks a price shape wherever one exists, so a label
    settles the sign and the classifier fills the rest. That is not a courtesy
    to the labels: 28 of the 37 undecided names already carry one, and booking
    NaN for them would refuse an answer this package has already bought. It
    also overturns one verdict outside the band, 1613, which is the single
    disagreement ``accuracy`` reports and is left to stand there — the rate the
    cuts earned is a fact about the cuts, and correcting the value a study books
    does not change it.

    Four bases, and ``basis`` is the whole of the column's contract: it names
    what produced the number, and the four map one-to-one onto what a caller has
    to do about it.

    ``failed``
        ``last_close * (1 - failed_haircut)``, so zero by default and nothing
        else without saying so. Zero is the default because it is the only value
        that needs no source: a failure that reaches a delisting has no
        consideration to look up, and the last close is not a price anyone could
        have sold at — these 41 names are frozen a median of 120 sessions before
        the exit and 20 of them for more than 180, so the print a haircut scales
        is months stale and untradeable in both directions. A study that models
        a liquidation instead — a recovery on the residue, an exit into 興櫃 at
        some fraction — passes the fraction it does *not* recover here. The
        median last close in this basis is NT$2.57 against NT$31.30 among the
        substituted, so the choice moves less than its range suggests.
    ``consideration``
        What was actually paid, priced on the panel where the payment was in
        shares. Exact, and no action.
    ``substituted``
        The last close standing in for a consideration nobody has looked up.
        Biased low by the amount ``substitute_error`` measures, and one filing
        closes it. A study counts these among the names it actually holds, which
        is how the number of lookups worth doing falls out of running the study
        rather than being estimated ahead of it.
    ``undecided``
        NaN, and the only NaN. The sign is what the band does not know, and a
        substitute there would be a guess at the direction, not at the size —
        the two other bases are guesses at a size at worst. A caller that hits
        one resolves it or drops it, and there are seven of them — the nine
        held-out band names less the two whose filings have since been read.

    The distinction that matters is the last two: both are missing something,
    they are missing different things, and the work that closes them is
    different — one filing against a name whose sign is already known, or the
    band's own question, which is what ``delisting_band.csv`` is registered
    against.
    """
    if not 0.0 <= failed_haircut <= 1.0:
        raise ValueError(
            f"failed_haircut={failed_haircut} is outside 0..1; it is the "
            f"fraction of the last close a failure does not return")
    if labels is None:
        labels = _hand_labels()
    known = labels[labels["label"].fillna("") != ""][["stock_id", "label"]]

    t = f[["stock_id", "stock_name", "delist_date", "sign",
           "last_close"]].merge(known, on="stock_id", how="left")
    resolved = t["label"].where(t["label"].notna(), t["sign"])
    paid = t["stock_id"].map(considerations(f).set_index("stock_id")["paid"])

    # `sign` stays beside `basis` because they answer different questions — what
    # the price path said, and what was booked once a label outranked it.
    t["basis"] = np.where(resolved == "distress", "failed",
                          np.where(resolved == "ambiguous", "undecided",
                                   np.where(paid.notna(), "consideration",
                                            "substituted")))
    t["terminal"] = np.select(
        [t["basis"] == "failed", t["basis"] == "consideration",
         t["basis"] == "substituted"],
        [t["last_close"] * (1 - failed_haircut), paid, t["last_close"]],
        default=np.nan)
    return t.drop(columns=["label"])


def main() -> None:
    f = features()
    sample = draw_sample(f)
    lookup = f[f["needs_lookup"]]

    f["in_label_sample"] = f["stock_id"].isin(sample["stock_id"])
    f.to_parquet(_OUT_FILE, index=False)

    if not _LABEL_FILE.exists():
        # Two roles, kept apart on purpose. The `measure` rows are a stratified
        # random draw and their labels estimate how often the shape is right;
        # the `resolve` rows are the undecided residue and are the hardest cases
        # by construction, so folding them into the estimate would bias it down.
        out = pd.concat([
            sample.assign(purpose="measure"),
            lookup[~lookup["stock_id"].isin(sample["stock_id"])].assign(
                purpose="resolve"),
        ])[["stock_id", "stock_name", "delist_date", "drawdown",
            "suspension_days", "tail_sessions", "shared_date", "sign",
            "stratum", "purpose"]]
        out = out.sort_values(["purpose", "stratum", "delist_date"])
        out["label"] = ""        # merger | distress — filled in by hand
        # swap | cash, and blank wherever `source` names a merger without saying
        # what was paid; reading a form into those would invent the fact the
        # column is counted for.
        out["form"] = ""
        out["source"] = ""       # where the label came from
        out.to_csv(_LABEL_FILE, index=False)

    print(f"{len(f)} delisted common stocks priced in "
          f"{_WIN_START.date()}..{_WIN_END.date()}")
    print(f"  distress-shaped (drawdown <= {_DD_DISTRESS}): "
          f"{(f['sign'] == 'distress').sum()}")
    print(f"  merger-shaped   (drawdown >  {_DD_MERGER}): "
          f"{(f['sign'] == 'merger').sum()}")
    print(f"  ambiguous: {(f['sign'] == 'ambiguous').sum()}, of which "
          f"{len(lookup)} carry no corroborating feature")
    # The residue only — a name that needs looking up and was also drawn is
    # already a `measure` row, and counting it twice overstated the file.
    residue = int((~lookup["stock_id"].isin(sample["stock_id"])).sum())
    print(f"  label sample: {len(sample)} to measure, {residue} to resolve")
    print(f"  wrote {_OUT_FILE.name}")

    labels = pd.read_csv(_LABEL_FILE, dtype={"stock_id": str})
    filled = labels[labels["label"].notna() & (labels["label"] != "")]
    if not len(filled):
        print(f"  {_LABEL_FILE.name}: 0 of {len(labels)} labelled — "
              f"accuracy pending")
        return
    accuracy(f, filled)

    if not _BAND_FILE.exists():
        held = band_holdout(f, labels)
        held["label"] = ""       # merger | distress — filled in by hand
        held["source"] = ""      # where the label came from
        held.to_csv(_BAND_FILE, index=False)
    band = pd.read_csv(_BAND_FILE, dtype={"stock_id": str})
    g = single_cut_gate(band)
    print(f"\n  single cut {_DD_SINGLE} registered on {len(band)} held-out "
          f"undecided names, {g['n']} labelled")
    if g["need"] is None:
        print(f"  gate unread: needs {_GATE_MIN_LABELS} labels, "
              f"{_GATE_MIN_LABELS - g['n']} short")
    else:
        print(f"  {g['correct']} correct; needs {g['need']}, and to beat "
              f"{g['trivial']} constant and {g['halt']} halt-rule — "
              f"{'adopt' if g['adopt'] else 'decline'}")

    e = substitute_error(f)
    print(f"\n  last close vs consideration actually paid, {len(e)} deals:")
    for k, g in e.groupby("kind"):
        print(f"    {k:5s} n={len(g)}  median {g['residual'].median():+.1%}  "
              f"range {g['residual'].min():+.1%}..{g['residual'].max():+.1%}  "
              f"gap {g['gap'].min()}..{g['gap'].max()}d  "
              f"acquirer sessions before last trade {g['overlap'].sum()}")
    print(f"  terminal value basis: "
          f"{terminal_value(f, labels)['basis'].value_counts().to_dict()}")


def accuracy(f: pd.DataFrame, filled: pd.DataFrame, verbose: bool = True) -> dict:
    """Agreement on the names that carry a verdict, weighted by stratum.

    Only the ``measure`` rows enter: they are the stratified random draw, so
    within a stratum each sampled name stands for ``N_s / n_s`` of the
    population. The ``resolve`` rows were picked precisely because they were
    undecided, which makes them the hardest cases by construction — averaging
    them in would bias the rate down.

    Whether a name is scored is decided by the name, not by its stratum. Both
    edge strata straddle a cut, so each holds names on either side of it, and an
    ``ambiguous`` name can never equal a ``merger``/``distress`` label — scoring
    it would count the undecided band as a wrong answer rather than as no
    answer.
    """
    m = filled[filled["purpose"] == "measure"].merge(
        f[["stock_id", "sign", "stratum"]], on="stock_id", suffixes=("_csv", ""))
    sizes = f["stratum"].value_counts()

    est_verdict = est_correct = est_amb = est_amb_merger = 0.0
    rows = []
    for stratum in [e[0] for e in _STRATA]:
        g = m[m["stratum"] == stratum]
        if not len(g):
            continue
        weight = int(sizes.get(stratum, 0)) / len(g)
        verdict = g[g["sign"] != "ambiguous"]
        amb = g[g["sign"] == "ambiguous"]
        correct = int((verdict["sign"] == verdict["label"]).sum())
        est_verdict += weight * len(verdict)
        est_correct += weight * correct
        est_amb += weight * len(amb)
        est_amb_merger += weight * int((amb["label"] == "merger").sum())
        rows.append((stratum, int(sizes.get(stratum, 0)), len(g), len(verdict),
                     correct, len(amb)))

    acc = est_correct / est_verdict
    if verbose:
        print("\n  stratum   size  drawn  verdicts  correct  undecided")
        for s, size, n, v, c, a in rows:
            print(f"  {s:9s} {size:4d}  {n:5d}  {v:8d}  {c:7d}  {a:9d}")
        print(f"  verdicts are right on {acc:.1%} of the "
              f"{est_verdict:.0f} names carrying one "
              f"({(f['sign'] != 'ambiguous').sum()} actual)")
        print(f"  the undecided band is ~{est_amb:.0f} names, "
              f"~{est_amb_merger:.0f} of them payouts "
              f"({(f['sign'] == 'ambiguous').sum()} actual)")
    scored = m[m["sign"] != "ambiguous"]
    return {"accuracy": acc, "n_verdict": est_verdict,
            "n_ambiguous": est_amb, "n_ambiguous_merger": est_amb_merger,
            "n_scored": len(scored),
            "missed": sorted(scored.loc[scored["sign"] != scored["label"],
                                        "stock_id"])}


if __name__ == "__main__":
    main()
