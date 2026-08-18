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

`COVERAGE_END` is where the download stopped, not a limit of the source.
"""
import pandas as pd

COVERAGE_START = pd.Timestamp("2011-01-25")
COVERAGE_END = pd.Timestamp("2024-12-31")
