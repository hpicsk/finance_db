"""Resumable Taiwan market data downloader (FinMind free tier).

Per-stock parquet files for three datasets:
  - ohlcv/{stock_id}.parquet          (TaiwanStockPrice)
  - instflow/{stock_id}.parquet       (TaiwanStockInstitutionalInvestorsBuySell)
  - shares/{stock_id}.parquet         (TaiwanStockShareholding)

Resumable: skips existing files. Retries on 402 rate-limit with backoff.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path("/home/st/research/finance_db/finmind_data")
LOG_FILE = ROOT / "download.log"
API = "https://api.finmindtrade.com/api/v4/data"
TOKEN_FILE = ROOT / ".token"
TOKEN = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""

DATASETS = {
    # existing (already downloaded for 2,111 stocks)
    "ohlcv":             "TaiwanStockPrice",
    "instflow":          "TaiwanStockInstitutionalInvestorsBuySell",
    "shares":            "TaiwanStockShareholding",
    # priority extension (informed-trading / reversal research).
    # TaiwanStockPriceAdj is gated above our `register` level for every calling
    # convention, so its "Free (with data_id)" doc line is wrong (re-probed
    # 2026-07-29; see README "Excluded"). Build the adjusted series from
    # TaiwanStockPrice plus the per-event exchange reference prices in
    # div_result / cap_red below.
    "per_pbr":           "TaiwanStockPER",
    "margin_short":      "TaiwanStockMarginPurchaseShortSale",
    "month_rev":         "TaiwanStockMonthRevenue",
    # second batch (fundamentals, ownership, lending).
    # TaiwanStockEPS / TaiwanStockShareholdingClassification are not
    # in FinMind's enum; TaiwanStockHoldingSharesPer is paid-only.
    "fin_is":            "TaiwanStockFinancialStatements",
    "fin_bs":            "TaiwanStockBalanceSheet",
    "fin_cf":            "TaiwanStockCashFlowsStatement",
    "dividend":          "TaiwanStockDividend",
    "sec_lending":       "TaiwanStockSecuritiesLending",
    # follow-up (sparse event endpoint, per-stock).
    # Most stocks have 0 rows; consolidate post-download with
    # consolidate_capred.py into a single capital_reduction.parquet.
    "cap_red":           "TaiwanStockCapitalReductionReferencePrice",
    # exchange-published 除權息 reference prices (before_price/after_price),
    # the per-event adjustment factor for a 還原股價 series. Verified reachable
    # at register level 2026-07-29, unlike TaiwanStockPriceAdj above.
    "div_result":        "TaiwanStockDividendResult",
}


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a") as fh:
        fh.write(line + "\n")


def fetch(dataset: str, stock_id: str, start: str, end: str,
          max_retries: int = 8, max_rate_limit_waits: int = 2) -> pd.DataFrame | None:
    """Single request with retry on rate limit (402) and transient errors."""
    params = {
        "dataset": dataset,
        "data_id": stock_id,
        "start_date": start,
        "end_date": end,
    }
    if TOKEN:
        params["token"] = TOKEN
    backoff = 30.0
    rate_limit_waits = 0
    for attempt in range(max_retries):
        try:
            r = requests.get(API, params=params, timeout=60)
        except requests.RequestException as e:
            log(f"  net-err {stock_id} {dataset}: {e}; sleep {backoff:.0f}s")
            time.sleep(backoff)
            backoff = min(backoff * 1.8, 600)
            continue

        if r.status_code == 200:
            payload = r.json()
            if payload.get("status") == 200:
                return pd.DataFrame(payload.get("data", []))
            # status 400 inside 200: treat as empty / error
            msg = payload.get("msg", "")
            if "Please update" in msg:
                log(f"  paid-only {stock_id} {dataset}: {msg}")
                return None
            log(f"  api-err {stock_id} {dataset}: {msg}")
            return pd.DataFrame()

        # HTTP 400 with "Please update" body = paid-tier endpoint; do not retry.
        # HTTP 422 = invalid dataset name; do not retry.
        if r.status_code in (400, 422):
            try:
                body_msg = r.json().get("msg", r.text[:200])
            except ValueError:
                body_msg = r.text[:200]
            if "Please update" in body_msg or r.status_code == 422:
                log(f"  non-retryable {stock_id} {dataset} (HTTP {r.status_code}): "
                    f"{body_msg[:120]}")
                return None

        if r.status_code in (402, 429):
            if rate_limit_waits >= max_rate_limit_waits:
                log(f"  rate-limit {stock_id} {dataset}: giving up after "
                    f"{rate_limit_waits} hourly waits")
                return None
            # Hourly quota — wait for the clock reset rather than backing off.
            sleep_s = 3600 - (time.time() % 3600) + 60
            rate_limit_waits += 1
            log(f"  rate-limit {stock_id} {dataset} (HTTP {r.status_code}); "
                f"sleep {sleep_s:.0f}s until next hour "
                f"(wait {rate_limit_waits}/{max_rate_limit_waits})")
            time.sleep(sleep_s)
            continue

        log(f"  http-{r.status_code} {stock_id} {dataset}: {r.text[:100]}")
        time.sleep(backoff)
        backoff = min(backoff * 1.8, 600)
    return None


def download_stock(stock_id: str, start: str, end: str, sleep_s: float,
                   datasets: dict[str, str]) -> dict:
    """Download the given datasets for one stock; skip existing files."""
    result = {subdir: "skip" for subdir in datasets}
    for subdir, dataset in datasets.items():
        path = ROOT / subdir / f"{stock_id}.parquet"
        if path.exists():
            continue
        df = fetch(dataset, stock_id, start, end)
        if df is None:
            result[subdir] = "fail"
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False)
        result[subdir] = f"ok({len(df)})"
        time.sleep(sleep_s)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2005-01-01")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--sleep", type=float, default=6.5,
                    help="seconds between requests (free tier ~600/hr → 6s)")
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--stocks", nargs="*", default=None,
                    help="explicit stock_id list (overrides universe)")
    ap.add_argument("--datasets", nargs="*", default=None,
                    help="subset of DATASETS keys (e.g. price_adj per_pbr); "
                         "default = all")
    args = ap.parse_args()

    if args.datasets is None:
        active = dict(DATASETS)
    else:
        unknown = set(args.datasets) - set(DATASETS)
        if unknown:
            log(f"unknown --datasets keys: {sorted(unknown)}; "
                f"valid: {sorted(DATASETS)}")
            return 2
        active = {k: DATASETS[k] for k in args.datasets}

    if args.stocks:
        stock_ids = args.stocks
    else:
        universe = pd.read_parquet(ROOT / "universe.parquet")
        stock_ids = universe["stock_id"].tolist()

    stock_ids = stock_ids[args.offset:]
    if args.limit > 0:
        stock_ids = stock_ids[: args.limit]

    log(f"=== start: {len(stock_ids)} stocks, {args.start}..{args.end}, "
        f"sleep={args.sleep}s, datasets={list(active)} ===")

    ok_n = fail_n = skip_n = 0
    for i, sid in enumerate(stock_ids, 1):
        res = download_stock(sid, args.start, args.end, args.sleep, active)
        status = " ".join(f"{k}={v}" for k, v in res.items())
        log(f"{i}/{len(stock_ids)} {sid}: {status}")
        if any(v == "fail" for v in res.values()):
            fail_n += 1
        elif all(v == "skip" for v in res.values()):
            skip_n += 1
        else:
            ok_n += 1

    log(f"=== done: ok={ok_n} skip={skip_n} fail={fail_n} ===")
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
