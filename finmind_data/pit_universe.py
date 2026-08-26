"""Which names were listed on a given session — the universe a backtest may hold.

``universe.parquet`` is a *name list*, not a point-in-time universe. It answers
"is this code a TWSE/TPEx common", and it answers it as of the pull, which is
the wrong question for a rebalance date: it carries the same 2,158 names on
every session of the window, so screening it at a 2013-06-28 rebalance puts 585
names in that session's universe that were not listed that day. Most of those
are ordinary timing, which dating the list fixes by construction. Three groups
are defects in the list itself and survive the dating unless they are handled —
each counted against the tape rather than assumed, and decomposed in README "A
universe is a name list until it is dated".

- **42 names were already dead when the window opened.** ``taiwan_stock_info``
  still serves a company that delisted in 2007 with a retired classification
  row, and ``build_universe.py`` keeps any code carrying a twse/tpex row. They
  never trade in-window.
- **21 listed after it closed.** The same pull carries 2025-2026 IPOs. A
  rebalance in 2013 that screens the name list is screening companies that did
  not exist.
- **120 spent part or all of the window on 興櫃.** The emerging board is not a
  listing, and the registry records only what a code is *now*, so a name
  promoted to TPEx in 2025 reads as TPEx for all of 2011-2024. It is 71,789
  code-sessions, 1.22 % of the panel.

So membership is derived from the tape — the record of what actually traded —
and corrected in the two places the tape alone is wrong.

**興櫃 sessions are removed.** A code is excluded on every session at or before
the date its ``emerging`` classification was retired. That date is the only
point-in-time market fact the registry carries: a retired row keeps the day it
was retired, a live row carries the query date, so a code still on 興櫃 today is
excluded throughout. The boundary is dated evidence like any other vendor pull
and the pull date is stamped into the artifact.

**The suspension before a delisting is added back.** For all 164 in-window
commons the tape's last session is exactly ``delisting_sign.last_trade``, which
is not the delisting — 台一 stopped trading 229 days before its listing ended.
Those sessions are absent from the tape and the company is still listed, still
held, and still owed a terminal value. Presence alone would drop a name at the
moment the delisting-return question starts, so a span runs to the session
before the delisting date. It is 5,392 sessions across 137 of the
164 — the other 27 last traded on the session before their exit and have
nothing to bridge.

**What is not corrected: an interior gap.** 580 codes have at least one session
between their first and last quote where the tape does not carry them, and the
span table splits on every one of them rather than bridging. The distribution is
bimodal and the two halves want opposite treatment — a median of 7 sessions is a
trading halt, where the name is still listed, and 45 codes have a gap of 60
sessions or more, up to 8227's nine years, which is not a halt and is not
explained by any registry in this package. Bridging serves the first and
fabricates the second. No threshold separating them is available that is not
chosen, so neither is applied: a halted name leaves the universe for the length
of its halt, and a caller that must hold through halts should read the gaps off
the span table rather than have this module guess which kind each one is.

    python -m finmind_data.pit_universe    # rebuild the spans and the calendar

    from finmind_data.pit_universe import universe_at, sessions
    universe_at("2016-06-30")                  # 1,702 codes
"""
from __future__ import annotations

import sys
from bisect import bisect_left
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests

from .window import COVERAGE_START, COVERAGE_END, clip

HERE = Path(__file__).resolve().parent
SPANS = HERE / "listing_spans.parquet"
CALENDAR = HERE / "trading_sessions.parquet"
TAPE = HERE / "tape"
API = "https://api.finmindtrade.com/api/v4/data"


# ---- runtime ---------------------------------------------------------------

@lru_cache(maxsize=1)
def _spans() -> pd.DataFrame:
    if not SPANS.exists():
        raise FileNotFoundError(
            f"{SPANS.name} not built — run `python -m finmind_data.pit_universe`")
    return pd.read_parquet(SPANS)


@lru_cache(maxsize=1)
def sessions() -> tuple[str, ...]:
    """Every session the exchange held in the window, from the tape.

    Kept as its own artifact rather than read off the spans, which was wrong in
    both directions: a span's endpoints are the days a name entered or left, so
    the union of them is neither all the sessions nor only sessions, and a
    holiday falling inside a span read as a trading day the market was open on.
    A rebalance calendar is usually written in month-ends and half of those are
    holidays, so snapping is the caller's decision and this is what it snaps
    against.
    """
    if not CALENDAR.exists():
        raise FileNotFoundError(
            f"{CALENDAR.name} not built — run `python -m finmind_data.pit_universe`")
    return tuple(pd.read_parquet(CALENDAR)["date"])


def universe_at(date: str | pd.Timestamp) -> pd.Index:
    """The codes listed on `date`, delisted-since names included.

    Raises rather than returning an empty index for a date the market was
    closed: a backtest that rebalances on a holiday would otherwise read a
    universe of zero names as a universe with nothing in it, and hold nothing
    that month without failing.
    """
    d = pd.Timestamp(date)
    if not (COVERAGE_START <= d <= COVERAGE_END):
        raise ValueError(
            f"{d.date()} is outside the window this package answers for "
            f"({COVERAGE_START.date()}..{COVERAGE_END.date()}); see window.py")
    key = d.strftime("%Y-%m-%d")
    if key not in sessions():
        raise ValueError(
            f"{key} is inside the window but is not a trading session, so no "
            f"universe is defined for it — snap to one with `sessions()`")
    s = _spans()
    hit = s[(s["start"] <= key) & (key <= s["end"])]
    return pd.Index(sorted(hit["stock_id"]), name="stock_id")


# ---- generator -------------------------------------------------------------

def _emerging_until() -> tuple[pd.Series, str]:
    """Per code, the day its 興櫃 classification stopped applying.

    One row per (stock, market, industry); a market the exchange has retired
    keeps its retirement date and one still in force carries the query date. The
    max over a code's emerging rows is therefore the end of its 興櫃 phase, or
    the query date if it is still there. The query date is returned with it and
    stamped into the artifact — this is a vendor pull, and the boundary it draws
    is only as current as the day it was taken.

    The column is object dtype and 32 rows carry the string ``"None"``, so both
    the stamp and the boundary are parsed rather than compared as text. An
    unparseable date on an emerging row is fatal: it would read as "no 興櫃
    phase" and admit the name to every session of the window, which is the
    failure this function exists to prevent.
    """
    raw = pd.DataFrame(requests.get(
        API, params={"dataset": "TaiwanStockInfo",
                     "token": (HERE / ".token").read_text().strip()},
        timeout=180).json()["data"])
    stamp = pd.to_datetime(raw["date"], errors="coerce").max()
    assert pd.notna(stamp) and stamp >= COVERAGE_END, (
        f"the registry's latest usable stamp is {stamp}, before the window "
        f"closes — a pull this old cannot say which codes are still on 興櫃")
    emerging = raw.loc[raw["type"] == "emerging", ["stock_id", "date"]].copy()
    emerging["date"] = pd.to_datetime(emerging["date"], errors="coerce")
    unparsed = emerging.loc[emerging["date"].isna(), "stock_id"].tolist()
    assert not unparsed, (
        f"{len(unparsed)} emerging rows carry no readable retirement date "
        f"({unparsed[:5]}); each would admit a 興櫃 name to the whole window")
    return (emerging.groupby("stock_id")["date"].max().dt.strftime("%Y-%m-%d"),
            stamp.strftime("%Y-%m-%d"))


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Recompute the spans and the session calendar from the tape.

    Both come out of the same read: membership is a statement about sessions,
    and a caller that has one without the other cannot tell a name that was not
    listed from a day the market was shut.
    """
    if not TAPE.exists():
        raise FileNotFoundError(
            f"{TAPE.name}/ not built — run `python -m finmind_data.tape_universe`")
    tape = clip(pd.concat([pd.read_parquet(p) for p in sorted(TAPE.glob("*.parquet"))],
                          ignore_index=True))
    cal = sorted(tape["date"].unique())
    at = {d: i for i, d in enumerate(cal)}

    universe = set(pd.read_parquet(HERE / "universe.parquet")["stock_id"])
    emerging, registry_pull = _emerging_until()

    # A delisting is an exit only if it lands inside the window: a code that
    # delisted earlier is absent from the tape anyway, and one that delists later
    # is still listed on the last session this package answers for.
    delisted = pd.read_parquet(HERE / "delisted_universe.parquet")
    exits = delisted[delisted["stock_id"].isin(universe)]
    exits = exits.set_index("stock_id")["date"]
    exits = exits[(exits >= cal[0]) & (exits <= cal[-1])]
    assert exits.index.is_unique, (
        f"a code delists twice inside the window, so one span cannot describe "
        f"it: {sorted(exits.index[exits.index.duplicated()])}")

    rows = []
    for code, quoted in tape[tape["stock_id"].isin(universe)].groupby("stock_id")["date"]:
        boundary = emerging.get(code)
        days = sorted(at[d] for d in quoted if boundary is None or d > boundary)
        if not days:
            continue                       # on 興櫃 for the whole window
        if code in exits.index:
            # 11 of the 164 delist on a day the exchange was shut, so the
            # first session the name is no longer listed on is the first one
            # at or after the date rather than the date itself.
            end = exits[code]
            stop = bisect_left(cal, end)
            assert stop > days[-1], (
                f"{code} is quoted on {cal[days[-1]]}, at or after its "
                f"{end} delisting — the code was reissued and one span "
                f"would merge two companies")
            days += list(range(days[-1] + 1, stop))
        run = [days[0], days[0]]
        for i in days[1:]:
            if i == run[1] + 1:
                run[1] = i
            else:
                rows.append((code, cal[run[0]], cal[run[1]]))
                run = [i, i]
        rows.append((code, cal[run[0]], cal[run[1]]))
    out = pd.DataFrame(rows, columns=["stock_id", "start", "end"])
    out["registry_pull"] = registry_pull
    out = out.sort_values(["stock_id", "start"]).reset_index(drop=True)
    return out, pd.DataFrame({"date": cal})


def main() -> int:
    spans, cal = build()
    spans.to_parquet(SPANS, index=False)
    cal.to_parquet(CALENDAR, index=False)
    print(f"{len(spans)} spans over {spans['stock_id'].nunique()} codes "
          f"-> {SPANS.name}; {len(cal)} sessions -> {CALENDAR.name}")
    for d in (cal["date"].iloc[0], "2016-06-30", cal["date"].iloc[-1]):
        n = int(((spans["start"] <= d) & (d <= spans["end"])).sum())
        print(f"  {d}: {n} listed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
