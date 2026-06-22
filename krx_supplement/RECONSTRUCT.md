# 일별 인덱스 멤버십 패널 재구성

`reconstruct_index_panel.py` 가 `index_members.parquet` (월말 스냅샷) 과
`index_changes.parquet` (편입/편출 이벤트 로그) 를 결합해 **일별 영업일 패널**과
**종목별 편입 구간(intervals)** 을 만든다. 코스피 200, 코스닥 150 모두 지원.

---

## 입력 파일

| 파일 | 생성 스크립트 | 역할 |
|---|---|---|
| `output/index_members.parquet` | `collect_index_members.py` | 월말 스냅샷 (ground truth) |
| `output/index_changes.parquet` | `collect_index_changes.py` | 정확한 편입/편출 이벤트 (적시성) |

스냅샷은 *맞는지(정확)*, 이벤트는 *언제(타이밍)* 를 담당한다.
재구성 로직은 두 데이터의 강점을 결합한다.

---

## 왜 단순 결합이 안 되는가

KRX 의 `index_changes` 이벤트 로그는 **불완전**하다. 검증 결과:

- KOSPI 200: 152 개 ISIN 이 ADD 만 있고 REMOVE 가 없음
- KOSDAQ 150: 동일 패턴 다수
- 결과적으로 이벤트 로그만 forward-roll 하면 anchor 시점에 12 (KOSPI200) /
  5 (KOSDAQ150) 종목의 *유령(ghost)* 이 잡힌다 (이미 사라진 종목이 계속 멤버로 남음).

미기록 사례 예시:
- `008810 LG종금` — 1999-06-11 ADD 후 합병/상폐로 사라짐, REMOVE 미기록
- `068270 셀트리온` — 2018 코스닥에서 코스피 이전상장, 코스닥 150 에서
  자동 빠짐, 별도 REMOVE 미기록
- `035720 카카오` — 2017 코스닥→코스피 이전상장, 동일 이슈
- `036420 제이콘텐트리` — 분할/합병 과정에서 이름 변경 시 REMOVE 미기록

→ **스냅샷을 ground truth 로 신뢰**하고, 이벤트는 정확한 일자를 위한 보조로만
사용한다. 스냅샷 diff 로 explained 안 되는 변경은 **합성 이벤트(synthetic)** 를
스냅샷 일자에 주입한다.

---

## 알고리즘 — 종목별 상태기계

각 (인덱스, 종목 T) 에 대해 timeline 을 구성한다:

```
timeline = [(event_date, 'event', 'ADD'|'REMOVE', 'log')]
         + [(snap_date,  'snap',  T_in_snap_bool, None)]
정렬: (date, event 가 snap 보다 먼저)   # snap 은 post-event 상태
```

`state ∈ {None, 'IN', 'OUT'}` 으로 초기 None. timeline 을 순회하며:

| 입력 | state 전이 | interval / synthetic |
|---|---|---|
| event ADD, state ∈ {None, OUT} | → IN | in_date=event_d, source=log |
| event ADD, state = IN | (무시: 중복 ADD) | — |
| event REMOVE, state = IN | → OUT | close interval, out_source=log |
| event REMOVE, state = None | → OUT | close interval (in_date=NaT, in_source=initial) |
| event REMOVE, state = OUT | (무시: 중복 REMOVE) | — |
| snap True, state = None | → IN | in_date=NaT, source=initial |
| snap True, state = OUT | → IN | in_date=snap_d, source=**synthetic** (ADD 누락) |
| snap True, state = IN | (consistent) | — |
| snap False, state = IN | → OUT | close interval, out_source=**synthetic** (REMOVE 누락) |
| snap False, state ∈ {None, OUT} | (consistent, state→OUT) | — |

루프 종료 시 `state == IN` 이면 open interval 추가 (`out_date=NaT`).

---

## 출력 파일

### `output/index_membership_intervals.parquet`
종목별 편입 구간. 한 종목이 여러 번 들어오고 나갔다면 여러 행.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `index` | str | `코스피 200` / `코스닥 150` |
| `ticker` | str | 6자리 종목코드 |
| `name` | str | 종목약칭 (스냅샷 우선, 이벤트 보조) |
| `in_date` | datetime | 편입 일자 (NaT = 첫 스냅샷 이전부터 편입중) |
| `in_source` | str | `log` / `synthetic` / `initial` |
| `out_date` | datetime | 편출 일자 (NaT = 현재까지 편입중, exclusive) |
| `out_source` | str | `log` / `synthetic` / null (NaT 일 때) |

해석: 종목은 `[in_date, out_date)` 구간 동안 인덱스에 포함됨.
`out_date` 당일은 OUT (KRX 적용일은 새 구성 적용일).

### `output/index_panel_daily.parquet`
일별 영업일 long format. interval 을 펼친 결과.

| 컬럼 | 타입 |
|---|---|
| `date` | datetime (영업일) |
| `index` | str |
| `ticker` | str |

기본 시작일 (CLI `--start-*` 기본값): KOSPI 200 = 1994-06-15 (출시일),
KOSDAQ 150 = 2015-07-07 (출시일). 단, 실제 패널은 이벤트 로그/스냅샷이
존재하는 첫 일자부터 시작한다 (KOSPI 200 = 1999-01-04, 아래 §한계 참조).

### `output/index_reconstruction_sanity.csv`
모든 스냅샷 일자에 대해 (실제 vs 재구성) 교차검증.
정상 동작 시 `only_actual = only_recon = 0` (모든 스냅샷에서 정확히 일치).

### `output/index_reconstruction_synthetic.csv`
주입된 합성 이벤트 목록 (감사용).

---

## 현재 데이터 기준 결과 (2026-04-27 시점)

```
[코스피 200] 238 snapshots: 2004-01-30 ~ 2026-02-27 (200 anchor members)
[코스피 200] intervals: 730, synthetic events: 12
[코스피 200] sanity: 238/238 snapshots match exactly
[코스피 200] daily panel: 1,257,120 rows (1999-01-04 ~ 2026-02-27)

[코스닥 150] 113 snapshots: 2015-07-31 ~ 2026-02-27 (150 anchor members)
[코스닥 150] intervals: 656, synthetic events: 9
[코스닥 150] sanity: 113/113 snapshots match exactly
[코스닥 150] daily panel: 416,115 rows (2015-07-07 ~ 2026-02-27)
```

`in_source` / `out_source` 분포:
```
in_source                  out_source
  initial    331           log         1,015
  log      1,055           synthetic      21
                           NaN (still in) 350
```

전체 종목 변경 1,386 건 중 21 건 (~1.5%) 만 합성 이벤트로 imputed.
나머지 98.5% 는 KRX 이벤트 로그의 정확한 일자.

합성 이벤트 21 건 모두 REMOVE — 상폐/이전상장으로 인한 자동 편출이
이벤트 로그에 기록되지 않은 사례들 (예: 셀트리온, 카카오, 우리은행 등).

---

## 한계

1. **합성 이벤트 일자 정밀도**: 월별 스냅샷 사용 시 실제 변경일은
   "직전 스냅샷 다음날 ~ 해당 스냅샷일" 사이 어딘가 → 최대 ~22 영업일 오차.
   더 높은 정밀도가 필요하면 `collect_index_members.py --freq weekly` (또는 `daily`)
   로 스냅샷 주기를 줄여 재수집 후 재구성.

2. **인덱스 출시일 ~ 첫 스냅샷 사이**:
   - KOSPI 200: 출시일 1994-06-15 이지만 이벤트 로그가 1999-01-04 부터만
     존재 → daily panel 은 1994-1998 구간을 포함하지 않고 1999-01-04 부터
     시작한다. 이벤트 로그로만 구성원을 누적하므로 1999-2004 구간은 멤버 수가
     점진적으로 증가한다 (1999-01-04 의 1 종목 → 2004 말 200 종목 도달).
     분석 윈도우인 2005-2024 구간은 매일 완전한 200 종목이다.
   - KOSDAQ 150: 2015-07-07 ~ 2015-07-30 구간. 같은 이슈로 다소 부정확할 수
     있음 (출시 직후 ~24 일).

3. **이벤트 로그 시작 이전의 미기록 변경**: 이벤트 로그가 KRX 의 *전체* 변경
   이력이라고 가정하지만, 1999 년 이전의 KOSPI 200 변경 또는 2010 년 이전의
   KOSDAQ 150 변경이 있었더라도 우리는 알 수 없다.

4. **스냅샷 자체의 부정확성**: KRX 스냅샷 API 가 returned 한 200/150 종목이
   *그 날의 실제 인덱스 구성* 이라고 가정. 코퍼릿 액션 (분할/합병/이전상장)
   집계 시점에 따라 일시적으로 199 또는 201 처럼 비정상 카운트가 나오는 날이
   있으나 (KOSPI200 mode=200, range 200-202; KOSDAQ150 mode=150, range 149-150),
   재구성은 그대로 따라간다 (왜곡 없음).

5. **이전상장(코스닥→코스피) 처리**: 이전상장된 종목은 코스닥 150 에서 빠지고
   코스피 200 에 들어가는 경우가 많음. 두 인덱스 패널을 합쳐 사용 시 같은
   ticker 가 같은 날 양쪽에 있는 일이 없음 (단방향).

---

## 사용법

```bash
# 기본 실행
python reconstruct_index_panel.py

# 일별 패널은 큰 파일이므로 필요 없으면
python reconstruct_index_panel.py --no-daily

# 패널 시작일/종료일 커스터마이즈
python reconstruct_index_panel.py \
    --start-kospi200 19940615 \
    --start-kosdaq150 20150707 \
    --end 20251231
```

```python
import pandas as pd

iv = pd.read_parquet("output/index_membership_intervals.parquet")

# 특정 일자에 KOSPI 200 멤버
def members_at(iv, idx, d):
    d = pd.Timestamp(d)
    sub = iv[iv["index"] == idx]
    in_d = sub["in_date"].fillna(pd.Timestamp.min)
    out_d = sub["out_date"].fillna(pd.Timestamp.max)
    return sub.loc[(in_d <= d) & (d < out_d), "ticker"].tolist()

print(len(members_at(iv, "코스피 200", "2020-06-30")))  # ≈ 200

# 특정 종목의 편입 이력
samsung = iv[(iv["index"] == "코스피 200") & (iv["ticker"] == "005930")]
print(samsung)

# 합성 이벤트 분리 (정확도가 중요한 분석)
exact_in_only = iv[iv["in_source"] == "log"]
exact_both = iv[(iv["in_source"] == "log") &
                (iv["out_source"].isin(["log", None]))]
```

---

## 기존 스크립트와의 관계

`reconstruct_index_panel.py` 는 입력으로 두 스크립트의 출력을 그대로 사용한다.
**기존 스크립트는 sanity check 와 재실행을 위해 보존**한다:

- `collect_index_members.py` — 새 월말 스냅샷 수집 (anchor + reconciliation 입력)
- `collect_index_changes.py` — 새 이벤트 로그 수집
- `reconstruct_index_panel.py` — 위 두 출력을 결합

스냅샷이나 이벤트 로그를 갱신하면 `reconstruct_index_panel.py` 만 재실행하면 됨.
