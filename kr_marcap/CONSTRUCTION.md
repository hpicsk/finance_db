# Constructing FnGuide-quality Korean price data from open sources

FnGuide DataGuide is the academic standard for Korean equity prices, and it is a
paid subscription. This package builds the same two adjusted-price series out of
sources that are free to anyone: the exchange's own daily 등락률, official
corporate-action filings, and 예탁원's dividend record. The question this file
answers is not whether that is *possible* — an adjusted series is
[unfalsifiable by inspection](VERIFICATION.md), so anything
plots — but **how close the free reconstruction actually gets, measured against
the paid series it reproduces.**

Answer, on the 10,255,070 ticker-days the two share:

| | price return<br>수정주가 | total return<br>수정주가(현금배당포함) |
|---|---:|---:|
| daily returns agreeing | **99.977 %** | **99.969 %** |
| tickers agreeing on *every* shared day | 92.11 % | 84.10 % |
| — on 2015+, the repo's research window | 99.993 % | 99.987 % |

The residue is 5,511 ticker-days, and three fifths of it is one diagnosed defect
in *our* pipeline with a known cause and a proposed guard ([below](#what-the-benchmark-found-that-the-oracle-gate-could-not)).

**Scope.** This file is about the reconstruction and its distance from the
benchmark. *Method* is in [`PRICE_ADJUSTMENT.md`](PRICE_ADJUSTMENT.md) (the
compounding rule and its failure modes) and
[`CORPORATE_ACTIONS_SPEC.md`](CORPORATE_ACTIONS_SPEC.md) (how a share-count
change is classified). *Verification against sources other than FnGuide* is in
[`VERIFICATION.md`](VERIFICATION.md).

---

## What is being reproduced

FnGuide publishes two conventions, and the repo builds both:

| FnGuide item | Sheet | Convention | Ours |
|---|---|---|---|
| `S410000700` | 수정주가 | capital changes only; the cash drop left in as a real return | `adj_close` |
| `S410007700` | 수정주가(현금배당포함) | cash dividends reinvested as well | `adj_close_tr` |

Each side is a separate project with a separate loader, and the benchmark reads
both through those rather than reconstructing either: ours from
`kr_marcap.adjusted_loader.load_adjusted_panel()`, theirs from
`fnguide_data.price_loader.load_price_panel()`. So the panel measured below is
the panel a consumer gets, not a private copy that can drift from it.

The benchmark export (`fnguide_data/raw/Price data.xlsx`, parsed once by
`fnguide_data.price_loader`) covers **3,590 tickers over 2005-01-03 –
2026-08-12**, pulled with DataGuide's "all codes" (전체 / 상폐 포함) filter, so
delisted names carry prices to their delisting date. **616 / 620 (99.4 %)** of
genuine common KOSPI/KOSDAQ delistings since 2005 are present; the 4 absentees
are closed-end funds and a resource trust, not ordinary commons. A benchmark
that stopped at survivors would grade the easy half of the problem, which is
what the previous FnGuide cross-check (currently-listed names, price return
only) did.

The overlap is bounded on our side, not FnGuide's: the factors file is built
from a marcap vintage ending **2026-02-20**, so the comparison runs
2005-01-03 – 2026-02-20 across **3,535 tickers**.

**Neither side's vintage is a property of the other, and refreshing one moves
the window.** The benchmark export was pulled 2026-08-13 and the marcap clone
ends 2026-02-20; the gate silently intersects them, so a re-pull of either
changes what was graded without changing any number in this file. Two rules
follow. Re-run the gate after refreshing *either* side, not only after an
`adjust` rebuild. And do not carry a coverage figure across vintages — FnGuide's
own `raw/` files were themselves pulled between 2026-02-14 and 2026-08-13 and do
not share a universe with each other, let alone with a February marcap
([`fnguide_data/README.md`](../fnguide_data/README.md#️-every-sheet-has-its-own-pull-date)).
`adj_factors.parquet` carries the marcap commit and data span as a provenance
stamp for exactly this reason; the FnGuide side has no equivalent stamp beyond
row 8 of each sheet.

## What "openly available" means here

Every input below is free. One needs a registration key; none needs a
subscription.

| Input | Source | Access | Supplies |
|---|---|---|---|
| 등락률 (`ChangesRatio`), OHLCV, `Stocks` | [`FinanceData/marcap`](https://github.com/FinanceData/marcap) | public git clone | the structural backbone — the whole price-return series |
| 회사합병 / 회사분할 / 주식교환 | DART OpenAPI | free API key | entity-change series breaks |
| genuine delisting calendar | KIND | free scrape | ticker-reuse breaks (`kr_delisted/`) |
| 수정주가 | KRX, via `pykrx` | free, rate-limited | 거래재개 reset detection + a second gate |
| 배당내역 (배정기준일, 주당배당금) | SEIBro | free, no key | the entire cash-dividend layer |

The asymmetry that makes this tractable is KRX's: **the exchange gives away the
hard part.** 등락률 is computed against the corporate-action 기준가, so splits,
무상·유상증자, 감자 and 액면병합 are already inside it and never have to be
reconstructed from share counts. What has to be built is the cash-dividend layer,
which KRX does not publish at all — 수정주가 is structural only — and the handful
of sessions where 등락률 is not a traded return.

## Construction

Two lines, in the order the code runs them.

**Price return.** Compound the exchange's own daily return per ticker, anchored
so the last traded session's adjusted close equals its raw close:

    gross[t]     = 1 + ChangesRatio[t] / 100
    adj_close[t] = anchor × cumprod(gross)[t] / cumprod(gross)[anchor]

Four classes of session do not compound, because on them 등락률 is not a return
the stock actually earned: an entity-change break (the move spans two different
companies), a ₩1 no-trade sentinel, a phantom 등락률 on a carried-flat no-trade
day, and a 거래재개 whose 등락률 is measured against an administrative reference.
The first is decided by official filings, never by a tuned threshold; the last is
decided against KRX's own 수정주가. Both are detailed in
[`PRICE_ADJUSTMENT.md`](PRICE_ADJUSTMENT.md) §§3–5b — and the fourth is where the
benchmark found a defect.

**Total return.** Reinvest each SEIBro cash-dividend event on the session it
actually went ex — the 배당락일 derived from its 배정기준일 under KRX T+2 — at that
session's close:

    step[ex] = 1 + dps / close[ex]

The ex close rather than the cum close is what makes the step exact rather than
first-order: composed multiplicatively it telescopes to `(P_ex + dps)/P_cum`, the
one-period total return. Reinvesting at the cum close understates the factor by a
median 0.9 bp per event but scales as the yield squared, reaching 806 bp on a
single return-of-capital payout.

## How close it gets

Compared on **log returns, not levels** — the two series are back-adjusted to
different anchors, so levels differ by a per-ticker constant that cancels in any
return, and returns are what the panels consume. Consecutive rows of the *merged*
frame are used, so both returns always span the same pair of sessions.

Agreement is scored against two bars, neither fitted to the outcome:

- **rounding** — FnGuide publishes 수정주가 rounded to the won, worth `0.5/P` per
  endpoint in log return; ours compounds 등락률, which marcap rounds to 0.01 %,
  worth 5e-5 per session. Their sum is arithmetic, and it is not small: both
  series are back-adjusted, so a name that later split carries single-digit
  adjusted prices early in its history.
- **material** — a flat 10 bp on the daily return, below the ~29 bp ex-day
  drop-off the total-return layer exists to resolve.

| | price return | total return |
|---|---:|---:|
| shared ticker-days | 10,255,070 | 10,255,070 |
| within the sources' own rounding | 99.967 % | 99.958 % |
| within 10 bp | 99.792 % | 99.502 % |
| **within either bar** | **99.977 %** | **99.969 %** |
| tickers agreeing on every shared day | 92.11 % (3,256 / 3,535) | 84.10 % (2,973 / 3,535) |
| \|Δ log-return\| p50 | 2.65e-05 | 3.45e-05 |
| p99 | 4.53e-04 | 7.15e-04 |
| p99.9 | 1.38e-03 | 2.01e-03 |

By slice — the delisted names are the ones a survivor-only benchmark would never
have graded, and they are measurably the harder half:

| slice | tickers | ticker-days | price return | total return |
|---|---:|---:|---:|---:|
| live | 2,504 | 8,397,753 | 99.996 % | 99.994 % |
| delisted | 1,031 | 1,857,317 | 99.891 % | 99.855 % |
| pre-2015 | 2,273 | 4,199,804 | 99.954 % | 99.943 % |
| 2015+ (the reliability floor, `RELIABLE_START`) | 3,051 | 6,055,266 | 99.993 % | 99.987 % |

### The cash-dividend layer on its own

Differencing each source's total return against its own price return removes the
structural adjustment entirely and leaves only the dividend treatment. On the
same 10.26 M ticker-days the SEIBro layer reproduces FnGuide's dividend content
to **four thousandths of a percentage point per year**:

| | annualised mean TR − PR wedge |
|---|---:|
| ours (SEIBro events, 배당락일 under T+2) | +1.124 %/yr |
| FnGuide | +1.128 %/yr |

This is a real check rather than a restatement of the headline, because the two
dividend layers share no input: SEIBro's 권리배정 record against whatever FnGuide
licenses. On the sessions where both book a dividend, the two steps agree to a
median 3.8e-05, and 98.78 % of them land within 10 bp.

The count of *which* sessions carry a dividend cannot be read off FnGuide
directly: it rounds its two series to the won independently, so their difference
is nonzero on 58 % of sessions from rounding alone, at a median step of 0.000 %.
Coverage therefore has to be measured above that floor —
[below](#dividend-events-the-open-source-misses).

## What the benchmark found that the oracle gate could not

**59.8 % of all disagreement is one defect, and it is ours.**

| cause | price return | total return | all | share |
|---|---:|---:|---:|---:|
| ours frozen — stuck KRX oracle | 1,650 | 1,648 | 3,298 | 59.8 % |
| both move, methods differ | 530 | 1,325 | 1,855 | 33.7 % |
| ours frozen — other | 128 | 183 | 311 | 5.6 % |
| FnGuide frozen | 21 | 26 | 47 | 0.9 % |

A disagreement is not symmetric evidence. Where *our* return is exactly zero on a
session FnGuide priced a move, our series has been frozen by an override — the
fault is ours whatever FnGuide did — and that is two thirds of the residue.

**Cause.** KRX's 수정주가 endpoint serves a stuck **₩1,000,000** instead of the
level for a few heavily back-adjusted delisted names: 18,891 rows across 56
tickers, 0.212 % of the oracle. It is not a ceiling — the oracle carries values
to ₩24.8 M — so the artifact is identifiable by the exact repeated value.
`build_adjustment_factors` trusts the oracle over 등락률 whenever the two diverge
by more than `_ORACLE_RESET_TOL`, which is correct for the 거래재개 administrative
reset it was written for and wrong here: on a stuck run `oracle_gross == 1`, so
the test fires on **every session that moved more than 1 %**, and the override
replaces the exchange's real move with a non-move.

Worked case — 015390 엘앤씨피, 2005-01-07. marcap reports `ChangesRatio = −1.09`
(raw close 1,370 → 1,355), so `gross_cr = 0.9891`. The oracle reads ₩1,000,000 on
both sessions, so `oracle_gross = 1.0`, and `|1.0 − 0.9891| = 0.0109 >
_ORACLE_RESET_TOL = 0.01`. The override fires and the day is recorded as flat.
FnGuide priced −1.09 %. The same thing happens on 490 of that ticker's sessions,
and on 415–488 sessions each for 045470 and 064060 — the three account for half
of all disagreeing ticker-days in the benchmark.

**Why the existing gate is blind to it.**
[`validate_against_oracle.py`](validate_against_oracle.py) compares our adjusted
return to the KRX oracle. On exactly these sessions `adjust.py` *assigns* our
return from the oracle, so the two agree by construction and the check passes.
No amount of running it would surface this; only a source outside the loop can,
which is the argument for keeping this gate as well as that one.

**Proposed guard, not yet applied.** Decline the override where the oracle is
serving the stuck level — `oracle_gross` computed from a `krx_adj_close ==
1_000_000` endpoint is not evidence about the day's move — and fall through to
등락률, which is what the rest of the series already trusts. Applying it means
rebuilding `adj_factors.parquet` and re-running every number above, so it is
recorded here rather than done silently. Projected effect, from holding the
stuck-oracle rows correct:

| | now | with the guard |
|---|---:|---:|
| price return, days agreeing | 99.9773 % | 99.9942 % |
| total return, days agreeing | 99.9690 % | 99.9859 % |
| disagreeing ticker-days (PR / TR) | 2,329 / 3,182 | 598 / 1,451 |
| tickers agreeing on every day (PR) | 92.11 % | 92.33 % |

The per-ticker rate barely moves because only **9** tickers in the overlap are
affected. The defect is severe per name and narrow across names — which is
exactly the shape that survives an aggregate check.

## What remains

**Where the reconstruction is right and the paid series is not.** 008080,
2013-09-11: FnGuide reports a log return of **+11.11** — a 67,000× move, which is
67,000 ÷ ₩1, the resume day's 등락률 measured against a ₩1 non-trading sentinel.
We report zero, because the sentinel guard neutralises it. KRX's own 수정주가
carries the same artifact. This is the largest single disagreement in the
benchmark and the free series has it right; a benchmark is a reference, not an
oracle, and 47 ticker-days are FnGuide frozen where we moved.

**Undiagnosed: both series move and disagree on the size (1,855 days, 33.7 %,
538 tickers).** This class is not rounding — it cleared the rounding bar by
construction — and it is not small: median \|Δ\| 1.5 %, upper quartile 3.3 %. Nor
does it have the shape the stuck-oracle class has. It is spread across the whole
window rather than concentrated early (19.7 % in 2005–2007, with the largest
single years 2023 and 2025), and it is over-represented on delisted names: 64.4 %
of these days sit on tickers that later delisted, which carry only 18.1 % of the
shared ticker-days. Whether that points at series-break placement around
delisting, at 정리매매 sessions, or at something else is **not established here** —
1 day in 5,500 is undiagnosed residue, and it is the obvious place for the next
pass to start.

**Total return is harder than price return, and the gap is where it should be.**
TR agrees on 99.969 % of days against PR's 99.977 %, and 84.10 % of tickers
against 92.11 %. The difference is the dividend layer — the one component KRX
does not publish and the reconstruction has to build.

### Dividend events the open source misses

Measured above FnGuide's rounding floor at a 0.5 % step — an order of magnitude
above the ~2e-4 rounding noise on a mid-priced name, and below the smallest
ordinary payout:

| | sessions |
|---|---:|
| both sources book a dividend | 19,932 |
| FnGuide books one, SEIBro does not | 1,005 |
| SEIBro books one, FnGuide does not | 45 |

**SEIBro finds 95.2 % of the dividend sessions FnGuide books**, and where both
find one they agree on its size: median step 1.819 % against 1.825 %. So the
layer's weakness is *coverage*, not arithmetic — which matches how SEIBro's own
record thins out backwards. The
1,005 misses sit on 208 tickers and are concentrated in the early window: 265 of
them in 2005 alone, 101 in 2008, and 6 in 2025. This is the same collection limit
already documented in [`README.md`](README.md) ("Known limitations": 2000–2001
carry almost no amounts, and SEIBro refuses 1,303 rows of the 2004-12-31 window),
now priced against an outside source rather than self-reported.

The 45 in the other direction are a smaller and separate question — events
SEIBro records that FnGuide's series does not step on — and are left open.

## Reproducing

```bash
python -m fnguide_data.price_loader            # xlsx → cache/fnguide_price.parquet (~1 min)
python -m kr_marcap.validate_against_fnguide    # the benchmark above (~5 min)
python -m kr_marcap.validate_against_oracle     # the KRX-oracle gate (different question)
python -m kr_marcap.validate_dividend_events    # the five total-return checks
```

The last three need `cache/adj_factors.parquet` (`python -m kr_marcap.adjust
build`) and `cache/dividend_events.parquet` (`python -m
kr_marcap.dividend_events build`).

`validate_against_fnguide` writes a complete per-ticker table to
`cache/fnguide_validation.csv`, and the disagreeing days — worst first, each
labelled by cause — to `cache/fnguide_validation_days.csv`. The headline rates,
the stuck-oracle attribution and the benchmark's delisted coverage are pinned in
`test_assertions.py`, so a rebuild that degrades any of them fails the suite.
Each is pinned together with the population it is quoted over — 3,535 tickers,
10,255,070 shared ticker-days, 5,511 disagreeing ones. A rate is only a claim
about the reconstruction while the denominator is the one the table above used;
a validation run that reached a handful of names would carry a rate near
1.000 and no information, and the suite has to fail on it rather than print it.

## Open

- **The stuck-oracle guard is proposed, not applied.** Everything above is
  measured against the pipeline as it stands today, with the defect in it.
- **Nothing here grades levels, only returns.** That is the right comparison for
  return research and the only anchor-invariant one, but a study consuming
  adjusted *price levels* is not covered by any number in this file.
- **A third of the residue has no diagnosis.** The 1,855 "both move" days are
  measured but not explained; see [What remains](#what-remains).
- **The benchmark cannot be redistributed.** `Price data.xlsx` is licensed
  DataGuide output and is gitignored; the reconstruction and every script here
  are not, which is the point of the exercise.
- **This document does not yet have its paper.** The construction, the benchmark
  design, and the stuck-oracle finding are the material for one — see `memo`.
