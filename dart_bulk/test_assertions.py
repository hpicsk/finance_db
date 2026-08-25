"""dart_bulk 가 문서에서 주장하는 것만 검사한다.

빈티지 선택은 이 패키지의 전부이므로 대부분이 그 검사다. 아카이브 자체가 없어도
규칙은 검사된다 — 가짜 이름으로 만든 임시 아카이브를 물린다.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_bulk import BULK_DIR, coverage, latest_vintages          # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    print(f"{'✓' if cond else '✗'} {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILED.append(name)


def picks(names, pattern="*_4Q_*.zip"):
    with tempfile.TemporaryDirectory() as d:
        for n in names:
            (Path(d) / n).write_bytes(b"")
        return latest_vintages(pattern, root=Path(d))


# 옛 것을 나중에 만들어 둔다. 글롭이 주는 순서가 아니라 14자리를 읽어서 고르는지를 본다.
p = picks(["2024_4Q_PL_20260819030822.zip", "2024_4Q_PL_20260813030928.zip"])
check("같은 (연도·분기·재무제표)에서는 한 벌만 살아남는다", len(p) == 1, f"{len(p)}벌")
check("살아남는 것은 생성시각이 가장 늦은 파일이다",
      p[0]["file"] == "2024_4Q_PL_20260819030822.zip", p[0]["file"])
check("밀려난 빈티지는 이름이 남는다 — 무엇을 안 읽었는지도 증거다",
      p[0]["superseded"] == "2024_4Q_PL_20260813030928.zip", p[0]["superseded"])

# 재무제표가 다르면 다른 빈티지다. FY2024 한 해만 해도 BS·PL·CF 의 생성시각이 전부
# 다르다(…030418 / …030822 / …031151). 연도로만 묶으면 두 벌이 통째로 사라진다.
p = picks(["2024_4Q_BS_20260819030418.zip", "2024_4Q_PL_20260819030822.zip",
           "2024_4Q_CF_20260819031151.zip", "2023_4Q_PL_20260101000000.zip"])
check("(연도·분기·재무제표)마다 따로 고른다", len(p) == 4, f"{len(p)}벌")

# 못 읽은 이름은 "빈티지 0"이 아니라 "빈티지 모름"이다. 기본값을 주는 순간 그 파일이
# 조용히 가장 낡은 것이 되어 정렬에서 지고, 진 사실은 어디에도 안 남는다.
try:
    picks(["2024_4Q_PL.zip"])
    dead = False
except SystemExit:
    dead = True
check("빈티지를 못 읽는 파일명은 멈춘다", dead)

# 분기 축을 안 보면 1분기와 사업보고서가 같은 칸에서 경쟁한다. 2026 년처럼 둘 다
# 있는 해에 한쪽이 통째로 사라지는 자리다.
p = picks(["2026_1Q_BS_20260813043130.zip", "2026_2Q_BS_20260819042705.zip"],
          pattern="*.zip")
check("분기가 다르면 다른 빈티지다", len(p) == 2, f"{len(p)}벌")

# 아카이브가 있는 설치에서는 표가 측정값이어야 한다 — 선언한 상수가 아니라.
if BULK_DIR.exists():
    cov = coverage()
    n_zip = len(list(BULK_DIR.glob("*.zip")))
    check("coverage() 가 디스크에서 나온다", not cov.empty and n_zip > 0,
          f"{n_zip}개 zip · {cov.shape[0]}행")
    check("빈티지 값은 14자리 생성시각이다",
          cov.stack().astype(str).str.fullmatch(r"\d{14}").all())
else:
    print(f"— 아카이브 없음({BULK_DIR}) · 규칙 검사만 수행")

# ── 수집기: 밀려난 빈티지를 지우는 방향 ──────────────────────────────────────
# download 가 받자마자 옛 빈티지를 지우므로 위 superseded 열은 앞으로 대개 빈다.
# 지운 것과 없던 것이 같은 빈칸이 되지 않도록, 지운 이름은 따로 덧붙여 남긴다.
import csv                                                          # noqa: E402

from dart_bulk import download                                      # noqa: E402


def prune(names, keep):
    """이름만 있는 가짜 아카이브에 prune 을 물린다. (지운 것, 남은 것)."""
    with tempfile.TemporaryDirectory() as d:
        for n in names:
            (Path(d) / n).write_bytes(b"")
        old_out, download.OUT = download.OUT, Path(d)
        try:
            gone = download.prune(Path(d) / keep)
            return sorted(gone), sorted(q.name for q in Path(d).glob("*.zip"))
        finally:
            download.OUT = old_out


OLD, NEW = "2024_4Q_PL_20260813030928.zip", "2024_4Q_PL_20260819030822.zip"
g, left = prune([OLD, NEW], NEW)
check("받은 빈티지보다 낡은 것은 지운다", g == [OLD] and left == [NEW], f"{g} / {left}")

# 방향이 있는 삭제다. 목록에 없는 더 새 파일이 디스크에 있으면 그것이 소비자가 읽을
# 파일이므로 건드리면 안 된다 — 지우는 쪽으로만 틀리는 코드는 복구가 재다운로드다.
g, left = prune([OLD, NEW], OLD)
check("받은 것보다 새 빈티지는 지우지 않는다", g == [] and left == [OLD, NEW], f"{g} / {left}")

g, left = prune([OLD, "2024_4Q_BS_20260101000000.zip"], NEW)
check("다른 (연도·분기·재무제표)는 건드리지 않는다",
      g == [OLD] and "2024_4Q_BS_20260101000000.zip" in left, f"{g} / {left}")

try:
    prune(["2024_4Q_PL.zip"], "2024_4Q_PL.zip")
    dead = False
except SystemExit:
    dead = True
check("빈티지를 못 읽는 이름이면 지우지 않고 멈춘다", dead)

# 덧붙이기만 한다. 매번 새로 쓰면 이번에 지운 것만 남고, 지난달에 지운 빈티지는
# 파일도 기록도 없어진다 — 그 조합이 "재생성된 적 없음"과 구분되지 않는다.
with tempfile.TemporaryDirectory() as d:
    old_p, download.PRUNED = download.PRUNED, Path(d) / "bulk_vintage_pruned.csv"
    try:
        download.record([("a_4Q_PL_20250101000000.zip", "a_4Q_PL_20250202000000.zip")])
        download.record([("b_4Q_BS_20250101000000.zip", "b_4Q_BS_20250202000000.zip")])
        rows = list(csv.DictReader(download.PRUNED.open(encoding="utf-8")))
    finally:
        download.PRUNED = old_p
check("지운 빈티지 기록은 덧붙이기만 한다",
      [r["file"][0] for r in rows] == ["a", "b"], str(rows))

print()
if FAILED:
    print(f"실패 {len(FAILED)}건: " + ", ".join(FAILED))
    sys.exit(1)
print("전부 통과.")
