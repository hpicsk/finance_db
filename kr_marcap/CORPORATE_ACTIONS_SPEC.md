# Corporate-action ground truth — replacing the calibrated adjustment heuristics

This is the runbook for the de-heuristicised price adjustment. The old
`kr_marcap/adjust.py` decided **entity breaks** and **거래재개 resets** from
constants tuned to a validation set (`_CORROBORATION_TOL=0.5`, `_GAP_DAYS=365`,
`_RESET_VOL_SPIKE=30`, …). Those are gone. Every break/reset verdict now comes
from an **official source**; the only numbers left are rounding/materiality
bounds (documented inline), never classification thresholds.

---

## TL;DR — what grounds what

| Old heuristic (removed) | Official replacement | Source | Reachable from dev host? |
|---|---|---|---|
| `_CORROBORATION_TOL` (split vs entity) | DART 회사합병/분할/주식교환 events + SPAC-name transition | DART API, marcap `Name` | ✅ |
| `_GAP_DAYS` / `_GAP_*` (reuse behind a gap) | KIND delisting + marcap re-appearance | `kr_delisted/delisting_calendar.csv` | ✅ |
| `_RESET_*` (거래재개 admin reset) | KRX 수정주가 oracle divergence | pykrx (`krx_adj_oracle`) | ✅ |
| manual FnGuide cross-check | automated oracle validation gate | pykrx | ✅ |
| (kept — *not* calibrated) | ₩1-sentinel & phantom-CR data-integrity guards | marcap structure | n/a |

**Only one source is blocked from this host:** `data.krx.co.kr` (거래정지/거래재개),
and it is **not needed** — the oracle already resolves resets, and marcap's
`ChangeCode == '0'` already flags halt *days* (see `kr_status/marcap_halt_infer.py`).
Only the official halt *reason* text lives behind `data.krx.co.kr`; no in-repo
collector ships for it, and it would require a KR-resident IP.

---

## Components

| File | Role |
|---|---|
| `kr_status/dart_corp_actions.py` | DART event collector → `kr_status/data/dart_corp_action_events.parquet` |
| `kr_marcap/krx_adj_oracle.py` | KRX 수정주가 collector → `kr_marcap/cache/krx_adj_oracle.parquet` |
| `kr_marcap/corp_actions.py` | assembles entity-break calendar (SPAC ∪ reuse ∪ DART-entity ∪ override) |
| `kr_marcap/adjust.py` | consumes the above; builds `adj_factors.parquet` |
| `kr_marcap/validate_against_oracle.py` | automated gate vs KRX 수정주가 |
| `kr_marcap/corp_action_overrides.csv` | reviewed manual overrides (residuals) |

---

## Refresh runbook

DART events and the oracle are **per-ticker** fetches; both collectors are
resume-safe (re-running skips cached tickers). The build is a **two-pass
bootstrap** because the DART collector keys off the share-jump candidate list
that the build itself writes.

```bash
source /home/st/miniconda3/bin/activate
export OPEN_DART_API_KEY=...            # already in .env

# ── Pass 0: seed the candidate list (uses whatever sources exist now) ─────────
python -m kr_marcap.adjust build        # writes cache/adjust_anomalies.csv (candidates)

# ── 1. DART corporate-action events (official entity/genuine classification) ──
#    Scope = the candidate tickers (material ≥10× share jumps); ~550 tickers. This
#    IS the complete set corp_actions.classify reads: it consults DART events only
#    on days whose share-count ratio is outside [0.1, 10.0] — the same band that
#    defines the candidate list — so events for any other ticker are never queried.
python -m kr_status.dart_corp_actions             # resume-safe; ~25-40 min
#    NB: `--all-universe` exists but does NOT change the adjustment output (it
#    fetches ~3,800 tickers classify never queries) and would overflow DART's
#    ~20k/day quota; don't run it for coverage.

# ── 2. KRX 수정주가 oracle (reset detection + validation) ─────────────────────
python -m kr_marcap.krx_adj_oracle --candidates   # ~10 min for the candidate set
#    Full universe (long-running, ~1-2 h) — needed for whole-market reset coverage:
#    python -m kr_marcap.krx_adj_oracle --all

# ── 3. Rebuild factors with official ground truth ────────────────────────────
python -m kr_marcap.adjust build

# ── 4. Validate against KRX official 수정주가 (replaces manual FnGuide check) ──
python -m kr_marcap.validate_against_oracle
#    review cache/oracle_validation.csv — any disagreement is a missed reset/break
#    or an oracle artifact; add real misses to corp_action_overrides.csv and rebuild.
```

Re-running step 2 with `--all` widens the oracle's validation coverage (the build
and validation are cheap to repeat). Step 1's `--all-universe` does NOT change the
adjustment output — see the note above — so there is no coverage reason to run it.

---

## How a share-count change is classified (no thresholds)

`corp_actions.classify(marcap)` walks each ticker's material share-count changes
(ratio outside `[0.1, 10.0]` — a coarse *materiality* floor, not a decision) and
labels each from official sources, in precedence order:

1. **SPAC merger** — `Name` went `…스팩…` → real company ⇒ **break** (`spac`).
2. **Ticker reuse** — code had a genuine KIND delisting and trades again ⇒
   **break** at re-appearance (`reuse`).
3. **DART entity event** (회사합병/회사분할/회사분할합병/주식교환) within the
   filing→effect window ⇒ **break** (`dart_entity`).
4. **Override** `kind=break` in `corp_action_overrides.csv` ⇒ **break**.
5. **DART genuine event** (유상/무상/유무상증자, 감자) ⇒ **genuine** (CR adjusts; not a break).
6. **Else** ⇒ **residual**: 액면분할/병합 (not in DART's event API) and true
   unknowns. Defaults to *not a break* (the ChangesRatio backbone stays
   continuous); written to `cache/corp_action_residuals.csv` for review. The
   oracle validation (step 4) is the safety net that flags a residual that was
   actually a missed break.

Breaks set `valid=False` for all rows before a ticker's **last** break, exactly
as before — loaders (`kr_marcap/market_loader.py`) drop them.

---

## The 거래재개 reset, via the oracle

A reset day is found by comparing our compounded-ChangesRatio daily return to
KRX's own official adjusted daily return on the same two trading days
(`krx_adj_oracle.parquet`). Where they disagree beyond CR's 0.01 % rounding
(`_ORACLE_RESET_TOL = 0.01`) and no data-integrity guard fired, the official
move is trusted (`gross = oracle_gross`). On ordinary and genuine
corporate-action days the two series agree, so the override never fires there;
where the oracle is uncovered (pre-2016, some preferred/SPAC shells) nothing
fires and the ChangesRatio backbone stands.

Coverage measured 2026-06-23 (oracle now run `--all`: **3995 tickers, 8.9M rows,
1996–2026**, incl. delisted). pykrx 수정주가 serves currently-listed names from
~2014 only (a ~3000-row / ~12-year cap; pre-2014 is **not** served and date-
chunking does **not** recover it — verified) and the **full archived life** of
names delisted well before 2014 (e.g. back to 2000). The oracle is itself dirty
on ₩1 ticker-reuse sentinels (008080); those are pre-empted by the deterministic
₩1-sentinel guard, which takes precedence. The unadjusted (raw) pykrx path is
blocked from this host (`data.krx.co.kr` 403) — marcap is the raw-price source.

---

## Validation results (full universe, 2026-06-23)

`validate_against_oracle.py` cross-checked **all 3995 tickers the oracle covers**
(currently-listed + delisted) against KRX official 수정주가 — comparing our
compounded-ChangesRatio daily return to KRX's own adjusted daily return on every
shared trading day (`--tol 0.02`).

**Result: 6 disagreeing days across 6 tickers — 99.8 % of tickers agree on every
shared day.** All six are benign (our side correct, or a non-target security),
not adjustment errors:

| ticker | type | day | what it is | verdict |
|---|---|---|---|---|
| 008080 | common | 2013-09-11 | ₩1 ticker-reuse sentinel; KRX serves the 66,999× ₩1→₩67,000 jump | our ₩1 guard zeroes it — **we beat KRX** |
| 004147 / 004149 | preferred | 2008-05-20 | never-traded 전환상환우선주 (Vol=0 for life); the Naver-sourced 수정주가 (pykrx) stored the **split-unadjusted** pre-split mark ₩41,000 and `validate` differenced it against the post-split ₩8,200 across a 5-month gap → spurious −80 %. Real event: the 5:1 split of 2008-05-09 (shares ×5, mark ÷5). | our flat ₩8,200 *is* the split-adjusted 수정주가; **oracle artifact, non-target** |
| 013650 데코 | common | 2001-07-27 | Vol=0 day, inconsistent CR (+5.53 % on a flat ₩12,400); the real 2:1 lands next session | **phantom-CR guard** correctly zeroes it |
| 081200 / 090980 | 선박투자펀드 | 2009-03-23 | illiquid ship-fund mark-to-reference prints; ±2 % just over tol, KRX records 0 | benign, marginal |

Independently, a direct return-level spot check on 6 delisted names (incl. a SPAC
and a 2009 delisting back to 2000) agreed with pykrx 수정주가 to `max|Δret| < 1 %`,
`corr = 1.00` — confirming the delisted adjustment is correct, not just the
currently-listed part.

Reproduce:

```bash
python -m kr_marcap.krx_adj_oracle --all        # 3995 tickers, ~1.5 h, resumable
python -m kr_marcap.adjust build                 # rebuild factors with the full oracle
python -m kr_marcap.validate_against_oracle      # -> cache/oracle_validation.csv
```

**Coverage caveat:** the pre-2014 window of long-lived currently-listed names is
not served by pykrx, so it stays validation-uncovered — marcap is the price
source there regardless. Delisted names (88 % of genuine-common delistings,
delisted ≥~2009) are fully covered and all agree to rounding.

---

## Residuals & overrides

`cache/corp_action_residuals.csv` lists material share jumps no official source
explained. Most are benign 액면분할/병합 (default not-break is correct) — confirm
with the oracle validation. For a residual that the oracle shows is a real break
(its pre-jump series is scaled differently from KRX's), add a row to
`corp_action_overrides.csv`:

```csv
ticker,date,kind,note
013890,2019-10-30,break,reverse-listing not in DART event API
```

`kind ∈ {break, genuine}`. Overrides are version-controlled and reviewed — the
audit trail that replaces a runtime guess.
