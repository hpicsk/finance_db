"""KOSPI 200 / KOSDAQ 150 구성종목 변경내역 — the exchange's own event log.

`collect_index_members.py` stacks month-end (or daily) snapshots and infers a
rebalancing from the difference between two of them. This script asks KRX for
the change events themselves, which it publishes:

    반영일 (``appl_dd``) | 편입종목 (``transschl``) | 제외종목 (``excld``)

One call returns the whole history — KOSPI200 from 2000-04-12, KOSDAQ150 from
2015-07 — and needs no login, unlike the membership endpoint.

Source
    https://index.krx.co.kr/contents/MKD/03/0304/03040101/MKD03040101T3.jsp
    (the 구성종목 tab, 구성종목변경내역 radio button), whose backing API is

      GET  /contents/COM/GenerateOTP.jspx?bld=...&name=form  -> OTP code
      POST /contents/MKD/99/MKD99000001.jspx with code+form  -> JSON

Output (``output/index_changes.parquet``)
    | date       | index      | action | isin         | ticker | name           |
    | 2025-12-29 | 코스피 200 | ADD    | KR7071970008 | 071970 | HD현대마린엔진 |
    | 2025-12-29 | 코스피 200 | REMOVE | KR7042670000 | 042670 | HD현대인프라코어 |

    An event carrying both an entry and an exit becomes two rows. A one-sided
    event — a delisting, say — arrives with only its own side filled.

    python collect_index_changes.py                  # both indices, whole history
    python collect_index_changes.py --start 20200101
"""

import argparse
import time
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import requests

from krx_utils import DEFAULT_DELAY, DEFAULT_END, save_with_csv, setup_logging

logger = setup_logging()

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

_BASE = "https://index.krx.co.kr"
_OTP_URL = f"{_BASE}/contents/COM/GenerateOTP.jspx"
_DATA_URL = f"{_BASE}/contents/MKD/99/MKD99000001.jspx"
_BLD = "/IDX/03/0304/03040101/mkd03040101T3_03"

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# ind_tp_cd, idx_ind_cd, idx_id, idxCd (the last is for the display URL)
INDEX_TARGETS: Dict[str, Tuple[str, str, str, str]] = {
    "코스피 200": ("1", "028", "K2G01P", "1028"),
    "코스닥 150": ("2", "203", "Q2C01P", "2203"),
}


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": _UA})
    s.get(f"{_BASE}/main/main.jsp", timeout=15)
    return s


def _fetch_one(
    s: requests.Session,
    index_name: str,
    ind_tp_cd: str,
    idx_ind_cd: str,
    idx_id: str,
    idxCd: str,
    fromdate: str,
    todate: str,
) -> List[dict]:
    referer = (
        f"{_BASE}/contents/MKD/03/0304/03040101/MKD03040101T3.jsp"
        f"?upmidCd=0102&idxCd={idxCd}&idxId={idx_id}"
    )
    otp = s.get(
        _OTP_URL,
        params={"bld": _BLD, "name": "form"},
        headers={"Referer": referer},
        timeout=15,
    )
    otp.raise_for_status()

    form = {
        "ind_tp_cd": ind_tp_cd,
        "idx_ind_cd": idx_ind_cd,
        "idx_id": idx_id,
        "lang": "ko",
        "compst_isu_tp": "2",
        "fromdate": fromdate,
        "todate": todate,
        "pagePath": "/contents/MKD/03/0304/03040101/MKD03040101T3.jsp",
        "code": otp.text,
    }
    r = s.post(
        _DATA_URL,
        data=form,
        headers={"Referer": referer, "X-Requested-With": "XMLHttpRequest"},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    return payload.get("output", []) or []


def _normalize(rows: List[dict], index_name: str) -> pd.DataFrame:
    records = []
    for row in rows:
        date = row.get("appl_dd", "").replace("/", "-")
        if not date:
            continue
        add_isin = (row.get("transschl_isu_cd") or "").strip()
        add_name = (row.get("transschl_isu_nm") or "").strip()
        rm_isin = (row.get("excld_isu_cd") or "").strip()
        rm_name = (row.get("excld_isu_nm") or "").strip()

        if add_isin or add_name:
            records.append({
                "date": date, "index": index_name, "action": "ADD",
                "isin": add_isin, "ticker": add_isin[3:9] if len(add_isin) >= 9 else "",
                "name": add_name,
            })
        if rm_isin or rm_name:
            records.append({
                "date": date, "index": index_name, "action": "REMOVE",
                "isin": rm_isin, "ticker": rm_isin[3:9] if len(rm_isin) >= 9 else "",
                "name": rm_name,
            })
    return pd.DataFrame(records)


def collect_index_changes(
    start: str = "19981228",
    end: str = DEFAULT_END,
    targets: Dict[str, Tuple[str, str, str, str]] = None,
    output_path: Path = OUTPUT_DIR / "index_changes.parquet",
    delay: float = DEFAULT_DELAY,
) -> pd.DataFrame:
    if targets is None:
        targets = INDEX_TARGETS

    s = _make_session()
    frames = []
    for index_name, (ind_tp_cd, idx_ind_cd, idx_id, idxCd) in targets.items():
        logger.info("Fetching %s (%s ~ %s)", index_name, start, end)
        rows = _fetch_one(s, index_name, ind_tp_cd, idx_ind_cd, idx_id, idxCd, start, end)
        df = _normalize(rows, index_name)
        logger.info("  → %d events (%d rows after expansion)", len(rows), len(df))
        if not df.empty:
            frames.append(df)
        time.sleep(delay)

    if not frames:
        logger.error("No data collected")
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.sort_values(["index", "date", "action", "ticker"]).reset_index(drop=True)

    save_with_csv(out, output_path)
    logger.info("Saved: %s  (%d rows)", output_path, len(out))
    return out


def main():
    parser = argparse.ArgumentParser(description="KOSPI200/KOSDAQ150 constituent-change collector")
    parser.add_argument("--start", default="19981228")
    parser.add_argument("--end",   default=DEFAULT_END)
    parser.add_argument("--delay", default=DEFAULT_DELAY, type=float)
    args = parser.parse_args()

    collect_index_changes(start=args.start, end=args.end, delay=args.delay)


if __name__ == "__main__":
    main()
