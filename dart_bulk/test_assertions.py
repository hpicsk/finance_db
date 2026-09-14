"""Integrity assertions for the claims `dart_bulk`'s documentation makes.

This repo has no CI; verification is ad-hoc. Run with the data trees populated,
from anywhere:

    python dart_bulk/test_assertions.py

or run every package's assertions at once with `./run_assertions.sh` from the
repo root. Each check prints PASS, FAIL, or SKIP where a prerequisite
artifact is absent, along with `n`, the size of the population it examined.
The script exits non-zero if any check fails, if any examined nothing, and if
any skipped — a skip verified nothing, so iterating without the artifact takes
`--allow-skips`. `n` is held against `populations.json`, which records what
each check last read; re-seed it with `--write-populations` after a refresh.

빈티지 선택은 이 패키지의 전부이므로 대부분이 그 검사다. 규칙은 아카이브가 없어도
검사된다 — 가짜 이름으로 만든 임시 아카이브를 물리고, `n` 은 물린 이름의 수다.
디스크를 읽는 검사는 아카이브가 없으면 SKIP 이지 통과가 아니다.
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from dart_bulk import BULK_DIR, coverage, latest_vintages  # noqa: E402
from dart_bulk import download  # noqa: E402

# Each check's population, recorded so a tree that lost rows fails rather
# than passing on a smaller one. Per package, not per repo: the root is a
# container and holds no package's numbers.
POPULATIONS = Path(__file__).with_name("populations.json")


class Skipped(Exception):
    """A prerequisite artifact is absent, so this check verified nothing.

    Distinct from a pass because it is: it used to print as one, which is the
    same confusion the population guard below exists to remove.
    """


# README § 지금 디스크에 있는 것, 2026-08-25 기준. 다음 갱신이 이 수를 옮기면 이
# 검사가 실패하고, 그 실패가 README 의 수를 같은 커밋에서 옮긴다.
ZIPS_ON_DISK = 138
GROUPS_WITH_SUPERSEDED = 14
STMTS = ("BS", "PL", "CF")


def _picks(names, pattern="*_4Q_*.zip"):
    """이름만 있는 가짜 아카이브에 latest_vintages 를 물린다."""
    with tempfile.TemporaryDirectory() as d:
        for n in names:
            (Path(d) / n).write_bytes(b"")
        return latest_vintages(pattern, root=Path(d))


def _prune(names, keep):
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


def _archive():
    """디스크의 아카이브를 (연도·분기·재무제표)마다 한 벌씩. 없으면 SKIP."""
    if not any(BULK_DIR.glob("*.zip")):
        raise Skipped(f"아카이브 없음({BULK_DIR}) — python -m dart_bulk.download")
    try:
        return latest_vintages("*.zip")
    except SystemExit as e:
        raise AssertionError(f"README: 이름이 규칙에 안 맞으면 멈춘다 — {e}")


# ---- 빈티지 선택 규칙 (README § 빈티지가 이 패키지의 전부다) ------------------

def test_latest_vintage_wins_by_stamp():
    # 옛 것을 나중에 만들어 둔다. 글롭이 주는 순서가 아니라 14자리를 읽어서 고르는지를 본다.
    names = ["2024_4Q_PL_20260819030822.zip", "2024_4Q_PL_20260813030928.zip"]
    p = _picks(names)
    assert len(p) == 1, f"README: 같은 (연도·분기·재무제표)에서는 한 벌만 살아남는다 — {len(p)}벌"
    assert p[0]["file"] == names[0], f"README: 생성시각이 가장 늦은 파일이 살아남는다 — {p[0]['file']}"
    assert p[0]["superseded"] == names[1], (
        f"README: 밀려난 빈티지는 이름이 남는다 — superseded={p[0]['superseded']!r}")
    return "생성시각이 늦은 한 벌만 남고, 밀려난 이름은 superseded 에 남는다", len(names)


def test_groups_are_year_quarter_statement():
    # 재무제표가 다르면 다른 빈티지다. FY2024 한 해만 해도 BS·PL·CF 의 생성시각이 전부
    # 다르다(…030418 / …030822 / …031151). 연도로만 묶으면 두 벌이 통째로 사라진다.
    # 분기 축을 안 보면 1분기와 사업보고서가 같은 칸에서 경쟁한다.
    by_stmt = ["2024_4Q_BS_20260819030418.zip", "2024_4Q_PL_20260819030822.zip",
               "2024_4Q_CF_20260819031151.zip", "2023_4Q_PL_20260101000000.zip"]
    by_quarter = ["2026_1Q_BS_20260813043130.zip", "2026_2Q_BS_20260819042705.zip"]
    p = _picks(by_stmt)
    assert len(p) == 4, f"README: (연도·분기·재무제표)마다 따로 고른다 — {len(p)}벌"
    p = _picks(by_quarter, pattern="*.zip")
    assert len(p) == 2, f"README: 분기가 다르면 다른 빈티지다 — {len(p)}벌"
    return "연도·분기·재무제표 세 축이 각각 빈티지를 가른다", len(by_stmt) + len(by_quarter)


def test_unparseable_name_stops():
    # 못 읽은 이름은 "빈티지 0"이 아니라 "빈티지 모름"이다. 기본값을 주는 순간 그 파일이
    # 조용히 가장 낡은 것이 되어 정렬에서 지고, 진 사실은 어디에도 안 남는다.
    bad = "2024_4Q_PL.zip"
    for side, fn in (("읽는 쪽", lambda: _picks([bad])), ("지우는 쪽", lambda: _prune([bad], bad))):
        try:
            fn()
        except SystemExit:
            continue
        raise AssertionError(f"README: 이름이 규칙에 안 맞으면 멈춘다 — {side}이 {bad} 를 받아들였다")
    return "빈티지를 못 읽는 이름은 읽는 쪽도 지우는 쪽도 멈춘다", 2


# ---- 수집기: 밀려난 빈티지를 지우는 방향 (README § 빈티지가 이 패키지의 전부다) ---

OLD, NEW = "2024_4Q_PL_20260813030928.zip", "2024_4Q_PL_20260819030822.zip"


def test_prune_is_directional():
    # 방향이 있는 삭제다. 목록에 없는 더 새 파일이 디스크에 있으면 그것이 소비자가 읽을
    # 파일이므로 건드리면 안 된다 — 지우는 쪽으로만 틀리는 코드는 복구가 재다운로드다.
    other = "2024_4Q_BS_20260101000000.zip"
    g, left = _prune([OLD, NEW], NEW)
    assert g == [OLD] and left == [NEW], f"README: 받은 빈티지보다 낡은 것은 지운다 — {g} / {left}"
    g, left = _prune([OLD, NEW], OLD)
    assert g == [] and left == [OLD, NEW], f"README: 받은 것보다 새 빈티지는 지우지 않는다 — {g} / {left}"
    g, left = _prune([OLD, other], NEW)
    assert g == [OLD] and other in left, f"README: 다른 (연도·분기·재무제표)는 건드리지 않는다 — {g} / {left}"
    return "낡은 것만, 같은 (연도·분기·재무제표)에서만 지운다", 6


def test_pruned_record_appends():
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
    assert [r["file"][0] for r in rows] == ["a", "b"], f"README: 지운 빈티지 기록은 덧붙이기만 한다 — {rows}"
    return "bulk_vintage_pruned.csv 는 덧붙이기만 한다", len(rows)


# ---- 디스크 (README § 지금 디스크에 있는 것) ---------------------------------

def test_coverage_is_measured_from_disk():
    # 아카이브가 있는 설치에서는 표가 측정값이어야 한다 — 선언한 상수가 아니라. README 가
    # 채워졌다고 적은 칸이 전부 차 있고, 빈 칸은 README 가 비었다고 적은 것뿐이다.
    _archive()
    cov = coverage()
    stamps = [str(v) for v in cov.to_numpy().ravel() if v == v]
    assert all(len(s) == 14 and s.isdigit() for s in stamps), "README: 빈티지 값은 14자리 생성시각이다"
    want = {(y, "FY", s) for y in range(2015, 2026) for s in STMTS}
    want |= {(y, r, s) for y in range(2016, 2025) for r in ("FQ", "HY", "TQ") for s in STMTS}
    want |= {(2025, "HY", "BS"), (2025, "HY", "PL")}
    want |= {(2026, r, s) for r in ("FQ", "HY") for s in STMTS}
    have = {(int(y), r, s) for (y, r), row in cov.iterrows() for s, v in row.items() if v == v}
    assert have == want, (
        f"README '지금 디스크에 있는 것'(2026-08-25 기준)과 디스크가 다르다 — "
        f"README 에만 {sorted(want - have)}, 디스크에만 {sorted(have - want)}")
    n_zip = len(list(BULK_DIR.glob("*.zip")))
    assert n_zip == ZIPS_ON_DISK, f"README: zip {ZIPS_ON_DISK}개 — 디스크에는 {n_zip}개"
    return f"coverage() 의 {len(have)}칸이 README 와 같고, zip 은 {n_zip}개다", n_zip


def test_superseded_vintages_still_on_disk():
    # download 가 받자마자 옛 것을 지우므로 superseded 는 보통 빈다. 지금 디스크의 예외는
    # pruning 이 생기기 전에 받은 것들이고, README 가 그 수를 적는다.
    picked = _archive()
    held = [p for p in picked if p["superseded"]]
    for p in held:
        olds = p["superseded"].split(";")
        assert all(int(z[-18:-4]) < int(p["vintage"]) for z in olds), (
            f"README: superseded 는 고른 것보다 낡은 빈티지다 — {p['file']}: {olds}")
    assert len(held) == GROUPS_WITH_SUPERSEDED, (
        f"README: 옛 빈티지를 한 벌 더 갖는 (연도·분기·재무제표)는 {GROUPS_WITH_SUPERSEDED}개 — "
        f"{len(held)}개")
    return (f"{len(picked)}개 (연도·분기·재무제표) 중 {len(held)}개가 밀려난 빈티지를 아직 "
            f"갖고 있다"), len(picked)


CHECKS = [
    test_latest_vintage_wins_by_stamp,
    test_groups_are_year_quarter_statement,
    test_unparseable_name_stops,
    test_prune_is_directional,
    test_pruned_record_appends,
    test_coverage_is_measured_from_disk,
    test_superseded_vintages_still_on_disk,
]


if __name__ == "__main__":
    # This block is the same in every package's test_assertions.py, and
    # run_assertions.sh fails when the copies differ: edit it in one, then copy
    # it to the rest. Nothing below is package-specific — it needs CHECKS,
    # Skipped and POPULATIONS from above, and nothing else.
    #
    # A check that skipped verified nothing, which is the state this runner
    # exists to tell apart from a pass — and a suite of nothing but skips used to
    # exit 0, which is the same confusion one layer up from the one `Skipped`
    # fixed. Tolerable while iterating locally, never on the path that reproduces
    # the tree, so the strict reading is the default and the loose one is asked
    # for by name.
    allow_skips = "--allow-skips" in sys.argv[1:]
    # The population a check examined fingerprints the tree it read, and non-zero
    # is only the floor of what that fingerprint catches: a count that halves
    # still passes. A population that *grew* is a re-pull and says nothing; one
    # that *shrank* means the check now reads less of the tree than it did, which
    # is the same silent weakening `n` was added to expose, one revision later.
    # The bound is per check because a population clipped to a window moves only
    # when the window does, while one open past it grows every time the vendor
    # is re-pulled — a single rule would either fail every refresh or catch
    # nothing.
    # Re-seeding is the documented path after a refresh, and it was unreachable:
    # a legitimately moved population fails its own guard, which counts as a
    # failure, which makes the re-seed refuse — so the path existed only while it
    # was not needed. Under `--write-populations` the recorded numbers are being
    # replaced on purpose, so the comparison against them is reported and not
    # enforced. Every other assertion still has to pass, which is what stops a
    # broken tree from being written down as the expectation.
    reseed = "--write-populations" in sys.argv[1:]
    baseline = json.loads(POPULATIONS.read_text()) if POPULATIONS.exists() else {}
    observed = {}
    drift = []
    failures = skipped = 0
    for fn in CHECKS:
        try:
            # Every check returns the size of the population it examined. One that
            # examined none of it cannot have found anything wrong, and prints the
            # same PASS as one that examined all of it — so the empty case fails
            # here, once, rather than in each check that remembers to guard it.
            # int() because a numpy count is not JSON-serialisable, and the
            # baseline below is written as JSON.
            msg, n = fn()
            n = int(n)
            assert n, ("examined an empty population, so nothing it asserts was "
                       "tested — the inputs it reads are missing, filtered away, "
                       "or no longer shaped the way it expects")
            observed[fn.__name__] = n
            want = baseline.get(fn.__name__)
            if want:
                moved = (n != want["n"] if want["bound"] == "exact"
                         else n < want["n"])
                if moved and reseed:
                    drift.append(f"{fn.__name__} {want['n']:,} -> {n:,}")
                    moved = False
                assert not moved, (
                    f"examined {n:,} where {POPULATIONS.name} records "
                    f"{want['n']:,} ({want['bound']}). A shrink means the check "
                    f"now reads less of the tree than it did, or the tree lost "
                    f"rows; a move under `exact` means a population clipped to "
                    f"a window changed, which a re-pull does only by moving the "
                    f"window. Re-seed with --write-populations once the change "
                    f"is understood")
            print(f"PASS  {fn.__name__} [n={n:,}]: {msg}")
        except Skipped as e:
            skipped += 1
            print(f"SKIP  {fn.__name__}: {e}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # missing data tree, etc. — report, don't hide
            failures += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(CHECKS) - failures - skipped}/{len(CHECKS)} checks passed"
          + (f", {skipped} skipped" if skipped else ""))
    if skipped and not allow_skips:
        print(f"FAIL  {skipped} check(s) read an artifact that is not built, so "
              f"they verified nothing. Build it, or pass --allow-skips to "
              f"iterate without it.")
    unseeded = [f.__name__ for f in CHECKS if f.__name__ not in baseline]
    if unseeded:
        print(f"NOTE  {len(unseeded)} check(s) absent from {POPULATIONS.name}, so "
              f"their population is unbounded above zero: {', '.join(unseeded)}")
    if reseed:
        # Re-seeding takes its numbers only from a run that passed — a baseline
        # written from a broken tree records the breakage as the expectation.
        for d in drift:
            print(f"MOVED {d}")
        if failures or skipped:
            print("REFUSED to re-seed from a run that did not pass every check")
            failures += 1
        else:
            merged = {k: {"n": v,
                          "bound": baseline.get(k, {}).get("bound", "monotone")}
                      for k, v in observed.items()}
            POPULATIONS.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
            print(f"wrote {POPULATIONS.name} for {len(merged)} checks")
    sys.exit(1 if failures or (skipped and not allow_skips) else 0)
