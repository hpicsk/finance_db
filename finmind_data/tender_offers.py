"""What a tender offer paid, for every 公開收購 the exchange has on file.

README caveat 8: the reason a company left is read off its filing subjects, but
the *amount* a holder received is in the 說明, and MOPS refuses the 說明 for 150
of the 164 names because they are no longer 公開發行. That gate is on the
company's registration today rather than on the filing, so it falls hardest on
exactly the companies whose consideration is worth knowing — the ones that left
by being bought.

This table is not behind it. 公開收購申報資料彙總表 is filed by the *offeror*
rather than by the target and is served by period rather than by company, so a
deregistered target has nothing to gate: 2325 矽品 and 4180 安成藥業 both answer
(probed 2026-08-25) where their own 說明 does not. It carries 收購對價 — the
per-share price — in words, along with who was buying, how much they got, and
whether the target delisted afterwards.

    mopsov.twse.com.tw/mops/web/ajax_t162sb03

Three limits, and the first is the binding one.

**It starts at ROC 105/11.** The form says so — 「僅提供105年11月以後之資料」 —
and 2016-11 is nearly half way through this package's window, so a delisting
before it is not reachable here at all. The per-company table ``ajax_t162sb01``
does answer for earlier years, but it returns a filing index whose prices are
inside 公開收購說明書 PDFs rather than in the page.

**A tender is not always the exit.** Eight of the fifteen offers made on a name
in this package's delisting frame were the first step of a two-step deal — a
tender, then a 股份轉換 or 合併 that ended the listing months later — and the
price a holder who did not tender received is the squeeze-out's, which this
table does not carry. The offers that *are* the exit are the ones that opened on
the day the shares stopped trading: Taiwan's going-private order is to terminate
the listing first and then buy out whoever is left, and 公開收購管理辦法 §18 caps
the offer at 50 days, so all three here open on the delisting date and close 49
days later exactly. Nothing later can have been their exit, because there was no
market left for it to precede. The 終止上市 column the offeror files does *not*
decide this — it is marked 是 for two of the three and 不適用 for the third on
identical facts.

**The server's date filter is not a filter.** Asking for one ROC year drops any
offer whose 期間 crosses the year end — 13 rows come back for ROC 106 against
the 15 the whole-range request returns — and every request appends whatever
offer is open today whatever range was asked for. So the range is asked for once
and wide, and the rows are cut here instead.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from finmind_data.window import COVERAGE_END  # noqa: E402

import requests  # noqa: E402

OUT_PATH = ROOT / "tender_offers.parquet"

URL = "https://mopsov.twse.com.tw/mops/web/ajax_t162sb03"
# The legacy host answers a plain form POST. The 2025 SPA reaches the same table
# through `mops/api/redirectToOld`, which hands back a signed URL to this host,
# so going straight here is the same request with one hop removed.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Referer": "https://mopsov.twse.com.tw/mops/web/t162sb03",
}
# The page declares UTF-8 in its Content-Type and means it. Left explicit rather
# than sniffed: chardet reads the long response as Cyrillic and returns mojibake
# that parses fine and is wrong in every cell.
ENCODING = "utf-8"

# 「僅提供105年11月以後之資料」, quoted from the query form. Asking earlier is not
# an error, it is an empty answer, so the floor is stated here rather than
# discovered as a coverage figure.
SOURCE_START_ROC = "10511"
# One request for the whole span, because a narrower one silently drops the
# offers that cross its boundary. The end is the window's, and the rows are cut
# to it below — the server returns the currently-open offer on top of whatever
# range is asked for, which in a 2026 run is a 2026 row.
RANGE_END_ROC = f"{COVERAGE_END.year - 1911}12"

# Every row carries 18 cells against this header. A row that does not is a
# spanning header or the footnote, not an offer.
COLUMNS = ["seq", "period_start", "period_end", "offeror", "offeror_is_pe",
           "offeror_is_management", "target", "agent", "instrument",
           "consideration", "funding", "cert_type", "max_qty", "min_qty",
           "actual_qty", "delisted_after", "outcome", "fail_reason"]
N_CELLS = len(COLUMNS)

# What the 被收購公司於收購後是否終止上市、上櫃或興櫃 column can say. It is filed by
# the offeror and is not filled consistently: 4762 and 4965 are marked 是 and
# 5304 不適用 on the same facts, all three having terminated their own listing
# before the offer opened. So it says whether *an* exit followed and not which
# transaction was one, and the rule that picks the exits reads the dates instead
# — see `linkage` in the module docstring and README caveat 8.
DELISTED_AFTER = {"是": "yes", "否": "no", "不適用": "not_applicable"}
SUCCEEDED = "成功"


def _roc_to_ts(s: str) -> pd.Timestamp:
    """`106/09/19` → a Gregorian timestamp; ROC 1 is 1912.

    A 期間 cell can carry a note after the date — `108/05/13 (延長至 108/06/12)`
    — so the leading date is matched rather than the whole cell parsed.
    """
    m = re.match(r"\s*(\d{2,3})/(\d{1,2})/(\d{1,2})", s or "")
    if not m:
        return pd.NaT
    y, mo, d = (int(x) for x in m.groups())
    return pd.Timestamp(y + 1911, mo, d)


def _cells(row_html: str) -> list[str]:
    return [re.sub(r"\s+", " ",
                   html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)]


def fetch() -> pd.DataFrame:
    """Every filed tender offer the table holds, parsed, uncut."""
    r = requests.post(URL, headers=HEADERS, timeout=120,
                      data={"encodeURIComponent": 1, "step": 1, "firstin": 1,
                            "off": 1, "start_YM": SOURCE_START_ROC,
                            "end_YM": RANGE_END_ROC})
    r.raise_for_status()
    text = re.sub(r"(?s)<script.*?</script>", " ", r.content.decode(ENCODING))
    rows = [c for c in (_cells(x) for x in
                        re.findall(r"(?s)<tr[^>]*>(.*?)</tr>", text))
            if len(c) == N_CELLS and c[0].isdigit()]
    if not rows:
        raise ValueError(
            f"{URL} returned no offers for {SOURCE_START_ROC}..{RANGE_END_ROC}. "
            f"The table answers a bad range with an empty page and HTTP 200, so "
            f"an empty parse is a refusal to record as an absence.")
    d = pd.DataFrame(rows, columns=COLUMNS)
    d["target_id"] = d["target"].str.extract(r"\((?:上市|上櫃|興櫃)?\s*(\d{4,6})\)")
    d["start_ts"] = d["period_start"].map(_roc_to_ts)
    d["end_ts"] = d["period_end"].map(_roc_to_ts)
    # 每股新台幣 27.5 元, and where terms were revised the cell names both — 「每股
    # 新台幣 60 元，其後提高為每股新台幣65元」. The last price in the cell is the
    # one that was paid, so the search is deliberately not anchored to the first.
    d["per_share"] = (d["consideration"].str.findall(r"([\d,]+(?:\.\d+)?)\s*元")
                      .str[-1].str.replace(",", "").astype(float))
    d["succeeded"] = d["outcome"] == SUCCEEDED
    d["linkage"] = d["delisted_after"].map(DELISTED_AFTER)
    if d["linkage"].isna().any():
        bad = sorted(d.loc[d["linkage"].isna(), "delisted_after"].unique())
        raise ValueError(
            f"unknown 終止上市 values {bad} — the column is what says whether an "
            f"offer ended the listing, and a value nobody has read cannot be "
            f"mapped to one that has.")
    return d


def collect() -> pd.DataFrame:
    """The offers this package answers for: cut to the window, sorted."""
    d = fetch()
    keep = (d["start_ts"] >= _roc_to_ts(f"{SOURCE_START_ROC[:3]}/"
                                        f"{SOURCE_START_ROC[3:]}/01")) & \
           (d["start_ts"] <= COVERAGE_END)
    return (d[keep].drop(columns=["seq"])
            .sort_values(["start_ts", "target_id"]).reset_index(drop=True))


if __name__ == "__main__":
    out = collect()
    out.to_parquet(OUT_PATH, index=False)
    print(f"{OUT_PATH.name}: {len(out)} offers, {out.target_id.nunique()} "
          f"targets, {out.start_ts.min().date()}..{out.start_ts.max().date()}")
    print(out["linkage"].value_counts().to_string())
