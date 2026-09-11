"""Download TWSE's own 除權除息計算結果表 (TWT49U) as a second cash-leg source.

``div_result/`` gives the reference prices ``before_price`` / ``after_price``
but not how the step divides between cash and shares, so a 除權息 that fuses
both needs the cash leg named from somewhere else. ``dividend/`` declares it,
and where that declaration is missing the price-return step was NaN — 250
events in 113 stocks before this file existed, 107 in 61 after it.

TWSE publishes the division itself. TWT49U reaches back to 2005, covering the
whole price series, and is free and keyless — unlike ``TaiwanStockPriceAdj``,
which is tier-gated and in any case ships an adjusted series rather than the
split this needs.

How much of the division it publishes changed in 2009. Through 2008 the report
carries 權值 (the share leg) and 息值 (the cash leg) as separate columns, which
names the cash leg outright. From 2009 those two columns are gone and only
their sum 權值+息值 remains, alongside a 權/息 label. The label still settles
the two pure cases — 息 means the whole step is cash, 權 means none of it is —
and leaves only a 權息 event genuinely undetermined. Both schemas are read, and
the columns absent in the later one are left NaN rather than filled, so a
caller can tell what the exchange published from what it did not.

The equivalent for OTC names is not reachable. TPEX's ``exDailyQ_result.php``
has the identical field list but serves a rolling few-day window and ignores
every date parameter tried, and its ``preAnnounce`` table likewise returns only
the current forward announcements. So this covers the 上市 side; the 上櫃
events stay unresolved and are reported as such.

Whole-year queries are not truncated — 2007 returns 538 rows either as one
call or as twelve monthly calls summed — so one request per year suffices.
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

from .window import COVERAGE_END

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "exright_reference.parquet"

URL = ("https://www.twse.com.tw/rwd/zh/exRight/TWT49U"
       "?startDate={start}&endDate={end}&response=json")

# The price series starts 2005-09-02; TWT49U serves the whole span (probed
# 2026-08-01, the earliest accepted start being 2005). The far end is
# `COVERAGE_END`'s year rather than a literal: the cash leg is wanted for the
# 除權息 the panel carries, so an extension that moves coverage into a new year
# leaves this file one year short of the events it exists to explain, and the
# events it cannot name come back as NaN price-return steps rather than as an
# error. Whole years are stored and the clip is applied where they are read.
YEARS = range(2005, COVERAGE_END.year + 1)

# One request per year against an exchange that publishes this for free.
_SLEEP_SECONDS = 3.0

# Present in every year.
_COLUMNS = {
    "資料日期": "date",
    "股票代號": "stock_id",
    "除權息前收盤價": "before_price",
    "除權息參考價": "after_price",
    "權值+息值": "total_value",
    "權/息": "kind",
}

# Dropped by TWSE from 2009 onward; see the module docstring.
_SPLIT_COLUMNS = {"權值": "stock_value", "息值": "cash_value"}

_NUMERIC = ("before_price", "after_price", "total_value",
            "stock_value", "cash_value")


def _roc_to_date(s: str) -> pd.Timestamp:
    """``96年08月10日`` → 2007-08-10. ROC year 96 is 1911 + 96."""
    y, rest = s.split("年")
    m, rest = rest.split("月")
    return pd.Timestamp(int(y) + 1911, int(m), int(rest.rstrip("日")))


def _number(s: str) -> float:
    """TWSE writes thousands separators and leaves blanks for a missing leg."""
    s = str(s).replace(",", "").strip()
    return float(s) if s not in ("", "-", "--") else float("nan")


def fetch(year: int) -> pd.DataFrame:
    url = URL.format(start=f"{year}0101", end=f"{year}1231")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.load(r)
    if payload.get("stat") != "OK":
        raise RuntimeError(f"TWT49U {year}: {payload.get('stat')}")
    rows = payload.get("data") or []
    raw = pd.DataFrame(rows, columns=payload["fields"])
    have = {k: v for k, v in _SPLIT_COLUMNS.items() if k in raw.columns}
    if have and len(have) != len(_SPLIT_COLUMNS):
        raise RuntimeError(f"TWT49U {year}: partial split columns {sorted(have)}")
    df = raw[list(_COLUMNS) + list(have)].rename(columns={**_COLUMNS, **have})
    df["date"] = df["date"].map(_roc_to_date)
    df["stock_id"] = df["stock_id"].astype(str).str.strip()
    df["kind"] = df["kind"].astype(str).str.strip()
    for c in _NUMERIC:
        df[c] = df[c].map(_number) if c in df.columns else float("nan")
    return df[["date", "stock_id", *_NUMERIC, "kind"]]


def main() -> None:
    frames = []
    for year in YEARS:
        df = fetch(year)
        print(f"{year}  {len(df):5d} events  "
              f"split published {int(df['cash_value'].notna().sum()):5d}",
              flush=True)
        frames.append(df)
        time.sleep(_SLEEP_SECONDS)

    out = pd.concat(frames).sort_values(["date", "stock_id"])
    out = out.reset_index(drop=True)
    out.to_parquet(OUT, index=False)
    print(f"\n{len(out):,} events / {out['stock_id'].nunique():,} stocks "
          f"({out['date'].min().date()} .. {out['date'].max().date()}) → {OUT}")
    print(f"息值 published outright     {int(out['cash_value'].notna().sum()):6,}")
    print(f"kind settles it (息 or 權)  "
          f"{int(out['kind'].isin(['息', '權']).sum()):6,}")
    print(out["kind"].value_counts().to_string())


if __name__ == "__main__":
    main()
