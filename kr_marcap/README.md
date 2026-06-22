# kr_marcap — marcap as primary KR OHLCV source

`kr_marcap/` makes the locally-cloned `marcap/` parquets the primary source of
Korean equity OHLCV — KOSPI + KOSDAQ + KONEX — and adds two thin layers on top:

1. A **point-in-time common-stock universe** selector (`universe.py`) so the
   panel is survivorship-bias-free without needing the `kr_delisted/`
   calendar overlay.
2. A **ChangesRatio price adjustment** layer (`adjust.py`) so historical prices
   are continuous across splits / 무상·유상증자 / 감자, putting marcap on par with
   FnGuide's 수정주가 for those event types.

It does **not** replace `fnguide_data/` for short selling, securities lending,
floating ratio, investor flow, or financials — marcap doesn't carry those.

marcap is itself effectively survivorship-bias-free (delisted tickers
remain in `marcap-{year}.parquet` past their delisting date). The pairing
with fnguide is tight: after filtering marcap to common stock via
`classify.py`, **99.8 %** of live commons and **98 %** of post-2021
common-stock delistings have a column in `fnguide_data/raw/data0203`
(**99.1 %** under `strict=True`; the single remaining post-2021 miss
is an ordinary fnguide hole, not a trust). The 4 live exceptions are
infrastructure / real-estate / resource trusts (`088980` 맥쿼리한국인프라투융자회사,
`415640` KB발해인프라, `094800` 맵스미래에셋맵스리얼티1, `152550` 한국ANKOR유전) —
call `universe(date, 'common', strict=True)` to drop them and get a set
that matches fnguide's master table exactly. The `STRICT_COMMON_EXCLUDE`
list has been audited for completeness across the full 619-delisting
history; no further trust-like tickers hide in the fnguide gaps. See
[`fnguide_data/DELISTED_COVERAGE.md`](../fnguide_data/DELISTED_COVERAGE.md).

## ⚠️ Use post-2015 data for Korean stocks

`marcap` reaches back to 1995, but two **independent** deficiencies make the
pre-2015 window unreliable for return research. **Start return panels at 2015.**
Pre-2015 rows are *kept*, not deleted (no survivorship bias) — opt into the clip
with `load_adjusted(ticker, reliable_only=True)`; the policy constant is
`kr_marcap.universe.RELIABLE_START` (`2015-01-01`).

| Window | Deficiency | Evidence (KOSPI+KOSDAQ common) |
|---|---|---|
| **1996–1999** | IMF-era illiquidity — a large share of listed names did not trade on a given day, so daily returns are stale/zero and the ChangesRatio chain rests on thin prints | no-trade (`Volume==0`) days **17 % (1996), 23 % (1997), 26 % (1998), 11 % (1999)** vs ~1–2 % in 2000–2024; ~720 of the 813 phantom no-trade ChangesRatio rows fall in 1996–99 (see [`PRICE_ADJUSTMENT.md`](PRICE_ADJUSTMENT.md)) |
| **pre-2014** | No cash-dividend data → no total return | DART's structured 배당 endpoint is populated only from fiscal 2014, so `adj_close_tr` is price-return-only before then |
| 2000–2014 | Price data is otherwise sound | `ChangesRatio`/`Stocks` 100 % present every year; no-trade ~1–2 % |

The binding constraint is **total return**: `adj_close_tr` reinvests dividends
only from fiscal 2014 on, so 2015 is the first full year where both price
liquidity *and* total-return coverage are clean.

## Quick start

```python
# 1. one-time build (re-run after each marcap refresh, ~1 min each)
from kr_marcap.universe import build_universe_panel
from kr_marcap.adjust import build_adjustment_factors
build_universe_panel()
build_adjustment_factors()
# optional — only if you need total_return=True (needs OPEN_DART_API_KEY, ~30 min):
from kr_marcap.dividends import build_dividends
build_dividends()

# 2. point-in-time common-stock universe
from kr_marcap.universe import universe
tickers = universe('2015-06-15', 'common')                 # → list of 6-digit codes
tickers = universe('2015-06-15', 'common', strict=True)    # additionally drops the
                                                           # 4 infra/RE/resource trusts
                                                           # → 100% fnguide-aligned

# 3. adjusted OHLCV for one ticker
from kr_marcap.adjust import load_adjusted
df = load_adjusted('005930')                    # Samsung Electronics (price return)
# columns: date, open, high, low, close, volume, amount, market_cap, stocks,
#          cum_factor, adj_open, adj_high, adj_low, adj_close, adj_volume

# 4. total return (reinvests DART cash dividends; needs the dividends cache)
df = load_adjusted('005930', total_return=True)  # + tr_factor, adj_close_tr
df = load_adjusted('005930', reliable_only=True) # drop deficient pre-2015 rows
```

Or via CLI:

```bash
python -m kr_marcap.universe build           # build the panel
python -m kr_marcap.universe                 # quick membership demo
python -m kr_marcap.adjust build             # build adjustment factors
python -m kr_marcap.adjust                   # Samsung 50:1 split spot-check
python -m kr_marcap.dividends build          # crawl DART dividends (needs OPEN_DART_API_KEY, ~30 min)
python -m kr_marcap.dividends                # Samsung dividend-yield demo
```

## Module map

| File | Purpose |
|---|---|
| `classify.py` | Pure `classify_ticker(code, name, market) → kind`. Returns one of `common / preferred / spac / reit / fund / etf / konex / other`. Run as `__main__` for the smoketest. |
| `universe.py` | Builds `cache/universe_panel.parquet` (per-ticker membership window + kind). `universe(date, kind)` returns the active set. |
| `adjust.py` | Builds `cache/adj_factors.parquet` by compounding the exchange `ChangesRatio` (등락률); the `Stocks`-column ratio is kept only to detect entity-change series breaks. `load_adjusted(ticker)` returns adjusted OHLCV for one name (`total_return=True` adds the dividend-reinvested series; `reliable_only=True` clips pre-2015). |
| `dividends.py` | Builds `cache/dividends.parquet` by crawling DART's structured 배당 report (fiscal 2014+) for the full common universe. Consumed by `load_adjusted(..., total_return=True)`. |

## What "common stock" means here

The classifier is the single source of truth. First match wins:

1. Name starts with an ETF brand prefix (`KODEX|TIGER|RISE|ACE|...`) → `etf`
2. Market is `KONEX` → `konex`
3. Code's last character is not `'0'` OR name ends with `우|우B|1우|2우|3우|MF` → `preferred`
4. Name contains `스팩|SPAC` → `spac`
5. Name contains `리츠|REIT` → `reit`
6. Name ends with `호` OR contains `선박투자` → `fund`
7. Market is `KOSPI | KOSDAQ | KOSDAQ GLOBAL` → `common`
8. Otherwise → `other`

KRX uses alphanumeric 6-character codes for some newly-listed names too
(e.g. `00088K` for 한화3우B, `0001A0` for 덕양에너젠). The `code[-1] != '0'`
test correctly catches the K/L/M-suffixed preferred shares; alphanumeric
commons end in `'0'` and fall through to the common-stock rule.

When a ticker's classification changes over its lifetime (e.g. KONEX → KOSDAQ
transfer, or a holdco renaming itself out of a `호` suffix), the universe
panel records the **latest** classification. The full per-kind day count is
written to `cache/universe_conflicts.csv` so unusual cases stay visible.

## How adjustment works

> **Full diagnosis** — failure modes (₩1 ticker-reuse sentinels, phantom-`ChangesRatio`
> no-trade days), their fixes, and why the residual extreme returns are *real* market
> events rather than glitches: see [`PRICE_ADJUSTMENT.md`](PRICE_ADJUSTMENT.md).

The back-adjusted close compounds the exchange's official daily return
`ChangesRatio` (등락률) per ticker:

    gross[t]      = 1 + ChangesRatio[t] / 100
    adj_close[t]  = anchor × cumprod(gross)[t] / cumprod(gross)[anchor]
    cum_factor[t] = adj_close[t] / raw_close[t]

`anchor` is the last *traded* (raw close > 0) row, so today's `adj_close ==
raw close` (back-adjusted convention preserved). KRX computes 등락률 against the
corporate-action 기준가, so splits / 무상·유상증자 / 감자 / 액면병합 are already
baked in — no reconstruction from share counts. ChangesRatio is rounded to
0.01 %, so compounded price *levels* drift slightly, but the anchor cancels in
any return (`adj_close[t] / adj_close[t-h] == ∏ gross`), so daily and h-day
returns — the pipeline's actual inputs — carry no accumulation.

Volume gets the inverse: `adj_volume = volume / cum_factor`, so
`adj_close × adj_volume ≈ raw_close × raw_volume` is continuous across splits.

### Entity-change detection (series breaks)

The `Stocks`-column ratio (`ratio[t] = Stocks[t-1] / Stocks[t]`) is **no longer
the adjustment factor** — it is kept only to detect entity changes. A big ratio
(`< 0.1` or `> 10`) whose same-day price move does *not* corroborate it (the
residual `(1 + raw_ret) / ratio − 1` exceeds `_CORROBORATION_TOL = 0.5`) marks a
**series break**: a SPAC merger, reverse listing, or ticker reuse where the
share count jumped without an inverse price move. Every row before a ticker's
last break is flagged `valid = False` and dropped at load time, so a pre-merger
shell's prices never pollute the operating company's series. Anomalies and their
break verdict are written to `cache/adjust_anomalies.csv`.

A second break path catches the same failure hidden behind a **long trading
gap**: a delisting+ticker-reuse, 우회상장, or 인적분할 재상장 whose share count moved
less than ×10 stays inside the `[0.1, 10]` band and escapes the test above. A
resume after a gap of more than `_GAP_DAYS` (365) is therefore also broken when
its gap-crossing move is uncorroborated — either a real share-count jump (ratio
outside `[_GAP_SHARE_LOW, _GAP_SHARE_HIGH]` = `[0.67, 1.5]`) with no inverse
price move, or a > 300 % price-regime leap (`_GAP_RESUME_RET`), the signature of
a ticker reused off a delisting-floor ₩-sentinel. Examples: 지누스 (013890,
2019-10-30), 하이트진로 (000080, 2009-10-19), 우리은행 (000030, 2014-11-19).

### Why ChangesRatio, not the `Stocks` ratio

The first version of this layer built `cum_factor` from the shares-outstanding
ratio (`Stocks[t-1] / Stocks[t]`), assuming every share-count change is matched
by an inverse price move. That holds for splits / 무상증자 / 감자 but **fails for
entity changes** (SPAC mergers, reverse listings, ticker reuse) and for
corporate actions whose `Stocks` update and price reset land on different days —
the factor then injects a fabricated return on the transition day.

Canonical case — 카이노스메드 (`284620`): on 2020-06-08 the 하나금융11호스팩 shell
became the operating company, `Stocks` jumped ×18.97 while the raw price moved
only −15.5 % (the real move, matching ChangesRatio). The Stocks-ratio factor
scaled the shell-era prices down ×0.0527, fabricating a **+1504 %** adjusted
daily return.

"Just drop the anomalies" doesn't work either: of the 715 rows flagged outside
`[0.1, 10]`, **457 are genuine splits** (including Samsung's 50:1). The
distinguishing signal is whether the price moved *inversely* to the shares — the
corroboration residual `(1 + raw_ret) / ratio − 1`. Genuine actions leave
`|residual| ≤ 0.495`; entity changes leave `≥ 0.522`, so `_CORROBORATION_TOL =
0.5` separates them cleanly. Adjusting from ChangesRatio and demoting the Stocks
ratio to this break detector cut the max daily return from **+1865 % to +700 %**
and `#|R_t| > 3` from **116 to 8** (each survivor is a penny-stock relisting the
exchange itself reported, not a glitch).

## Known limitations

Splits, free/paid rights offerings (무상·유상증자), capital reductions (감자), and
액면병합 are all handled correctly because they are already in 등락률 — including
the 유상증자 case the previous Stocks-ratio method under-adjusted. The
2018-05-04 Samsung 50:1 split stays continuous (`adj_close` 52,900 → 51,800, the
real −2.1 % move). What remains:

- **Cash dividends** — `adj_close` is a *price* return: KRX 등락률 does not reset
  the 기준가 for ordinary cash dividends, so it matches KRX exactly but understates
  total return. This gap is now **quantified and optionally closed** —
  `load_adjusted(ticker, total_return=True)` adds `adj_close_tr`, reinvesting DART
  cash-dividend yields (`kr_marcap.dividends`, fiscal 2014+). Measured on a
  stratified 300-stock 2014–2024 DART sample, the omitted drift is
  **~1.4 %/yr cap-weighted** (≈ KOSPI's published yield): negligible for
  daily/h-day returns — it lands only on the single annual ex-dividend day — but
  **~15 % over a decade and ~32 % over 20 yr** for buy-and-hold totals (KOSPI
  names ≈2× KOSDAQ; ~21 % of names never pay, i.e. zero drift). Pre-2014 has no
  dividend data, so `adj_close_tr` is price-return-only there (see
  [Use post-2015 data](#️-use-post-2015-data-for-korean-stocks)).
- **The largest surviving returns are real, not errors.** Relisting / 거래재개
  first days after a long halt (no price limit) and the 2015 우선주 품절주 mania
  produce extreme but genuine adjusted returns the exchange itself reported; they
  are faithfully reflected rather than suppressed, and most are penny stocks or
  preferreds that liquid-universe filters exclude. The real fabrications are moves
  that did *not* trade — ₩1 ticker-reuse sentinels and phantom-`ChangesRatio`
  no-trade days — which are neutralised (`gross = 1`), plus the one fabrication on
  a day that *did* trade: a 거래재개 resume whose `ChangesRatio` is measured against
  an administrative reference and diverges from the traded close move, corrected by
  using the traded move (`reset_cr`; see [`PRICE_ADJUSTMENT.md`](PRICE_ADJUSTMENT.md)
  §5b). See [`PRICE_ADJUSTMENT.md`](PRICE_ADJUSTMENT.md) for the full failure-mode catalogue.

## Cross-checked against FnGuide 수정주가

The adjustment layer was validated against professional FnGuide DataGuide 수정주가
exports (KOSPI + KOSDAQ currently-listed common, 1998–2026) with return-based
comparison (daily log returns are anchor-invariant). Three results:

- **Dividend treatment agrees.** Across all 2,528 common names, none track a
  total-return series — FnGuide 수정주가 reflects capital changes only, *not* cash
  dividends, exactly like `adj_close`. This confirms the [cash-dividend
  gap](#known-limitations) is a shared market convention, not a defect; use
  `total_return=True` for the dividend-reinvested series.
- **It surfaced the long-gap splice class.** The cross-check flagged entity
  changes the break detector missed; the gap-triggered break above cut splice
  tickers (`max_abs > 1` vs. FnGuide) from 9 to 3, the 3 remaining being gap-free
  1999-01-04 early-data artifacts inside the gated pre-2015 window. No false
  breaks; the Samsung 50:1 split is unaffected.
- **It surfaced the 거래재개 reset class** (2026-06 re-check, extending the scan
  below the splice band). On a 거래재개 KRX sometimes measures `ChangesRatio`
  against an administrative reference, so compounding it mis-scaled pre-event
  history for ~60 currently-listed names (e.g. 232830 by ×2.5). The `reset_cr`
  override (uses the traded close move on these days; see `PRICE_ADJUSTMENT.md`
  §5b) closes it: post-2015 disagreement `> 0.3` band **12 → 0**, names agreeing
  to <1 % every day **94.1 % → 96.5 %**, with no name worse and the splice/Samsung
  results unchanged. FnGuide-calibrated — 68/68 cross-checked cases agree exactly.

## Files in `cache/` (gitignored)

| File | What it is | How to regenerate |
|---|---|---|
| `universe_panel.parquet` | Per-ticker membership table (code, name, market, kind, first_date, last_date, n_days) | `python -m kr_marcap.universe build` |
| `universe_conflicts.csv` | Tickers whose kind changed over their marcap lifetime | (same) |
| `adj_factors.parquet` | Per-ticker daily (date, code, raw_close, stocks, ratio, cum_factor, adj_close, valid) — `ratio` is the diagnostic Stocks ratio, `valid=False` marks pre-series-break shell history | `python -m kr_marcap.adjust build` |
| `adjust_anomalies.csv` | Ratio outside [0.1, 10] or missing Stocks, with corroboration verdict (raw_ret, adj_ret, is_break) | (same) |
| `dividends.parquet` | Per-(ticker, fiscal_year) cash-dividend yield + DPS from DART (code, fiscal_year, yield_pct, dps) | `python -m kr_marcap.dividends build` |
