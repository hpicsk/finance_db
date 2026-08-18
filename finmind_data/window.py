"""The span of Taiwanese history this package will answer questions about.

**Coverage starts 2011-01-25.** Prices reach back to 2005, and the per-stock
trees still hold those years, but a price series is not usable on its own: a
capital reduction cuts the share count and the quoted price together, and
without the filing that says so the cut is indistinguishable from a −70 % day.
The filings start on 2011-01-25 and cannot be pushed back. TWSE publishes them
in 股票減資恢復買賣參考價格 (TWTAUU), which refuses any query beginning before
ROC 100/1/1 — 2011-01-25 is its first row — and FinMind's
`TaiwanStockCapitalReductionReferencePrice` begins on the same day because it
mirrors that table. No paid tier and no second vendor reaches further back;
the limit is the publisher's.

Six years of prices with no event log underneath them is not a shorter panel,
it is a panel whose errors are silent, and the choice is which of the two this
package hands a researcher. It hands the shorter one.

`COVERAGE_END` is not where the download stopped — the trees run past it, and
`download.py --extend` moves that edge whenever it is run. It is the last
session this package answers for, and it stops at the study window the rest of
the repo quotes its figures on.

`clip` is how a reader applies the window, and it exists as one function
because the alternative is the same comparison written out at each of them.
The tree holds sessions on both sides of the window, so a reader that forgets
does not fail — it quietly measures a wider panel than it reports, and the
number it returns is the kind that gets published. The check is that every
module `grep -l "ohlcv/" *.py` names imports from here, `download.py` excepted:
it writes the tree, and writing it short is what the window is not for.
"""
import pandas as pd

COVERAGE_START = pd.Timestamp("2011-01-25")
COVERAGE_END = pd.Timestamp("2024-12-31")


def clip(df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
    """Restrict `df` to the sessions this package answers for.

    Applied at the read rather than to a result: everything a reader derives —
    a back-adjustment anchor, a panel's last session, an event count — is a
    property of the rows it was given, so a frame clipped afterwards has
    already been measured over the wrong span.
    """
    d = pd.to_datetime(df[col])
    return df[(d >= COVERAGE_START) & (d <= COVERAGE_END)].reset_index(drop=True)
