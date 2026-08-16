# Korean adjusted prices — how we know they are right

An adjusted price series is **unfalsifiable by inspection**. A series that
half-removes an ex-dividend drop, removes it a day late, or removes it twice
plots as the same smooth line as a correct one. Nothing about the output says
which you are holding.

So every check below exists to answer one question: *what would have broken if
this were wrong?*

Method and failure modes for the Korean price layer are in
[`PRICE_ADJUSTMENT.md`](PRICE_ADJUSTMENT.md) and
[`CORPORATE_ACTIONS_SPEC.md`](CORPORATE_ACTIONS_SPEC.md). This file is about
**verification**, not construction.

## How Korea is put together

| | |
|---|---|
| **Structural adjustment** | KRX `ChangesRatio` compounded (`kr_marcap.adjust`) |
| **Cash-dividend layer** | SEIBro events, ex-date derived under KRX T+2 (`kr_marcap.dividend_events`) |
| **Exchange publishes a total-return factor?** | **No** — KRX 수정주가 is structural only |
| **Price-return series** | `adj_close` — free, it *is* `ChangesRatio` |
| **Total-return series** | `adj_close_tr` — derived by adding SEIBro cash |
| **Builder** | `kr_marcap.adjust.load_adjusted(…, total_return=True)` |

KRX splits the problem for you, publishing a structural-only factor and nothing
for cash. So Korea's `adj_close` is free and `adj_close_tr` is the derived one.

The series does not end at zero, and should not. Affected sessions are marked
with `is_ex_date` instead.

**There is a seventh check, and it is the strongest: the paid series itself.**
FnGuide DataGuide publishes both Korean conventions, so
`kr_marcap.validate_against_fnguide` scores the reconstruction directly against
the vendor it reproduces — 99.977 % (price return) and 99.969 % (total return) of
daily returns on 10.26 M shared ticker-days, delisted names included. It belongs
here as *verification* but is written up with the construction, in
[`CONSTRUCTION.md`](CONSTRUCTION.md), because what it mostly established was a
defect in the builder rather than a property of the output. Its one structural
lesson generalises to §3: a check against a source the builder *consumes* cannot
see the sessions where the builder assigns from it.

---

## 1. Is the input actually raw?

Adjusting an already-adjusted series double-counts, and the failure is silent.
This has to be settled before anything else.

Settled by the standing oracle gate against KRX official 수정주가 — see §3 below
and [`validate_against_oracle.py`](validate_against_oracle.py).

## 2. Does a derived date match the physical evidence?

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

## 3. Do two independent institutions agree?

Korea has no exchange-published total-return factor, so the check splits into
two, against two unrelated authorities.

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

## 4. Would a coding error survive?

Correct arithmetic can still be wrongly implemented. Two identities must hold
by construction and catch different classes of bug.

```
adj_close_tr == adj_close × tr_factor      → indexing / broadcasting errors
adj_close_tr[today] == close[today]        → normalisation / anchor errors
```

Both are exactly `0.000e+00` across spot-checked Korean payers (005930
quarterly, 000660, 033780 high-yield).

**Double counting** is checked separately, because the two factor chains must be
disjoint: 1,118 주식배당 events are excluded from the cash factor; they already
reset KRX's 기준가 and so live inside `ChangesRatio`. The 666 동시배당 events
contribute their cash leg only.

## 5. Did the contamination actually go away?

The final check is the one the whole exercise is for. Measured on the rows whose
forward return spans an event, over 2020–2024:

| event | affected rows | raw | total-return |
|---|---:|---:|---:|
| 배당락 | 0.219 % | −160 bp | **+82 bp** |

**Nothing lands on zero, and that is correct.** Prices fall short of the full
distribution — the Korean drop-off ratio is 0.663, stable across mass December
ex-dates (0.665) and scattered interim ones (0.643). The holder receives 100 %
of the cash, so a total-return series must add 100 %, and the difference is the
real ex-day tax/clientele effect. It is marked, not erased.

That row and that 0.663 are one measurement, taken on a downstream research
panel as a same-date payer-versus-non-payer contrast. Nothing in this repo
rebuilds them.

---

## The trap that cost a measurement

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

## Free parameters, and which ones are load-bearing

Every threshold below is a researcher choice. The rule applied is the repo's:
justify it, or delete it. One was deleted; the rest report their own sensitivity
rather than quote one level.

| parameter | where | status |
|---|---|---|
| delisting cut-off `> 2021-01-01` | DART split | **deleted.** It selected the recent, cleaner delistings and read 98.9 % where the whole calendar reads 96.3 %; it also mislabelled 360 pre-2021 rows as "still listed". No result needed it. |
| yield trim `TRIM_Q = 0.99` | ex-date localisation | **kept, sensitivity now printed.** Load-bearing for the *slope* — untrimmed −0.31 against −0.81 at any trim from the top 1 % to the top 10 % — but the check's actual claim (the drop sits on ex+0 and nowhere else) holds at every level. |
| tolerance `±0.5원` | DART DPS match | **kept, justified by the unit.** DPS is quoted in won, so this is "rounds to the same won", not a fitted band. |
| window `Y0, Y1 = 2020, 2024` | §2, §5 | **kept, justified.** Five full years ending before the 2024 배당절차 개선 dispersed record dates out of December. |
| `_SHORTFALL_TOL = 0.02` | SEIBro collection guard | **kept, weakest of the set.** The observed server-side count drift is ~0.4 %, so 2 % is a hand-picked 5× headroom. It only gates a fail-loud abort and touches no published number. |

**The step convention was a free parameter, and is no longer.** Korea now uses
the exact step, `1 + dps/close_ex`. The distinction is not cosmetic. A one-period
total return is `(P_ex + D)/P_cum`, so in *return* space the cum close is the
exact denominator and `ChangesRatio + dps/close_cum` is right, which is what the
payer-versus-non-payer check in §2 uses. But a back-adjustment factor composes
*multiplicatively* across time, and there the same step telescopes correctly only
with the ex close. Korea used the cum close and so understated the factor. On a
200-ticker sample (1,694 events) the correction is a median 0.88 bp per event and
a median 0.105 % compounded, but it scales as the yield squared, so the tail is
not small: q95 32.3 bp per event, and a maximum of 806 bp on one event and
+44.1 % compounded over a ticker's history, on the return-of-capital payers whose
yields run to tens of percent.

## Reproducing

```bash
python -m kr_marcap.validate_dividend_events    # dividend-layer checks, read-only, ~1 min
python -m kr_marcap.validate_against_oracle     # structural vs KRX 수정주가 (§3)
python -m fnguide_data.price_loader             # FnGuide 수정주가 export → parquet
python -m kr_marcap.validate_against_fnguide    # both conventions vs FnGuide
python -m kr_marcap.dividend_events             # Samsung quarterly ex-date demo
```

## Open

- **The §5 row has no generator in this repo.** The −160 bp / +82 bp pair is
  same-date payer versus non-payer across the 23 ex-dates in the window,
  measured once on a downstream research panel rather than on `marcap/`, which
  is why nothing here rebuilds it. It is the only number in this document a
  re-run would not catch drifting.

  Three estimators of the same ex-day drop-off are in play and none of them is a
  reading of another. The published 0.663 is that same-date contrast over all 23
  ex-dates. Check [3] runs the identical contrast restricted to the December
  session alone and reads −155 bp / +71 bp. A third — mean raw against mean
  `ChangesRatio + dps/close_cum` over affected rows, no payer/non-payer
  differencing at all — reads −73 bp / +145 bp on 0.209 % of
  rows, a ratio of 0.33, while check [1]'s cross-sectional slope reads 0.81
  trimmed and 0.31 untrimmed. The affected-row share is the one quantity all of
  them agree on. Quote the estimator with the number, always.

  The step-convention change above is not a candidate explanation for any of the
  gaps: on a 400-ticker measurement of the multiplicative path it moves the mean
  total return on ex rows by +5 bp.
- **2004 dividend coverage is partial** — SEIBro refuses 1,303 rows of
  the 2004-12-31 window. Reported by the build rather than silently dropped;
  see the defect table in [`README.md`](README.md).
- **Capital reductions are not separable.** `ChangesRatio` folds them in with
  everything else structural, so whether they carry a larger per-event
  distortion than ordinary structural events cannot be checked with what is
  built.
