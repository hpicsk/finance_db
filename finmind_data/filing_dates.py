"""When each Taiwanese financial report was actually published.

README caveat 9: `available_date.py` dates a statement by the deadline the law
set for it, which is a valid upper bound for a company that filed on time and
wrong for one that did not. A late filer, or one granted a 不可抗力 extension,
published after the date that module computes, and a join on it hands a trader
a figure before it existed. Closing that needs the announcement date, and the
announcement date is what this module collects.

Source. TWSE's document server publishes, per filing, the timestamp at which the
electronic report was uploaded:

    doc.twse.com.tw/server-java/t57sb01?step=1&mtype=A&co_id=<id>&year=

A blank `year` returns the company's whole filing history rather than one year,
so this costs one request per company and not one per company-quarter. The
server is separate from 公開資訊觀測站 and does not carry MOPS's registration
gate: it answers for delisted and deregistered names alike (6012, 4703 and 2456
probed 2026-08-24), which is what makes it usable on a frame that is deliberately
not survivorship-free.

What the timestamp is. 上傳日期 is when the filing reached the server, to the
second. It is not the board-approval date and not the press release; it is the
moment the document became public, which is the moment the figures in it became
tradable. Where a report was later corrected the server keeps both rows, so a
period can carry more than one timestamp and the earliest is when its numbers
first existed.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import requests

ROOT = Path(__file__).resolve().parent
LOG_FILE = ROOT / "filing_dates.log"
OUT_DIR = ROOT / "filing_dates"
PANEL = ROOT / "filing_dates.parquet"

URL = "https://doc.twse.com.tw/server-java/t57sb01"
# mtype A is 財務報告書. The other document classes the server carries — 財務預測書,
# 公開說明書, 年報 — answer a different question and are not pulled here.
MTYPE = "A"
# The page is served in Big5, not UTF-8, and has been since it was written.
ENCODING = "big5"

# The document server throttles, and says so in the page body rather than in a
# status code: it answers 「查詢過量，請稍後再查詢!」 in a 469-byte page that
# returns HTTP 200 and parses to zero filings. A collector that reads rows and
# trusts the status code therefore writes an empty history for a company that
# has one — which is what this collector did on 66 of its first 110 names
# before THROTTLED was added.
#
# What the limit is, measured 2026-08-24: at 3-second spacing it refused after
# 14 requests and accepted again 16 seconds later. So it is a burst allowance
# with a short cooldown, not a rate — spacing the requests out buys nothing but
# a longer run, and the cheap response is to keep asking at speed and wait out
# the refusal when it comes.
SLEEP_S = 1.0

# A 金融控股公司 gets a subsidiary picker instead of its own filings: the page
# lists the holdco's subsidiaries and says so in this sentence, and carries a
# hidden `check2858=Y` that asks for the parent's own reports. Sending the flag
# only after seeing the picker leaves the request for the other 2,215 companies
# exactly as it was. Without it the fifteen listed 金控 — 2880 through 2892,
# 5820 and 5880, which is the whole sector — record an empty filing history.
HOLDCO_PICKER = "金融控股公司"
HOLDCO_FLAG = {"check2858": "Y"}

# The throttle page, matched on the phrase rather than on the byte count so a
# reworded version still trips it. Seeing it means the request was refused, not
# answered: wait and ask again rather than record an absence.
THROTTLED = "查詢過量"

# Measured cooldown is 16 seconds; this waits longer than that because the cost
# of waiting too long is a slower run and the cost of waiting too little is
# spending a retry to learn nothing.
THROTTLE_WAIT_S = 20.0

# Throttle waits are counted apart from transient-error retries: a refusal is
# the server rationing, not failing, and burning the error budget on it would
# abandon companies the server would have served a few seconds later. This
# ceiling exists so a server that is down rather than busy still ends the run.
MAX_THROTTLE_WAITS = 20

# 電子檔案 is named <YYYY><QQ>_<code>_<class>.<ext> — 202301_1101_AI1.pdf is 2023
# Q1, consolidated. The filename is parsed rather than 資料年度 ("112 年 第一季")
# because it is already Gregorian and already numeric, and because a row can omit
# 資料年度 while no row omits its own filename.
FILENAME = re.compile(r"^(\d{4})(\d{2})_[^_]+_([A-Z0-9]+)\.")
QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}

# The server drops empty `<td>`s rather than emitting them, so a row carries 7,
# 8 or 9 cells against an 11-column header and nothing can be read by position.
# Each field is identified by what it looks like instead.
IS_ROC_PERIOD = re.compile(r"^\d{2,3}\s*年")
IS_SIZE = re.compile(r"^[\d,]+$")
IS_NATURE = re.compile(r"財報|合併報表|個體|英文版")

# The class suffix in the filename, which says what the document is without
# depending on a cell being present. AI1 is the Chinese consolidated report —
# the one whose arrival makes a quarter's figures public. AIA is the English
# translation and lands weeks later, so dating a quarter by it would move the
# availability of numbers that were already out.
CLASS_CONSOLIDATED = "AI1"

COLUMNS = ["stock_id", "period_end", "nature", "class_code", "detail",
           "filename", "upload_ts", "roc_period"]


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a") as fh:
        fh.write(line + "\n")


def _cells(row_html: str) -> list[str]:
    """Every cell of one row, empties kept — position is what identifies them."""
    return [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
            for c in re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)]


def _roc_ts(s: str) -> pd.Timestamp:
    """`112/05/11 19:58:13` → a Gregorian timestamp. ROC 1 is 1912."""
    m = re.match(r"(\d{2,3})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})", s or "")
    if not m:
        return pd.NaT
    y, mo, d, hh, mm, ss = (int(x) for x in m.groups())
    return pd.Timestamp(y + 1911, mo, d, hh, mm, ss)


def fetch(stock_id: str, max_retries: int = 5) -> pd.DataFrame | None:
    """This company's whole 財務報告書 filing history, one row per document."""
    backoff = 15.0
    throttle_waits = 0
    holdco = False
    while max_retries > 0:
        try:
            params = {"step": 1, "colorchg": 1, "seamon": "", "mtype": MTYPE,
                      "co_id": stock_id, "year": ""}
            if holdco:
                params.update(HOLDCO_FLAG)
            r = requests.get(URL, params=params,
                             headers={"User-Agent": "Mozilla/5.0 (research; finance_db)"},
                             timeout=60)
        except requests.RequestException as e:
            log(f"  net-err {stock_id}: {e}; sleep {backoff:.0f}s")
            max_retries -= 1
            time.sleep(backoff)
            backoff = min(backoff * 1.8, 300)
            continue
        if r.status_code != 200:
            log(f"  http-{r.status_code} {stock_id}")
            max_retries -= 1
            time.sleep(backoff)
            backoff = min(backoff * 1.8, 300)
            continue
        text = r.content.decode(ENCODING, errors="replace")
        if HOLDCO_PICKER in text and not holdco:
            holdco = True
            continue
        if THROTTLED in text:
            throttle_waits += 1
            if throttle_waits > MAX_THROTTLE_WAITS:
                log(f"  throttled {stock_id}: still refused after "
                    f"{MAX_THROTTLE_WAITS} waits; giving up")
                return None
            time.sleep(THROTTLE_WAIT_S)
            continue
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
            c = _cells(tr)
            if not c or not re.fullmatch(r"\d{4,6}[A-Z]?", c[0].strip()):
                continue
            body = [x.strip() for x in c[1:]]
            fname = next((x for x in body if FILENAME.match(x)), "")
            m = FILENAME.match(fname)
            if not m:
                # No filename means no document; the row is a header artefact
                # or the server's 更(補)正 note, not a filing.
                continue
            year, qq, klass = int(m.group(1)), int(m.group(2)), m.group(3)
            if qq not in QUARTER_END:
                log(f"  odd-period {stock_id} {fname}")
                continue
            ts = next((x for x in body if not pd.isna(_roc_ts(x))), "")
            nature = next((x for x in body if IS_NATURE.search(x)
                           and x != fname), "")
            period = next((x for x in body if IS_ROC_PERIOD.match(x)), "")
            used = {fname, ts, nature, period}
            detail = next((x for x in body if x not in used
                           and not IS_SIZE.match(x) and x != "財務報告書"
                           and x not in ("無", "有")), "")
            mo, day = QUARTER_END[qq]
            rows.append({
                "stock_id": c[0].strip(),
                "period_end": pd.Timestamp(year, mo, day),
                "nature": nature,
                "class_code": klass,
                "detail": detail,
                "filename": fname,
                "upload_ts": _roc_ts(ts),
                "roc_period": period,
            })
        return pd.DataFrame(rows, columns=COLUMNS)
    return None


# The 英文版 translation of a report lands weeks after the Chinese one and
# carries no new figures, so it cannot be what made a period public. Dating a
# quarter by it would move availability past the day the numbers were already
# being traded on.
ENGLISH = "英文版"


def documents() -> pd.DataFrame:
    """Every Chinese report collected, one row per document."""
    files = sorted(OUT_DIR.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"{OUT_DIR.name}/ is empty — run this module first")
    # Keyed by the code the page was asked for, which is the file's own name.
    # A company that listed after it was already 公開發行 filed its earliest
    # reports under a six-digit registration number — 3095's 1998-2000 rows are
    # filed as 232320 — and the server returns those on the listed code's page.
    # They are the same company, so they are kept; but joining a panel on the
    # code inside the row would file them under an identifier no price series
    # has. The row's own code is kept beside it as `filed_as`.
    # Out of range per file, before the concat rather than after it. A
    # 更(補)正 filename the server stores as given can encode a period a century
    # away — ROC 920 reads as 2831 — which pandas cannot hold as a nanosecond
    # timestamp at all, so a concat that mixes one such frame with the rest
    # raises where a later filter would have caught it. Dropped rather than
    # clipped, because a period that cannot be read is not a period this panel
    # can date; 13 rows in 255,943, all of them pre-2001 documents.
    frames, unreadable = [], []
    for f in files:
        one = pd.read_parquet(f).assign(requested_id=f.stem)
        ok = (one["period_end"] >= pd.Timestamp("1990-01-01")) & \
             (one["period_end"] <= pd.Timestamp("2030-12-31"))
        unreadable += one.loc[~ok, "filename"].tolist()
        frames.append(one[ok])
    if unreadable:
        log(f"  unreadable-period dropped {len(unreadable)}: {unreadable[:4]}")
    d = pd.concat(frames, ignore_index=True)
    d = d.rename(columns={"stock_id": "filed_as", "requested_id": "stock_id"})
    d = d[~d["nature"].str.contains(ENGLISH, na=False)]
    if d["upload_ts"].isna().any():
        raise ValueError(f"{int(d['upload_ts'].isna().sum())} filings carry no "
                         f"上傳日期; a row without one cannot date anything")
    return d


def consolidate() -> pd.DataFrame:
    """One row per company-quarter: when its figures first became public.

    A period can carry several documents — a parent report and a consolidated
    one, an original and a 更(補)正 correction — and the earliest of them is
    when a reader could first have acted. Corrections are deliberately not
    preferred over the original: a figure restated in August was still the
    published figure in May, and dating the period by the restatement would
    hand a trader the corrected number for months it did not exist.
    """
    d = documents()
    # A report uploaded on or before the last day of the quarter it is filed
    # under cannot be that quarter's report. The filename numbers a company's
    # fiscal quarters and QUARTER_END reads them as calendar ones, so a company
    # whose fiscal year does not end in December files each report under a
    # quarter it does not close: 3087's 201201 was uploaded on 2012-02-24.
    # Those documents are dropped before the earliest is taken, so a quarter
    # that also carries a report uploaded after it closed is dated by that
    # report. The same fiscal years' reports uploaded after their quarter
    # closed look like a December filer's and stay.
    early = d["upload_ts"].dt.normalize() <= d["period_end"]
    if early.any():
        log(f"  filed before its quarter closed, dropped {int(early.sum())} "
            f"from {d.loc[early, 'stock_id'].nunique()} companies")
    d = d[~early]
    out = (d.sort_values("upload_ts")
             .groupby(["stock_id", "period_end"], as_index=False)
             .first()[["stock_id", "period_end", "upload_ts", "class_code",
                       "nature", "filename", "filed_as"]]
             .rename(columns={"upload_ts": "first_public"})
             .sort_values(["stock_id", "period_end"])
             .reset_index(drop=True))
    return out


def targets() -> list[str]:
    """The companies whose statement trees this dates: `fin_is/` is the frame."""
    ids = sorted(p.stem for p in (ROOT / "fin_is").glob("*.parquet"))
    if not ids:
        raise FileNotFoundError("fin_is/ is empty — nothing to date")
    return ids


def covers_tree(stock_id: str) -> bool:
    """Whether the cached history reaches the newest period the tree carries.

    What the file holds, not that it exists. The statements are pulled on their
    own schedule and this cache on its own, so a file written before the tree
    gained a quarter is skipped for existing and that quarter can never be
    dated: `observed_date` returns NaT and the row leaves a join silently
    instead of failing. A company whose newest statement genuinely has no filing
    on the server is re-asked once per run, which is what not skipping the ones
    that do costs.
    """
    tree = ROOT / "fin_is" / f"{stock_id}.parquet"
    path = OUT_DIR / f"{stock_id}.parquet"
    if not path.exists():
        return False
    if not tree.exists() or not pq.read_metadata(tree).num_rows:
        return True                          # no statements to date
    ends = pd.to_datetime(pd.read_parquet(tree, columns=["date"])["date"])
    have = pd.to_datetime(pd.read_parquet(path, columns=["period_end"])["period_end"])
    return bool(len(have)) and have.max() >= ends.max()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated stock_ids")
    ap.add_argument("--consolidate", action="store_true",
                    help="build filing_dates.parquet from what is collected")
    args = ap.parse_args()

    if args.consolidate:
        out = consolidate()
        out.to_parquet(PANEL, index=False)
        log(f"{PANEL.name}: {len(out):,} company-quarters, "
            f"{out.stock_id.nunique():,} companies, "
            f"{out.period_end.min().date()}..{out.period_end.max().date()}")
        return 0

    ids = args.only.split(",") if args.only else targets()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    done = failed = skipped = empty = 0

    for i, sid in enumerate(ids, 1):
        path = OUT_DIR / f"{sid}.parquet"
        if covers_tree(sid):
            skipped += 1
            continue
        df = fetch(sid)
        time.sleep(SLEEP_S)
        if df is None:
            failed += 1
            log(f"  fail {sid}")
            continue
        if not len(df):
            # An empty history is an answer only because `fetch` refuses to
            # return a throttle page as one. Written so the next run does not
            # ask again, and counted so the total is visible rather than buried.
            empty += 1
        df.to_parquet(path, index=False)
        done += 1
        if i % 50 == 0 or len(df) == 0:
            log(f"  {i}/{len(ids)} {sid} rows={len(df)}")

    log(f"filing_dates: wrote {done}, skipped {skipped}, failed {failed}, "
        f"empty {empty}")
    if done == 0 and skipped == 0:
        log("FAIL nothing was collected")
        return 1
    if empty:
        # Twice now an empty history has meant the collector misread the page
        # rather than the company having filed nothing — the throttle notice,
        # then the 金控 subsidiary picker. Both returned HTTP 200 and parsed to
        # zero rows, and both were found only because someone counted. A listed
        # company with no financial report at all is rare enough that the run
        # ends non-zero and names them, rather than reporting a clean pass over
        # a gap of unknown cause.
        names = sorted(p.stem for p in OUT_DIR.glob("*.parquet")
                       if not len(pd.read_parquet(p)))
        log(f"FAIL {len(names)} companies recorded an empty filing history "
            f"({names[:8]}). Check one against the site before accepting it")
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
