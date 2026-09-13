# Adjusted prices

The total-return adjusted close: FinMind's `TaiwanStockPriceAdj` as served,
the 54 stocks it does not serve rebuilt from the exchange's reference prices,
its one wrong event patched, and every row marked with where its factor came
from. `README.md` § "Adjusted prices" is the short form; this file is the
methodology and the measurements behind it.

`ohlcv/close` is raw, so any return spanning a 除權息 or 減資 session
carries the full reference-price step. The back-adjusted series is
`price_adj/` — FinMind's `TaiwanStockPriceAdj`, bought at the sponsor
tier — and `derive/adjusted_loader.py` joins it onto the raw series, fills the
54 stocks it does not serve, and replaces its step on the one event where
it disagrees with the exchange in size rather than in a cent:

```python
from finmind_data.derive.adjusted_loader import load_adjusted

df = load_adjusted("2330")   # raw OHLCV + tr_factor / adj_close_tr
                             #   + adj_source / adj_method / is_valid
```

**A study names its own period.** `load_adjusted` and `window.clip` take
`start` and `end`. Without them they return the package's coverage, and a
figure quoted on that inherits whatever this package currently answers for
instead of a period the study chose. The span is a property of the numbers
rather than a filter on them — the factor anchors on the span's last priced
session, and a series break is measured inside it — so the same stock read
over two spans returns two sets of adjusted prices, correct on both.

```python
df = load_adjusted("2330", start="2011-01-25", end="2024-12-31")
```

`test_taiwan_loader_takes_the_callers_span` keeps that argument load-bearing.
It cuts one stock's frame the session before a 除權息 event and requires the
whole shared stretch to rescale by a single constant, which is 1.0 exactly
when the span was accepted and then dropped — the failure an argument that
only filtered the output would not show.

**One convention, and it is total return.** Cash dividends come out
along with 無償配股, 現增 and 減資, so `adj_close_tr` measures what a
holder earned, not what the price did. There is no price-return variant
of the endpoint at any tier, and the exchange makes one hard to build:
TWSE/TPEx publish a single fused reference price per 除權息 event
covering cash and shares together, so recovering the price-only half
means splitting that number event by event. A study that needs the
price alone has no source here.

The factor is the primary output — any other price column adjusts the
same way (`adj_open_tr = open * tr_factor`) — and it is re-anchored to
1.0 on the last covered session, so the adjusted close there is the raw
close. The vendor anchors its own series to the latest session in
FinMind's database, which moves on every re-download; re-anchoring is
what makes a repeated download reproduce the same numbers rather than
merely the same returns. It does so only where the vendor's steps did
not change between the two downloads. **What the vendor computes** counts
the steps the last re-pull moved.

**What the vendor computes**, and where it is wrong. Each 除權息 event
should contribute the exchange's own `before_price / after_price`, and
`derive/vendor_event_audit.py` grades all 21,418 filed events against it —
21,224 of them sit between two adjacent covered sessions and can be
read. Both numbers come out of the same file and neither is a filter
that moved: `checkable` is the column that separates them, and the 194
it excludes are 174 events in the stocks the vendor serves nothing for,
19 whose bracketing sessions sit more than ten days apart, and 3454's
non-positive row. Every
*rate* below is over the 21,224; every count of what was filed is over
the 21,418. The step matches to 1e-6 on 81.4 % and to 1e-3 on 99.6 % (p99
7.0e-4, max 3.0e-2). The residual is FinMind reaching the same number a
different way: it subtracts the *declared* distribution from the prior
close instead of reading the reference price, and the two land a whole
cent apart in the per-share amount. 3006's 2011-07-04 event is typical —
the exchange repriced 38.65 → 37.64 (息值 1.01) and the vendor removed
1.00. That difference is bounded per event, does not accumulate, and
lives only on the ex-date session.

Which of the two numbers an event carries can change between pulls. The
re-pull of 2026-09-12 moved the vendor's step on 749 events in 165 stocks, by
at most 6.3e-4. 664 of the moved steps now equal the declared distribution to
1e-6. None of the 664 did in the tree the re-pull replaced. That tree matched
the exchange to 1e-6 on 83.7 % of events. 155 of the 165 stocks had an event
filed after 2026-08-18.

One event is not a cent apart but wrong, and `adjusted_loader` replaces
the vendor's step with the exchange's on it. It is filed twice, so it
carries two defect labels:

| defect | n | what it is |
|---|---|---|
| `malformed_twin` | 1 | the real leg of 3454 on 2011-07-27, 84.20 → 79.07. The vendor removed 7.42 = 5.12 + 2.30, reading both filings as one distribution |
| `nonpositive_leg` | 1 | the other filing of the same event, reading before 0.00 / after −2.30 — not gradable itself, and the reason the first leg is wrong |

The patch moves the ex-date factor by 2.98 %, taking that session's
adjusted return from +4.19 % to +1.19 %. The defect is found by *shape* —
a date carrying a non-positive reference leg — so a re-download is graded
rather than matched against a list of stock ids.

**A second defect class exists and the window holds none of it.** A
現金增資 subscribed **above** the market raises the reference price, and on
six such events the vendor scaled the history the other way — `sign_flip`
in the audit's vocabulary. All six are dated between 2005-04-21 and
2008-09-16, which is before this package answers for anything, so the
class is a fact about the vendor rather than a rate in the panel: the
window's 16 upward reprices, 2011-08-09 through 2026-06-11, all carry the
exchange's own direction and none is flagged. Two consequences for
anyone extending the coverage backwards: a search for more of these can
be confined to pre-2009, and a defect rate measured on a 2005-2007
delisting sample cannot be extrapolated to the panel, because that sample
would sit entirely inside the defective era.

`vendor_event_audit.parquet` is the fixed record of all of this, one row
per filed event. A step found later at a `vendor`/`rebuilt` boundary is
answered by that file rather than re-derived from scratch;
`test_assertions.py` regenerates it and fails if the committed copy has
drifted.

**Two columns say which rows to trust**, and both need filtering, not
reading past:

```python
df = load_adjusted("2330")
df = df[df["is_valid"] & df["adj_close_tr"].notna()]   # then take returns
```

`is_valid` is "this row is a position a study could have held", and it
fails three ways. Two are the ends of the series: behind the last break
— a share cancellation no filing priced, or a multi-year trading gap
after which the ticker came back as a different listing (53 breaks in 51
stocks, 24,743 rows, 0.37 % of the panel) — and past the delisting date,
the 1,134 quotes in the four delisted names below. The third is one
session anywhere between them: the stock did not trade (133,590 rows in
1,200 stocks), so no level the panel carries was a price anyone could
transact at.

`invalid_reason` says which, because the flag is one column and the four
are not the same problem: `unpriced_cancellation` means a step is
missing from the chain, `series_break` means the rows behind belong to
another company, `post_delisting_emerging` means the price is right and
the exchange had ended the listing before it, `no_trade` means there was
nothing to buy. None of them means "this price is wrong". The vendor
marks none of them: 8101 stopped trading 2024-08-21 at 1.90, cancelled
80 % of its shares over a 90-day suspension no filing prices, and came
back on 2024-11-19 at 10.45 — and the vendor's series carries both
numbers at a factor step of exactly 1, leaving a +450 % return across the
gap (CAVEATS.md 5).

The two segment reasons win where they overlap the third, so the 2,793
no-trade sessions a segment claims keep the segment's name — a row in a
history this series does not continue, or one printed after the listing
ended, would not have been holdable had it traded either. `adj_close_tr` was already NaN on all 136,383, so
the two-column filter above dropped them before this reason existed;
what changed is that `is_valid` alone now drops them too, and that every
False row in the panel's 6,676,907 carries a reason for being one.

**`adj_source` says where the row's factor came from**, and `adj_method`
which convention produced its ex-date steps. Split a panel on them
before comparing anything across the boundary:

| `adj_source` | `adj_method` | rows |
|---|---|---|
| `vendor` | `declared_dividend` | FinMind's series as served |
| `vendor_patched` | `declared_dividend` | behind the one replaced event (120 rows) |
| `vendor_carried` | `declared_dividend` | the first traded session, where the vendor series starts late or serves it at the raw close — factor carried from the adjacent session (616: 497 sessions ahead of the vendor series, the Saturday make-up session right after it in four of those stocks, and 115 first sessions the vendor serves unadjusted) |
| `rebuilt_factored` | `exchange_reference` | 37 of the 54 holes, with a factor chain (50,064 rows) |
| `rebuilt_noevent` | `none` | 17 of the 54, no corporate action in window — factor is 1.0 (11,441 rows) |
| `""` | `""` | no price: the stock did not trade, or nothing covers the session |

`vendor_patched` is a **span, not a session**. A factor anchored at the
present carries every step in the rows behind it, so replacing one
rescales that stock's history from the ex date back to its first
session: 3454's 2011-07-27 event carries the 120 sessions behind it, back
to the first one in the window. Flagging only the ex date would say one
session differs from FinMind's series when the whole span does.

The two rebuilt values are kept apart on purpose: the cumulative-product
path is the one with somewhere to go wrong, and separating it lets a
later check isolate it without re-deriving which stocks had events.

**There is no `raw_covered` column any more.** It used to say whether `ohlcv/`
served the date, and was False on 303 rows — the make-up sessions the raw tree
had no row for, reconstructed from the adjusted series, whose prices and volumes
were derived rather than read. `repair/backfill_make_up_sessions.py` has since read all
1,941 missing sessions back from the endpoint that serves them, and the loader
now *refuses* to derive one rather than deriving it and flagging it, so the
column could no longer take its False value under any input. A boolean that
cannot vary is not provenance; the guard that raises is, and the flag was
dropped rather than kept as a constant nothing reads.

`adj_close_tr` is NaN where the raw `close` is 0 — FinMind's encoding
for a session the stock did not trade (**136,383 rows, 2.04 %, in 1,208
stocks**, and the same figure in `ohlcv/` as in the panel: the 93-row
difference the two used to show was the no-trade sessions the loader
reconstructed, and the raw tree now holds them). The vendor prices
133,956 of the ones `ohlcv/` holds anyway, at the last traded price, so
the zero that identifies them survives only in `ohlcv/`; filtering on
`adj_close_tr > 0` alone would keep every one of them, and so would
filtering on `is_valid` alone before `no_trade` existed.

## The vendor's survivorship hole, and the rebuild that fills it

`price_adj/` reaches 6,477,647 of the 6,540,524 traded sessions in
`ohlcv/` — 99.04 % — and the 62,877 it misses are not missing at
random. They split five ways: **61,505** in the 54 stocks with no adjusted
series at all, **0** past the end of a vendor series that stopped at a
delisting, **498** sessions ahead of the vendor's first,
**872** make-up sessions the raw endpoint serves and the adjusted product
does not, and **2** weekdays inside a live series the adjusted endpoint is
simply short of — 3064 on 2026-08-26 and 6236 on 2026-08-12, each a lone
traded day inside a suspension, and each served short when the endpoint is
asked for the stretch directly. The panel marks both `adj_covered=False`.
Only the first is a bias.

**50 of the 179 in-window universe delistings have raw prices
and no adjusted series at all** (60,371 sessions). They delisted
between 2012 and 2020, scattered rather than banked against either edge
of the window, which is the shape the 2026-08-17 delisting refresh
exposed: the hole was read as a pre-2015 artifact only because the
vendor's own table did not yet know about the later names. They are 50
of the 57 names `derive/build_universe.py` carries as its survivorship overlay
— added precisely because FinMind's live `taiwan_stock_info` had dropped
them — and `TaiwanStockPriceAdj` drops them on the same registry.

Four more names sit in the same hole without being in-window exits.
1107, 2341, 2381 and 2396 delisted between 2007 and 2010 and went on
being quoted on 興櫃 into the window; the vendor's series for each ends
at its delisting, which is before `COVERAGE_START`, so inside the window
they have raw prices and no adjusted row to carry a factor from. That
makes them a hole rather than the ragged end of a covered series, and
the rebuild takes them on the same path as the 50: 54 stocks, 61,505
traded sessions in all.

92 downloaded adjusted files are empty inside the window: the 54 above,
and 38 that have no raw prices in it either — 37 delisted before it opens,
and one is a zero-row file. Quoting the 99.98 % these same files give once the
54 leave the denominator reports the coverage of a panel the bias has already
been removed from — the vendor's coverage is 99.04 %, and `available_stocks()`
lists the 2,140 names it serves.

`load_adjusted` fills all 54 rather than returning a column of NaN a
panel build would drop. `derive/adjust.py` rebuilds the factor from the
exchange's own per-event reference prices — `div_result/` and
`capital_reduction.parquet`, never `price_adj/` — which is why the hole
is recoverable at all: the reference prices are published per event and
do not depend on the registry that dropped the names. All 54 come back
priced across all 61,505 traded sessions, 37 with a factor chain and 17
with no corporate action in window at all. That last figure is checked
against two sources the factor path never reads: none of the 17 has a
declaration in `dividend/` or a row in `exright_reference.parquet`,
either — a distribution with no reference price behind it would leave the
factor flat across an event that happened, and `div_result/` and
`capital_reduction.parquet` are the two chains that decided it was flat
in the first place.

**The rebuild is validated where the vendor exists.** The gate set is
the 131 in-window delistings `price_adj/` *does* cover — same era, same
delisting situation — run through the identical code path. Across
247,422 daily adjusted returns the rebuild reproduces the vendor on
99.952 % to 1e-6 and 99.994 % to 1e-3; what is left is the declared-vs-
published cent above, on the ex-date session only. All 15 returns past 1e-3
fall on a 除權息 date, and 11 of them are two financials that delisted in
2025-2026 with long, low-priced dividend histories, where one cent is a
larger share of the price.

`adj_covered` stays False across all 54 even though they now carry a
price, so the vendor's hole remains countable after it is filled — as a
column rather than frame metadata, because `DataFrame.attrs` survives
`pd.concat` only when every frame agrees. A panel of uniformly covered
stocks would keep an `adj_coverage` nobody needs, and one mixing covered
with uncovered stocks drops it silently; `merge` and `groupby` drop it
always. The warning would go missing in exactly the case it exists to
raise, so `df.attrs` is single-stock only.

Five of the 54 carry invalid traded sessions, and none of it is a defect
of the rebuild. Four are the pre-window exits above, invalid end to end
under `post_delisting_emerging` because every in-window session they have
is past their delisting date. The fifth is a break: code 4415's first
occupant traded 2005-01-03 to 2011-11-07, 台原藥 took the code over after
a 1,249-day gap and delisted 2019-12-16, and the earlier company's 192
in-window traded sessions come back `is_valid=False` with
`invalid_reason == "series_break"` rather than NaN, because they are
ordinary prices of a different issuer rather than unrecoverable ones —
and NaN could not have said which.

The share cancellations that used to claim sessions here reach nothing
now: 970 rows across 1207, 1462, 2544 and 2811, all four delisted between
2005 and 2007, so the 2011-01-25 window start drops them and the
survivorship overlay reinstates in-window delistings only — none is in
`universe.parquet` either. The behaviour is unchanged; the population
moved.

## The edge of the vendor series, and the edge that left with the window

The other 616 carried sessions are not whole stocks but one end of a
series the vendor serves. 496 stocks are short 498 traded sessions ahead of
the vendor's first — one each, and two in the two stocks whose listing-day
Saturday the re-pull fill put in front of one (CAVEATS.md 15). 497 of them are
carried and 4141's is refused, below. In four of those stocks the series opens
on a Friday and the Saturday make-up session after it is missing too; the carry
covers both. The remaining 115 are first sessions the vendor serves at the raw
close, described under "One pull per adjusted file".

The window has **one** edge, not two. A vendor series that stops at a
delisting while `ohlcv/` keeps printing used to be the other, and inside
2011-01-25..2026-09-09 no such stretch exists: every name it applied to
delisted before the window opens, so the vendor covers none of its
in-window sessions and there is no adjacent covered factor to carry.
Those names are the four in the hole above, filled by the rebuild rather
than by a carry. The edge did not disappear because the vendor changed;
it stopped being an edge because the window no longer contains a covered
session next to it.

The head is filled, and it is not a splice. A back-adjustment factor
moves only on an ex date, so across a gap with no filing in it the
adjacent covered session's factor *is* the missing one — the same
number, not an interpolation, and the level is continuous by
construction. The condition is checked per row against every filed 除權息
and 減資 plus the share cancellations no filing explains, and a row whose
gap holds one is left NaN. It refuses exactly one: 4141's first print
sits 376 days before the vendor's first session, with a cancellation on
that session. Those rows are `adj_source == "vendor_carried"`.

What the head fill recovers is **493 first returns**, not 493 prices.
The price was never the loss — the session-1-to-session-2 return was,
and in a listing study that is the observation.

The quoted tails are still in the panel; they are rebuilt rather than
carried, and what they recover is evidence, not tradable history. 興櫃 is
a negotiated market: `open` is the previous session's average rather than
a trade, a quote depends on a recommending broker standing behind it, and
median volume across the four names runs at 3.0-49 % of each one's own
listed-era median. So those rows carry `is_valid=False` under
`invalid_reason == "post_delisting_emerging"`, which keeps a backtest out
of them automatically — 1,134 in-window sessions, and the flag reaches
nothing else. What they are good for is the **terminal value**: where a
delisted name converges over the months after it leaves the exchange is
a market observation, and the last exchange close is not one. A name
that left by merger does not go to 興櫃 at all, so the presence of a
tail is itself a weak signal on the delisting reason (CAVEATS.md 8).

And `ohlcv/` itself is a zero-row file for one stock while 37 more hold
prices only outside the window; `load_adjusted` raises on all 38.

## The gap that runs the other way, and the 1,941 returns it cost

Every figure above counts sessions `ohlcv/` has and `price_adj/` does not. The
reverse difference used to be quoted as **303 sessions in 96 stocks** on 14
Saturdays, each a 補行交易日 worked to make up a holiday. That number is a set
difference between two local trees, so it can only see a session at least one
of them holds, and it was read as the size of the hole rather than as the part
of it the other tree could still reach.

`collect/tape_universe.py` measures the same hole against the vendor instead — one
date-keyed request per session, so the reference is what the endpoint serves
rather than what either tree stored. The hole is **1,941 rows in 507 stocks**,
on 15 dates: the same 14 Saturdays, carrying 1,940 of the rows, and a single
no-trade row for 2910 on an ordinary Wednesday, 2021-01-20. Of them **303 had a
`price_adj/` row** — exactly the set the loader could reconstruct, which is why
the count reproduced — and **1,638 were in neither tree**, so nothing reported
them and no flag marked them.

**The cost is not the missing rows.** A gap in the calendar makes the *next*
session's return span two sessions rather than one, so the 1,940 absent
Saturdays were 1,940 overstated returns, clustered on 14 holiday-adjacent dates
rather than scattered, which is the shape a study reads as an effect. The coverage
decomposition above cannot see it: it counts rows, and the damage is in the
gaps between them.

**The endpoint serves them, so the trees were behind a backfill.** A `data_id`
request for 1338 on 2012-02-04 returns the row `ohlcv/1338.parquet` lacked;
the same holds for every one checked. That is the behaviour
`TaiwanStockDelisting` showed between the 315-row and 723-row pulls — the
vendor fills history in after the fact, and a tree downloaded once does not
follow. `repair/backfill_make_up_sessions.py` reads the 15 dates back and inserts
them, 1,311 traded sessions and 630 zero-volume rows, and the insert is
additive: 507 files, 1,941 rows added, not one pre-existing row altered.

The recovered rows are the vendor's own, not a reconstruction. `spread` is
present on all 1,941 where the arithmetic recovery left it NaN, and the volume
is the raw endpoint's answer.

**What the repair costs, stated plainly.** Of the 1,941 restored rows, only
**303 had an adjusted counterpart** when they were restored — 210 traded and 93
no-trade, exactly the set the loader used to reconstruct. The other 1,638 were
sessions the vendor's *adjusted* product did not cover then, so they entered
the panel with `adj_close_tr` NaN and `adj_covered` False: **1,101 of them
traded** (1,067 in universe names) and 537 did not. That is a real change in
what a study meets. Before the repair those sessions were absent, so a return
computed across one of them silently spanned two sessions and looked like an
ordinary observation; after it, the same span is an explicit NaN. The raw
calendar is now correct and the adjusted series is now visibly incomplete where
the vendor is, which is the trade this makes: one silently wrong return
exchanged for two missing ones. The re-pull under "One pull per adjusted file"
has since brought 237 make-up-session rows into `price_adj/`. "Why the adjusted
tree was not repaired the same way" counts the sessions it still lacks.

**The reconstruction is retired and a guard stands where it was.**
`_recover_make_up_sessions` is now `_require_raw_covers_vendor`, which raises
instead of deriving a row: the trees fell behind a vendor backfill once and
nothing in the package noticed, so the answer to it happening again is to stop
and repair the tree, not to paper over the gap on every load. It is the cheap
per-load half of the check — it sees only what `price_adj/` exposes, and the
1,638 rows neither tree held were invisible to it by construction. The full
measurement is `test_taiwan_no_session_the_tape_holds_is_missing`, which pins
the condition from both directions against the tape: no session the tape holds
is absent from the interior of a raw series, across 6,710,863 vendor-served
ticker-days, and `price_adj/` carries none `ohlcv/` lacks.

### Why the adjusted tree was not repaired the same way

A raw print carries no factor. A back-adjusted close is anchored at the
present, so a row fetched today carries every event since the file was written
and a row already in the file does not. Measured across four dates the trees
already cover, `ohlcv/` reproduces the endpoint **exactly** on every one of
~1,500 closes, while `price_adj/` differs on **38 stocks by up to 32 %** —
re-anchorings, not errors, and inserting one into a file at the older anchor
would splice two vintages inside a single series.

So the adjusted insert is gated per stock against the dates its file already
holds, and it refused **44 rows in 12 stocks** — 1597, 2066, 2496, 3147, 4162,
4432, 5206, 5222, 6432, 6574, 6691, 8077 — whose committed values disagreed
with the endpoint. Those needed the whole file re-downloaded rather than a row
added. The re-pull under "One pull per adjusted file" brought in all 44, and
193 more make-up-session rows in 52 stocks: 237 rows, 161 of them traded.

Inside a universe name's `price_adj/` series the tape holds 1,384 sessions the
file does not: 1,368 on the 14 Saturdays and 16 on weekdays. The file is the
per-stock endpoint's whole answer, so the endpoint does not serve them for that
stock. The 501 rows before a file's first session are the documented
`vendor_carried` edge.

### The Saturday rows `ohlcv/` already held carried an older count

On 12 of the 14 Saturdays, `ohlcv/` held a count the vendor has since raised.
Against the tape, `ohlcv/`'s volume and value fell short on 5,925 rows in 745
stocks, all on those 12 Saturdays. Every other in-window row the tape holds
matched on both. The median row was short by 0.42 % of its volume, and the
worst by 99.5 %. The per-stock endpoint `ohlcv/` was downloaded from serves
the tape's count too: the re-pull under README "Provenance" matches the tape on every
Saturday row of its sample.

`repair/volume_repair.py` read the 12 sessions back from the endpoint on 2026-09-11
and wrote its volume, value and trade count over the 5,925 rows. It stops on a
row whose price differs from the endpoint's. No row did. `price_adj/` held the
same first count on 3,982 of the rows, and a lower count than `ohlcv/`'s on
3713's 2020-02-27. The repair set its three count columns to `ohlcv/`'s on
those 3,983 rows: only its prices are adjusted. `volume_repair.parquet` keeps
every value the repair replaced. `ohlcv/` now matches the tape on every
in-window row the tape holds.

The whole re-pull of `price_adj/` on 2026-09-12 brought the adjusted
endpoint's counts back. They fell short of `ohlcv/`'s on 3,300 rows in 440
stocks: 3,299 on the 12 Saturdays, and 3713's 2020-02-27. `volume_repair
--adjusted-only` set them to `ohlcv/`'s again.

## One pull per adjusted file

A back-adjusted close is anchored at the day it is pulled. The factor under it
moves only on the first session at or after an event: a 除權息, 減資 or 面額變更
filing, or a share cancellation no filing explains. `collect/download.py --extend` used
to append to `price_adj/` the way it appends to the other trees. An append
leaves the rows already in a file at their old anchor, so the factor also steps
on the first appended session, where nothing was filed.

`price_adj/` was assembled that way from three pulls: 2005..2024 on 2026-08-16,
2025-01-02..2026-07-31 on 2026-08-18, and 2026-08-03 onward on 2026-09-10. The
two appends put a factor step with no event under it into 232 of the universe's
files: on 2025-01-02 in 10, and on 2026-08-03 in 222 (in 3 of them on
2026-08-04, the first session they traded). 231 of the 232 steps equal the
inverse product of the exchange's steps for the events filed between the two
pulls. 4747's step, exactly 0.5, has no filing in the event tables.
`load_adjusted` passed each step through as a one-day return: median −3.2 %,
and beyond ±10 % in 24 stocks, from −66.5 % to +61.7 %. `vendor_event_audit`
graded every event and passed, because on an event's own session both sides of
the step sit at the later anchor.

All 2,159 universe files were re-pulled whole on 2026-09-12. `collect/download.py
--extend` now re-pulls a back-adjusted file whole instead of appending to it.
The 72 files outside the universe were never appended to: none holds a row
after 2024-12-31.

`test_taiwan_adjusted_factor_moves_only_on_events` reads every factor step in
the universe's files. It finds 22,017. Every one sits on an event's first
session except the step into a series' second session, in 116 files. In 115 of
those the vendor serves the first row at its own anchor, so its adjusted close
is the raw close. Kept, the step would be the second session's return: negative
in all 115, median −5.6 %, beyond −10 % in 23, and −90.6 % on 7780.
`load_adjusted` drops the first row's factor and carries the second session's
onto it, under the guard the edge carry uses. The row is then `vendor_carried`,
and `adj_covered` stays True because the vendor did serve it.
`test_taiwan_unadjusted_first_sessions_are_carried` holds the 115 sessions the
trees show against the 115 the loader carries.
