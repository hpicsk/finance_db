# Taiwanese adjusted prices — how we know they are right

An adjusted price series is **unfalsifiable by inspection**. A series that
half-removes an ex-dividend drop, removes it a day late, or removes it twice
plots as the same smooth line as a correct one. Nothing about the output says
which you are holding.

So every check below exists to answer one question: *what would have broken if
this were wrong?*

The Korean series answers the same questions against different authorities, and
the asymmetry between the two is worth reading as a pair —
[`kr_marcap/VERIFICATION.md`](../kr_marcap/VERIFICATION.md), with the
side-by-side summary in the [repo README](../README.md#adjusted-price-series--korea-vs-taiwan).

## How Taiwan is put together

| | |
|---|---|
| **Structural adjustment** | Exchange 除權息 / 減資 reference prices (`div_result`, `cap_red`) |
| **Cash-dividend layer** | Already inside the exchange factor (`after_price` nets the cash out) |
| **Exchange publishes a total-return factor?** | **Yes** — `after_price/before_price` covers cash *and* rights |
| **Price-return series** | `adj_close_pr` — derived by splitting the fused factor (§6) |
| **Total-return series** | `adj_close_tr` — free, it *is* `after_price/before_price` |
| **Builder** | `finmind_data.adjust.load_adjusted` |

TWSE/TPEx publish **one fused reference price** per 除權息 event covering cash,
無償配股 and 現增 together, so Taiwan's `adj_close_tr` is free and `adj_close_pr`
is the derived one — the opposite of Korea, where KRX publishes a
structural-only factor and the total-return series is the one that has to be
built.

The series does not end at zero, and should not. Affected sessions are marked
with `is_ex_date` and `is_cap_red` instead.

Deriving the price-return series does **not** go through the TWSE formula, which
reproduces the published `after_price` for only 77.8 % of mixed events because
the declared 配股率 omits 員工配股 and 董監酬勞 dilution. It goes through the
event *label* instead. `stock_or_cache_dividend` marks each event 息, 權 or 權息,
and that settles 79.8 % of events with no arithmetic at all — a cash-only event
has no structural step, a stock-only event is all structural. Only the mixed
20.2 % need the split, and there `pr_step = step × (1 − D/before)` needs the cash
dividend alone. See §6. Where `D` was never declared, TWSE's own 息值 supplies
it — the two agree to 1e-6 on 97.1 % of the events where both speak (§8).

There is no Taiwanese counterpart to the Korean check against a paid vendor
series: `TaiwanStockPriceAdj` is gated above this account's tier, so the rows
below are the strongest available evidence here.

---

## 1. Is the input actually raw?

Adjusting an already-adjusted series double-counts, and the failure is silent.
This has to be settled before anything else.

The exchange publishes the official pre-event close (`before_price`) for every
除權息 event. Compared against our stored prior close:

| window | n | `1e-6` (exact) | `1e-2` (published precision) |
|---|---:|---:|---:|
| 2020–2024 | 7,441 | **99.87 %** | **99.87 %** |
| 2005–2024 | 22,105 | **99.81 %** | **99.81 %** |

One comparison settles three things at once — our closes are raw, the event
dates align, and the ticker join is right. Any one of those being wrong
collapses the agreement rate.

Both tolerances are reported because neither is a pass mark. `before_price` is
published to two decimals, so `1e-2` is "identical at the exchange's own
precision" and `1e-6` is "bit-identical"; quoting only the looser one would let
a tuned threshold pass for a result.

This **contradicts what `README.md` used to claim** (that FinMind closes reflect
capital reductions and splits). They do not. The README is corrected;
`TaiwanStockPriceAdj` is a separate dataset, gated above our `register` tier and
never downloaded.

## 2. Is the exchange factor a black box?

Reproducing a published number from its own disclosed components proves we
understand the mechanism rather than copying the output.

**Identity check.** The exchange publishes three numbers per event —
`before_price`, `after_price`, and the deducted amount. One arithmetic relation
must hold between them:

```
before_price − 차감액 == after_price
```

Exact for **8,478 of 8,478** events labelled `除息` / `除權` / `除權息`.

**Formula check.** Independently recomputing the reference price from the
disclosed dividend components under the TWSE/TPEx rule

```
ref = (前收盤價 − 現金股利 + 現增認購價 × 現增配股率) / (1 + 無償配股率 + 現增配股率)
```

reproduces the published factor for **93.8 %** of pure cash-dividend events
(n = 15,449) at 0.005, and **99.99 %** at 2 전. The shortfall is publication
rounding — `after_price` is published to 2 decimals, which quantises the implied
factor by `0.005/before_price` (median 1.5e-4 at the median price of NT$34.30).

On mixed events the same formula reproduces only **77.8 %** even at 2 전, and
that is not rounding: the implied 配股率 exceeds the declared one in 99.65 % of
cases — one-directional, which is the signature of a missing dilution term
(員工配股, 董監酬勞), not of a bad cash figure. The price-return split in §6 is
built to need the cash figure and not the 配股率, precisely because of this.

Two units are easy to get wrong here and both were: `CashIncreaseSubscription
Rate` is **每仟股認購股數**, so the ratio is that value over 1,000, and
`StockEarningsDistribution` is quoted **per NT$10 par**, so the ratio is that
value over 10.

**Residual.** 2,580 events (11.5 %) where `stock_and_cache_dividend` is not the
price deduction. This is a semantics problem in an auxiliary column that the
pipeline never reads — the build uses `after_price/before_price` directly — so
it does not gate anything. Recorded here so it is not rediscovered as a bug.

## 3. Do two independent sources agree?

`TaiwanStockDividend` carries `CashExDividendTradingDate`, a declared ex-date
sourced from the company's 股利分派公告 rather than from the 結果表 that
`div_result` comes from. The two agree on **19,722 of 19,730** comparable events
(**99.96 %**). Of the 2,228 non-matches, 2,220 are declared dates outside that
stock's `div_result` coverage span and only **8** are genuine disagreements
inside it.

This confirms `div_result.date` is the ex-dividend *trading* date and not the
record or announcement date — but it is two disclosures rather than two
institutions, so it ranks below the Korean DART check
([`kr_marcap/VERIFICATION.md`](../kr_marcap/VERIFICATION.md) §3). The
load-bearing Taiwanese evidence stays §1: `before_price` matching the *prior*
session's close pins the date independently of any declaration.

## 4. Would a coding error survive?

Correct arithmetic can still be wrongly implemented. Two identities must hold
by construction and catch different classes of bug.

```
adj_close_tr == adj_close × tr_factor      → indexing / broadcasting errors
adj_close_tr[today] == close[today]        → normalisation / anchor errors
```

Both are exactly `0.000e+00` across **all 2,141 Taiwanese stocks with price
rows** — the identity runs over the whole universe rather than a sample, since
the factor is per-event and cheap.

**Double counting** is checked separately, because the two factor chains must be
disjoint: 減資 (627 events, `cap_red`) and 除權息 (`div_result`) share **zero**
`(stock_id, date)` pairs, so the two chains compose without overlap. Disjoint
is not the same as complete: the 減資 chain starts six years after the price
series does, which §7 covers.

## 5. Did the contamination actually go away?

The final check is the one the whole exercise is for. Measured on the rows whose
forward return spans an event, over 2020–2024:

| event | affected rows | raw | price-return | total-return |
|---|---:|---:|---:|---:|
| 除權息 (n = 7,513) | 0.340 % | −405 bp | −311 bp | **+29 bp** |
| 減資 現金 (n = 85) | 0.004 % | **+1,613 bp** | −649 bp | **+48 bp** |
| 減資 彌補虧損 (n = 126) | 0.006 % | **+11,654 bp** | −190 bp | **−190 bp** |

The price-return column is a check as much as a result — but only on the rows
where it can fail. On 除權息 it must sit strictly between raw and total-return,
since it removes the structural part of the step and keeps the cash part, and it
does, absorbing 94 of the 405 bp. On a 彌補虧損 減資 it must equal total-return to
the digit, and it does — but that row is a construction identity rather than
evidence: the build sets `pr_step = step` there, so nothing could make the two
disagree. The falsifiable form of the same question is the share-count table in
§6, which asks whether each branch recovers the right cancellation ratio from a
third endpoint.

The 現金減資 row is what that identity was hiding. Under the earlier treatment of
the endpoint as uniformly cash-free the two columns agreed by construction on
every reduction, and the combined row read −94 bp on both — a check that passed
because it could not fail. Split by reason, the cash branch reads −649 bp on `pr`
against +48 bp on `tr`, and the 697 bp between them is the refund the
price-return series had been deleting as though it were a share-count artefact.

The two event types are reported apart rather than netted, because they
contaminate in opposite directions — 除權息 removes a price drop, 減資 removes a
price *rise*. Netting them reports −197 bp for a panel whose dividend
contamination is really −405 bp.

**減資 is the larger per-event distortion by an order of magnitude** — +7,609 bp
across both reasons against −405 bp, roughly nineteen times — on a twentieth as
many events. It is worth naming separately because the unadjusted Taiwan panel
carries it in full: a capital reduction cancels shares, so the mechanical price
jump is a share-count artefact with no return content whatsoever. The bulk sits
in the loss-offset branch, which cancels roughly twice the fraction of shares a
cash refund does — a median `r` of 0.423 against 0.199.

**Nothing lands on zero, and that is correct.** Prices fall short of the full
distribution; the holder receives 100 % of the cash, so a total-return series
must add 100 %, and the difference is the real ex-day tax/clientele effect. It
is marked, not erased. The drop-off ratio itself is measured on the Korean side
([`kr_marcap/VERIFICATION.md`](../kr_marcap/VERIFICATION.md) §5) — these rows
are a different estimator answering the same question, so read that file's
[Open](../kr_marcap/VERIFICATION.md#open) before comparing the two.

---

## 6. Can the fused factor be split?

Yes, and not by the route that looks obvious. §2 shows the TWSE formula failing
on 77.8 % of mixed events, which is the reason the earlier version of this
document concluded a price-return series was not constructible in Taiwan. That
conclusion was wrong: it tested the hard route and stopped.

**The event label does most of the work.** `stock_or_cache_dividend` already
tells you what kind of event it is, and two of the three kinds need no
arithmetic at all:

| kind | n | share | structural step |
|---|---:|---:|---|
| 息 / 除息 — cash only | 15,888 | 71.0 % | none; `pr_step = 1` |
| 權 / 除權 — stock only | 1,958 | 8.8 % | all of it; `pr_step = step` |
| 權息 / 除權息 — both | 4,524 | 20.2 % | needs the split |
| 減資 彌補虧損 — loss offset, pays nothing | 351 | — | all of it; `pr_step = step` |
| 減資 現金 — refunds cash | 276 | — | needs the split |

So 79.8 % of 除權息 events, plus the 351 減資 that pay nothing, resolve from the
label alone.

**The remaining 20.2 % need one number, and it is not the 配股率.** Writing the
exchange's own relation as `after = (before − D)/(1 + r)`, the total-return step
is `before/after = (1+r)·before/(before−D)` and the structural step is just
`1+r`. Dividing one by the other:

```
pr_step = step × (1 − D / before)
```

`r` cancels. That matters, because `r` is the term the declaration gets wrong —
it omits 員工配股 and 董監酬勞 — while `D` is the term it gets right.

**`D` is verified where it can be.** It cannot be checked on the mixed events it
is used for; that is why it is needed there. It can be checked on the 15,449
cash-only events, where `r` is zero by construction and the relation collapses
to `after == before − D`, and it is the same column either way. That holds for
**99.99 %** of them at 2 전, median error exactly 0.

The mixed events then get a one-sided consistency check: the implied `1+r` must
exceed 1, since a 權 event dilutes (**99.98 %**), and must not fall below the
declared 配股率, since the declaration undercounts dilution (**99.65 %**). A
two-sided failure would have indicted `D`; a one-sided one indicts only the term
the split never reads.

**A 現金減資 needs the same split, and needs no declaration to get it.** 276 of
the 627 reductions refund cash for the shares they cancel. Treating the endpoint
as uniformly cash-free — `pr_step = step`, which is what the first version of
this build did — moved a real payment to holders into the structural chain and
deleted it from the price-return series, at a median 6.8 % of the pre-event price
per event and a compounded median 9.8 % over the 199 stocks affected. Par value
settles it: a cash reduction refunds par, so cancelling a fraction `r` of the
shares pays `C = 10r` and the exchange prices `after = (before − C)/(1 − r)`.
Eliminating `r` between the two,

```
r = (after − before) / (after − 10),   C = 10 r,   pr_step = step × (1 − C/before)
```

— the same expression as the mixed 除權息 case, reached from a different premise.
Nothing is declared and nothing is fitted; both published prices are already in
hand. `ReasonforCapitalReduction` separates the two branches and was sitting
unread in the same file the reference prices come from.

**Here the split can be checked head-on.** `shares/NumberOfSharesIssued` is a
third endpoint and reports how many shares a cancellation actually removed —
which is the `r` both branches solve for. Median `|r_formula − r_shares|`:

| reason | n | its own formula | the other branch's |
|---|---:|---:|---:|
| 現金減資 — `r = (after−before)/(after−10)` | 269 | **0.00018** | 0.061 |
| 彌補虧損 — `r = 1 − before/after` | 326 | **0.00012** | 0.268 |

Each formula reproduces the cancelled fraction on its own reason to the fourth
decimal and misses by two to three orders of magnitude on the other. That is what
makes the reason label load-bearing rather than assumed: were the column noise,
both rows would be equally bad; were the cash leg negligible, both would be
equally good. The separation is sharper than the table shows, because the refund
identity is not merely inaccurate on a loss-offset filing — it is undefined on
225 of the 351, putting `r` outside `[0, 1)`. Two different arithmetics, not two
tunings of one. The remaining check is one-sided: 99.6 % of the implied `r` land
within 0.5 pp of an integer percent, which is how these are filed.

The check is run against the shipped `_refund_per_share` rather than a retyped
copy of the formula, so it fails on a bug in the implementation and not only on a
bug in the algebra.

**What it costs.** 107 fused events across 61 stocks have no recoverable cash leg
and cannot be split. Those stocks' price-return columns are NaN before the last
such event — 95,396 rows — rather than carrying a guessed step. The
total-return columns are unaffected. It was 250 events in 113 stocks and 122,973
rows until §8 added the exchange's own split as a second source for the leg.

**Which one to use is a research choice.** `tr` measures what a holder earned;
`pr` measures the price alone and is what most vendors call "adjusted close", so
it is the series to pick for symmetry with KRX `ChangesRatio`. The cost of `pr`
is visible in §5: the ex-day drop survives as a −311 bp mean on 除權息 sessions,
and Taiwan's ex-dividend season is concentrated in July–September, so those
sessions are calendar-clustered. Any flow-return study on `pr` has to handle
that rather than ignore it, and the demeaning trap in
[`kr_marcap/VERIFICATION.md`](../kr_marcap/VERIFICATION.md) rules out the reflex
fix of subtracting a date mean.

---

## 7. What the sources do not cover

Four limits live in the inputs rather than in the build. None is repairable by
better arithmetic, so each is marked in the output instead of smoothed over.

**減資 events begin on 2011-01-25; prices and 除權息 begin in 2005.** The
capital-reduction endpoint has no earlier rows, and the limit is the exchange's
own rather than the vendor's. TWSE publishes the same report itself as TWTAUU
(股票減資恢復買賣參考價格), free and without a key; it rejects any start date
before ROC 100/1/1 with `查詢開始日期小於100年1月1日，請重新查詢!` and its first
row is 100/01/25, the same 2011-01-25 FinMind starts on. So this is not a
truncated download and not a paywall — no tier and no mirror reaches further
back, and the reference prices for an earlier reduction do not exist in
published form. A reduction inside the uncovered window therefore leaves its
full mechanical price jump in the adjusted series with `is_cap_red` reading
False. The canonical case is 2357 華碩 on 2010-06-24: shares fall 4,246,777,484 →
637,016,623 (−85.0 %), trading stops for 38 days, the close goes 50.40 → 240.50,
and `tr_factor` does not move.

`shares/NumberOfSharesIssued` is a third endpoint and does cover 2005. It can say
*that* a cancellation happened, never by how much the exchange repriced, so
`detect_unpriced_actions.py` uses it strictly as a detector and never as a factor
source. A material share drop straddling a trading suspension with no filing
within 30 days is reported, and `adjust.py` marks the history behind it
`is_valid = False`. Scored on the years where the filed events can score it,
2011-01-25 onward, the detector runs **92.6 % precision and 92.0 % recall**. It
finds 250 cancellations in 193 stocks inside the uncovered window; with splices
included that is 309 breaks in 231 stocks, 3.0 % of rows marked invalid.

Marking is the conservative direction and is not an assertion of error.
`is_valid = False` means "this row does not connect to the rows after it", so a
false positive costs history while a false negative is precisely the failure the
flag exists to prevent. `load_adjusted` raises if `unpriced_actions.parquet` is
absent rather than adjusting as though the window were clean.

**A session with no trading is written `close = 0`, not omitted** — 179,749 rows,
2.34 % of the panel, across 1,325 stocks; 8934 alone carries 2,441 of its 3,833.
Zero is not a price, so both adjusted closes are NaN there while the factors stay
defined. The earlier build multiplied the zero through to `adj_close_tr = 0.0`,
which reads as −100 % followed by an infinite return. Every check in
`validate_adjust` already masked these rows; `load_adjusted` did not — the shape
of a silent failure is exactly that, knowledge that existed and never reached the
output.

**TWSE stopped publishing the 除權息 split in 2009, and TPEX never did.** §8's
third source carries 權值 and 息值 as separate columns only through 2008; from
2009 the report keeps their sum and a 權/息 label. The label still settles a pure
息 or 權 event — all cash, or none of it — so what the later schema costs is
exactly the fused 權息 events, which is why 143 of the 250 unresolved legs are
recoverable and the remaining 107 are not. The OTC side has no archive at all:
TPEX's `exDailyQ_result.php` publishes the identical field list but serves a
rolling few-day window and ignores every date parameter tried, and its
`preAnnounce` table returns only the current forward announcements. Both limits
are the publisher's; neither is a download that stopped early.

**A few raw prices are simply wrong**, and no adjustment repairs a bad input.
Check [7] is the standing report: extreme one-day adjusted moves on rows carrying
no event and sitting after the last break. What it finds are stale near-zero
quotes, sporadic pre-listing 興櫃 sessions (2007-03-03 and 2007-04-14 carry
clusters, all TPEx), and isolated corrupted rows — 8454 on 2014-09-09 reports
`open` 241.04 and `max` 242.49 against `min` = `close` = 3.43, a −98.6 % followed
by +6,853 %. A systematic search finds no class behind that last one: zero rows
in the whole panel have `close` outside `[min, max]`, and only 0.042 % have
`max/min > 1.25`, mostly first sessions after listing. So it is listed rather
than patched.

### Which years are usable, and why the obvious cut is the wrong one

The 減資 coverage boundary invites "use 2011 onward". That would be the wrong
read of it. 88.83 % of pre-2011 rows are already `is_valid`, and 1,283 of the
1,507 stocks with pre-2011 history (85.1 %) are unmarked throughout it, so
cutting at 2011-01-25 discards 1,659,324 valid rows — 21.6 % of the panel — to
avoid 208,621 rows the flag already handles. `is_valid` exists so the era does
not have to be dropped wholesale.

The reason to look harder is the detector's 92.0 % recall: roughly one pre-2011
cancellation in twelve should still be unmarked. Off-event moves on `is_valid`
rows do run heavier before the boundary than after — check [7] reads 1.10 against
0.19 per 10,000, a factor of 5.8 — which is what that contamination would look
like. The sign test says it is not. **A cancellation nobody priced can only jump
upward**, since the history behind it is never scaled up, so a population of
missed reductions has to skew the early era positive. It does not separate: 85.1 %
of the 175 early hits are up against 78.0 % of the 109 later ones, a
two-proportion `z` of +1.54. Repeating at a 25 % threshold moves the gap to
70.7 % against 71.3 %, `z = −0.20` — the difference changes sign with the cut,
which is what noise does and what a real population of missed reductions could
not.

What does separate is price level: median prior close NT$17.10 against NT$46.50,
and 20.0 % of early hits under NT$5 against 8.3 % of later ones. The heavier
early residual is tick-size arithmetic on cheap stocks. Note the bound this
establishes covers *large* misses only — a 10 % reduction never enters a 35 %
count, and nothing here excludes those.

Read by year, the weak window is not the oldest one:

| year | `is_valid` | off-event \|ret\|>25 % per 10k | prior close < NT$5 |
|---|---:|---:|---:|
| 2005 | 81.9 % | 0.55 | 4.8 % |
| 2006 | 83.7 % | 0.60 | 4.8 % |
| 2007 | 87.2 % | **8.35** | 1.5 % |
| 2008 | 89.4 % | 5.75 | 4.4 % |
| 2009 | 92.3 % | 4.16 | 5.0 % |
| 2010 | 95.5 % | 1.62 | 1.6 % |
| 2011 | 97.3 % | 1.57 | 2.4 % |
| 2012 | 98.8 % | 1.45 | 3.7 % |
| 2013 | 99.6 % | 0.77 | 2.5 % |
| 2018-2024 | ≥ 99.9 % | ≤ 0.35 | ≤ 2.0 % |

The `is_valid` column climbs monotonically for a mechanical reason, not a quality
one: the flag marks everything *behind* a stock's last break, so an early year is
more likely to sit behind one no matter how sound its own rows are. The quality
column is the middle one, and it does not order by age — 2005 and 2006 carry the
lowest residual in the panel while 2007 carries the highest. The 2007 spike is
the 興櫃 pre-listing clusters check [7] names; 2008-2009 is crisis-era penny
composition. Both are input artefacts a price floor removes, not adjustment
failures.

So: 2013 onward needs no thought, 2011-01-25 onward is the floor for anything
that reads capital reductions directly, and 2005 onward is sound for 除權息 work
after filtering — with the caveat that 2005-2006's low residual is partly
survivorship, since the rows surviving `is_valid` there belong to the stocks that
never broke.

---

## 8. Does the cash leg have a second source?

§6 splits a fused 權息 by subtracting the declared dividend `D`. Where nothing
was ever declared the leg is unrecoverable and the price-return chain goes NaN —
250 events when §6 was written. That framing had a gap: it treated the
declaration as the only place the number could come from, when the exchange
computes the split itself in order to publish the reference price.

**TWT49U (除權除息計算結果表)** is that computation, free and keyless at
`www.twse.com.tw/rwd/zh/exRight/TWT49U`, and it reaches back to 2005 — the whole
price series. It carries the same `before_price` / `after_price` as
`div_result/`, plus 權值 and 息值 as separate columns. `download_exright.py`
pulls it in 20 requests; whole-year queries are not truncated (2007 returns 538
rows either as one call or as twelve monthly calls summed).

Three comparisons, in increasing order of what they can falsify:

| check | n | result |
|---|---:|---|
| `before` == 除權息前收盤價 | 13,891 | 100.0000 % within 1e-6 |
| `after` == 除權息參考價 | 13,891 | 100.0000 % within 1e-6 |
| our kind marker == 權/息 label | 13,891 | 99.9424 % (8 disagree) |
| 息值 == declared `D` | 10,495 | 97.14 % within 1e-6, 100 % within 1 % |

The first two only prove the join found the same events, which is worth proving
because everything after depends on it. The third is informative: TWSE's own
權/息 label and FinMind's `stock_or_cache_dividend` are independently produced
and agree on all but 8 of 13,891 events, so the classification the whole split
branches on is not resting on one vendor's field.

The fourth is what licenses the fill. The exchange's 息值 and the declared
dividend are *the same number* — a source that disagreed here would be changing
values rather than filling holes, and the fill would need adjudicating instead of
adopting. Because they agree, the declaration stays primary and TWSE is read only
where it is silent, so no leg the build already named moves.

**What it recovers.** 143 of the 250 events, leaving 107 in 61 stocks. The
remainder is exactly what §7's fourth limit predicts: fused events from 2009 on,
after TWSE narrowed the schema, plus the 23 上櫃 events with no archive to read.

The three-source structure now matches the 減資 side: `div_result` gives the
step, the declaration gives the cash leg, TWT49U checks both and fills the leg
where the declaration is silent — the same shape as §6's use of
`shares/NumberOfSharesIssued` as an outside witness to the 減資 split.

---

## 9. Does an independent implementation agree?

Every check so far compares this build against a *source*. None answers the
question a reader asks first: someone must already have written this, so why
was it written again? The honest form of that question is a number, and there
is exactly one implementation to get it from.

FinMind carried one inside `taiwan_stock_daily_adj()` until **PR #269** (merged
2023-09-24) deleted the arithmetic and moved the series behind its sponsor tier.
The 226 lines are still readable at the parent commit, `c31098c4`. Nothing else
public computes these factors: a repository search turns up only single-star
personal projects, FinLab's `etl:adj_close` is closed data, and the one blog
walkthrough of a free reimplementation uses TWT49U reference prices — the same
source as §8 — without 減資 or a price-return split.

It reads the same two tables this build reads and diverges in two places, so
check [9] runs its arithmetic on our events and compares the back-adjustment
multiplier event by event.

| chain | n | agrees < 1e-6 | p99 \|rel\| | max \|rel\| |
|---|---:|---:|---:|---:|
| 除權息 | 22,369 | 88.47 % | 8.72e-04 | 3.95e-02 |
| 減資 | 620 | 100.00 % | 2.00e-15 | 1.51e-14 |

Compounded into the level of each stock's oldest bar: median 4.4e-16, p95
2.4e-03, max 0.0386 (1442).

**The 減資 row corrects something §6 implies.** FinMind inverts the par-value
rule for every reason alike, with no branch on `ReasonforCapitalReduction`,
which §6 would lead you to expect fails on a 彌補虧損 that refunds nothing. It
does not fail. The inversion `r = (after − before)/(after − 10)` undoes the
exchange's own forward rule, so the par-value assumption cancels and the
total-return step is right regardless of reason. The reason branch this build
carries is load-bearing in the price-return split and nowhere else — §6's
two-sided test establishes that the label carries information, not that the
total-return chain needs it.

**The 除權息 row is where the column choice shows.** FinMind subtracts
`stock_and_cache_dividend` from the prior close; this build reads the reference
price in the next column over. §2 already measured that identity failing on
18.6 % of bare-kind rows, and this is what that costs: disagreement on 11.5 % of
events, but small — under 9e-4 at the 99th percentile, worst 3.95 % on a 權
event. Compounded across a full history it clears 1 % on 4 of 1,947 stocks.

So the total-return series is not what justifies this build. A researcher who
needs only `adj_close_tr` would have been served by those 226 lines to within
0.24 % at the 95th percentile of stocks. What the reference implementation
cannot produce at all is the rest: no price-return series (§6), no placement for
an ex-date the exchange closed — it matches ex-dates with `==` and silently drops
the event when that date is not a session, 272 of them here — no validity
marking behind a series break, no detector for unpriced actions (§7), and it
deletes `close == 0` rows from its own output rather than marking them.

---

## Two traps that cost a measurement each

Each produced confident, wrong numbers that the checks above caught. They are
recorded because neither is obvious and both will recur.

**Forward returns put the event on the previous row.** `R_t1` is the 1-day
*forward* return, so an ex-day drop lands in the window `(t → t+1)` when `t+1`
is the ex-date — that is, on the **cum-date row**. Joining the event onto the
ex-date row instead measures the post-drop session and reports −18 bp where the
truth is −413 bp, a 20-fold understatement. Verify the alignment before
trusting any contamination figure (`R_t1` reconstructs exactly from
`close.shift(-1)/close - 1`, max difference 0.0).

**A disclosed event date is not always a session, and a filing is not always
unique.** Matching an event to its exact date left 274 of the 22,997 filed
steps unapplied, which reads as a rounding error and is not one. 271 of them fall on
one of 21 dates when *nothing* traded — 2009-08-07 (Morakot), 2016-07-08
(Nepartak), 2023-08-03 (Khanun), 2024-07-24/25 (Gaemi), and so on. TWSE 順延s an
event whose date lands on a closure, and the data says so: `before_price` equals
the close of the session before the closure, and the resumption session's own
return is the reference-price step. The remaining three are 減資 suspensions,
where the stock stops trading for 12 to 18 days to exchange certificates and the
disclosed date falls inside the gap. Both belong on the first session **on or
after** the disclosed date, not on the exact date and not nowhere. The steps are
large — one 100 % 無償配股 was sitting inside a −46 % one-day forward return.

Switching to next-session placement then exposes the second half of the trap.
Three filings are duplicates, the same action recorded twice under two dates,
and exact-date matching had been discarding the stray copy for free. Next-session
placement applies it a second time instead. Two of the three are told apart by
the calendar (2327 and 3018 file their 減資 under both the suspension date and
the resumption, and only one of those traded), but 6109 files its 2018 現金減資
again under 2020-09-25, a date it traded straight through, so both copies look
equally real. What separates them is the anchor: the reference price is computed
off the last close before the event, so a filing whose predecessor closed at
something else is not describing this series. 6109's stray copy misses by 3.95
on a 10.50 reference. That copy was being applied by exact-date matching too, so
the anchor is a correction to the old behaviour and not only a guard on the new.

---

## Free parameters, and which ones are load-bearing

Every threshold below is a researcher choice. The rule applied is the repo's:
justify it, or delete it. Each reports its own sensitivity rather than quoting
one level.

| parameter | where | status |
|---|---|---|
| tolerance `1e-6` / `1e-2` | raw-input check (§1) | **kept, both reported.** `1e-2` is the exchange's own published precision; reporting one alone would let a tuned threshold pass for a result. |
| tolerance `_TOL_BEFORE_PRICE = 1e-2` | event placement | **kept, and not a cut.** It asks whether `before_price` agrees with the prior close at the exchange's own published precision. Every value from `1e-6` to `0.5` rejects the same single filing (6109's duplicate, off by 3.95) and no other, so there is no band to tune. |
| window `Y0, Y1 = 2020, 2024` | §1, §5 | **kept, justified.** Five full years ending before the 2024 배당절차 개선 dispersed Korean record dates out of December, so the two markets' contamination tables share a window. |
| `_PAR_VALUE = 10.0` | 現金減資 split | **not a free parameter.** NT$10 is the statutory par value of Taiwanese common stock and the amount a cash reduction refunds per cancelled share. Its correctness is what the share-count table in §6 tests: a wrong par would not reproduce `r` to the fourth decimal on 269 events. |
| `_TWIN_WINDOW_DAYS = 30` | duplicate filings | **kept, and the distribution has no band to tune.** A filing repeated under its suspension and its resumption date is days apart; the 28 same-price pairs that are *not* duplicates are years apart. Every cut between the two leaves the same 4 dropped events. |
| `_BREAK_GAP_DAYS = 730` | series splices | **kept, sits in an empty region.** Observed gap lengths run 91–419 days and then jump to 738–5,392 with nothing between, so every cut in (419, 738] marks the same 17 splices. The two populations differ by more than length: the short gaps reconnect at a median 10 % price move, the long ones at 537 %. |
| `_MIN_SHARE_DROP = 0.05`, `_MIN_SUSPENSION_DAYS = 5` | unpriced-action detector | **kept, calibrated against ground truth, and it does not touch a price.** 92.6 % precision / 92.0 % recall where the filed events can score it (§7). Precision is flat at ~92 % across drop thresholds once the suspension condition is on, so the drop floor buys recall rather than setting a pass mark. It only sets `is_valid`; no factor is derived from it. |
| `_EXTREME_MOVE = 0.35` | check [7] display | **kept, not load-bearing.** It sets how much of the residual tail check [7] prints. No published number depends on it. |
| source precedence: declaration before TWSE 息值 | mixed-權息 cash leg | **kept, and the data makes it immaterial.** The two sources agree to 1e-6 on 97.14 % of the 10,495 events where both speak and to 1 % on all of them (§8), so the ordering changes no leg either one already names — it only decides who fills a hole, and only one of them ever can. Had they disagreed this would be an adjudication, not a precedence. |

**The step convention was a free parameter, and is no longer.** Taiwan uses the
exact step, `before/after`. A back-adjustment factor composes *multiplicatively*
across time, and a linear approximation telescopes wrong. Taiwan's step is large
— median 4.6 % of the cum price, q95 12.6 %, since it carries share-count changes
as well as cash — so the linear form would have been off by a median 22.6 bp per
event and a median 3.7 % compounded (q99 30.5 %). The Korean side made and
corrected the same mistake at a smaller scale;
[`kr_marcap/VERIFICATION.md`](../kr_marcap/VERIFICATION.md) carries that
measurement.

## Reproducing

```bash
python -m finmind_data.consolidate_capred       # cap_red/*.parquet → capital_reduction.parquet
python -m finmind_data.detect_unpriced_actions --calibrate   # → unpriced_actions.parquet (§7)
python -m finmind_data.download_exright         # TWSE TWT49U → exright_reference.parquet (§8)
python -m finmind_data.validate_adjust          # checks §1–§7, ~20 min
python -m finmind_data.adjust                   # adjusted-series demo
```

## Open

- **107 fused events cannot be split** — no recoverable cash leg, so the
  price-return columns are NaN before the last such event in the 61 stocks
  affected (§6). The total-return columns are unaffected, and whether the 95,396
  NaN rows matter depends on which convention the study uses. This is what
  remains after §8; the residue is structural rather than a gap left unsearched
  — TWSE stopped publishing the split in 2009 and TPEX never published one.
- **The pre-2011 減資 window is marked, not reconstructed, and this is now
  closed rather than open.** §7 detects the cancellations from a third endpoint
  and invalidates the history behind them, which costs 3.0 % of rows and leaves
  ~7 % of the flags as false positives that cost history they did not need to.
  The earlier version of this entry hoped a source publishing Taiwanese
  reference prices before 2011 would replace the detector outright. There is
  none: TWSE's own TWTAUU refuses start dates before 2011-01-01 and begins on
  the same 2011-01-25, so the limit is the exchange's publication and not this
  account's tier. The detector is the ceiling, not a stopgap.
