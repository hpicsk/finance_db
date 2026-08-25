"""OpenDART 재무정보 일괄다운로드 — 전 상장사 재무제표를 파일 몇 개로.

왜 이 경로인가: 기업별 엔드포인트(fnlttSinglAcntAll)는 기업-연도마다 한 콜이다.
300종목 11년 스크린 하나가 약 3,300콜이고, 그만큼 부르면 호출 IP 가 막힌다
(opendart 가 /error1.html 로 리다이렉트한 뒤 TLS 를 끊는다). 일괄 엔드포인트는
같은 재무제표를 (사업연도·보고서·재무제표)당 zip 한 개로 주므로 11년 전체 갱신이
33 요청이고 한도에 걸릴 수가 없다.

목록 파싱은 선택이 아니다. zip 이름에 생성 시각이 박혀 있고(2015_4Q_BS_2023…zip)
FSS 가 파일을 다시 만들 때마다 그 시각이 바뀌므로 URL 을 상수로 둘 수 없다.

  python -m dart_bulk.download --list
  python -m dart_bulk.download --years 2015-2025 --reports FY
  python -m dart_bulk.download --years 2026 --reports FQ,HY --statements BS,PL,CF

보고서: FY 사업보고서 · HY 반기 · FQ 1분기 · TQ 3분기
재무제표: BS 재무상태표 · PL 손익계산서 · CF 현금흐름표 · CE 자본변동표
"""
import argparse
import csv
import re
import sys
import time
import zipfile
from pathlib import Path

import requests

from .loader import BULK_DIR, REPORT_KO, STMT_KO

BASE = "https://opendart.fss.or.kr"
LIST_URL = f"{BASE}/disclosureinfo/fnltt/dwld/list.do"
DOWN_URL = f"{BASE}/cmm/downloadFnlttZip.do"
HERE = Path(__file__).resolve().parent

OUT = BULK_DIR
PRUNED = HERE / "bulk_vintage_pruned.csv"

HDRS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Referer": f"{BASE}/disclosureinfo/fnltt/dwld/main.do",
}
ENTRY_RE = re.compile(
    r"download_ext002\('(\d{4})','([A-Z]{2})',\s*'([A-Z]{2})',\s*'([^']+)'\)")

VINTAGE_RE = re.compile(r"^(.*_)(\d{14})\.zip$")


def atomic(path: Path, write) -> Path:
    """옆에 쓰고 제자리로 옮긴다. 막는 것은 쓰다 죽는 것이 아니라 **짧아진 파일이
    자리에 남는 것**이다 --- 아래 fetch 가 존재만 보고 건너뛰므로, 잘린 zip 이 남으면
    다시 받지 않고 소비자가 매번 그것을 연다. 임시 파일을 같은 파일시스템 안에
    두어야 replace 가 원자적이다."""
    tmp = path.with_name(path.name + ".part")
    try:
        write(tmp)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def catalog(sess) -> list[tuple[str, str, str, str]]:
    """(year, report, statement, filename) — 사이트가 지금 제공하는 전부."""
    r = sess.post(LIST_URL, headers=HDRS, timeout=90)
    r.raise_for_status()
    entries = ENTRY_RE.findall(r.text)
    if not entries:
        raise SystemExit("목록 파싱 실패 — 페이지 구조가 바뀌었을 수 있음")
    return entries


def fetch(sess, fname: str, retries=3) -> Path | None:
    dest = OUT / fname
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    for a in range(retries):
        try:
            r = sess.get(DOWN_URL, params={"fl_nm": fname}, headers=HDRS, timeout=600)
            if r.status_code == 200 and r.content[:2] == b"PK":
                atomic(dest, lambda t: t.write_bytes(r.content))
                return dest
            print(f"    HTTP {r.status_code}, {len(r.content):,}B — zip 아님")
        except Exception as e:
            print(f"    retry {a+1}: {type(e).__name__}")
        time.sleep(3 * (a + 1))
    return None


def prune(keep: Path) -> list[str]:
    """같은 (연도·분기·재무제표)에서 keep 보다 낡은 빈티지를 지운다. 지운 이름을 준다.

    이름 끝 14자리를 정수로 비교한다. 사전순이 마침 시각순인 것에 기대면 자리수가
    바뀌는 날 조용히 최신 파일을 지운다 --- loader.latest_vintages 와 같은 이유다.
    낡은 것만 지우므로 디스크에 더 새 파일이 있으면 이 함수는 아무것도 안 지운다.
    """
    m = VINTAGE_RE.match(keep.name)
    if not m:
        sys.exit(f"빈티지를 읽을 수 없는 파일명: {keep.name} — "
                 "{연도}_{분기}Q_{재무제표}_{생성시각 14자리}.zip 이어야 한다")
    gone = []
    for old in OUT.glob(f"{m[1]}*.zip"):
        o = VINTAGE_RE.match(old.name)
        if o and int(o[2]) < int(m[2]):
            old.unlink()
            gone.append(old.name)
    return gone


def record(gone: list[tuple[str, str]]):
    """지운 빈티지 이름을 추적 파일에 덧붙인다.

    지우기만 하면 그 파일이 있었다는 사실이 사라진다. 소비자의 bulk_vintage.csv 는
    오늘 디스크에 남은 것만 superseded 로 적으므로, 청소한 뒤 그 열은 늘 비고
    "재생성된 적 없음"으로 읽힌다 --- 지운 것과 없던 것이 같은 빈칸이 된다.
    일괄파일이 다시 만들어졌다는 것 자체가 개정 신호라서, 값이 아니라 그 사실을
    남긴다. 덧붙이기만 하고 지우지 않는다.
    """
    rows = {}
    if PRUNED.exists():
        with PRUNED.open(encoding="utf-8") as fh:
            rows = {r["file"]: r for r in csv.DictReader(fh)}
    rows.update({f: {"file": f, "superseded_by": by} for f, by in gone})
    with PRUNED.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["file", "superseded_by"])
        w.writeheader()
        w.writerows([rows[k] for k in sorted(rows)])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", default="2015-2025", help="2015-2025 또는 2026")
    ap.add_argument("--reports", default="FY", help="FY,HY,FQ,TQ 중 쉼표 구분")
    ap.add_argument("--statements", default="BS,PL,CF",
                    help="BS,PL,CF,CE 중 쉼표 구분")
    ap.add_argument("--list", action="store_true", help="받지 않고 목록만 출력")
    a = ap.parse_args()

    lo, _, hi = a.years.partition("-")
    years = {str(y) for y in range(int(lo), int(hi or lo) + 1)}
    reports = set(a.reports.split(","))
    stmts = set(a.statements.split(","))

    OUT.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()
    try:
        sess.get(BASE, headers=HDRS, timeout=30)
    except Exception as e:
        sys.exit(f"opendart 접속 불가 ({type(e).__name__}) — 차단 여부 확인")

    entries = catalog(sess)
    print(f"사이트 제공 파일 {len(entries)}개 "
          f"(FY{min(e[0] for e in entries)}–{max(e[0] for e in entries)})")

    want = [e for e in entries if e[0] in years and e[1] in reports and e[2] in stmts]
    print(f"요청 조건 일치 {len(want)}개\n")
    if a.list:
        for y, rep, sj, fn in sorted(want):
            print(f"  {y} {REPORT_KO.get(rep,rep):<8} {STMT_KO.get(sj,sj):<7} {fn}")
        return

    ok, fail, total, gone = 0, [], 0, []
    for y, rep, sj, fn in sorted(want):
        p = fetch(sess, fn)
        if p:
            n = len(zipfile.ZipFile(p).namelist())
            total += p.stat().st_size
            ok += 1
            # 받은 뒤에만 지운다. 캐시로 건너뛴 파일도 지나가므로 다시 돌리면 밀린
            # 옛 빈티지가 정리된다.
            old = prune(p)
            gone += [(o, fn) for o in old]
            print(f"  ✓ {y} {REPORT_KO.get(rep,rep):<8} {STMT_KO.get(sj,sj):<7} "
                  f"{p.stat().st_size/1e6:7.1f}MB  {n}개 파일"
                  + (f"  (옛 빈티지 {len(old)}개 삭제)" if old else ""))
        else:
            fail.append(fn)
            print(f"  ✗ {fn}")
        time.sleep(1.0)

    if gone:
        record(gone)
        print(f"\n옛 빈티지 {len(gone)}개 삭제 → 이름은 {PRUNED.name} 에 남는다")

    print(f"\n완료 {ok}/{len(want)} · {total/1e6:,.0f}MB → {OUT}")
    if fail:
        print("실패:", ", ".join(fail))
        sys.exit(1)


if __name__ == "__main__":
    main()
