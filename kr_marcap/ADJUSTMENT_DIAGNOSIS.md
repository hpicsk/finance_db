# Price adjustment: Stocks-ratio failure & ChangesRatio migration

**Status:** code changed in `adjust.py` / `market_loader.py` (verified on a temp
build); canonical `cache/adj_factors.parquet` and all downstream consumers
**pending regeneration**.

**Date:** 2026-06

## TL;DR

The original price adjustment built `cum_factor` from the **shares-outstanding
(`Stocks`) ratio**, assuming every share-count change is matched by an inverse
price move. That holds for splits / 무상증자 / 감자 but **fails for entity
changes** (SPAC mergers, reverse listings, ticker reuse) and for corporate
actions where the `Stocks` update and the price reset land on different days.
The failures inject fake returns up to **+1504 %** in a single day.

The fix (decision "B2"):

1. **Adjust prices from the exchange's official daily return `ChangesRatio`
   (등락률)** instead of the `Stocks` ratio. KRX computes 등락률 against the
   corporate-action 기준가, so it already absorbs splits, 무상/유상증자, and 감자
   correctly — including the cases the `Stocks` ratio misses.
2. **Keep the `Stocks` ratio only as an entity-change detector.** A big `Stocks`
   jump *not* corroborated by an inverse price move is a **series break**: the
   pre-break history belongs to a different entity (e.g. the pre-merger shell)
   and is dropped (`valid=False`).

Verified effect (2018–2024 common-stock universe, daily return `R_t`):

| metric | old (Stocks-ratio) | new (ChangesRatio) |
|---|---|---|
| max `R_t` | 18.65 (+1865 %) | **7.00** |
| `#  \|R_t\| > 3` | 116 | **8** |
| max `R_t20` (20d fwd) | 39.99 | **15.41** |
| `#  \|R_t20\| > 3` | 2318 | **640** |

The 8 residual `R_t > 3` are **not** glitches — each equals the exchange's own
`ChangesRatio` exactly (penny-stock relistings the exchange itself reported as
+400 % … +700 %).

---

## 1. The bug

`cum_factor` came from

    ratio[t]      = Stocks[t-1] / Stocks[t]
    cum_factor[t] = product of ratio[s] for s > t      (back-adjusted)

The implicit assumption is **price moves inversely to share count**. When the
share count changes for a reason that does *not* reset the price proportionally,
the factor injects a spurious return on the transition day.

Two failure classes (both invisible to the `[0.1, 10]` anomaly band):

- **Entity change** — a different company takes over the listing. Shares jump,
  price does not.
- **Missed corporate action** — a 감자 / 액면병합 whose `Stocks` update lags the
  price reset by a day, or whose ratio lands just inside `[0.1, 10]`. The price
  jumps on the 기준가 reset; the factor stays ~1 and never adjusts it.

### Canonical example — 카이노스메드 284620 (SPAC merger)

| date | name | raw close | Stocks | Stocks ratio | ChangesRatio |
|---|---|---|---|---|---|
| 2020-06-05 | 하나금융11호스팩 | 4750 | 5,401,000 | 1.00 | +9.20 % |
| 2020-06-08 | 카이노스메드 | 4015 | 102,458,042 | **0.0527** | **−15.47 %** |

A SPAC shell became the operating company. `Stocks` jumped ×18.97; the raw price
moved only −15.47 % (the real economic move, matching `ChangesRatio`). The old
factor scaled the shell-era prices down ×0.0527, so the adjusted series jumped

    adj_close[06-08] / adj_close[06-05] = 4015 / (4750 × 0.0527) ≈ 16.04  →  +1504 %

a fabricated daily return. The shell's pre-2020-06-08 prices (하나금융11호스팩)
also reflect none of 카이노스메드's fundamentals.

### Downstream impact

After the panel's `D ≠ 0` (capacity-bound institutional flow) filter, the
adjusted-close returns still carried `R_t` up to **+1420 %** and `R_t20` up to
**+3598 %**, and the main return-prediction regressions consume them
**un-winsorized** — a handful of +1400 % observations is enough to bend OLS
coefficients and t-stats.

---

## 2. Why "just drop the anomalies" is wrong

The anomaly sidecar holds 921 flagged rows across 535 tickers. **457 of them are
genuine large splits** — including Samsung Electronics' 50:1 split
(005930, 2018-05-04, `ratio = 0.02`). Neutralising all anomalies would break
every real split.

The distinguishing signal is whether the price moved inversely to the shares.
For a big-jump `ratio`, the residual return the factor would inject is

    adj_ret = (1 + raw_ret) / ratio − 1

- **≈ 0** → price moved inversely → genuine split (keep).
- **large** → share count changed without a matching price move → entity change.

| ticker | event | raw_ret | ratio | adj_ret | verdict |
|---|---|---|---|---|---|
| 005930 Samsung | 50:1 split | −98.0 % | 0.02 | **−2.1 %** | real → keep |
| 284620 Kainos | SPAC merger | −15.5 % | 0.053 | **+1504 %** | entity change |
| 005770 | shares ×3407, price flat | 0 % | 0.0003 | **+340 700 %** | entity change |

The split is **clean at `_CORROBORATION_TOL = 0.5`**: genuine actions leave
`|adj_ret| ≤ 0.495`, entity changes leave `|adj_ret| ≥ 0.522`.

---

## 3. The fix (B2)

### 3a. Adjust from ChangesRatio

`adj_close` is built per ticker by compounding the exchange daily return:

    gross[t]      = 1 + ChangesRatio[t]/100
    adj_close[t]  = anchor × cumprod(gross)[t] / cumprod(gross)[anchor]

where `anchor` = the last **traded** (raw close > 0) row, so the latest
`adj_close == raw close` (back-adjusted convention preserved). `cum_factor =
adj_close / raw_close` is stored for the loaders.

`gross` is forced to `1.0` (no compounding) on: NaN ChangesRatio (first row),
non-positive/garbage values, no-trade rows (`Close ≤ 0`), and entity-change
break days. `cum_factor` is `NaN` on no-trade rows (loaders drop them via the
`Volume > 0` filter).

Why this is correct *and* clean:

- **Corporate-action correct.** 등락률 is computed against the 기준가, so every
  split / 무상·유상증자 / 감자 / 액면병합 is already in it — no reconstruction.
- **No rounding accumulation in returns.** ChangesRatio is rounded to 0.01 %,
  so compounded *price levels* drift slightly, but the anchor cancels in any
  return: `adj_close[t]/adj_close[t−h] = ∏ gross`, so daily and h-day returns
  carry no accumulation (< ~1e-4). On a normal day `R_t == ChangesRatio/100`
  exactly.
- **Splits verified.** Samsung 2018-05-04 stays continuous: `adj_close`
  52 900 → 51 800 (−2.1 %, the real intraday move); `cum_factor` 0.0200 → 0.998.

### 3b. Stocks-ratio → entity-change detector only

The `Stocks` ratio + corroboration test now produces only a **series break**
flag. For every ticker, rows strictly before its **last** break are marked
`valid = False`; loaders (`market_loader.load_market_data`,
`adjust.load_adjusted`) drop them. Build: 368 746 rows across 224 tickers.

For 카이노스메드 this drops the 490 pre-merger shell rows; the merger day onward
is kept, and the merger-day return is `NaN` (no prior in-entity row).

---

## 4. Remaining limitations

- **ChangesRatio data errors** on relisting/new-listing first days survive
  (the 8 residual `R_t > 3`). They equal the exchange's reported value and
  affect only their local window, not the rest of the series. Most are
  sub-1000-won penny stocks the paper universe filters out.
- **Cash dividends** are still excluded (price return, not total return) — this
  is unchanged and matches KRX 등락률, which does not adjust the stock 기준가 for
  cash dividends.
- The `Stocks` ratio is retained in the output (`ratio` column) **for diagnosis
  only**; it is no longer the adjustment factor.

---

## 5. What changed

| file | change |
|---|---|
| `adjust.py` | `build_adjustment_factors`: adj_close via ChangesRatio compounding; Stocks-ratio reduced to break detection; new `valid` output column; richer anomaly sidecar (`raw_ret`/`adj_ret`/`is_break`). Module docstring rewritten. `load_adjusted` drops `valid=False`. |
| `market_loader.py` | `load_market_data` reads `valid`, drops pre-break rows. |

**Output schema** (`cache/adj_factors.parquet`): `date, code, raw_close, stocks,
ratio, cum_factor, adj_close, valid`. (`valid` is new; `ratio` is now
diagnostic.)

Regenerate:

    python -m kr_marcap.adjust build

⚠️ The README sections **"How adjustment works"** and **"Known limitation:
유상증자 under-adjustment"** still describe the old Stocks-ratio method and are
now stale — update them when this lands.
