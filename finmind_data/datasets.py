"""Every FinMind dataset this package collects, named once.

One entry per tree: the vendor's dataset name, the columns that identify a row
within one stock, the cadence a date-keyed sweep asks it at, and whether the
series is back-adjusted. The list used to be spelled in seven places
(``download.py``, ``repull_fill.py``, ``short_sale_repair.py``, the fingerprint
script, the README, the suite and ``.gitignore``), so a tree added to one was
absent from the others with nothing failing. Everything that needs the list
derives it from here.

``cadence`` is what the date-keyed endpoint keys a dataset on, learned by asking
it (2026-09-13): every one ignores ``end_date`` and answers for ``start_date``
alone, except the capital-reduction table, which honours the range.

``day``      any calendar day may carry a row: prices, because a make-up
             session falls on a Saturday; dividends, because ``date`` is the
             board's resolution date
``session``  rows fall on exchange sessions only, so the sessions the vintage's
             own ``ohlcv`` answered for are the dates asked
``month``    the first of each month (``month_rev.date`` is the month after the
             revenue month)
``quarter``  the four quarter ends
``range``    one request for the whole span
"""
from __future__ import annotations

from dataclasses import dataclass

# The instrument scope every tree is narrowed to: 4-digit numeric codes, which is
# `build_universe`'s own filter. It keeps ETFs (00xx) and depositary receipts
# (91xx), which the universe then excludes by code, and drops warrants,
# preferreds and the 5- and 6-digit funds.
CODE = r"\d{4}"


@dataclass(frozen=True)
class Dataset:
    tree: str
    vendor: str
    key: tuple[str, ...]
    cadence: str
    back_adjusted: bool = False
    # Rows are not unique under `key`: `sec_lending` carries one row per
    # transaction type and repeats some (CAVEATS.md 12); `div_result` files
    # 3454's 2011-07-27 twice. A fill adds such a date whole or not at all.
    repeats: bool = False


DATASETS: tuple[Dataset, ...] = (
    Dataset("ohlcv", "TaiwanStockPrice", ("date",), "day"),
    # Total-return 還原股價: anchored at the day it is pulled, so an append
    # splices two anchors and a file is only ever replaced whole.
    Dataset("price_adj", "TaiwanStockPriceAdj", ("date",), "session", back_adjusted=True),
    Dataset("instflow", "TaiwanStockInstitutionalInvestorsBuySell", ("date", "name"), "session"),
    Dataset("shares", "TaiwanStockShareholding", ("date",), "session"),
    Dataset("per_pbr", "TaiwanStockPER", ("date",), "session"),
    Dataset("margin_short", "TaiwanStockMarginPurchaseShortSale", ("date",), "session"),
    Dataset("sec_lending", "TaiwanStockSecuritiesLending", ("date",), "session", repeats=True),
    Dataset("div_result", "TaiwanStockDividendResult", ("date",), "session", repeats=True),
    Dataset("dividend", "TaiwanStockDividend", ("date", "year"), "day"),
    Dataset("month_rev", "TaiwanStockMonthRevenue", ("date",), "month"),
    Dataset("fin_is", "TaiwanStockFinancialStatements", ("date", "type"), "quarter"),
    Dataset("fin_bs", "TaiwanStockBalanceSheet", ("date", "type"), "quarter"),
    Dataset("fin_cf", "TaiwanStockCashFlowsStatement", ("date", "type"), "quarter"),
    Dataset("cap_red", "TaiwanStockCapitalReductionReferencePrice", ("date",), "range"),
)

BY_TREE: dict[str, Dataset] = {d.tree: d for d in DATASETS}
