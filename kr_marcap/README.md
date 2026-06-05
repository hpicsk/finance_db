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

## Quick start

```python
# 1. one-time build (re-run after each marcap refresh, ~1 min each)
from kr_marcap.universe import build_universe_panel
from kr_marcap.adjust import build_adjustment_factors
build_universe_panel()
build_adjustment_factors()

# 2. point-in-time common-stock universe
from kr_marcap.universe import universe
tickers = universe('2015-06-15', 'common')                 # → list of 6-digit codes
tickers = universe('2015-06-15', 'common', strict=True)    # additionally drops the
                                                           # 4 infra/RE/resource trusts
                                                           # → 100% fnguide-aligned

# 3. adjusted OHLCV for one ticker
from kr_marcap.adjust import load_adjusted
df = load_adjusted('005930')                    # Samsung Electronics
# columns: date, open, high, low, close, volume, amount, market_cap, stocks,
#          cum_factor, adj_open, adj_high, adj_low, adj_close, adj_volume
```

Or via CLI:

```bash
python -m kr_marcap.universe build           # build the panel
python -m kr_marcap.universe                 # quick membership demo
python -m kr_marcap.adjust build             # build adjustment factors
python -m kr_marcap.adjust                   # Samsung 50:1 split spot-check
python -m kr_marcap.reconcile_fnguide        # validate classifier vs fnguide
```

## Module map

| File | Purpose |
|---|---|
| `classify.py` | Pure `classify_ticker(code, name, market) → kind`. Returns one of `common / preferred / spac / reit / fund / etf / konex / other`. Run as `__main__` for the smoketest. |
| `universe.py` | Builds `cache/universe_panel.parquet` (per-ticker membership window + kind). `universe(date, kind)` returns the active set. |
| `adjust.py` | Builds `cache/adj_factors.parquet` by compounding the exchange `ChangesRatio` (등락률); the `Stocks`-column ratio is kept only to detect entity-change series breaks. `load_adjusted(ticker)` returns adjusted OHLCV for one name. |
| `reconcile_fnguide.py` | Applies the classifier to fnguide's `currently_listed/` ticker list and diffs commons against marcap as of the latest marcap date. Writes `cache/reconcile_report.md`. |

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

## Known limitations

Splits, free/paid rights offerings (무상·유상증자), capital reductions (감자), and
액면병합 are all handled correctly because they are already in 등락률 — including
the 유상증자 case the previous Stocks-ratio method under-adjusted. The
2018-05-04 Samsung 50:1 split stays continuous (`adj_close` 52,900 → 51,800, the
real −2.1 % move). What remains:

- **Cash dividends** are not adjusted (price return, not total return). KRX
  등락률 likewise does not reset the 기준가 for ordinary cash dividends, so the
  adjusted series matches KRX but drifts from a dividend-adjusted vendor series
  (e.g. FnGuide's 수정주가) the further back you go. Add a DART-sourced dividend
  layer here if a study needs total returns.
- **ChangesRatio data errors** on a few relisting / new-listing first days
  survive the compounding. They equal the value the exchange itself reported and
  affect only their local window, not the rest of the series; most are
  sub-1000-won penny stocks that liquid-universe filters exclude.

## Files in `cache/` (gitignored)

| File | What it is | How to regenerate |
|---|---|---|
| `universe_panel.parquet` | Per-ticker membership table (code, name, market, kind, first_date, last_date, n_days) | `python -m kr_marcap.universe build` |
| `universe_conflicts.csv` | Tickers whose kind changed over their marcap lifetime | (same) |
| `adj_factors.parquet` | Per-ticker daily (date, code, raw_close, stocks, ratio, cum_factor, adj_close, valid) — `ratio` is the diagnostic Stocks ratio, `valid=False` marks pre-series-break shell history | `python -m kr_marcap.adjust build` |
| `adjust_anomalies.csv` | Ratio outside [0.1, 10] or missing Stocks, with corroboration verdict (raw_ret, adj_ret, is_break) | (same) |
| `reconcile_report.md` | Symmetric set-diff between marcap commons and fnguide currently-listed commons | `python -m kr_marcap.reconcile_fnguide` |
