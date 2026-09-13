"""What every check module shares: the paths, the window, the tree reader, the population helpers."""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from finmind_data.window import clip  # noqa: E402
from finmind_data.paths import DATA  # noqa: E402

# Each check's population, recorded so a tree that lost rows fails rather
# than passing on a smaller one. Per package, not per repo: the root is a
# container and holds no package's numbers.
POPULATIONS = Path(__file__).resolve().parents[1] / "populations.json"

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

# Where `create_time` goes from a trickle to the rule (README caveat 9). Not a
# tuned cut: the reporting month before the frontier carries the stamp on under
# a hundredth of its rows and every month after on essentially all of them, so
# any value between the two clusters names the same month.
_STAMP_SPLIT = 0.5

# ---- Taiwan: the statement trees are survivorship-incomplete ---------------
# Measured, not chosen: the latest delisting date whose income statement the
# trees do not hold. Every name that left after it has one, so the value is a
# property of the pulls rather than a cut this file picked, and the check
# derives it again rather than trusting this line. A refresh that moves it is
# the evidence that the retention rolls forward with the pull date (README
# caveat 10). `_PER_STOCK_BREAK` is the same date for the rows the per-stock
# query returned, and the rows `date_keyed_fill.py` added are what separate
# the two.
_STATEMENT_BREAK = pd.Timestamp("2020-06-19")

_PER_STOCK_BREAK = pd.Timestamp("2020-11-20")

# ---- Taiwan: what the bought adjusted series is, and what it does not mark --
# The one day the vendor stamped a session onto codes that had not begun
# trading. Named rather than derived: the silence that follows those rows runs
# unbroken from a week to fourteen months, so no gap threshold separates them
# from a suspension, and the date is the only thing all of them share.
_PRE_LISTING_DAY = "2011-04-14"

# Every other series in the panel waits a median of one day between its first
# two sessions and exactly one waits longer than a month. A month is clear of
# both, and of the seven-day minimum inside the cohort.
_NORMAL_START_GAP_DAYS = 31

# Caveat 9's late-filing figures are quoted on period ends through 2024-12-31,
# where coverage ended when they were measured. The end does not follow
# `COVERAGE_END`: an end that moved with coverage would move every figure
# quoted on the frame. The move would be large, because the late rate falls
# from the frame's last year on. Right-censoring biases the newest years down,
# since a report enters `filing_dates.parquet` only once it is uploaded.
# `test_taiwan_late_rate_falls_after_the_frame` bounds that bias and finds it
# small next to the fall.
_LATE_FRAME_END = pd.Timestamp("2024-12-31")


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
    u = pd.read_parquet(DATA / "universe.parquet")
    return sorted(u["stock_id"].astype(str))


def _tape_universe():
    p = DATA / "tape_universe.parquet"
    if not p.exists():
        raise Skipped("tape_universe.parquet not built "
                      "(python -m finmind_data.collect.tape_universe)")
    return pd.read_parquet(p)
