"""公開資訊觀測站 (MOPS) 重大訊息 for the commons that delisted inside the window.

Why this exists. `TaiwanStockDelisting` carries date, code and name and nothing
else (README caveat 8), so a delisting return computed from the price alone
books −100 % where a merger paid a premium and a premium where the shell was
worthless. The reason is published per company in a MOPS filing, never in a
table, and no FinMind endpoint mirrors it.

Which host. The legacy site refuses a delisted company outright: of the 164
names in `delisting_sign.parquet`, `mopsov.twse.com.tw/mops/web/ajax_t05st01`
served 14 and refused 150 — 144 「公開發行公司不繼續公開發行！」and 6
「上市公司已下市！」 (probed 2026-08-24). The 2025 backend at
`mops.twse.com.tw/mops/api/...` serves the refused names, so it is the only
route that reaches the population this package needs. Both hosts were probed on
the same day and the refusal is a property of the host, not of the company: 1613
answers on both because it stayed a 公開發行公司 after leaving the exchange.

Two stages, each resumable by file, because they cost two orders of magnitude
apart: `listings` is one request per company-year and carries the 主旨, while
`details` is one request per announcement and carries 符合條款, 事實發生日 and
說明. Which announcements the second stage is spent on is decided from the
corpus the first one returns, not from a keyword list written in advance.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
LOG_FILE = ROOT / "mops.log"
LISTING_DIR = ROOT / "mops_listing"
DETAIL_DIR = ROOT / "mops_detail"
FRAME = ROOT / "delisting_sign.parquet"
REFUSALS = ROOT / "mops_detail_refusals.csv"

LISTING_COLS = ["stock_id", "company_name", "spoke_date", "spoke_time",
                "subject", "roc_year", "market_kind", "enter_date", "serial_no"]
DETAIL_COLS = ["stock_id", "spoke_date", "serial_no", "subject", "clause",
               "fact_date", "body"]

API = "https://mops.twse.com.tw/mops/api"
# The backend answers a bare POST with 「因為安全性考量」 unless it looks like the
# SPA that fronts it; Referer is the header it actually checks.
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Referer": "https://mops.twse.com.tw/mops/",
    "Origin": "https://mops.twse.com.tw",
}

# Announcements are pulled for the delisting ROC year and the two before it.
# A merger is resolved by the board, approved by shareholders and only then
# completed, so the filing that gives the reason predates the exit by quarters
# rather than days; two full years ahead of it is the span that covers that
# chain without paying for a third. Where the earliest reason-bearing filing
# actually falls inside this window is measured in README caveat 8 rather than
# assumed here — a name whose filing sits on the boundary is what widens it.
LOOKBACK_ROC_YEARS = 2

# MOPS is a public service with no published quota. One request per second is
# below the rate a single browser session generates and is what this package
# spends; it is not a limit the host advertises.
SLEEP_S = 1.0

# What each stage can actually get. The 主旨 comes back for every one of the 164;
# the 符合條款 and 說明 behind it do not. Both hosts gate the detail on the
# company's *current* registration, not on the filing: 「該 NNNN 公開發行公司不繼續
# 公開發行！」 or 「該 NNNN 上市公司已下市！」, and the gate is the same on
# mopsov and on the 2025 backend (probed 2026-08-24, 15 of 16 sampled names
# refused). So the reason a company left is read from its subject lines, and the
# filing body is a bonus for the few that stayed registered — `details` is not
# filtered, because there is nothing to save by filtering a set this small.
REFUSAL_MARKERS = ("不繼續公開發行", "已下市")



# What `call` returns for 406 「查無相符資料」: the request was answered and the
# answer was no rows. Distinct from None, which is a failure to get an answer.
EMPTY: dict = {}


class Refused(Exception):
    """The host will not serve this company: it is no longer registered."""


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a") as fh:
        fh.write(line + "\n")


def call(api_name: str, payload: dict, max_retries: int = 5) -> dict | None:
    """One MOPS API call. Returns the `result` object, or None if it failed.

    A 500 with 「傳入參數異常」 is the backend rejecting the payload shape, not a
    transient error, so it is not retried — every field it wants is a string,
    including the two day bounds that are left empty.
    """
    backoff = 15.0
    for attempt in range(max_retries):
        try:
            r = requests.post(f"{API}/{api_name}", headers=HEADERS,
                              data=json.dumps(payload), timeout=60)
        except requests.RequestException as e:
            log(f"  net-err {api_name} {payload.get('companyId')}: {e}; "
                f"sleep {backoff:.0f}s")
            time.sleep(backoff)
            backoff = min(backoff * 1.8, 300)
            continue
        try:
            d = r.json()
        except ValueError:
            log(f"  non-json {api_name} {payload.get('companyId')} "
                f"(HTTP {r.status_code}): {r.text[:120]}")
            time.sleep(backoff)
            backoff = min(backoff * 1.8, 300)
            continue
        if d.get("message") == "查詢成功":
            return d.get("result")
        if d.get("code") == 406:
            # 「查無相符資料」 is the backend saying this company filed nothing in
            # the year asked for, which is an answer and not a failure. Reading
            # it as one discards the company's other years with it: a name that
            # was quiet two years before it left the exchange would be dropped
            # whole, and the year that carries its delisting filing never gets
            # requested.
            return EMPTY
        if any(m in str(d.get("message")) for m in REFUSAL_MARKERS):
            # The host declining to serve a deregistered company. An answer
            # about coverage, not a transport failure: retrying cannot change
            # it and counting it as a failure would hide how far the source
            # reaches.
            raise Refused(str(d.get("message")).strip())
        if d.get("code") == 500 and "傳入參數異常" in str(d.get("message")):
            log(f"  bad-params {api_name} {payload}")
            return None
        log(f"  api-msg {api_name} {payload.get('companyId')}: "
            f"code={d.get('code')} {str(d.get('message'))[:80]}")
        return None
    return None


def listings_for(stock_id: str, roc_years: list[int]) -> pd.DataFrame | None:
    """Every 重大訊息 header this company filed in the given ROC years."""
    rows = []
    for y in roc_years:
        res = call("t05st01", {"companyId": stock_id, "year": str(y),
                               "month": "all", "firstDay": "", "lastDay": ""})
        time.sleep(SLEEP_S)
        if res is None:
            return None
        if not res:
            continue
        for rec in res.get("data") or []:
            # [code, name, 發言日期, 發言時間, 主旨, {detail call}]
            det = rec[5] if len(rec) > 5 and isinstance(rec[5], dict) else {}
            par = det.get("parameters") or {}
            rows.append({
                "stock_id": rec[0],
                "company_name": rec[1],
                "spoke_date": rec[2],
                "spoke_time": rec[3],
                "subject": (rec[4] or "").strip(),
                "roc_year": y,
                "market_kind": par.get("marketKind", ""),
                "enter_date": par.get("enterDate", ""),
                "serial_no": par.get("serialNumber", ""),
            })
    return pd.DataFrame(rows, columns=LISTING_COLS)


def details_for(listing: pd.DataFrame) -> tuple[pd.DataFrame | None, str]:
    """符合條款 / 事實發生日 / 說明 for each announcement in `listing`.

    Returns the frame and the refusal message, one of which is always empty.
    The refusal is raised on the first request because the gate is on the
    company, so it costs one request to learn it and not one per announcement.
    """
    rows = []
    for r in listing.itertuples():
        try:
            res = call("t05st01_detail", {
                "enterDate": r.enter_date, "serialNumber": str(r.serial_no),
                "companyId": r.stock_id, "marketKind": r.market_kind})
        except Refused as e:
            return pd.DataFrame(columns=DETAIL_COLS), str(e)
        time.sleep(SLEEP_S)
        if res is None:
            return None, ""
        for rec in res.get("data") or []:
            # [序號, 發言日期, 發言時間, 發言人, 職稱, 電話, 主旨, 符合條款,
            #  事實發生日, 說明]
            rows.append({
                "stock_id": r.stock_id,
                "spoke_date": rec[1],
                "serial_no": rec[0],
                "subject": (rec[6] or "").strip(),
                "clause": (rec[7] or "").strip(),
                "fact_date": (rec[8] or "").strip(),
                "body": (rec[9] or "").strip(),
            })
    return pd.DataFrame(rows, columns=DETAIL_COLS), ""


def _append_refusal(row: dict) -> None:
    """Add one refusal to `mops_detail_refusals.csv`, replacing any earlier one.

    Rewriting the whole file each time costs nothing at this size and keeps the
    invariant a reader depends on — one row per name per stage — without a
    second pass to deduplicate.
    """
    new = pd.DataFrame([row])
    if REFUSALS.exists():
        old = pd.read_csv(REFUSALS, dtype={"stock_id": str})
        new = (pd.concat([old, new], ignore_index=True)
                 .drop_duplicates(["stock_id", "stage"], keep="last"))
    new.sort_values(["stage", "stock_id"]).to_csv(REFUSALS, index=False)


def frame() -> pd.DataFrame:
    """The 164 in-window delisted commons this package answers for."""
    f = pd.read_parquet(FRAME)
    return f.sort_values("delist_date").reset_index(drop=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("listings", "details"))
    ap.add_argument("--only", default="", help="comma-separated stock_ids")
    args = ap.parse_args()

    f = frame()
    if args.only:
        keep = set(args.only.split(","))
        f = f[f.stock_id.isin(keep)]
        if len(f) != len(keep):
            log(f"FAIL --only named {len(keep)} ids, frame holds {len(f)}")
            return 1

    out_dir = LISTING_DIR if args.stage == "listings" else DETAIL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    done = failed = skipped = 0
    refused = []

    for i, r in enumerate(f.itertuples(), 1):
        path = out_dir / f"{r.stock_id}.parquet"
        if path.exists():
            skipped += 1
            continue
        delist_roc = pd.Timestamp(r.delist_date).year - 1911
        note = ""
        if args.stage == "listings":
            years = list(range(delist_roc - LOOKBACK_ROC_YEARS, delist_roc + 1))
            try:
                df = listings_for(r.stock_id, years)
            except Refused as e:
                df, note = pd.DataFrame(columns=LISTING_COLS), str(e)
        else:
            lst = LISTING_DIR / f"{r.stock_id}.parquet"
            if not lst.exists():
                log(f"FAIL {r.stock_id}: details asked for before listings")
                return 1
            df, note = details_for(pd.read_parquet(lst))
        if df is None:
            failed += 1
            log(f"  fail {r.stock_id} {r.stock_name}")
            continue
        if note:
            row = {"stock_id": r.stock_id, "stock_name": r.stock_name,
                   "stage": args.stage, "refusal": note}
            refused.append(row)
            # Appended as it is learned rather than held to the end of the loop.
            # A refusal is the coverage answer for that name, and a run stopped
            # part-way would otherwise discard every one it had already paid a
            # request to find out.
            _append_refusal(row)
        df.to_parquet(path, index=False)
        done += 1
        log(f"  {i}/{len(f)} {r.stock_id} {str(r.stock_name)[:12]} "
            f"rows={len(df)}{' REFUSED: ' + note if note else ''}")

    log(f"{args.stage}: wrote {done}, skipped {skipped}, failed {failed}, "
        f"refused {len(refused)}")
    if done == 0 and skipped == 0:
        log("FAIL nothing was collected")
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
