"""Resumable Taiwan market data downloader (FinMind API).

Per-stock parquet files for three datasets:
  - ohlcv/{stock_id}.parquet          (TaiwanStockPrice)
  - instflow/{stock_id}.parquet       (TaiwanStockInstitutionalInvestorsBuySell)
  - shares/{stock_id}.parquet         (TaiwanStockShareholding)

Resumable: skips existing files. Retries on 402 rate-limit with backoff.

`--extend` tops each existing file up to a later `--end` instead of skipping
it. Skip-existing is per *file*, so it cannot move an end date: every file
exists, so a plain re-run with a later `--end` downloads nothing and reports a
clean pass. Under `--extend` a file's own last date is what the next request
starts from, and the pull is appended to it. A back-adjusted file is re-pulled
whole instead: its rows are anchored at the day they were pulled, so an append
would splice two anchors into one series.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
LOG_FILE = ROOT / "download.log"
API = "https://api.finmindtrade.com/api/v4/data"
TOKEN_FILE = ROOT / ".token"


def token() -> str:
    """The API token. Raises if `.token` is absent — it is never optional.

    Duplicated from `auth.py` rather than imported: this script runs as
    `python download.py`, not `python -m`, so it has no package to import a
    sibling from. The datasets below are sponsor-tier, so a request without the
    token is refused rather than served a free-tier subset.
    """
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(
            f"{TOKEN_FILE} is missing — write your FinMind token there "
            f"(it is gitignored). See finmind_data/README.md.")
    return TOKEN_FILE.read_text().strip()

DATASETS = {
    # existing (already downloaded for 2,111 stocks)
    "ohlcv":             "TaiwanStockPrice",
    "instflow":          "TaiwanStockInstitutionalInvestorsBuySell",
    "shares":            "TaiwanStockShareholding",
    # back-adjusted price (還原股價), sponsor tier only. Total-return
    # convention: cash dividends are removed along with the share events, so
    # `close` here is dividend-inclusive and the vendor publishes no
    # price-return variant beside it (README "Adjusted prices").
    "price_adj":         "TaiwanStockPriceAdj",
    # priority extension (informed-trading / reversal research).
    "per_pbr":           "TaiwanStockPER",
    "margin_short":      "TaiwanStockMarginPurchaseShortSale",
    "month_rev":         "TaiwanStockMonthRevenue",
    # second batch (fundamentals, ownership, lending).
    # Two names asked for here are not in the vendor's enum; they are
    # registered in catalogue.KNOWN_ABSENT, where a check re-confirms the
    # absence rather than trusting this comment. TaiwanStockHoldingSharesPer
    # exists but is paid-only.
    "fin_is":            "TaiwanStockFinancialStatements",
    "fin_bs":            "TaiwanStockBalanceSheet",
    "fin_cf":            "TaiwanStockCashFlowsStatement",
    "dividend":          "TaiwanStockDividend",
    "sec_lending":       "TaiwanStockSecuritiesLending",
    # follow-up (sparse event endpoint, per-stock).
    # Most stocks have 0 rows; consolidate post-download with
    # consolidate_capred.py into a single capital_reduction.parquet.
    "cap_red":           "TaiwanStockCapitalReductionReferencePrice",
    # exchange-published 除權息 reference prices (before_price/after_price).
    # Their ratio is the per-event factor price_adj above is checked against.
    "div_result":        "TaiwanStockDividendResult",
}


# A back-adjusted series is anchored at the day it is pulled: an event after that
# rescales every row before it. Appending a later pull to one leaves the old rows
# at the old anchor, and the adjusted return jumps on the first appended session
# with no event under it. `--extend` re-pulls these whole.
BACK_ADJUSTED = {"price_adj"}


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
    # In a header rather than the query string, which `requests` writes into
    # the net-err message logged below (see `auth.py`).
    headers = {"Authorization": f"Bearer {token()}"}
    backoff = 30.0
    rate_limit_waits = 0
    for attempt in range(max_retries):
        try:
            r = requests.get(API, params=params, headers=headers, timeout=60)
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
            # An error the vendor names is not an answer. Returned empty, it
            # would be written as a zero-row file or appended as nothing, and
            # both read later as "the stock had no rows in the range".
            log(f"  api-err {stock_id} {dataset}: {msg}")
            return None

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
                   datasets: dict[str, str], extend: bool = False) -> dict:
    """Download the given datasets for one stock.

    Skips existing files, or under `extend` requests only what each one is
    missing at its far end and appends that — except a back-adjusted file,
    which it re-pulls whole. Every dataset here carries a
    `date` column, so the resume point is read from the file rather than
    tracked separately — a per-dataset key table would be one more thing to
    keep in step with the vendor's schema.
    """
    result = {subdir: "skip" for subdir in datasets}
    for subdir, dataset in datasets.items():
        path = ROOT / subdir / f"{stock_id}.parquet"
        whole = subdir in BACK_ADJUSTED
        old = None
        req_start = start
        if path.exists():
            if not extend:
                continue
            old = pd.read_parquet(path)
            if not len(old):
                # An empty file records that the stock had no rows in the range
                # pulled, which says nothing about a range it did not cover, so
                # it is re-pulled whole rather than treated as a resume point.
                old = None
            elif whole:
                # From the file's own first row where that is earlier, so a
                # `--start` chosen to bound the appends cannot cut its history.
                req_start = min(start, str(old["date"].min())[:10])
            else:
                last = pd.to_datetime(old["date"]).max()
                if last >= pd.Timestamp(end):
                    continue
                req_start = (last + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        df = fetch(dataset, stock_id, req_start, end)
        if df is None:
            result[subdir] = "fail"
            continue
        time.sleep(sleep_s)
        if whole and old is not None:
            held = set(old["date"].astype(str).str[:10])
            got = set(df["date"].astype(str).str[:10]) if len(df) else set()
            gone = sorted(held - got)
            if gone:
                # The vendor dropping some of the stock's history, or an `--end`
                # short of the file's last row: the file is kept whole at its
                # own anchor and the stock counts as a failure.
                log(f"  refused {stock_id} {dataset}: the whole re-pull lacks "
                    f"{len(gone)} of the {len(held)} dates the file holds, {gone[:3]}")
                result[subdir] = "fail"
                continue
            result[subdir] = f"whole({len(df)})"
        elif old is not None:
            if set(df.columns) != set(old.columns) and not df.empty:
                # A column added or dropped between pulls would be concatenated
                # into a ragged file whose new rows carry NaN for the old
                # columns and vice versa. Refuse and leave the file as it was.
                log(f"  schema-drift {stock_id} {dataset}: "
                    f"+{sorted(set(df.columns) - set(old.columns))} "
                    f"-{sorted(set(old.columns) - set(df.columns))}")
                result[subdir] = "fail"
                continue
            added = len(df)
            if added:
                df = (pd.concat([old, df], ignore_index=True)
                        .sort_values("date", kind="stable")
                        .reset_index(drop=True))
            else:
                df = old
            result[subdir] = f"+{added}"
            if not added:
                continue
        else:
            result[subdir] = f"ok({len(df)})"
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2005-01-01")
    # The session `window.COVERAGE_END` names, so a fresh clone pulls to where
    # coverage ends; `test_taiwan_coverage_does_not_outrun_the_data` keeps the
    # two equal.
    ap.add_argument("--end", default="2026-09-09")
    ap.add_argument("--sleep", type=float, default=6.5,
                    help="seconds to wait *in addition to* the request itself. "
                         "The quota is spent per request, not per sleep, so the "
                         "pace is 3600/api_request_limit_hour minus the "
                         "round-trip — measured at 0.27 s here, which is "
                         "negligible against the register tier's 6 s budget and "
                         "close to half of the sponsor tier's 0.6 s. Register "
                         "600/hr -> 5.7, sponsor 6000/hr -> 0.33; "
                         "api.web.finmindtrade.com/v2/user_info reports the "
                         "limit. Leave a margin: overshooting earns a 402, and "
                         "fetch() answers that by sleeping to the top of the "
                         "hour and then failing the stock after two of them")
    ap.add_argument("--extend", action="store_true",
                    help="top existing files up to --end instead of skipping "
                         "them; each file resumes from its own last date, and a "
                         "back-adjusted one is re-pulled whole")
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
        f"sleep={args.sleep}s, datasets={list(active)}"
        f"{', extend' if args.extend else ''} ===")

    ok_n = fail_n = skip_n = 0
    for i, sid in enumerate(stock_ids, 1):
        res = download_stock(sid, args.start, args.end, args.sleep, active,
                             extend=args.extend)
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
