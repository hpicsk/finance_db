"""일괄파일 아카이브를 읽는 쪽. **어느 빈티지를 읽을지**가 이 모듈의 전부다.

FSS 는 제출이 들어오는 대로 일괄파일을 다시 만들고, 새 파일은 이름 끝 14자리
생성시각만 바꿔 붙는다. 옛 파일은 지워지지 않으므로 같은 (연도·분기·재무제표)에
빈티지가 여러 벌 남는다. 고르는 규칙이 아카이브의 성질이라 여기 있고, 읽은 값을
무슨 계정으로 해석하는지는 소비자의 방법론이라 여기 없다.

    from dart_bulk import latest_vintages, open_zip, sheets

    for p in latest_vintages("*_4Q_PL_*.zip"):
        with open_zip(p) as zf:
            for info, name, consolidated in sheets(zf):
                ...            # 항목코드 → 필드 매핑은 부르는 쪽이 한다
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:                      # pandas stays out of the import path;
    import pandas as pd                # only coverage() needs it, at the call.

HERE = Path(__file__).resolve().parent
BULK_DIR = HERE / "data" / "bulk"

# 각 zip 은 업종으로 갈린다 — 일반(무접미사) / 금융기타 / 보험 / 은행 / 증권. 금융업
# 시트는 계정 체계가 달라 같은 항목코드가 다른 것을 뜻하므로, 거르는 쪽이 기본이다.
FINANCIAL_SECTORS = ("금융기타", "보험", "은행", "증권")

ZIP_RE = re.compile(r"(\d{4})_(\d)Q_([A-Z]{2})_(\d{14})\.zip")

REPORT_KO = {"FY": "사업보고서", "HY": "반기보고서", "FQ": "1분기보고서", "TQ": "3분기보고서"}
STMT_KO = {"BS": "재무상태표", "PL": "손익계산서", "CF": "현금흐름표", "CE": "자본변동표"}
QUARTER_REPORT = {"1": "FQ", "2": "HY", "3": "TQ", "4": "FY"}


def latest_vintages(pattern: str, root: Path | None = None) -> list[dict]:
    """(연도·분기·재무제표)마다 생성 시각이 가장 늦은 zip 하나씩. 고른 근거를 함께 준다.

    전부 읽으면 먼저 정렬된 옛 스냅샷이 중복 제거에서 이겨 — 다중키 sort_values 는
    안정 정렬이라 동점은 읽은 순서로 풀린다 — 최신 파일을 받아놓고도 옛 숫자를 쓴다.
    우연히 그럴 때가 있는 것이 아니라 항상 그 방향이다.

    사전순이 시각순인 것에 기대지 않고 14자리를 명시적으로 뽑는다. 이름이 규칙에
    맞지 않으면 멈춘다: 못 읽은 이름은 "빈티지 0"이 아니라 "빈티지 모름"이고,
    기본값을 주는 순간 그 파일이 조용히 가장 낡은 것이 되어 정렬에서 진다.

    옛 빈티지로 결측을 메우지 않는다. 폐기된 파일의 값과 현재 파일의 값을 한
    기업-연도 행에 섞으면 어느 시점에도 존재한 적 없는 행이 된다. 최신 한 벌만
    믿고 나머지는 버린다.

    superseded 는 "오늘 디스크에 남아 있는 옛 빈티지"다. download 가 받자마자
    지우므로 보통 비어 있고, 빈 것은 "재생성된 적 없음"이 아니라 "이미 치웠음"을
    뜻한다. 지운 이름은 bulk_vintage_pruned.csv 에 남는다.
    """
    groups: dict[tuple[int, str, str], list[tuple[str, Path]]] = {}
    for zp in sorted((root or BULK_DIR).glob(pattern)):
        m = ZIP_RE.fullmatch(zp.name)
        if not m:
            sys.exit(f"빈티지를 읽을 수 없는 파일명: {zp.name} — "
                     "{연도}_{분기}Q_{재무제표}_{생성시각 14자리}.zip 이어야 한다")
        groups.setdefault((int(m[1]), m[2], m[3]), []).append((m[4], zp))

    picked = []
    for (year, quarter, stmt), cands in sorted(groups.items()):
        cands.sort()
        vintage, zp = cands[-1]
        picked.append({"year": year, "quarter": quarter, "stmt": stmt,
                       "vintage": vintage, "file": zp.name,
                       "superseded": ";".join(z.name for _, z in cands[:-1])})
    return picked


def open_zip(picked: dict | str, root: Path | None = None) -> zipfile.ZipFile:
    """latest_vintages 가 고른 한 벌(또는 파일명)을 연다."""
    name = picked["file"] if isinstance(picked, dict) else picked
    return zipfile.ZipFile((root or BULK_DIR) / name)


def entry_name(info: zipfile.ZipInfo) -> str:
    """zip 엔트리 이름은 CP949 바이트인데 아카이버가 CP437 로 태그해 놓았다."""
    try:
        return info.filename.encode("cp437").decode("cp949")
    except Exception:
        return info.filename


def sheets(zf: zipfile.ZipFile, skip_sectors=FINANCIAL_SECTORS):
    """(info, 이름, 연결여부) 순회. 기본값은 금융업 시트를 뺀 '일반' 업종."""
    for info in zf.infolist():
        nm = entry_name(info)
        if not nm.lower().endswith(".txt"):
            continue
        if any(s in nm for s in skip_sectors):
            continue
        yield info, nm, ("_연결_" in nm or nm.endswith("_연결.txt"))


def coverage(root: Path | None = None) -> "pd.DataFrame":
    """디스크에 실제로 있는 것. 선언이 아니라 측정이다 --- 대장은 조용히 낡는다.

    행이 (연도·분기), 열이 재무제표, 값이 빈티지 생성시각. 빈칸은 "안 받음"이고
    "발행처가 안 냄"이 아니다: 둘을 가르려면 download.catalog() 로 사이트가 지금
    제공하는 목록을 받아 이 표와 대조한다.
    """
    import pandas as pd
    rows = latest_vintages("*.zip", root)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["report"] = df["quarter"].map(QUARTER_REPORT)
    return (df.pivot_table(index=["year", "report"], columns="stmt",
                           values="vintage", aggfunc="first")
              .sort_index())
