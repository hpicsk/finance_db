"""Separate a delisting that took shareholders to zero from one that paid them.

``delisted_universe.parquet`` records that a name left a board and on what date.
It does not record *why*, and the two whys have opposite signs: a company that
failed is a total loss, one that was acquired or folded into a holding company
pays out at something near its last price. A study that drops delisted names
loses both; one that marks them all -100 % is wrong on the larger half. The
exchange publishes the reason only for TPEx names delisted from 2021 (7 of the
173 priced in-window delistings), so the reason has to be read off the panel
instead.

It is legible there because the price paths differ in shape. An acquisition is
announced, jumps to a premium, then converges flat to the consideration and
stops at its own high. A failure collapses. The ratio of the last traded close
to the highest close of the preceding year separates them without needing the
level, the currency, or any adjustment — raw and adjusted closes give the same
ratio to four decimals (median |log difference| 0.0000, correlation 0.984), so
this runs on every name with a price history rather than the 135 the vendor's
adjusted series covers.

**The cuts below were fixed before any label was collected, and this file is
that record.** They are not tuned to the labels and must not be: an accuracy
measured at a cut chosen after seeing the answers is an accuracy of the choosing.
``delisting_labels.csv`` is drawn here, filled in by hand from the exchange and
the filings, and read back by this same script to report how often the shape was
right. The labels are in, and at the cuts as committed the shape is right on
99 % of the 140 names carrying a verdict — an estimate from 18 labelled
verdicts, weighted by stratum, turning on the single miss 1613.

They also show the cuts are placed conservatively: inside the undecided band the
truth turns over near a drawdown of 0.50, where one cut would decide most of
what two leave open. That stays a hypothesis for a later pre-registration. The
0.50 boundary was read off the same 38 labels any rate at it would be scored
against, so adopting it here would buy a better-looking number by spending the
only thing that makes the number mean anything.

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
    CHOSEN, structural. The routine gap between a last trade and the formal date
    is 7-14 days for 73 of the priced delistings; anything past a month is a
    halt, not paperwork.
``_STRATUM_BRACKET``
    CHOSEN, structural. How far either side of a cut the draw treats as its
    boundary. Its value matters less than its being applied to both cuts, which
    is what ties the sample to them.
``_SAMPLE_SEED``, ``_ALLOCATION``
    CHOSEN, pre-registered. Stratified because a uniform draw would spend most
    of its labels in the ``clear`` band where the shape is least in doubt; the
    strata are sized so the boundaries and the undecided middle carry the
    labels, and weighted back up by stratum size to recover a panel-wide rate.
    Also stratified by era: the composition moves hard across the window (25 of
    the 65 names delisted 2005-2008 are distress-shaped against 0 of the 22
    delisted 2011-2014), so a sample drawn only from recent names would measure
    the wrong mix.

BASELINE: price-shape classification | obvious alternative: the exchange's own
stated reason, which exists for 7 of the 173 | discharge: the reason was read by
hand for 38 names and the shape agrees with it on all but one, so the objection
is answered by measurement rather than by argument. The 7 TPEx names are in the
draw on the same footing as the rest and carry no special weight; 7 labels could
not have settled this alone, which is why the other 31 were bought.

Not every row of the delisting table is an exit. A name that changes boards is
recorded as leaving the one it left and goes on trading, so it has no sign to
classify and is dropped here; a 4-digit code reissued years later to a different
company did exit, and keeps its row with the successor's sessions discounted.
Both are found by asking whether the name is still quoted on the panel's last
session — a fact about the market rather than about the delisting table, and
binary, with the tails that really end doing so 12 to 18 years short of it.

Two things this file deliberately does not use. Balance-sheet equity, because
the vendor's statement history begins 2012-03-31 and 80 of the 173 delisted
before 2011 — the coverage is absent by construction rather than by non-filing,
and where it exists it is a quarter stale by the time the failure lands. And a
shared delisting date, which marks a correlated event but not its direction:
2018-04-30 retires 日月光 and 矽品 into one holding company while 2007-04-11 and
2007-06-20 retire three names of the 力霸 group into bankruptcy. It is recorded
below as corroboration and never as a verdict.

    python -m finmind_data.delisting_sign
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .adjusted_loader import _BREAK_GAP_DAYS

HERE = Path(__file__).resolve().parent

# The research window; outside it the delisted table is not price-backed.
_WIN_START, _WIN_END = pd.Timestamp("2005-01-01"), pd.Timestamp("2024-12-31")

_PEAK_WINDOW_DAYS = 365
_DD_DISTRESS = 0.30
_DD_MERGER = 0.70
_LONG_SUSPENSION_DAYS = 30

# Stratum edges on the drawdown, and how many labels each stratum gets per era.
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
_EARLY_ERA_END = 2010
_ALLOCATION = {          # stratum: (labels from <=2010, labels from >2010)
    "deep": (2, 2),
    "edge_lo": (6, 2),
    "mid": (4, 6),
    "edge_hi": (1, 4),
    "clear": (3, 3),
}
_SAMPLE_SEED = 20260817

_LABEL_FILE = HERE / "delisting_labels.csv"
_OUT_FILE = HERE / "delisting_sign.parquet"


def _price(stock_id: str) -> pd.DataFrame | None:
    """Raw closes for one name, positive rows only, in date order."""
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


def features() -> pd.DataFrame:
    """One row per in-window delisted common stock with a price history."""
    d = pd.read_parquet(HERE / "delisted_universe.parquet")
    d["date"] = pd.to_datetime(d["date"])
    d["stock_id"] = d["stock_id"].astype(str)
    d = d[(d["date"] >= _WIN_START) & (d["date"] <= _WIN_END)]
    # 6-digit codes are ETFs, ETNs and foreign issues; the target is common stock.
    d = d[d["stock_id"].str.fullmatch(r"[0-9]{4}")]

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
    panel_end = f["quoted_through"].max()
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

    f["era"] = np.where(f["delist_date"].dt.year <= _EARLY_ERA_END, "early", "late")
    f["stratum"] = pd.cut(f["drawdown"],
                          [e[1] for e in _STRATA] + [_STRATA[-1][2]],
                          labels=[e[0] for e in _STRATA], include_lowest=True)
    return f


def draw_sample(f: pd.DataFrame) -> pd.DataFrame:
    """The stratified label draw, fixed by ``_SAMPLE_SEED``."""
    rng = np.random.default_rng(_SAMPLE_SEED)
    picked = []
    for stratum, (n_early, n_late) in _ALLOCATION.items():
        for era, want in (("early", n_early), ("late", n_late)):
            pool = f[(f["stratum"] == stratum) & (f["era"] == era)]
            take = min(want, len(pool))
            if take:
                picked.extend(rng.choice(pool["stock_id"].to_numpy(),
                                         take, replace=False))
    s = f[f["stock_id"].isin(picked)].copy()
    s["purpose"] = "measure"
    return s


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
            "stratum", "era", "purpose"]]
        out = out.sort_values(["purpose", "stratum", "delist_date"])
        out["label"] = ""        # merger | distress — filled in by hand
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
    print(f"  label sample: {len(sample)} to measure, {len(lookup)} to resolve")
    print(f"  wrote {_OUT_FILE.name}")

    labels = pd.read_csv(_LABEL_FILE, dtype={"stock_id": str})
    filled = labels[labels["label"].notna() & (labels["label"] != "")]
    if not len(filled):
        print(f"  {_LABEL_FILE.name}: 0 of {len(labels)} labelled — "
              f"accuracy pending")
        return
    accuracy(f, filled)


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
