# Price adjustment — method, failure modes, and diagnosis

How `kr_marcap.adjust` turns raw KRX marcap prices into a continuous,
corporate-action-adjusted series, the silent-fabrication failure modes that were
found and fixed, and the residual large returns that are **real and kept on
purpose**.

All code lives in `kr_marcap/adjust.py` (`build_adjustment_factors`,
`load_adjusted`); the materialised factors are `kr_marcap/cache/adj_factors.parquet`.
Loaders that consume them (`kr_marcap/market_loader.py`) drop `valid == False`
rows. Prices in `marcap/` and `kr_delisted/` stay **unadjusted**; use the
adjusted series only when you need a continuous line through splits / 무상증자 /
감자 / 액면병합.

---

## TL;DR

| | |
|---|---|
| **Adjustment input** | KRX `ChangesRatio` (등락률), compounded — *not* `close/prev_close` |
| **Why** | `ChangesRatio` is computed against KRX's corporate-action 기준가, so it already absorbs splits, 무상/유상증자, and 감자 — including cases a shares-outstanding ratio misses |
| **Shares ratio role** | Detects *entity changes* (SPAC merger / reverse listing / ticker reuse) only — never used for the price adjustment itself |
| **Worst valid \|adj_ret\| before fixes** | **66,999×** (008080, a ₩1-sentinel fabrication) |
| **Worst valid \|adj_ret\| after fixes** | **29.46×** (003260, a *real* 거래재개 after a month-long halt) |
| **Returns neutralised** | only moves that **did not trade**: entity-change breaks, ₩1 sentinels, phantom-CR no-trade days |
| **Returns kept** | every move that traded — relisting/거래재개 first days, the 2015 우선주 품절주 mania, penny-stock limit-up runs |

The guiding principle, applied everywhere below: **a price change that did not
trade is not a realized return.** Conversely, an extreme move that *did* trade is
real data and is left intact, however ugly.

---

## 1. The method: compounding `ChangesRatio`

For each ticker the back-adjusted close is built by compounding the exchange's
official daily return:

```
adj_close[t] / adj_close[t-1] == 1 + ChangesRatio[t] / 100
```

anchored so the **last traded day's** `adj_close` equals its raw close, and
`cum_factor = adj_close / raw_close` is stored for loaders.

Why `ChangesRatio` and not `close / prev_close`? Because KRX computes
`ChangesRatio` against the corporate-action **기준가**, so on a corporate-action
day it is *not* equal to `close / prev_close`:

- **Samsung 005930, 2018-05-04 (50:1 split):** raw close drops ~2,650,000 →
  ~53,000. A naïve `close/prev_close` would read **−98%**; KRX's `ChangesRatio`
  is instead a small ordinary number, so `cumprod(gross)` stays continuous
  through the split. This is the entire reason the method works.

**Invariant.** On any day where no `gross` override fires (see §3),
`gross[t] = 1 + ChangesRatio[t]/100`. On *ordinary* (non-corporate-action) days
this happens to equal `close[t]/close[t-1]`, so `cumprod(gross) ∝ raw close` and
adjusted returns between two trading days equal raw returns. The adjustment only
*departs* from raw on corporate-action days (where `ChangesRatio` is the correct
one) and on the override days below.

**Known level drift.** `ChangesRatio` is rounded to 0.01%, so compounded price
*levels* carry a tiny drift; daily and h-day *returns* (the pipeline's actual
inputs) are unaffected beyond ~1e-4 because the anchor cancels.

---

## 2. Entity-change detection (`is_break`)

The shares-outstanding (`Stocks`) ratio is used **only** to detect entity
changes, never for the adjustment:

```
ratio[t] = Stocks[t-1] / Stocks[t]
```

- A ratio outside `[0.1, 10]` (`_RATIO_FLAG_LOW/HIGH`) is a **big jump** —
  candidate split or entity change.
- It is a *genuine* corporate action only if the **same-day price moved
  inversely** to the share count, i.e. the residual adjusted return it would
  inject is near zero. Empirically (2026-06 diagnosis) genuine actions leave
  `|residual| ≤ 0.495` and entity changes leave `|residual| ≥ 0.522`, so
  `_CORROBORATION_TOL = 0.5` separates them cleanly.
- A **non-corroborated** big jump is an `is_break`: the listing changed hands
  (SPAC merger, reverse listing, ticker reuse). Every row **strictly before a
  ticker's last break** is marked `valid = False`; loaders drop it, because that
  history belongs to a different entity (the pre-merger shell / a prior listing).

---

## 3. `gross` overrides — the complete list

`gross` is overridden (the compounded `ChangesRatio` is not used) when **any** of
these holds — set to `1.0` (no compounding) for the first six, and to the **traded
close move** `1 + raw_ret` for the last:

| override | condition | gross → | rationale |
|---|---|---|---|
| first row | `ChangesRatio` is NaN | `1.0` | no prior day |
| garbage | `gross ≤ 0` | `1.0` | non-positive return is not meaningful |
| entity break | `is_break` (§2) | `1.0` | the move spans two different entities; pre-break history is dropped anyway |
| no-trade ₩0 | `Close ≤ 0` | `1.0` | a ₩0 no-trade row carries no price |
| **₩1 sentinel** | `prev_close == 1 & prev_volume == 0` | `1.0` | §4 |
| **phantom CR** | `volume == 0 & close carried flat & \|CR\| > 1 & no share change` | `1.0` | §5 |
| **거래재개 reset** | in-band modest share change + resume-day volume explosion + CR differs from the traded move | `1 + raw_ret` | §5b |

The last three are the silent fabrications this diagnosis found. The first four
predate it.

---

## 4. Failure mode 1 — the ₩1 ticker-reuse sentinel (008080)

**Symptom.** `load_adjusted('008080')` produced a single **+6,699,900%**
adjusted return (global worst `|adj_ret|` of 66,999×).

**Mechanism.** 008080 is a ticker-reuse boundary. Some marcap vintages fill a
suspension / relisting gap with **`Close == 1, Volume == 0`** placeholder rows.
The first real trade after the gap then carries a `ChangesRatio` computed against
that ₩1:

```
008080  2013-09-11 resume:  Close 67000,  Volume 44663,  ChangesRatio = 6,699,900  (= 67000 / 1)
```

The entity break is correctly detected at the **start** of the sentinel block
(the `Stocks` jump), so the resume day itself is *not* flagged as a break — and
its garbage `ChangesRatio` escapes the break guard and compounds into a +6.7M%
step.

**Fix.** Neutralise the resume of a ₩1 sentinel:
`sentinel_prev = (close_prev == 1) & (vol_prev == 0)` → `gross = 1`.

**Why it is narrow (1 row of impact).** Only ₩1 placeholders trigger it:

- A **₩0** sentinel is different — KRX measures the resume `ChangesRatio` against
  the real 기준가, so that return is genuine and is left alone.
- A **same-day** entity break like 052670 (the resume *is* the break day) is
  already neutralised by `is_break`.

**Result.** Global worst valid `|adj_ret|` fell **66,999 → 29.46**; Samsung's
split and the 008080 loader both verified clean.

---

## 5. Failure mode 2 — phantom `ChangesRatio` on carried-flat no-trade days (016600)

**Symptom.** Adjusted returns that *straddle* certain 1990s dates were skewed by
a constant factor with no visible jump on any trading day.

**Mechanism.** On some no-trade days marcap records a large nonzero
`ChangesRatio` while the close is **carried flat** — the `ChangesRatio` field is
simply wrong (a par-value-era data error), not a real move:

```
016600  1998-01-05:  Close 2960 → 2960 (flat),  Volume 0,  Stocks unchanged,  ChangesRatio = -68.31
```

Compounding `gross = 0.317` here injects a phantom ×0.317 into the **entire
pre-date history**, so a return computed across 1998-01-05 was off by ~3×.

**Fix.** A nonzero `ChangesRatio` on a no-trade day whose close was carried flat,
with no share-count change, is a data error → `gross = 1`:

```python
phantom_cr = (volume == 0) & (|close/close_prev - 1| < 0.005)
             & (|ChangesRatio| > 1) & (ratio ≈ 1 or unknown)
```

**Scope of the fix.** It neutralises **77 rows across 75 tickers**, `|CR|` from
1.01 to 637.74 — **all pre-2004** (78% in 1998, the par-value-restatement era),
**zero post-2010**. The distortion was therefore confined to cross-1990s returns
on long-delisted micro-caps, entirely outside the post-2004/post-2010
KOSPI+KOSDAQ common research window. It is fixed anyway so a long-horizon series
is not silently skewed.

**Why it is zero-regression.** The guard fires only when the close is *flat*, so
it cannot touch any real-volume return or the much larger class of correct
no-trade reference resets in §6.

---

## 5b. Failure mode 3 — the 거래재개 administrative 기준가 reset (232830, 448900)

**Symptom.** Surfaced by extending the FnGuide cross-check below the `max_abs > 1`
splice band: a class of **currently-listed common** names whose adjusted returns
disagreed with FnGuide by **10–93 %** on a single post-2015 day — and whose entire
pre-event history was mis-scaled as a result.

**Mechanism.** On a **거래재개** (resume after a suspension) KRX may compute
`ChangesRatio` against an administrative **evaluation reference price**, not the
corporate-action 기준가. So the CR diverges from the actual traded close move, while
the share count moved only modestly:

```
232830 아이티센피엔에스  2023-06-29:  Close 7,570 → 9,150 (traded +21 %),  ChangesRatio = +205.00,  Stocks ×1.21
448900 한국피아이엠      2025-04-04:  Close 19,590 → 16,100 (traded −18 %), ChangesRatio = +43.75,  Stocks ×1.18
```

The modest `Stocks` change keeps the ratio inside `[0.1, 10]`, so the §2
entity-break test never fires; the day follows no >365-day gap, so the gap test
never fires; and the day *traded*, so none of the §3–§5 no-trade overrides apply.
Compounding `gross = 1 + 205/100 = 3.05` instead of the +21 % real move injects a
**×2.52 factor into all pre-2023-06-29 history** for 232830 (pre-event prices
scaled to ×0.40 of FnGuide's).

**Fix.** Trust the **traded close move** on these days: `gross = 1 + raw_ret`. The
signature is a **resume-day volume explosion** (`volume / trailing-5d mean >
_RESET_VOL_SPIKE = 30`) + an **in-band modest share change**
(`_RESET_SHARE_MIN < |ratio − 1| < _RESET_SHARE_MAX`) + a CR that **materially
differs** from the traded move (`|gross_CR/(1+raw_ret) − 1| > _RESET_DIVERGE`).

**Why the volume explosion is the discriminator.** A naive "CR ≠ traded move →
distrust CR" would destroy genuine corporate actions (Samsung's split *is* a
CR ≠ close/prev day). The clean separator is that genuine same-day splits / free
issues / 감자 do **not** trade on a 30× volume spike (and their CR is correct
anyway), whereas a 거래재개 does. Samsung's 50:1 (`ratio` ×50, out of band) and
entity breaks (`is_break`) are excluded outright.

**Calibrated and verified against FnGuide ground truth (2026-06).** On **68 / 68**
currently-listed-common candidate days, FnGuide's adjusted return equals the raw
traded move *exactly* — i.e. FnGuide applies no factor on these days, so the
override matches it every time, with **zero** cases where FnGuide instead applied a
real factor. After the fix the post-2015 FnGuide disagreement bands collapse:
`> 0.3`: **12 → 0**; `0.1–0.3`: **35 → 1**; names agreeing to <1 % on every day:
**94.1 % → 96.5 %**. No name's agreement got worse; the splice count (3 full-
history / 0 post-2015) and Samsung's split are unchanged. (The 2 residuals are not
resets: 089590 제주항공 is a 2015-11-09 IPO-week artifact, 219420 a 0.07
sub-threshold case.)

---

## 6. The critical contrast — what is *not* a bug

Two no-trade-day signatures look superficially alike but need **opposite**
treatment. The discriminator is *which field is the culprit*:

| signature | example | `ChangesRatio` | close | current behaviour | verdict |
|---|---|---|---|---|---|
| **phantom CR** | 016600 1998-01-05 | **−68.31** (nonzero) | 2960 → 2960 (flat) | compounds ×0.317 | **bug → fixed (§5)** |
| **reference reset** | 267060 2017-09-28 | **0.00** | 18300 → 5980 (moved) | `gross = 1`, `adj_ret ≈ 0` | **correct — kept** |

For the reference-reset case KRX's official 등락률 is **0** — KRX itself records
"no return"; the close-print change is an administrative 기준가 reset (e.g. a
거래정지 re-evaluation). Trusting `ChangesRatio = 0` (the current behaviour) is
right, so these are left untouched. Of the 17 *post-2010* no-trade reprice rows,
16 are this benign `CR ≈ 0` kind and 1 is the isolated ambiguous row in §8 —
**none is a carried-flat phantom-CR error, so the §5 fix changes zero post-2010
rows.**

A third no-trade signature, the **016397-type reference print** (close steps up
on a Volume-0 day *and* `ChangesRatio` matches that step, e.g. +593%), is
faithful to raw and sits on a non-tradeable day, so it is excluded by any
volume/liquidity filter and left alone.

Across the 813 no-trade rows where `ChangesRatio` disagrees with the actual close
move:

- **519** are reference resets (`CR ≈ 0`, close moved) → correct, kept.
- **214** are ambiguous (both move, disagree) — 213 pre-2010, 1 isolated 2014
  row; left alone rather than guessed (see §8).
- **80** are carried-flat phantom-CR errors → 77 neutralised by §5 (the 3-row
  gap are slightly-non-flat rows conservatively classed ambiguous, not phantom).

---

## 7. The residual large adjusted returns are *real*

After the §4–§5 fixes, the largest surviving adjusted returns on `valid` rows are
genuine market events. Counts on `valid & adj_close > 0` rows (14,840,281):
`|adj_ret| > 2.0`: **45**; `> 1.0`: **121**; `> 0.5`: **1,486** — of the 1,486,
**1,476 traded on real volume** and only 10 sat on zero-volume days (down from 16
before the §5 phantom-CR fix).

Worst offenders, all real:

| code | date | adj_ret | what it is |
|---|---|---|---|
| 003260 | 2002-04-09 | 29.46 | 거래재개 after a month-long halt; resumes on 39,311 vol, settles ~10,000 |
| 018570 | 2002-04-29 | 8.63 | same class — halt → resume |
| 103650 | 2016-07-07 | 8.60 | penny-stock limit-up sequence |
| 008705 | 2015-07-06 | 6.31 | **2015 우선주 품절주 mania** — 128,000 on 47,457 real volume, then collapse |
| 225860/225850 | 2022-04-20 | 7.00 / 6.33 | 거래재개 with no price limit |

In every case `ChangesRatio == close/prev_close − 1` exactly (no mis-measured
corporate action), the prior price is a legitimate traded/carried reference, and
real volume changed hands. These are **faithfully reflected and intentionally
kept** — suppressing them would be fabricating *away* real data.

---

## 8. Deliberately not neutralised

- **Real extreme returns (§7).** Relisting/거래재개 first days (no price limit)
  and the 품절주 mania. Real volume, real prices.
- **No-trade reference resets with `CR = 0` (§6).** KRX records no return; trusting
  it is correct.
- **016397-type no-trade reference prints (§6).** Faithful to raw, non-tradeable,
  excluded by volume filters.
- **Ambiguous no-trade rows (§6).** e.g. 032560 1998-01-05 — close moved −7.9%
  *and* `ChangesRatio = −56.19`; both nonzero and contradictory. Resolving which
  is right needs external KRX/DART corporate-action data (and the host is
  edge-blocked from `data.krx.co.kr`), so these are left as-is rather than
  guessed. 213 of 214 are pre-2010; the one post-2010 case (124500, 2014-03-05)
  is a single isolated row.

---

## 9. Verification / reproduction

All checks are ad-hoc (no CI). Rebuild factors, then re-run the scans:

```bash
source /home/st/miniconda3/bin/activate
python -u kr_marcap/adjust.py build        # ~35s → kr_marcap/cache/adj_factors.parquet
```

Key assertions confirmed after the fixes:

- Global worst valid `|adj_ret|`: **29.46** (003260), down from 66,999.
- 008080 max valid `|adj_ret|`: **0.795** (was 66,999).
- 016600 cross-1998 return corrected: `adj_ret 0.1390 → 0.4386` (== raw).
- 267060 reference reset unchanged: `adj_close 3754.4 → 3754.4` (no phantom).
- `phantom_cr` fires on exactly **77 rows / 75 tickers**, all pre-2004.
- Samsung 005930 50:1 split still continuous (`python kr_marcap/adjust.py`).
- `reset_cr` (§5b): 232830 2023-06-29 `adj_close` now flows 7,570 → 9,150 (the
  +21 % traded move) with `cum_factor ≈ 1.0` — no ×2.52 pre-event step; FnGuide
  post-2015 disagreement `> 0.3` band **12 → 0**, no name worse.

---

## 10. Summary of changes

- `sentinel_prev` guard — neutralises ₩1 ticker-reuse sentinel resumes (§4).
- `phantom_cr` guard — neutralises carried-flat phantom-`ChangesRatio` no-trade
  days (§5).
- `reset_cr` guard — on a 거래재개 administrative-reference reset, uses the traded
  close move instead of the divergent CR (§5b); FnGuide-calibrated, 68/68 exact.
- All extend one principle: **the realized return is the one that traded** — the
  no-trade cases compound nothing (`gross = 1`); the 거래재개 reset, which *did*
  trade, compounds the traded move (`gross = 1 + raw_ret`) rather than the CR
  measured against an administrative reference.

No research-impacting fabrication remains in `load_adjusted`. The residual large
returns are real market events; the only genuinely defective class (phantom CR)
was pre-2004 and out of the research universe, and is fixed regardless.
