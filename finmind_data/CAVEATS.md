# Caveats

Every known defect a study meets in this package, one entry each. Each entry
says what the defect is, how much of the panel it touches, which check in
`test_assertions.py` pins it so a refresh cannot move it silently, and what a
study does about it. The measurements are quoted on the window
2011-01-25..2026-09-09 unless an entry names its own frame. How each was found
is in `NOTES.md` and the commit log; the adjusted-price entries are expanded in
`ADJUSTED_PRICES.md` and the delisting entry in `delisting/README.md`.

## 1. Individual retail flow is not reported

**What.** `instflow/` carries the exchange's 三大法人 categories only.
**How much.** Every stock-day.
**Pinned by.** Nothing; it is a property of the source.
**For a study.** Derive retail flow as `Trading_Volume − Σ(buy+sell)/2` per
stock-day, or use it as a residual sign.

## 2. Series are partial inside the window

**What.** A name that listed after 2011-01-25 or delisted before 2026-09-09 has
a shorter series, and `universe.parquet` carries every name on every session.
**How much.** 586 of the 2,159 names are not listed on a 2013-06-28 rebalance.
**Pinned by.** `test_taiwan_pit_universe_is_dated_and_keeps_its_delistings`,
`test_taiwan_listing_spans_reconcile_with_the_tape`.
**For a study.** Filter by `date` after any concat, and take membership from
`derive/pit_universe.universe_at(date)` rather than from the name list.

## 3. ETFs, depositary receipts and warrants are excluded

**What.** The universe is common stock; `00xx` ETFs and `91xx` depositary
receipts are dropped by code, warrants and preferreds by the 4-digit filter.
**How much.** 11 of the 190 in-window delistings are such instruments and are
absent from the universe (`delisted_universe.parquet` against `universe.parquet`).
**Pinned by.** `test_taiwan_universe_excludes_the_instruments_it_claims_to`.
**For a study.** Nothing; this is the intended scope.

## 4. Raw closes reflect no corporate action, and the adjusted series is incomplete

**What.** `ohlcv/` closes are raw. `price_adj/` is the vendor's back-adjusted
series, in the total-return convention only, and it serves nothing at all for
54 stocks, is wrong on one event, and stops one traded session short at the
start of 494 series. `derive/adjusted_loader.load_adjusted` rebuilds the first
from the exchange's reference prices, patches the second and carries the third,
marking each in `adj_source`. Read `price_adj/` directly and you get none of it.
**How much.** The 54 are 61,505 traded sessions, 50 of them in-window
delistings; the patch moves 120 rows; the carry recovers 493 first returns.
**Pinned by.** `test_taiwan_ohlcv_is_raw`, `test_taiwan_adjusted_survivorship_hole`,
`test_taiwan_survivorship_hole_is_rebuilt`, `test_taiwan_rebuild_matches_vendor`,
`test_taiwan_vendor_defects_are_patched`, `test_taiwan_vendor_edges_are_carried`,
`test_taiwan_adj_source_partitions_the_panel`.
**For a study.** Load through `load_adjusted`, filter on `is_valid` and
`adj_close_tr.notna()`, and split on `adj_source` before comparing across the
vendor/rebuilt boundary (`ADJUSTED_PRICES.md`).

## 5. Capital reductions are filed from 2011-01-25, and par-value changes were in no chain

**What.** The exchange publishes 減資 reference prices from ROC 100/1/1 and no
earlier; a reduction filed before that leaves its full price jump inside the
adjusted series, the vendor's included. `derive/detect_unpriced_actions.py`
finds cancellations from `shares/NumberOfSharesIssued` instead and
`load_adjusted` marks the history behind each one `is_valid=False`. A 面額變更
divides the price and multiplies the share count by the same factor; until
`split_reference.parquet` existed the rebuilt factor stepped straight across
every one.
**How much.** Of the 651 share-count drops inside the window, 608 match a filed
減資 and 43 in 41 stocks do not (93.4 % precision, 90.4 % recall where the filed
events can score it). 23 par-value changes in the window, ratios 0.05 to 0.50,
now reproduced against the vendor to 1e-3 on all 23.
**Pinned by.** `test_capital_reduction_artifact_exists`,
`test_taiwan_par_value_changes_are_priced`,
`test_taiwan_no_event_holes_are_event_free_in_three_sources`.
**For a study.** Run `detect_unpriced_actions` after `consolidate_capred`;
`load_adjusted` raises if its output is missing. Filter on `is_valid`.

## 6. A handful of raw prices are wrong

**What.** Stale near-zero quotes, sporadic pre-listing 興櫃 sessions, and at
least one corrupted row: 8454 on 2014-09-09 reports `open` 241.04 and `max`
242.49 against `min` = `close` = 3.43. On 2011-04-14 the vendor stamped one
session onto 12 codes that then do not trade again for 7 to 419 days.
**How much.** The 12-code cohort is pinned rather than truncated, because no
published listing date says where to cut and a rule inferred from the silence
would reach 56 series with a gap over 180 days, 50 of them mid-series halts.
**Pinned by.** `test_taiwan_pre_listing_sessions_are_one_vendor_day`.
**For a study.** `is_valid` does not cover these; they are bad prices, not
broken series. Screen them yourself.

## 7. TWSE stopped publishing the 除權息 split in 2009

**What.** `exright_reference.parquet` carries 權值 and 息值 separately for
2005-2008 and only their sum from 2009, with a 權/息 label that still settles a
pure event. TPEx publishes no equivalent at all.
**How much.** Only a fused 權息 event after 2008 is left without a cash leg.
**Pinned by.** Nothing; it is the publisher's limit.
**For a study.** A price-return convention cannot be built here; the adjusted
series is total return only.

## 8. No delisting reason and no terminal value in the vendor's table

**What.** `TaiwanStockDelisting` carries date, code and name. Nothing separates
a bankruptcy from a buyout, and no field records what a holder received, so
booking the last close as the terminal value is wrong in a direction the table
omits. `delisting/` reads the reason off the tape and the MOPS filings, and
books a terminal value with its basis named.
**How much.** Of the 164 exits dated 2011-01-25..2024-12-31, the filings settle
the reason for 146; what a study meets is 41 `failed`, 23 `consideration`,
93 `substituted` (the last close, biased by +0.68 % median on cash deals and
−13.9 %..+24.8 % on swaps) and 7 `undecided`.
**Pinned by.** `test_taiwan_delisting_table_has_no_reason`,
`test_taiwan_reason_frame_is_frozen`, `test_taiwan_delisting_sign_accuracy`,
`test_taiwan_single_cut_is_registered_unscored`,
`test_taiwan_substitute_error_splits_by_deal_form` and the other checks
`delisting/README.md` names.
**For a study.** Book through `delisting.delisting_sign.terminal_value` and
read its `basis` column. The frame is frozen on 2024-12-31; the 15 names that
delisted later are in every survivorship check and have no reason read.

## 9. Fundamentals are dated by fiscal period end, not by publication

**What.** `fin_is/`, `fin_bs/` and `fin_cf/` key on the quarter that closed and
carry no publication date; `month_rev/` carries one only from reporting month
2026-03. Joining on `date` hands a trader figures before they existed.
`derive/available_date.py` answers twice: `available_date` is the statutory
deadline, a bound; `observed_date` is the day the report was uploaded to TWSE's
document server, collected by `collect/filing_dates.py` into
`filing_dates.parquet`, rolled to the next session where the upload landed
after the 13:30 close.
**How much.** Of 93,520 company-quarters ending 2011-12-31..2024-12-31, 6.56 %
were published after their deadline and 14.66 % could not be traded on by it.
20 of the 106,671 in-window `fin_is` quarters have no observed date and are left
`NaT`. The deadline table spans a regime change: the annual report shortened
from four months to three from FY2011, the half-year to 45 days from FY2013.
**Pinned by.** `test_taiwan_fundamentals_are_fiscal_dated`,
`test_taiwan_month_rev_date_is_the_following_month`,
`test_taiwan_filing_deadline_table_covers_the_data`,
`test_taiwan_filing_deadline_q2_boundary_is_fy2013`,
`test_taiwan_filing_dates_cover_the_statement_trees`,
`test_taiwan_filing_dates_drop_reports_filed_before_their_quarter`,
`test_taiwan_statements_are_published_after_their_deadline`,
`test_taiwan_late_rate_falls_after_the_frame`,
`test_taiwan_observed_date_leaves_the_undatable_undated`,
`test_taiwan_observed_date_rolls_past_the_session_close`.
**For a study.** Join statements on `observed_date`; join revenue on
`available_date(kind="monthly_revenue")`, since the document server carries no
revenue filings.

## 10. The statement trees drop old delistings

**What.** The endpoints serving filings answer for a company that still
reports, so a name that left the board and stopped filing has an empty statement
file however long it traded. The daily trees the exchange publishes show no such
break.
**How much.** Of the 179 in-window delistings, `fin_is/` carries rows for 84,
`fin_cf/` 91, `fin_bs/` 97, `shares/` 122; `per_pbr/` 177 and `instflow/` 171.
Every one of the 70 names delisted after 2020-06-19 has an income statement,
against 14 of the 109 before it.
**Pinned by.** `test_taiwan_statement_trees_drop_old_delistings`.
**For a study.** A fundamental signal on this panel is survivorship-biased where
a price signal is not, and the two are not separable by care in the join: the
names that left are the names whose statements are gone.

## 11. `open` is outside `[min, max]` on 2.0 % of traded rows

**What.** `open` sits above the session `max` or below the `min`; `close` never
does. On 興櫃 sessions `open` is the previous day's average price by definition.
**How much.** 131,261 traded rows in 684 stocks; 29,651 of them on 興櫃
sessions `pit_universe` removes. On the sessions it keeps the share is 1.57 %,
falling from 3.33 % of 2011's rows to 0.06 % of 2024's and none from 2025. A
re-pull of 40 affected stocks returned every price unchanged.
**Pinned by.** `test_taiwan_open_outside_session_range`,
`test_taiwan_repull_returns_the_stored_prices`.
**For a study.** Screen with `open.between(min, max)` before entering at the
open; a strategy on `close` is unaffected.

## 12. `sec_lending` carries 86,002 rows twice

**What.** Pairs identical in every column, all dated 2017-12-18..2020-10-27, in
989 stocks; no row appears three times and no pair exists outside the span. The
vendor still served them on 2026-09-12.
**How much.** 172,004 of the 1,541,802 in-window rows, 53-58 % of each of
2018, 2019 and 2020.
**Pinned by.** `test_taiwan_sec_lending_pairs_are_disclosed`.
**For a study.** `drop_duplicates()` keeps one of each; it would also merge a
genuine identical pair, of which the rest of the window has none.

## 13. `fin_bs/` holds the vendor's revision only where the filing sides with it

**What.** A 2026-09-12 date-keyed pull of `TaiwanStockBalanceSheet` differs
from the tree in 7,326 company-periods from 2013 Q1. `repair/fin_bs_vintage.py`
graded each against the balance sheet the company filed on MOPS and wrote the
revision only where the filing agrees with every revised amount.
**How much.** The filing sides with the tree in 3,697 company-periods and with
the revision in 3,498, which now hold the revision's values (31,514 rows
changed, 7 added, 2,875 kept where the revision carries no row). 32 agree with
neither vintage and 99 could not be graded. `fin_is/`, `fin_cf/` and `fin_bs/`
before 2013 Q1 hold the values they were pulled with.
**Pinned by.** `test_taiwan_fin_bs_revision_follows_the_filing`;
`records/fin_bs_vintage.parquet` and `fin_bs_vintage_grade.parquet` carry every
value compared.
**For a study.** A vendor revision is not a correction; where a figure matters,
the grade file says which side the filing took.

## 14. Some company-periods come from the date-keyed query

**What.** FinMind answers a query naming no stock from other coverage than a
query naming one. `repair/date_keyed_fill.py` added every company-period a
date-keyed pull carries and the tree lacked, for universe names in the window.
**How much.** 199 rows to `fin_is/` for 6 names and 467 to `fin_cf/` for 15,
all in the empty files of in-window delistings the per-stock query returns
nothing for; 7 to `fin_bs/`; 3,483 company-months to `month_rev/` for 719 names,
of which 1,454 are not served per stock and 1,409 were added by the vendor
after the tree was pulled. A company-period the tree held kept its rows.
**Pinned by.** `test_taiwan_date_keyed_fill_is_in_the_trees`;
`records/date_keyed_fill/` holds every added row.
**For a study.** Nothing; the trees carry the rows. A fresh per-stock clone
lacks them.

## 15. Some rows of the daily trees come from a second whole pull

**What.** `download.py --extend` asks a file only for what follows its last row,
so a row the vendor publishes earlier never reaches the tree. The six daily
trees were pulled again whole on 2026-09-13 and `repair/repull_fill.py` added
what the pull carries under a key the tree held no row of.
**How much.** 111,056 rows to `instflow/` for 805 names (105,528 of them before
the file's first row: the vendor now serves flows from years earlier), 8,399 to
`per_pbr/` on the make-up Saturdays, 682 to `margin_short/`, 4 to `ohlcv/`. The
re-pull carried no row for 56,727 stock-dates the trees hold; those rows stay,
and `records/repull_fill/unserved.parquet` lists them.
**Pinned by.** `test_taiwan_repull_fill_is_in_the_trees`.
**For a study.** Nothing; the trees carry the rows. The next such fill is
`repair/fill_from_vintage.py`, which reads `raw/<vintage>/` instead of a
per-stock snapshot.

## 16. `margin_short`'s short-sale flows were crossed in the first pull

**What.** `ShortSaleBuy` and `ShortSaleSell` were served exchanged on every row
the 2026-04-27 build wrote, which the row's own balance identity shows:
`ShortSaleTodayBalance == ShortSaleYesterdayBalance + ShortSaleSell −
ShortSaleBuy − ShortSaleCashRepayment`. `repair/short_sale_repair.py` exchanged
them back.
**How much.** 761,472 of 5,748,771 in-window rows in 750 names, 2011-2024; the
2026-09-13 re-pull serves all of them exchanged and contradicts no balance.
**Pinned by.** `test_taiwan_short_sale_flows_match_the_balances`,
`test_taiwan_short_sale_series_has_no_regime_gap`;
`records/short_sale_repair.parquet` keeps every row as the tree held it.
**For a study.** A short-sale figure read before 2026-09-13 measured the
volume bought back.

## 17. The make-up Saturdays were missing, and their counts were stale

**What.** The trees had no row for 1,941 sessions the vendor serves, 1,940 of
them on 14 補行交易日 Saturdays, so the return after each one spanned two
sessions; and on 12 of those Saturdays `ohlcv/` held a volume the vendor has
since raised. `repair/backfill_make_up_sessions.py` read the rows back from the
date-keyed endpoint and `repair/volume_repair.py` wrote the current counts over
the stale ones.
**How much.** 1,941 rows in 507 stocks added; 5,925 rows in 745 stocks
recounted, short by a median 0.42 % of volume and 99.5 % at worst. `price_adj/`
takes its three count columns from `ohlcv/`.
**Pinned by.** `test_taiwan_no_session_the_tape_holds_is_missing`,
`test_taiwan_volume_repair_matches_the_tape`; `records/volume_repair.parquet`
keeps every replaced count.
**For a study.** Nothing now; `ohlcv/` matches the tape on every in-window row
it holds. `ADJUSTED_PRICES.md` counts the make-up sessions the adjusted tree
still lacks.
