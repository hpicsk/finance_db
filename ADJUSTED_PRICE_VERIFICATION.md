# Adjusted prices — how we know they are right

An adjusted price series is **unfalsifiable by inspection**. A series that
half-removes an ex-dividend drop, removes it a day late, or removes it twice
plots as the same smooth line as a correct one. Nothing about the output says
which you are holding.

So every check below exists to answer one question: *what would have broken if
this were wrong?* Six families of check, applied to both markets. The Korean
and Taiwanese series are built from different inputs against different
authorities, so the same six questions get different answers in each — that
asymmetry is the point of this file.

Method and failure modes for the Korean price layer are in
[`kr_marcap/PRICE_ADJUSTMENT.md`](kr_marcap/PRICE_ADJUSTMENT.md) and
[`kr_marcap/CORPORATE_ACTIONS_SPEC.md`](kr_marcap/CORPORATE_ACTIONS_SPEC.md).
This file is about **verification**, not construction.

---

## TL;DR

| | Korea | Taiwan |
|---|---|---|
| **Structural adjustment** | KRX `ChangesRatio` compounded (`kr_marcap.adjust`) | Exchange 除權息 / 減資 reference prices (`finmind_data/div_result`, `cap_red`) |
| **Cash-dividend layer** | SEIBro events, ex-date derived under KRX T+2 (`kr_marcap.dividend_events`) | Already inside the exchange factor (`after_price` nets the cash out) |
| **Exchange publishes a total-return factor?** | **No** — KRX 수정주가 is structural only | **Yes** — `after_price/before_price` covers cash *and* rights |
| **Raw input confirmed raw** | via KRX 수정주가 oracle | 99.87 % exact vs exchange `before_price` |
| **Factor reproduced from first principles** | 96.2 % vs DART (independent 2nd source) | 100 % identity on 8,479 `除` events; 93.8 % via the TWSE formula |
| **Residual after adjustment** | +82 bp on ex-dates | +29 bp on 除權息, −94 bp on 減資 |
| **Residual is a defect?** | **No** — prices fall ~66 % of the dividend; the rest is the real ex-day effect | Same |
| **Price-return series** | `adj_close` — free, it *is* `ChangesRatio` | `adj_close_pr` — derived by splitting the fused factor (§7) |
| **Total-return series** | `adj_close_tr` — derived by adding SEIBro cash | `adj_close_tr` — free, it *is* `after_price/before_price` |
| **Builder** | `kr_marcap.adjust.load_adjusted(…, total_return=True)` | `finmind_data.adjust.load_adjusted` |

Neither series ends at zero, and neither should. Both mark the affected sessions
instead — `is_ex_date` on both sides, plus `is_cap_red` on the Taiwanese one.

**Both markets expose both conventions**, so a raw → price-return →
total-return comparison is constructible on either side. Getting there is
asymmetric, though. KRX splits the problem for you, publishing a
structural-only factor and nothing for cash, so Korea's `adj_close` is free and
`adj_close_tr` is the derived one. TWSE/TPEx do the opposite: they publish **one
fused reference price** per 除權息 event covering cash, 無償配股 and 現增
together, so Taiwan's `adj_close_tr` is free and `adj_close_pr` is derived.

Deriving it does **not** go through the TWSE formula, which reproduces the
published `after_price` for only 77.8 % of mixed events because the declared
配股率 omits 員工配股 and 董監酬勞 dilution. It goes through the event *label*
instead. `stock_or_cache_dividend` marks each event 息, 權 or 權息, and that
settles 79.8 % of events with no arithmetic at all — a cash-only event has no
structural step, a stock-only event is all structural. Only the mixed 20.2 %
need the split, and there `pr_step = step × (1 − D/before)` needs the cash
dividend alone. See §7.

---

## 1. Is the input actually raw?

Adjusting an already-adjusted series double-counts, and the failure is silent.
This has to be settled before anything else.

**Taiwan.** The exchange publishes the official pre-event close (`before_price`)
for every 除權息 event. Compared against our stored prior close:

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

This **contradicts what `finmind_data/README.md` used to claim** (that FinMind
closes reflect capital reductions and splits). They do not. The README is
corrected; `TaiwanStockPriceAdj` is a separate dataset, gated above our
`register` tier and never downloaded.

**Korea.** Settled by the standing oracle gate against KRX official 수정주가 —
see §4 below and [`validate_against_oracle.py`](kr_marcap/validate_against_oracle.py).

## 2. Is the exchange factor a black box?

Reproducing a published number from its own disclosed components proves we
understand the mechanism rather than copying the output.

**Taiwan, identity check.** The exchange publishes three numbers per event —
`before_price`, `after_price`, and the deducted amount. One arithmetic relation
must hold between them:

```
before_price − 차감액 == after_price
```

Exact for **8,478 of 8,478** events labelled `除息` / `除權` / `除權息`.

**Taiwan, formula check.** Independently recomputing the reference price from
the disclosed dividend components under the TWSE/TPEx rule

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
(員工配股, 董監酬勞), not of a bad cash figure. The price-return split in §7 is
built to need the cash figure and not the 配股率, precisely because of this.

Two units are easy to get wrong here and both were: `CashIncreaseSubscription
Rate` is **每仟股認購股數**, so the ratio is that value over 1,000, and
`StockEarningsDistribution` is quoted **per NT$10 par**, so the ratio is that
value over 10.

**Residual.** 2,580 events (11.5 %) where `stock_and_cache_dividend` is not the
price deduction. This is a semantics problem in an auxiliary column that the
pipeline never reads — the build uses `after_price/before_price` directly — so
it does not gate anything. Recorded here so it is not rediscovered as a bug.

## 3. Does a derived date match the physical evidence?

**Korean 배당락일 is published nowhere.** SEIBro gives 배정기준일 only; the
ex-date is *derived* under KRX T+2 (`ex = cal[j-1]` where `j` indexes the last
session on or before the record date). There is no reference list to check the
derivation against.

So the check does not consult a data source at all — it asks whether the
physical fingerprint is where the derivation says it should be. If the date is
right, payers must underperform non-payers on that session and not on its
neighbours. Measured on the 2020–2024 Korean research panel:

| offset from derived ex-date | payer − non-payer |
|---|---:|
| −3 | −7 bp |
| −2 | +18 bp |
| −1 | +20 bp |
| **0** | **−77 bp** |
| +1 | +7 bp |
| +2 | −3 bp |

The drop is on the derived session and nowhere else. This is the strongest
check in the file precisely because it is target-free — no second source is
trusted, only prices.

**What it caught.** The predecessor layer reinvested DART's annual yield on the
fiscal year's *last* trading row. That is one session late: 배당락 sits on
폐장일 −1. The old series therefore left the real drop uncorrected **and** added
a spurious spike on 폐장일.

## 4. Do two independent institutions agree?

Korea has no exchange-published total-return factor, so the single Taiwanese
identity splits into two checks against two unrelated authorities.

| component | authority | result |
|---|---|---|
| structural | KRX official 수정주가 | **99.43 %** of daily returns within `1e-3` (n = 8,590,146 rows / 3,995 tickers), median difference 2.5e-5 |
| cash | DART 사업보고서 배당 | **96.2 %** DPS match to ±0.5원 (n = 12,115 ticker-years / 1,615 tickers) |

Returns are compared rather than levels because the two series use different
back-adjustment anchors; returns are anchor-invariant. The exact-match rate at
`1e-6` is only 13 %, which is KRX publishing 수정주가 rounded to the won —
median 2.5e-5 is 0.25 bp, i.e. quantisation, not disagreement.

The DART comparison has teeth because **예탁원 and 금감원 record the same
dividend for unrelated reasons** — one to allocate the entitlement, the other to
receive a disclosure. Neither copies the other, so agreement is evidence rather
than tautology.

**The DART side is restricted to December-fiscal-year issuers**, and the
restriction is load-bearing rather than cosmetic. SEIBro is keyed by 배정기준일,
so a calendar-year sum of its events equals a fiscal-year total only when
FY == CY. Lifting it admits 221 more pairs (12,336 / 1,615 → 1,658 tickers)
whose two sides are not the same accounting object, so the resulting 96.1 % is
the weaker number even though it is barely different.

**Survivorship.** Splitting the matched pairs on the KIND delisting calendar,
delisted issuers reconcile at **96.3 %** against **96.2 %** for those never
delisted — indistinguishable, which is the point: the SEIBro collection is not
biased toward survivors. An earlier version of this split used only delistings
after 2021-01-01 and reported 98.9 %, which was an artefact — the cut-off kept
the recent, cleaner delistings and, worse, filed the 360 rows / 62 tickers
delisted *before* 2021 under a bucket labelled "still listed". The cut-off was a
free parameter no result needed and is gone.

**Taiwan gets a weaker version of the same check.** `TaiwanStockDividend`
carries `CashExDividendTradingDate`, a declared ex-date sourced from the
company's 股利分派公告 rather than from the 結果表 that `div_result` comes from.
The two agree on **19,722 of 19,730** comparable events (**99.96 %**). Of the
2,228 non-matches, 2,220 are declared dates outside that stock's `div_result`
coverage span and only **8** are genuine disagreements inside it.

This confirms `div_result.date` is the ex-dividend *trading* date and not the
record or announcement date — but it is two disclosures rather than two
institutions, so it ranks below the Korean DART check. The load-bearing
Taiwanese evidence stays §1: `before_price` matching the *prior* session's
close pins the date independently of any declaration.

## 5. Would a coding error survive?

Correct arithmetic can still be wrongly implemented. Two identities must hold
by construction and catch different classes of bug.

```
adj_close_tr == adj_close × tr_factor      → indexing / broadcasting errors
adj_close_tr[today] == close[today]        → normalisation / anchor errors
```

Both are exactly `0.000e+00` across spot-checked Korean payers (005930
quarterly, 000660, 033780 high-yield) and across **all 2,141 Taiwanese stocks
with price rows** — the Taiwanese side runs the identity over the whole universe
rather than a sample, since the factor is per-event and cheap.

**Double counting** is checked separately, because the two factor chains must be
disjoint:

- Korea — 1,118 주식배당 events are excluded from the cash factor; they already
  reset KRX's 기준가 and so live inside `ChangesRatio`. The 666 동시배당 events
  contribute their cash leg only.
- Taiwan — 減資 (627 events, `cap_red`) and 除權息 (`div_result`) share **zero**
  `(stock_id, date)` pairs, so the two chains compose without overlap.

## 6. Did the contamination actually go away?

The final check is the one the whole exercise is for. Measured on the rows whose
forward return spans an event, over 2020–2024:

| | event | affected rows | raw | price-return | total-return |
|---|---|---:|---:|---:|---:|
| Taiwan | 除權息 (n = 7,513) | 0.340 % | −405 bp | −311 bp | **+29 bp** |
| Taiwan | 減資 (n = 211) | 0.010 % | **+7,609 bp** | −94 bp | **−94 bp** |
| Korea | 배당락 | 0.219 % | −160 bp | — | **+82 bp** |

The price-return column is a check as much as a result. On 減資 it must equal
the total-return column *exactly*, since a capital reduction has no cash leg to
remove — and it does, to the digit. On 除權息 it must sit strictly between raw
and total-return, since it removes the structural part of the step and keeps the
cash part — and it does, absorbing 94 of the 405 bp.

The two Taiwanese event types are reported apart rather than netted, because
they contaminate in opposite directions — 除權息 removes a price drop, 減資
removes a price *rise*. Netting them reports −197 bp for a panel whose dividend
contamination is really −405 bp.

**減資 is the larger per-event distortion by an order of magnitude** — +7,609 bp
against −405 bp, roughly nineteen times — on a twentieth as many events. It is
worth naming separately because the unadjusted Taiwan panel carries it in full:
a capital reduction cancels shares, so the mechanical price jump is a
share-count artefact with no return content whatsoever.

**Nothing lands on zero, and that is correct.** Prices fall short of the full
distribution — the Korean drop-off ratio is 0.663, stable across mass December
ex-dates (0.665) and scattered interim ones (0.643). The holder receives 100 %
of the cash, so a total-return series must add 100 %, and the difference is the
real ex-day tax/clientele effect. It is marked, not erased.

The Korean row and that 0.663 are one measurement, taken on the qf_paper panel
as a same-date payer-versus-non-payer contrast. Nothing in this repo rebuilds
them, and the Taiwanese rows are a different estimator that happens to answer
the same question. See Open before comparing the two.

---

## 7. Can the fused Taiwanese factor be split?

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
| 減資 (separate endpoint) | 627 | — | all of it; `pr_step = step` |

So 79.8 % of 除權息 events, plus every 減資, resolve from the label alone.

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

**What it costs.** 250 mixed events across 113 stocks have no declared cash leg
and cannot be split. Those stocks' price-return columns are NaN before the last
such event — 122,973 rows — rather than carrying a guessed step. The
total-return columns are unaffected.

**Which one to use is a research choice.** `tr` measures what a holder earned;
`pr` measures the price alone and is what most vendors call "adjusted close", so
it is the series to pick for symmetry with KRX `ChangesRatio`. The cost of `pr`
is visible in §6: the ex-day drop survives as a −311 bp mean on 除權息 sessions,
and Taiwan's ex-dividend season is concentrated in July–September, so those
sessions are calendar-clustered. Any flow-return study on `pr` has to handle
that rather than ignore it, and the demeaning trap below rules out the reflex
fix of subtracting a date mean.

---

## Three traps that cost a measurement each

Each produced confident, wrong numbers that the checks above caught. They are
recorded because none is obvious and all will recur.

**Forward returns put the event on the previous row.** `R_t1` is the 1-day
*forward* return, so an ex-day drop lands in the window `(t → t+1)` when `t+1`
is the ex-date — that is, on the **cum-date row**. Joining the event onto the
ex-date row instead measures the post-drop session and reports −18 bp where the
truth is −413 bp, a 20-fold understatement. Verify the alignment before
trusting any contamination figure (`R_t1` reconstructs exactly from
`close.shift(-1)/close - 1`, max difference 0.0).

**Do not demean within date to estimate the ex-day *level*.** On 배당락일 payers
are a *majority* of the cross-section, so subtracting the date mean removes much
of their own effect and manufactures a spurious **+144 bp intercept** (t = 26,
robust to trimming) — which reads as the correction overshooting to +165 bp. The
clean estimator is a same-date payer-versus-non-payer contrast, giving +82 bp.

The *slope* is a different quantity and survives the same estimator: on the same
sample, date-demeaned gives −0.778 against −0.774 for payer-minus-non-payer.
So −0.809 versus −0.663 is a **universe** difference (full `kr_marcap` versus
the research panel), not an estimator artefact. Quote the one whose universe
matches the claim, and do not carry the level and the slope on the same warning.

**A disclosed event date is not always a session, and a filing is not always
unique.** Matching an event to its exact date left 274 of the 22,997 filed
Taiwanese steps unapplied, which reads as a rounding error and is not one. 271 of them fall on
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
justify it, or delete it. Two were deleted; the rest report their own
sensitivity rather than quote one level.

| parameter | where | status |
|---|---|---|
| delisting cut-off `> 2021-01-01` | Korean DART split | **deleted.** It selected the recent, cleaner delistings and read 98.9 % where the whole calendar reads 96.3 %; it also mislabelled 360 pre-2021 rows as "still listed". No result needed it. |
| yield trim `TRIM_Q = 0.99` | Korean ex-date localisation | **kept, sensitivity now printed.** Load-bearing for the *slope* — untrimmed −0.31 against −0.81 at any trim from the top 1 % to the top 10 % — but the check's actual claim (the drop sits on ex+0 and nowhere else) holds at every level. |
| tolerance `1e-6` / `1e-2` | Taiwan raw-input check | **kept, both reported.** `1e-2` is the exchange's own published precision; reporting one alone would let a tuned threshold pass for a result. |
| tolerance `_TOL_BEFORE_PRICE = 1e-2` | Taiwan event placement | **kept, and not a cut.** It asks whether `before_price` agrees with the prior close at the exchange's own published precision. Every value from `1e-6` to `0.5` rejects the same single filing (6109's duplicate, off by 3.95) and no other, so there is no band to tune. |
| tolerance `±0.5원` | Korean DART DPS match | **kept, justified by the unit.** DPS is quoted in won, so this is "rounds to the same won", not a fitted band. |
| window `Y0, Y1 = 2020, 2024` | both | **kept, justified.** Five full years ending before the 2024 배당절차 개선 dispersed record dates out of December. |
| `_SHORTFALL_TOL = 0.02` | SEIBro collection guard | **kept, weakest of the set.** The observed server-side count drift is ~0.4 %, so 2 % is a hand-picked 5× headroom. It only gates a fail-loud abort and touches no published number. |

**The step convention was a free parameter, and is no longer.** Both markets now
use the exact step — Taiwan's `before/after`, Korea's `1 + dps/close_ex`. The
distinction is not cosmetic. A one-period total return is `(P_ex + D)/P_cum`,
so in *return* space the cum close is the exact denominator and
`ChangesRatio + dps/close_cum` is right, which is what the payer-versus-non-payer
check above uses. But a back-adjustment factor composes *multiplicatively* across
time, and there the same step telescopes correctly only with the ex close.
Korea used the cum close and so understated the factor. On a 200-ticker sample
(1,694 events) the correction is a median 0.88 bp per event and a median 0.105 %
compounded, but it scales as the yield squared, so the tail is not small: q95
32.3 bp per event, and a maximum of 806 bp on one event and +44.1 % compounded
over a ticker's history, on the return-of-capital payers whose yields run to tens
of percent. Taiwan's step is larger still — median 4.6 % of the cum price, q95
12.6 %, since it carries share-count changes as well as cash — so the linear form
there would have been off by a median 22.6 bp per event and a median 3.7 %
compounded (q99 30.5 %).

## Reproducing

```bash
python -m kr_marcap.validate_dividend_events    # Korean checks, read-only, ~1 min
python -m kr_marcap.validate_against_oracle     # Korean structural vs KRX 수정주가 (§4)
python -m kr_marcap.dividend_events             # Samsung quarterly ex-date demo
python -m finmind_data.validate_adjust          # Taiwanese checks §1–§7, ~15 min
python -m finmind_data.adjust                   # Taiwan adjusted-series demo
```

## Open

- **The Korean row of §6 has no generator in this repo.** The two Taiwanese rows
  come out of `finmind_data.validate_adjust` check [5] and re-measure themselves
  on every run. The −160 bp / +82 bp pair does not: it is same-date payer versus
  non-payer across the 23 ex-dates in the window, measured once on the *qf_paper*
  panel rather than on `marcap/`, which is why nothing here rebuilds it. It is
  the only number in this document a re-run would not catch drifting.

  Three estimators of the same ex-day drop-off are in play and none of them is a
  reading of another. The published 0.663 is that same-date contrast over all 23
  ex-dates. Check [3] runs the identical contrast restricted to the December
  session alone and reads −155 bp / +71 bp. A port of Taiwan's check [5] — mean
  raw against mean `ChangesRatio + dps/close_cum` over affected rows, no
  payer/non-payer differencing at all — reads −73 bp / +145 bp on 0.209 % of
  rows, a ratio of 0.33, while check [1]'s cross-sectional slope reads 0.81
  trimmed and 0.31 untrimmed. The affected-row share is the one quantity all of
  them agree on. Quote the estimator with the number, always.

  The step-convention change above is not a candidate explanation for any of the
  gaps: on a 400-ticker measurement of the multiplicative path it moves the mean
  total return on ex rows by +5 bp.
- **2004 Korean dividend coverage is partial** — SEIBro refuses 1,303 rows of
  the 2004-12-31 window. Reported by the build rather than silently dropped;
  see the defect table in [`kr_marcap/README.md`](kr_marcap/README.md).
- **250 Taiwanese mixed events cannot be split** — no declared cash leg, so the
  price-return columns are NaN before the last such event in the 113 stocks
  affected (§7). The total-return columns are unaffected, and whether the 122,973
  NaN rows matter depends on which convention the study uses.
- **Korea has no `is_cap_red` analogue.** `ChangesRatio` folds capital
  reductions in with everything else structural, so the Taiwanese finding that
  減資 is the larger per-event distortion (§6) cannot be checked on the Korean
  side with what is built.
