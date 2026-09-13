# Investigation notes

Dated records of how a correction or a caveat was found, moved here from
`README.md` on 2026-09-13 so the reference documents describe the package as
it stands. Each note says what was believed, what showed it wrong, and what
changed. The state the notes led to is in `README.md`, `CAVEATS.md`,
`ADJUSTED_PRICES.md` and `delisting/README.md`; the commit log carries the
same record per change.

## The window

The window was originally 2015-01-01 → 2024-12-31; on 2026-04-27 the start
was rolled back to 2005-01-01 for a 20-year span, and on 2026-08-17 the
answerable range was cut to 2011-01-25 for the reason above. The far end moved
to 2026-09-09 on 2026-09-10, when `collect/download.py --extend` topped every tree up to
the vendor's last published session: it is where the download reached, not a
period anything here reports on.

## The universe

### The overlay gate was never evidence for its own premise

The re-add used to be gated at `date < 2015-01-01`, on the premise that the
live endpoint keeps every name that delisted from 2015 on. It does not, and
the gate could not have caught that: the delisting table it was checked
against held 315 rows and simply did not know about the names that would
have falsified it. The 2026-08-17 refresh brings the table to 723, and 46 of
the names it adds delisted in 2015 or later with no row in the live endpoint
at all — so the universe was survivorship-biased across 2015-2020, not only
before 2015 as the gate assumed.

The gate is now the window itself, and the test of whether a name needs
re-adding is the one the date was standing in for: whether the endpoint
still serves the company. Company rather than code, because a 6-digit code
can be reissued after its first occupant delists, and the endpoint answers
for the successor — testing the code would report the predecessor as still
listed and drop it from the overlay.

A 4-digit code is not by itself a common stock, either: Taiwan numbers its
ETFs `00xx` and its depositary receipts `91xx`, and the refreshed table puts
11 of them inside the window. The overlay drops both blocks by code. An
instrument-type screen cannot do this, because it reads the type from the
endpoint, which no longer serves the companies the overlay re-adds. The
endpoint has no row for 0015, a `00xx` code that trades on the tape until
2014-02-18. The delisting table lacks 0015 too. Nothing else kept 0015 out of
the overlay. `test_taiwan_universe_excludes_the_instruments_it_claims_to`
checks the code of every row, the 57 overlay rows included.

### The exclusions ran against rows, and admitted 33 names

`taiwan_stock_info` returns one row per (market, industry) a stock has
been classified under — 835 of 2,162 four-digit TWSE/TPEx codes carry
more than one, rows still in force stamped with the query date and
retired ones with the date they were retired. Until 2026-08-17 the
filters above dropped matching *rows* and deduplicated afterwards, which
drops nothing when a stock has a second row: every Innovation Board name
also carries an ordinary industry row, so all 30 in the file survived on
it — 29 of them wrongly, and 2432 under a name and industry three years
stale, kept only because its row stands for the predecessor rather than
the Innovation Board company now holding the code. Four TDRs — 9101
福雷電, 9102 東亞科, 9104 萬宇科, 9151 旺旺 — came back by the other route,
since the overlay asked whether a code was absent from the *filtered*
table and the filter had just removed them.

The count beside this section was asserted and the criterion was not, so
2,154 stayed green while 33 of the names under it were forbidden. Both
filters now drop the stock on the evidence of any of its rows,
`derive/build_universe.py` asserts that no excluded instrument survived, and
`test_taiwan_universe_excludes_the_instruments_it_claims_to` checks the
criterion rather than the total.

Six of the 29 have since transferred to the ordinary board and are
excluded here too: the earliest retired Innovation Board classification
is stamped 2024-11-25, so each was on the relaxed-disclosure tier until at
least then — all but the last five weeks of the window as it stood when the
exclusion was decided. The rule excludes a code on any row carrying the
classification, so all six stay out for the whole window, including the
sessions after their transfer that the 2026-09-10 extension added.

Two things this correction did not do. Per-stock files under
`ohlcv/`, `price_adj/` and the rest still exist for the 33 removed
names and are simply unread — no download was rerun. And the rest of
the file is the 2026-04-27 snapshot: 675 of the retained rows still
carry the industry the endpoint listed first rather than the one in
force, which only a full rebuild refreshes.

### How the point-in-time universe was perturbed

**The two are not interchangeable, and the split is measured rather than
tidy.** Breaking the artifact six ways: dropping a suspension bridge, holding a
delisted name one session past its exit, deleting one outright, and losing a
session from the calendar all fail the first check, three of them naming the
company. Re-admitting a 興櫃 name across the whole window fails it too — but only
because the size pins sit on the first and last session and a full-window span
moves both. **Admit the same name for the middle of the window only and the
first check passes**; nothing in it reads a market classification. The
reconciliation catches it and nothing else does. So a clone without `tape/` can
verify that no delisted name is missing, and cannot verify that no 興櫃 name is
present.

**The tape is swept one file per year, and a year written short is the one way
it goes wrong quietly.** `sweep()` used to skip a year whose file existed,
which is right while every year inside coverage is whole and wrong the moment
coverage ends inside one: the file holds January to the coverage end, the next
sweep skips it, and the rest of that year never reaches
`trading_sessions.parquet`. `universe_at` then raises on a session the market
held. The skip now reads how far the file reaches rather than that it is there,
and `test_taiwan_tape_years_are_whole` fails on one already written that way —
the gap is the calendar ending early, which no continuity check can tell from
coverage ending early.

## The first dated vintage

The date-keyed sweep of 2026-09-13 (`collect/sweep.py`, `raw/2026-09-13/`)
was the first reading of the whole market that did not go through the
universe. A dry run of `repair/fill_from_vintage.py` against it, on the years
the sweep had finished by 20:50 that day, found the trees complete: for
`ohlcv/` over 2011-2015 the vintage carried no row the trees lacked, and the
trees carried 1,134 stock-dates it did not, the post-delisting 興櫃 quotes of
1107, 2341, 2381 and 2396 (CAVEATS.md 15). For `cap_red` the vintage lacked
three filings the committed table holds, 2327's 2022-10-21, 3018's 2023-11-11
and 6109's 2020-09-25, the duplicate filings `derive/adjust.py` already drops;
the vendor has withdrawn them since the table was pulled. The repairs of
2026-09-10..13 had therefore brought the per-stock trees to what the date-keyed
endpoint serves, for the span checked.
