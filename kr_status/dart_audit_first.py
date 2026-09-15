"""DART 사업보고서 first filings → each audit opinion as first published.

``dart_audit`` asks the structured endpoint (``accnutAdtorNmNdAdtOpinion.json``)
for each (ticker, bsns_year), and that endpoint answers from the report as last
amended. This collector finds each report's first filing and its opinion:

  1. ``list.json`` (정기공시, every version) lists each 사업보고서 of a corp_code,
     the original and every 정정, with its receipt number and date.
  2. A report never amended is the filing ``dart_audit`` already read: its first
     filing is that one, and the opinion is the cached one, unless the endpoint
     gave no opinion text; then the document is read as in step 3.
  3. For an amended report, ``document.xml`` fetches the first filing, and the
     opinion is read from its opinion table — the cells DART tags ``OPN_CMTk``,
     the ones the structured endpoint reports, or in older untagged forms the
     table whose header names 사업연도 and 감사의견 (where none does, 감사(검토)의견
     or 사업년도) — on the current-period row.

Output (``data/dart_audit_first_filings.parquet``): one row per (ticker,
bsns_year) of ``data/dart_audit_opinions.parquet`` — ticker, bsns_year,
rcept_no, receipt_dt, opinion_code, raw, n_amendments. ``receipt_dt`` is the
접수일자 ``list.json`` gives, which can fall a day or more after the date in the
receipt number (the date ``dart_audit_opinions`` carries). A row whose first
filing cannot be read keeps rcept_no, receipt_dt and n_amendments and leaves raw
and opinion_code empty. Resume-safe: rows already written are skipped, so a
harvest that adds a fiscal year only fetches the new rows.

Usage (from the repo root, with OPEN_DART_API_KEY exported):
    python -m kr_status.dart_audit_first
"""
from __future__ import annotations

import html
import io
import os
import re
import sys
import time
import zipfile

import pandas as pd
import requests

from kr_status.corp_code_map import DATA_DIR
from kr_status.dart_audit import OPINIONS_PATH, _classify

FIRST_PATH = DATA_DIR / "dart_audit_first_filings.parquet"
CORP_CODES = DATA_DIR / "corp_code_cache.parquet"

_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
_DOC_URL = "https://opendart.fss.or.kr/api/document.xml"
LIST_FROM = "20150101"   # the first bsns_year dart_audit reads is 2015

# "사업보고서 (2021.12)", "[기재정정]사업보고서 (2021.12)": the bracket marks an
# amendment, and the period's year is the bsns_year the structured endpoint uses.
# "[첨부추가]" is the exception: DART relabels the original filing itself when an
# attachment is added to it, so that entry keeps the original's receipt number.
_REPORT_RE = re.compile(r"^(?:\[(?P<amend>[^\]]+)\])?사업보고서 \((?P<year>\d{4})\.\d{2}\)$")
# DART tags the opinion table's cells ACODE="OPN_YEARk" / "OPN_CMTk" for row k; the form
# in use since the FY2024 reports splits the opinion into AUNIT="OPN_CMTk_A" (감사보고서)
# and "_C" (연결), in that order, and the first is what the structured endpoint
# reports. Older forms leave the table untagged, so it is found by its header.
_TAG_RE = re.compile(
    r'<(TE|TD|TU)[^>]*(?:ACODE|AUNIT)="OPN_(YEAR|CMT)(\d)(?:_[A-Z])?"[^>]*>(.*?)</\1>', re.S)
_CELL_ANY_RE = re.compile(r"<(TD|TE|TH|TU)\b[^>]*>(.*?)</\1>", re.S)
_PERIOD_RE = re.compile(r"제\s*(\d+)\s*기")
_COLS = ["ticker", "bsns_year", "rcept_no", "receipt_dt", "opinion_code", "raw",
         "n_amendments"]


def _key() -> str:
    key = os.environ.get("OPEN_DART_API_KEY")
    if not key:
        raise RuntimeError("OPEN_DART_API_KEY not set in env")
    return key


def _quota_or_raise(status: str, message: str) -> None:
    if status in ("020", "021"):
        raise RuntimeError(f"DART quota/rate failure: status={status} msg={message}")
    raise RuntimeError(f"DART answered status={status} msg={message}")


def annual_filings(corp_code: str) -> pd.DataFrame:
    """Every 사업보고서 filing of `corp_code` since LIST_FROM, originals and 정정."""
    rows, page = [], 1
    while True:
        r = requests.get(_LIST_URL, params={
            "crtfc_key": _key(), "corp_code": corp_code, "bgn_de": LIST_FROM,
            "end_de": pd.Timestamp.today().strftime("%Y%m%d"), "last_reprt_at": "N",
            "pblntf_ty": "A", "page_no": page, "page_count": 100}, timeout=30)
        r.raise_for_status()
        j = r.json()
        status = str(j.get("status"))
        if status == "013":       # no filing in the window
            break
        if status != "000":
            _quota_or_raise(status, j.get("message"))
        for it in j.get("list", []):
            m = _REPORT_RE.match(it["report_nm"].strip())
            if m and "철" not in (it.get("rm") or ""):
                rows.append({"bsns_year": int(m["year"]),
                             "amended": m["amend"] not in (None, "첨부추가"),
                             "rcept_no": it["rcept_no"],
                             "receipt_dt": pd.Timestamp(it["rcept_dt"])})
        if page >= int(j.get("total_page") or 1):
            break
        page += 1
    return pd.DataFrame(rows, columns=["bsns_year", "amended", "rcept_no", "receipt_dt"])


def _clean(cell: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cell)
                                           .replace("&cr;", "\n"))).strip()


def _current(rows: list[tuple[str, str]]) -> str:
    """The opinion of the current period among (period label, opinion) rows: the
    row labelled 당기 — the order varies, some filers list the oldest first —
    else the highest 제N기, else the first row."""
    def period(label: str) -> int:
        m = _PERIOD_RE.search(label)
        return int(m.group(1)) if m else -1
    pool = [r for r in rows if "당" in r[0] and "전" not in r[0]] or rows
    return max(pool, key=lambda r: period(r[0]))[1] if any(period(r[0]) >= 0 for r in pool) else pool[0][1]


def opinion_from_document(text: str) -> str | None:
    """The current-period 감사의견 in a 사업보고서's main document, or None when it
    has no opinion table. Tagged cells are read first; an untagged table is the
    first with a header row whose cells are 사업연도 and 감사의견…, and where no
    table has one, 감사(또는 검토)의견, 감사(검토)의견 or 감사 및 검토 의견 — a
    header that can also stand over a review conclusion — with 사업연도 in its
    older spelling 사업년도."""
    tagged: dict[int, list[str | None]] = {}
    for _, kind, k, body in _TAG_RE.findall(text):
        row = tagged.setdefault(int(k), ["", None])
        if kind == "YEAR":
            row[0] = _clean(body)
        elif row[1] is None:
            row[1] = _clean(body)
    rows = [(label, opinion) for _, (label, opinion) in sorted(tagged.items()) if opinion is not None]
    if rows:
        return _current(rows)
    tables = re.findall(r"<TABLE\b.*?</TABLE>", text, re.S)
    for loose in (False, True):
        for table in tables:
            trs = [[_clean(c) for _, c in _CELL_ANY_RE.findall(tr)]
                   for tr in re.findall(r"<TR\b.*?</TR>", table, re.S)]
            # A header cell is the label itself; a listing-requirements table also has
            # a row mentioning "최근 사업연도 감사의견 적정", which is not a header.
            norm = [[re.sub(r"\s+", "", c) for c in r] for r in trs]
            if loose:
                norm = [[re.sub(r"\(.*?\)|및검토", "", c).replace("사업년도", "사업연도")
                         for c in r] for r in norm]
            head = next((i for i, r in enumerate(norm)
                         if "사업연도" in r and any(c.startswith("감사의견") for c in r)), None)
            if head is None:
                continue
            col = next(j for j, c in enumerate(norm[head]) if c.startswith("감사의견"))
            rows = [(r[0], r[col]) for r in trs[head + 1:] if len(r) > col and r[0]]
            if rows:
                return _current(rows)
    return None


def first_opinion(rcept_no: str) -> str | None:
    """The current-period 감사의견 of filing `rcept_no` (see opinion_from_document).

    None when DART holds no document for the filing (status 013/014) or the
    document has no opinion table; a quota or any other DART error raises.
    """
    r = requests.get(_DOC_URL, params={"crtfc_key": _key(), "rcept_no": rcept_no},
                     timeout=120)
    r.raise_for_status()
    if not zipfile.is_zipfile(io.BytesIO(r.content)):
        m = re.search(r"<status>(\d+)</status>.*?<message>(.*?)</message>", r.text, re.S)
        status, message = m.groups() if m else ("?", r.text[:200])
        if status in ("013", "014"):
            return None
        _quota_or_raise(status, message)
    # The main document is <rcept_no>.xml; older archives store it as /<rcept_no>.xml.
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    raw = zf.read({n.lstrip("/"): n for n in zf.namelist()}[f"{rcept_no}.xml"])
    # Older filings are EUC-KR, and a few carry a stray byte outside it; only the
    # opinion table is read, where a replaced character would show in `raw`.
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp949", errors="replace")
    return opinion_from_document(text)


def _first_rows(corp_rows: pd.DataFrame, filings: pd.DataFrame, sleep_s: float) -> list[dict]:
    out = []
    for r in corp_rows.itertuples(index=False):
        f = filings[filings["bsns_year"] == r.bsns_year].sort_values("rcept_no")
        orig, amends = f[~f["amended"]], f[f["amended"]]
        row = {"ticker": r.ticker, "bsns_year": r.bsns_year, "rcept_no": None,
               "receipt_dt": pd.NaT, "opinion_code": None, "raw": None,
               "n_amendments": len(amends)}
        if len(orig):
            first = orig.iloc[0]
            row.update(rcept_no=first["rcept_no"], receipt_dt=first["receipt_dt"])
            # Never amended, and the filing dart_audit read, whose row is dated by
            # its receipt number rather than by 접수일자: its opinion is cached —
            # unless the endpoint gave no text, when the document is read instead.
            cached = str(r.raw if pd.notna(r.raw) else "").strip() not in ("", "nan", "-")
            if (amends.empty and first["rcept_no"][:8] == r.receipt_dt.strftime("%Y%m%d")
                    and cached):
                row.update(raw=r.raw, opinion_code=r.opinion_code)
            else:
                text = first_opinion(first["rcept_no"])
                time.sleep(sleep_s)
                if text is not None:
                    row.update(raw=text, opinion_code=_classify(text))
        out.append(row)
    return out


def collect(sleep_s: float = 0.1) -> pd.DataFrame:
    opinions = pd.read_parquet(OPINIONS_PATH)
    codes = pd.read_parquet(CORP_CODES).set_index("ticker")["corp_code"]
    opinions["corp_code"] = opinions["ticker"].map(codes)
    missing = opinions["corp_code"].isna()
    if missing.any():
        raise RuntimeError(f"{int(missing.sum())} cached opinions have no corp_code in "
                           f"{CORP_CODES.name}; run dart_audit first")
    done = pd.read_parquet(FIRST_PATH) if FIRST_PATH.exists() else pd.DataFrame(columns=_COLS)
    have = set(zip(done["ticker"], done["bsns_year"]))
    todo = opinions[[k not in have for k in zip(opinions["ticker"], opinions["bsns_year"])]]
    print(f"[dart_audit_first] {opinions['corp_code'].nunique()} corp_codes, "
          f"{todo['corp_code'].nunique()} to list", file=sys.stderr)
    new: list[dict] = []
    try:
        for i, (corp, corp_rows) in enumerate(todo.groupby("corp_code", sort=True)):
            filings = annual_filings(corp)
            time.sleep(sleep_s)
            new += _first_rows(corp_rows, filings, sleep_s)
            if (i + 1) % 100 == 0:
                print(f"  {i + 1} corp_codes, {len(new)} rows", file=sys.stderr)
                done = _save(done, new)
                new = []
    finally:            # a quota stop keeps what it fetched; the next run resumes
        done = _save(done, new)
    print(f"wrote {len(done)} first filings → {FIRST_PATH}", file=sys.stderr)
    return done


def _save(done: pd.DataFrame, new: list[dict]) -> pd.DataFrame:
    if new:
        parts = [df for df in (done, pd.DataFrame(new, columns=_COLS)) if len(df)]
        done = pd.concat(parts, ignore_index=True)
    done = done.sort_values(["ticker", "bsns_year"]).reset_index(drop=True)
    # Labels are re-derived from `raw` on every write, as dart_audit does, so a
    # classifier change reaches every row; an unread first filing stays empty.
    done["opinion_code"] = done["raw"].map(lambda t: None if pd.isna(t) else _classify(t))
    FIRST_PATH.parent.mkdir(parents=True, exist_ok=True)
    done.to_parquet(FIRST_PATH, index=False)
    return done


def main(argv=None) -> int:
    collect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
