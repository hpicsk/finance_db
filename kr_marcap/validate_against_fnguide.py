"""How close the reconstruction gets to the FnGuide series it is reconstructing.

``kr_marcap`` builds both adjusted-price conventions from openly available
sources — KRX 등락률 out of marcap, official corporate actions out of DART/KIND,
cash-dividend events out of SEIBro. FnGuide DataGuide sells the same two
conventions. This module measures the gap on every session the two share:

Each side comes in through its own project's loader — ``kr_marcap.adjusted_loader``
and ``fnguide_data.price_loader`` — so this module holds no construction logic of
its own and cannot drift from the panels research actually reads:

| Ours (``adjusted_loader``) | FnGuide (``price_loader``) | Convention |
|---|---|---|
| ``adj_close``    | ``adj_close_pr`` (수정주가, ``S410000700``)               | price return |
| ``adj_close_tr`` | ``adj_close_tr`` (수정주가(현금배당포함), ``S410007700``) | total return |

Comparison is on **log returns, not levels**. Both series are back-adjusted to a
different anchor (ours to the last traded marcap session, FnGuide's to its own
export date) so levels are related by a per-ticker constant that cancels in any
return, and returns are what the research panels actually consume.

Consecutive rows of the *merged* frame are used, so both returns span exactly the
same pair of sessions even where one source is missing a day the other serves.

Agreement is measured against two bars:

**Rounding bar** — the disagreement the two sources cannot avoid. FnGuide
publishes 수정주가 rounded to the won, so each endpoint carries up to ±₩0.5, worth
``0.5/P`` in log return; on a back-adjusted history this is *not* negligible,
because a name that later split has single-digit adjusted prices early on. Our
side compounds 등락률, which marcap rounds to 0.01 %, worth ±5e-5 per session
compounded. Their sum is a derived bound, not a fitted threshold: a day inside it
is one where the two sources are as close as their published precision permits.

**Material bar** — a fixed 10 bp on the daily return, the scale at which a
difference would move a research result rather than a decimal place.

Neither bar is tuned to the outcome; the rounding bar is arithmetic and the
material bar is a stated research tolerance. Days outside both are real
differences, and the run labels each one by which side failed: a session where
*our* return is exactly zero and FnGuide priced a move is our series frozen by
an override, not a difference of convention. See ``_diagnose``.

This gate is not redundant with ``validate_against_oracle``. That one compares
our series to the KRX 수정주가 oracle — which ``adjust`` also *consumes*, and on
the affected sessions assigns to, so the two agree there by construction. Only
an outside source can see those days.

Usage:
    python -m kr_marcap.validate_against_fnguide
    python -m kr_marcap.validate_against_fnguide --tickers 005930,000660
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fnguide_data.price_loader import PRICE_PATH as FNGUIDE_PRICE_PATH
from kr_marcap.adjust import FACTORS_PATH
from kr_marcap.adjusted_loader import load_adjusted_panel
from kr_marcap.krx_adj_oracle import load_oracle
from kr_marcap.universe import RELIABLE_START

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = Path(__file__).resolve().parent / "cache"
DELISTING_CALENDAR = REPO_ROOT / "kr_delisted" / "delisting_calendar.csv"
OUT_TICKERS = CACHE_DIR / "fnguide_validation.csv"
OUT_DAYS = CACHE_DIR / "fnguide_validation_days.csv"

# Half of FnGuide's ₩1 publication quantum. A ±₩0.5 rounding on an adjusted level
# P is worth 0.5/P in log return; summed over the two endpoints of a return it is
# the disagreement no implementation can remove.
_WON_HALF = 0.5
# Half of marcap's 0.01 % 등락률 quantum (0.0001/2), the per-session rounding our
# compounded series carries. Scaled by the number of marcap sessions a merged-row
# pair spans, since each session contributes one rounded 등락률.
_CR_HALF = 5e-5
# Daily-return difference that would change a research result rather than a
# decimal place. Stated tolerance, not fitted: 10 bp is below the ~29 bp ex-day
# drop-off the total-return layer exists to resolve (see README "Known limitations").
_MATERIAL_TOL = 1e-3
# Cap on the worst-first disagreeing-day sample written to disk. Display only —
# the per-ticker table is complete, and the run prints how many rows were cut.
_MAX_DAY_ROWS = 50_000
# KRX's 수정주가 endpoint serves a stuck ₩1,000,000 instead of the level for a few
# heavily back-adjusted delisted names. Not a ceiling — the oracle carries values
# to ₩24.8 M — so the artifact is identified by the exact repeated value, which
# occurs 18,891 times across 56 tickers and nowhere else in that concentration.
_ORACLE_STUCK_LEVEL = 1_000_000
# "No move" in log-return space. Used to tell a frozen series from a differing one.
_FLAT = 1e-12
# Floor for counting a session as carrying a dividend. FnGuide rounds its price-
# and total-return series to the won independently, so their difference is nonzero
# on ~58 % of sessions from rounding alone at a median step of 0.000 %. 0.5 % is an
# order of magnitude above that noise on a mid-priced name and below the smallest
# ordinary Korean payout, so it separates the two populations rather than cutting
# into either. Used for counting only — no factor is derived from it.
_DIV_MATERIAL = 5e-3


def _compare(m: pd.DataFrame, ours: str, theirs: str) -> pd.DataFrame:
    """Log-return difference and the two agreement bars, per merged row."""
    g = m.groupby("code", sort=False)
    with np.errstate(divide="ignore", invalid="ignore"):
        our_ret = np.log(m[ours].to_numpy() / g[ours].shift(1).to_numpy())
        their_ret = np.log(m[theirs].to_numpy() / g[theirs].shift(1).to_numpy())
        prev_theirs = g[theirs].shift(1).to_numpy()
        quant = _WON_HALF / m[theirs].to_numpy() + _WON_HALF / prev_theirs
    n_sess = (m["sess"].to_numpy() - g["sess"].shift(1).to_numpy())
    out = pd.DataFrame({
        "code": m["code"].to_numpy(),
        "date": m["date"].to_numpy(),
        "our_ret": our_ret,
        "fn_ret": their_ret,
        "diff": np.abs(our_ret - their_ret),
        "round_tol": quant + _CR_HALF * n_sess,
    })
    out["within_rounding"] = out["diff"] <= out["round_tol"]
    out["within_material"] = out["diff"] <= _MATERIAL_TOL
    return out.dropna(subset=["diff"])


def _summarise(cmp: pd.DataFrame, label: str, delisted: set[str]) -> pd.DataFrame:
    """Print the headline rates for one convention, return the per-ticker table."""
    n = len(cmp)
    agree = cmp["within_rounding"] | cmp["within_material"]
    per = cmp.assign(bad=~agree).groupby("code").agg(
        n_days=("diff", "size"),
        n_disagree=("bad", "sum"),
        max_diff=("diff", "max"),
        median_diff=("diff", "median"),
    )
    per["clean"] = per["n_disagree"] == 0
    per["delisted"] = per.index.isin(delisted)

    print(f"\n[{label}] {n:,} shared ticker-days across {cmp['code'].nunique():,} tickers",
          file=sys.stderr)
    print(f"  within the two sources' rounding : {100*cmp['within_rounding'].mean():6.3f} %",
          file=sys.stderr)
    print(f"  within {_MATERIAL_TOL*1e4:.0f} bp                    : "
          f"{100*cmp['within_material'].mean():6.3f} %", file=sys.stderr)
    print(f"  within either bar                : {100*agree.mean():6.3f} %", file=sys.stderr)
    print(f"  tickers agreeing on every day    : {100*per['clean'].mean():6.2f} % "
          f"({per['clean'].sum():,}/{len(per):,})", file=sys.stderr)
    for grp, sub in per.groupby("delisted"):
        tag = "delisted" if grp else "live    "
        cd = cmp[cmp["code"].isin(sub.index)]
        cd_agree = cd["within_rounding"] | cd["within_material"]
        print(f"    {tag}: {len(sub):,} tickers, {len(cd):,} days, "
              f"{100*cd_agree.mean():6.3f} % agree, "
              f"{100*sub['clean'].mean():5.1f} % of tickers clean", file=sys.stderr)
    # Split at the repo's documented reliability floor: pre-RELIABLE_START rows are
    # already flagged deficient for reasons independent of this benchmark
    # (illiquidity, code corruption), so the window research actually reads is the
    # one whose agreement rate matters.
    for tag, sub in [("pre-%s " % RELIABLE_START.year, cmp[cmp["date"] < RELIABLE_START]),
                     ("%s+   " % RELIABLE_START.year, cmp[cmp["date"] >= RELIABLE_START])]:
        if len(sub):
            sa = sub["within_rounding"] | sub["within_material"]
            n_clean = sub["code"].nunique() - sub.loc[~sa, "code"].nunique()
            print(f"    {tag}: {sub['code'].nunique():,} tickers, {len(sub):,} days, "
                  f"{100*sa.mean():6.3f} % agree, "
                  f"{100*n_clean/sub['code'].nunique():5.1f} % of tickers clean",
                  file=sys.stderr)
    q = cmp["diff"].quantile([0.5, 0.9, 0.99, 0.999, 1.0])
    print("  |diff| quantiles  p50 %.2e  p90 %.2e  p99 %.2e  p99.9 %.2e  max %.2e"
          % tuple(q.to_numpy()), file=sys.stderr)
    return per


def _dividend_layer(m: pd.DataFrame) -> None:
    """Score the cash-dividend layer alone, by differencing TR against PR.

    Within each source, total return minus price return cancels the structural
    adjustment exactly and leaves only the dividend treatment — so this reads the
    SEIBro layer against FnGuide's without the 등락률 backbone in the way, and the
    two layers share no input.

    Counting *which* sessions carry a dividend needs a floor: FnGuide rounds its
    two series to the won independently, so their difference is nonzero on most
    sessions from rounding alone. ``_DIV_MATERIAL`` sits an order of magnitude
    above that noise and below the smallest ordinary Korean payout.
    """
    g = m.groupby("code", sort=False)

    def lr(col):
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.log(m[col].to_numpy() / g[col].shift(1).to_numpy())

    ours = lr("adj_close_tr") - lr("adj_close")
    theirs = lr("fn_close_tr") - lr("fn_close_pr")
    ok = np.isfinite(ours) & np.isfinite(theirs)
    ours, theirs = ours[ok], theirs[ok]

    # Sessions per year from the panel itself, not a calendar constant.
    span_yr = (m["date"].max() - m["date"].min()).days / 365.25
    per_yr = m["date"].nunique() / span_yr

    o_has, f_has = np.abs(ours) > _DIV_MATERIAL, np.abs(theirs) > _DIV_MATERIAL
    both = o_has & f_has
    d = np.abs(ours - theirs)[both]
    print(f"\n[dividend layer] TR − PR wedge on {ok.sum():,} ticker-days "
          f"({per_yr:.0f} sessions/yr)", file=sys.stderr)
    print(f"  annualised mean wedge   ours {1e2*ours.mean()*per_yr:+.3f} %/yr"
          f"   FnGuide {1e2*theirs.mean()*per_yr:+.3f} %/yr", file=sys.stderr)
    print(f"  sessions booking a step >{_DIV_MATERIAL:.1%}: both {int(both.sum()):,}, "
          f"FnGuide only {int((f_has & ~o_has).sum()):,}, "
          f"ours only {int((o_has & ~f_has).sum()):,}", file=sys.stderr)
    if both.any():
        print(f"  where both book one: median |Δ| {np.median(d):.2e}, "
              f"{100*(d < _MATERIAL_TOL).mean():.2f} % within "
              f"{_MATERIAL_TOL*1e4:.0f} bp; median step ours "
              f"{1e2*np.median(np.abs(ours[both])):.3f} % vs FnGuide "
              f"{1e2*np.median(np.abs(theirs[both])):.3f} %", file=sys.stderr)
    if f_has.any():
        recall = both.sum() / f_has.sum()
        print(f"  SEIBro finds {100*recall:.1f} % of the dividend sessions "
              f"FnGuide books", file=sys.stderr)


def _diagnose(bad: pd.DataFrame) -> pd.DataFrame:
    """Label each disagreeing day with the side that failed and, where known, why.

    A disagreement is not symmetric evidence. If our return is exactly zero on a
    session FnGuide priced a move, our series is *frozen* — some override
    suppressed a real return — and the fault is ours regardless of what FnGuide
    did. The dominant cause is mechanical and identifiable: on a stuck-oracle
    session ``oracle_gross == 1``, so ``adjust``'s 거래재개 reset override sees a
    divergence from ``ChangesRatio`` larger than ``_ORACLE_RESET_TOL`` and
    replaces the exchange's real move with the oracle's non-move. It fires
    whenever the day moved more than the tolerance, which is why the affected
    names lose their large days specifically.
    """
    o = load_oracle()
    if o.empty:
        bad = bad.copy()
        bad["oracle_stuck"] = False
    else:
        o = o.copy()
        o["code"] = o["code"].astype(str).str.zfill(6)
        o["date"] = pd.to_datetime(o["date"])
        o = o.sort_values(["code", "date"])
        stuck = o["krx_adj_close"] == _ORACLE_STUCK_LEVEL
        # Either endpoint of the return being stuck is enough to force the override.
        prev = stuck.groupby(o["code"]).shift(1).eq(True)
        o["oracle_stuck"] = stuck | prev
        bad = bad.merge(o[["code", "date", "oracle_stuck"]], on=["code", "date"], how="left")
        # .eq(True) rather than fillna(False): a left-merge miss is object-dtype NaN.
        bad["oracle_stuck"] = bad["oracle_stuck"].eq(True)

    ours_flat = bad["our_ret"].abs() < _FLAT
    fn_flat = bad["fn_ret"].abs() < _FLAT
    bad["cause"] = np.select(
        [ours_flat & ~fn_flat & bad["oracle_stuck"],
         ours_flat & ~fn_flat,
         fn_flat & ~ours_flat],
        ["ours frozen — stuck KRX oracle",
         "ours frozen — other",
         "FnGuide frozen"],
        default="both move, methods differ",
    )
    return bad


def validate(factors_path: Path = FACTORS_PATH,
             fnguide_path: Path = FNGUIDE_PRICE_PATH,
             events_path: Path | None = None,
             tickers: list[str] | None = None) -> dict[str, pd.DataFrame]:
    if not fnguide_path.exists():
        raise FileNotFoundError(
            f"{fnguide_path} not found — run "
            "`python -m fnguide_data.price_loader` first"
        )
    keep = {t.zfill(6) for t in tickers} if tickers else None
    ours = load_adjusted_panel(factors_path, events_path, keep)
    fn = pd.read_parquet(fnguide_path)
    fn = fn.rename(columns={"ticker": "code", "adj_close_tr": "fn_close_tr",
                            "adj_close_pr": "fn_close_pr"})
    if keep:
        fn = fn[fn["code"].isin(keep)]

    m = (ours.merge(fn, on=["code", "date"], how="inner")
             .sort_values(["code", "date"])
             .reset_index(drop=True))
    if m.empty:
        raise ValueError("no shared (code, date) between the factors file and FnGuide")

    cal = pd.read_csv(DELISTING_CALENDAR, dtype={"ticker": str})
    delisted = set(cal["ticker"])

    span = f"{m['date'].min():%Y-%m-%d}–{m['date'].max():%Y-%m-%d}"
    print(f"[fnguide] overlap {span}; ours ends {ours['date'].max():%Y-%m-%d}, "
          f"FnGuide ends {fn['date'].max():%Y-%m-%d}", file=sys.stderr)

    results = {}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    per_frames, day_frames = [], []
    for label, ours_col, fn_col in [("price return", "adj_close", "fn_close_pr"),
                                    ("total return", "adj_close_tr", "fn_close_tr")]:
        # A non-positive FnGuide level has no log return and would make the
        # rounding bound infinite, i.e. silently unfalsifiable. Drop, don't pass.
        sub = m[m[fn_col] > 0]
        cmp = _compare(sub, ours_col, fn_col)
        per = _summarise(cmp, label, delisted)
        key = "pr" if fn_col.endswith("_pr") else "tr"
        results[key] = cmp
        per_frames.append(per.add_suffix(f"_{key}"))
        bad = cmp[~(cmp["within_rounding"] | cmp["within_material"])].copy()
        bad["convention"] = key
        day_frames.append(bad)

    per_all = pd.concat(per_frames, axis=1)
    per_all.to_csv(OUT_TICKERS)
    days = _diagnose(pd.concat(day_frames, ignore_index=True))
    days = days.sort_values("diff", ascending=False)
    tab = pd.crosstab(days["cause"], days["convention"], margins=True, margins_name="all")
    tab["share %"] = (100 * tab["all"] / len(days)).round(1)
    print(f"\n[cause] {len(days):,} disagreeing ticker-days\n"
          + tab.to_string(), file=sys.stderr)
    stuck_tickers = days.loc[days["oracle_stuck"], "code"].nunique()
    if stuck_tickers:
        print(f"  the stuck-oracle rows come from {stuck_tickers} tickers", file=sys.stderr)

    _dividend_layer(m[(m["fn_close_pr"] > 0) & (m["fn_close_tr"] > 0)])
    print(f"\n  -> {OUT_TICKERS} ({len(per_all):,} tickers)", file=sys.stderr)
    # The per-ticker table above is complete; this one is a worst-first sample for
    # eyeballing, so it is capped — and says so rather than truncating silently.
    days.head(_MAX_DAY_ROWS).to_csv(OUT_DAYS, index=False)
    print(f"  -> {OUT_DAYS} ({min(len(days), _MAX_DAY_ROWS):,} of "
          f"{len(days):,} disagreeing ticker-days, largest first)", file=sys.stderr)
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tickers", help="comma-separated subset")
    args = ap.parse_args(argv)
    tickers = [t.strip() for t in args.tickers.split(",")] if args.tickers else None
    validate(tickers=tickers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
