"""DART 사업보고서 first filings → each audit opinion as first published.

``dart_audit`` asks the structured endpoint (``accnutAdtorNmNdAdtOpinion.json``)
for each (ticker, bsns_year), and that endpoint answers from the report as last
amended. This collector finds each report's first filing and its opinion:

  1. ``list.json`` (정기공시, every version) lists each 사업보고서 of a corp_code,
     the original and every 정정, with its receipt number and date.
  2. A report never amended is the filing ``dart_audit`` already read: its first
     filing is that one, and the opinion is the cached one.
  3. For an amended report, ``document.xml`` fetches the first filing, and the
     opinion is the cell DART tags ``OPN_CMT1`` — the 당기 감사의견 in
     "V. 회계감사인의 감사의견 등", the cell the structured endpoint reports.

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
# DART tags the 당기 opinion cell ACODE="OPN_CMT1"; the form in use since the FY2024
# reports splits it into AUNIT="OPN_CMT1_A" (감사보고서) and "OPN_CMT1_C" (연결), in
# that order, and the first is the row the structured endpoint reports first.
_CELL_RE = re.compile(
    r'<(TE|TD|TU)[^>]*(?:ACODE|AUNIT)="(OPN_CMT1(?:_[A-Z])?|OPN_YEAR1)"[^>]*>(.*?)</\1>', re.S)
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


def first_opinion(rcept_no: str) -> str | None:
    """The 당기 감사의견 of filing `rcept_no`, read from its OPN_CMT1 cell.

    None when DART holds no document for the filing (status 013/014), the
    document carries no such cell, or row 1 is labelled 전기; a quota or any
    other DART error raises.
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
    # opinion cell is read, where a replaced character would show in `raw`.
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp949", errors="replace")
    cells = [(code, re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body)
                                                         .replace("&cr;", "\n"))).strip())
             for _, code, body in _CELL_RE.findall(text)]
    year = next((v for c, v in cells if c == "OPN_YEAR1"), "")
    opinion = next((v for c, v in cells if c.startswith("OPN_CMT1")), None)
    # Row 1 of the form is the 당기; a label naming 전기 means the tags lie.
    return None if opinion is None or "전" in year else opinion


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
            # its receipt number rather than by 접수일자: its opinion is cached.
            if amends.empty and first["rcept_no"][:8] == r.receipt_dt.strftime("%Y%m%d"):
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
    FIRST_PATH.parent.mkdir(parents=True, exist_ok=True)
    done.to_parquet(FIRST_PATH, index=False)
    return done


def main(argv=None) -> int:
    collect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
