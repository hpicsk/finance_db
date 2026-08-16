# KRX Supplement Data Pipeline

FnGuide DataGuide 접근 불가 상황에서 KRX 공식 API를 통해
**업종 맵핑**과 **KOSPI200/KOSDAQ150 구성종목**을 수집하는 파이프라인.

기존 FnGuide 데이터셋(`fn_README.md`)에서 누락된 두 가지 핵심 데이터:

| 필요 데이터 | 소스 | 비고 |
|---|---|---|
| 전 종목 일별 업종 맵핑 | KRX 업종분류현황 API | 상장폐지 종목 자연 포함 |
| KOSPI200/KOSDAQ150 일별 구성종목 | KRX 지수구성종목 API | 리밸런싱 이력 포함 |

> **상장폐지 유니버스는 `~/research/finance_db/kr_delisted/` 파이프라인을 사용** (KIND 기반,
> 무인증, marcap 비수정 OHLCV 포함). KRX `data.krx.co.kr` 기반 상폐 마스터 수집기는
> IP 차단 이력 및 ISIN 보강 외 용도 부재로 제거됨.

---

## 사전 준비: KRX 계정 설정 (필수)

2024년 이후 KRX `data.krx.co.kr` API는 **로그인된 세션**에서만 데이터를 반환한다.
비로그인 요청에는 `LOGOUT (400)` 응답이 반환된다.

### 1. KRX 계정 생성
1. [https://data.krx.co.kr](https://data.krx.co.kr) 접속
2. 우측 상단 **회원가입** 클릭 → 아이디/비밀번호 설정 (무료)

### 2. 환경변수 설정

```bash
# ~/.bashrc 또는 ~/.zshrc 에 추가
export KRX_ID="your_krx_id"
export KRX_PW="your_krx_password"
```

또는 실행 시 인라인 설정:

```bash
KRX_ID="id" KRX_PW="pw" python collect_sector.py --start 20240101 --end 20260320
```

---

## 설치

```bash
pip install pykrx finance-datareader requests tqdm pandas pyarrow
```

---

## 빠른 시작

각 스크립트를 직접 실행한다 (전체 end-to-end 래퍼는 없음).

```bash
# 1) 업종 맵핑 (영업일별 스냅샷, KRX_ID/PW 필요)
python collect_sector.py --start 20050101 --freq daily

# 2) 인덱스 구성종목 (KOSPI200 + KOSDAQ150, 월별 스냅샷, KRX_ID/PW 필요)
python collect_index_members.py --start 19940615 --end 20260320 --freq monthly

# 3) 인덱스 편입/편출 이벤트 로그 (전 기간 일괄, 로그인 불필요)
python collect_index_changes.py

# 4) 1+3 결합 → 일별 인덱스 패널 재구성
python reconstruct_index_panel.py
```

소요 시간 가이드:
- 빠른 테스트 (최근 2년, 월별): `--start 20240101` 으로 1~2 만 돌리면 ~5분
- 인덱스 구성종목 전체 (2000~현재, 월별): 1~2 시간
- 업종 맵핑 전체 (2005~현재, 영업일별): 2~3 시간 (~5,500 영업일)

### 일별 인덱스 패널을 얻기 위한 최소 파이프라인

`reconstruct_index_panel.py` 는 수집기가 아니라 **순수 변환 단계**다.
`output/index_members.parquet` 와 `output/index_changes.parquet` 를 읽어
일별 패널을 만들기 때문에, 이 두 입력을 먼저 만들어야 한다.

```bash
# 1) 월말 스냅샷 (ground truth) — KRX_ID/KRX_PW 필요
python collect_index_members.py --start 20000101 --freq monthly

# 2) 편입/편출 이벤트 로그 (정확한 변경 일자) — 로그인 불필요
python collect_index_changes.py

# 3) 1 + 2 결합 → output/index_panel_daily.parquet
python reconstruct_index_panel.py
```

왜 스냅샷과 이벤트 로그 둘 다 필요한가:
- KRX 이벤트 로그는 **불완전**하다 — 상장폐지/합병으로 자동 편출되는 종목은
  `REMOVE` 이벤트가 누락되는 경우가 많다.
- 따라서 월말 스냅샷을 ground truth 로 쓰고, 이벤트 로그는 변경 일자를 정확히
  짚어주는 보조 데이터로 결합한다. 자세한 알고리즘은 `RECONSTRUCT.md` 참조.

> **업종(sector) 맵핑은 별도**: `reconstruct_index_panel.py` 는 인덱스 멤버십만
> 다룬다. 업종이 필요하면 `collect_sector.py` 를 따로 실행할 것 (sector 변경에
> 대응하는 KRX 이벤트 로그가 없어서 재구성 단계가 없다).

---

## 출력 파일 구조

```
output/
├── sector_mapping.parquet                  # 업종 맵핑 (영업일별 스냅샷)
├── index_members.parquet / .csv            # 인덱스 구성종목 (월별 스냅샷)
├── index_changes.parquet / .csv            # 인덱스 편입/편출 이벤트 로그
├── index_membership_intervals.parquet/.csv # 종목별 편입 구간
├── index_panel_daily.parquet               # 일별(영업일) 재구성 패널
├── index_reconstruction_sanity.csv         # 재구성 정합성 리포트 (감사용)
└── index_reconstruction_synthetic.csv      # 합성 이벤트 목록 (감사용)
```

> **수집 cadence**:
> - `sector_mapping.parquet` 는 **영업일별 스냅샷** (`--freq daily`,
>   현재 데이터 범위: 2005-01-03 ~ 2026-04-27, 5,561 영업일).
> - `index_members.parquet` 는 **월말 스냅샷** (`--freq monthly`,
>   변경 시점은 최대 한 달 지연).
> - `index_changes.parquet` 는 KRX의 **정확한 변경 이벤트 로그** (전 기간 일괄).
> - `index_panel_daily.parquet` 는 월말 스냅샷(ground truth) + 이벤트 로그를
>   결합해 **영업일별로 재구성**한 패널이다.

### sector_mapping.parquet
| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | datetime | 조회 기준일 |
| `ticker` | str | 6자리 종목코드 (`005930`) |
| `name` | str | 종목약칭 |
| `market` | str | `KOSPI` / `KOSDAQ` |
| `sector_krx` | str | KRX 거래소 업종명 (e.g. 전기전자, 서비스업) |

### index_members.parquet
| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | datetime | 기준일 (월말 스냅샷) |
| `index` | str | `코스피 200` / `코스닥 150` |
| `ticker` | str | 6자리 종목코드 |
| `name` | str | 종목약칭 |

### index_changes.parquet
KRX `index.krx.co.kr` 구성종목변경내역 페이지에서 수집한 **정확한 편입/편출 일자**.
한 반영일에 ADD/REMOVE가 모두 있으면 2행으로 분해된다.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | datetime | 반영일 (appl_dd) |
| `index` | str | `코스피 200` / `코스닥 150` |
| `action` | str | `ADD` / `REMOVE` |
| `isin` | str | 12자리 ISIN |
| `ticker` | str | 6자리 종목코드 |
| `name` | str | 종목약칭 |

### index_membership_intervals.parquet
한 (인덱스, 종목)의 한 편입 구간 = 한 행. `in_source` / `out_source` ∈
{`log` (이벤트 로그), `synthetic` (스냅샷 diff로 imputed), `initial` (첫 스냅샷
이전부터 편입), `None` (현재까지 편입중)}.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `index` | str | `코스피 200` / `코스닥 150` |
| `ticker` | str | 6자리 종목코드 |
| `name` | str | 종목약칭 |
| `in_date` | datetime | 편입일 (NaT면 첫 스냅샷 이전부터) |
| `in_source` | str | `log` / `synthetic` / `initial` |
| `out_date` | datetime | 편출일 (NaT면 현재까지 편입중) |
| `out_source` | str | `log` / `synthetic` / `None` |

### index_panel_daily.parquet
영업일별로 forward-fill된 long-format 멤버 패널. KOSPI200은 1999-01-04부터
(이벤트 로그 시작일; 2005년 이후 매일 완전한 200 종목), KOSDAQ150은
2015-07-07부터. 자세한 내용은 RECONSTRUCT.md §한계 참조.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | datetime | 영업일 |
| `index` | str | `코스피 200` / `코스닥 150` |
| `ticker` | str | 6자리 종목코드 |

---

## Python 사용 예시

```python
import pandas as pd

# ─────────────────────────────────────────────────────────────────
# 1. 업종 맵핑 로드
# ─────────────────────────────────────────────────────────────────
sector = pd.read_parquet("output/sector_mapping.parquet")
# date가 datetime64인지 확인
sector["date"] = pd.to_datetime(sector["date"])

# 특정 날짜의 업종 맵핑
snap = sector[sector["date"] == "2024-01-31"]
print(snap.groupby("sector_krx")["ticker"].count().sort_values(ascending=False))

# 종목별 업종 변경 이력 (영업일별)
samsung = sector[sector["ticker"] == "005930"][["date","sector_krx"]]
print(samsung.drop_duplicates())

# ─────────────────────────────────────────────────────────────────
# 2. 인덱스 구성종목 로드
# ─────────────────────────────────────────────────────────────────
members = pd.read_parquet("output/index_members.parquet")

# 특정 날짜 KOSPI200 구성종목
kospi200 = members[
    (members["date"] == "2024-01-31") &
    (members["index"] == "코스피 200")
]["ticker"].tolist()
print(f"KOSPI200 구성종목 수: {len(kospi200)}")

# 특정 종목이 KOSPI200에 편입/편출된 날짜
ticker = "000660"  # SK하이닉스
history = members[
    (members["ticker"] == ticker) &
    (members["index"] == "코스피 200")
]["date"].sort_values()
print(f"{ticker} KOSPI200 편입 기간: {history.iloc[0]} ~ {history.iloc[-1]}")

# ─────────────────────────────────────────────────────────────────
# 3. Survivorship-bias-free 유니버스 구성
# ─────────────────────────────────────────────────────────────────
# 상폐 종목은 ~/research/finance_db/kr_delisted/ 의 KIND 기반 파이프라인을 사용.
# from kr_delisted.delisted_loader import universe
# delisted_tickers = set(universe()["ticker"])

live_tickers  = set(sector["ticker"].unique())
# full_universe = live_tickers | delisted_tickers

# ─────────────────────────────────────────────────────────────────
# 4. FnGuide 데이터와 업종 맵핑 조인
# ─────────────────────────────────────────────────────────────────
# FnGuide 일별 종가 데이터 (wide format → long format 변환 가정)
# price_long: columns = [date, ticker, close]

# 특정 날짜 기준 업종 조인
def join_sector(price_df: pd.DataFrame, sector_df: pd.DataFrame,
                method: str = "asof") -> pd.DataFrame:
    """
    가격 데이터에 업종 정보를 조인.
    method='asof': 각 날짜에 가장 가까운 과거 스냅샷을 사용 (forward-fill).
    """
    sector_dates = sector_df["date"].unique()
    sector_sorted = sector_df.sort_values("date")

    # 각 날짜별로 가장 최근 스냅샷 찾기
    result = pd.merge_asof(
        price_df.sort_values("date"),
        sector_sorted[["date","ticker","sector_krx","market"]].rename(columns={"date": "sector_date"}),
        left_on="date", right_on="sector_date",
        by="ticker",
        direction="backward",
    )
    return result
```

---

## 스냅샷 주기 선택 가이드

| 주기 | 요청 수 (2000~2026) | 소요 시간 | 권장 용도 |
|---|---|---|---|
| `daily` | ~6,500회 | 2~4시간 | 정밀 리밸런싱 백테스트 |
| `weekly` | ~1,350회 | 30~45분 | 주간 팩터 모델 |
| `monthly` | ~312회 | 5~10분 | **기본값** — 월별 팩터/인덱스 연구 |
| `yearly` | ~26회 | <1분 | 빠른 확인/테스트 |

월별 스냅샷의 경우 업종 변경 이벤트를 최대 한 달 늦게 포착할 수 있으나,
대부분의 학술 연구에서 허용 가능한 수준이다.

---

## 상장폐지 종목 처리 전략

### KRX 데이터의 자연적 포함
업종분류현황 API는 **조회 기준일에 상장된 종목**만 반환한다.
따라서 날짜별 스냅샷을 시계열로 쌓으면, 이후 폐지된 종목도 자동으로 포함된다.

```
2020-01-31 스냅샷: 종목 A 포함 (당시 상장 중)
2021-06-30 스냅샷: 종목 A 없음 (2021-03에 상폐)
→ 2020년 1월까지의 종목 A 데이터는 sector_mapping에 존재
```

### FnGuide 데이터셋과 통합

기존 FnGuide 데이터셋의 생존자 편향 보완은 `~/research/finance_db/kr_delisted/` 의
KIND 기반 파이프라인(`delisted_calendar.csv`, `delisted_loader.py`)을 활용.
marcap 비수정 OHLCV가 함께 제공되므로 별도 시세 보완 불필요.

---

## KRX OpenAPI 대안 (인증키 방식)

KRX 계정 대신 [KRX Open API](https://openapi.krx.co.kr)에서 **인증키(AUTH_KEY)**를
발급받아 사용하는 방법도 있다. 단, 현재 OpenAPI가 제공하는 업종분류현황/지수구성종목
엔드포인트가 제한적이므로 계정 로그인 방식이 더 넓은 데이터를 커버한다.

```python
# OpenAPI 방식 예시 (인증키 발급 후)
import requests
headers = {"AUTH_KEY": "your_auth_key"}
r = requests.get(
    "https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES001_S1.cmd",
    headers=headers, params={"bld": "...", "trdDd": "20260422"}
)
```

---

## 알려진 제약사항

1. **업종 분류 기준**: KRX 거래소 분류만 제공 (WICS/GICS는 FnGuide 전용).
   학술 논문에서 GICS가 필요한 경우 KRX 분류로 대체하거나
   [KOSPI 업종 → GICS 매핑 테이블](https://www.msci.com/gics)을 별도 구축해야 함.

2. **리얼타임 vs 일별**: KRX API는 영업일 마감 후 당일 데이터가 반영됨.
   장중 조회 시 전일 데이터가 반환될 수 있음.

3. **요청 속도 제한**: KRX 서버는 과도한 연속 요청을 차단할 수 있음.
   기본 딜레이(0.5~0.7초)를 유지할 것.

4. **KRX 계정 세션 만료**: 1시간 후 세션 만료 → 자동 재로그인 처리됨.

5. **KOSDAQ150 출시일**: 2015년 7월 7일. 이전 날짜에 대해서는 빈 응답 반환.

6. **수집 실패는 로그로만 남고 데이터 공백이 됨.** `fetch_sector_snapshot`과
   `fetch_index_members`는 `except Exception` → 경고 로그 후 해당 (날짜, 시장)을
   건너뛴다. 출력에는 그 행이 그냥 없으므로 "그날은 원래 데이터가 없음"과
   "가져오기가 실패함"이 구분되지 않는다. 수집 후 로그를 확인할 것.

   `collect_foreign_ownership`은 한 단계 더 나쁘다. `_fetch`의
   `except KeyError → None`이 *비거래일*과 *응답 스키마 변경*을 같은 값으로
   접고, `None`이면 `_EMPTY_SCHEMA` 파켓을 기록한다. 그 빈 파일은 재실행 시
   `out.exists()` 재개 검사에 걸려 건너뛰어지므로, 스키마가 바뀐 구간은 몇 번을
   다시 돌려도 영구히 비어 있다. 해당 구간은 파일을 지우고 다시 받아야 한다.

---

## 파일 구성

```
krx_supplement/
├── README.md                     이 파일
├── RECONSTRUCT.md                일별 패널 재구성 알고리즘 상세
├── collect_sector.py             업종 맵핑 수집기 (영업일별 스냅샷, pykrx)
├── collect_index_members.py      인덱스 구성종목 수집기 (월별 스냅샷, pykrx)
├── collect_index_changes.py      인덱스 편입/편출 이벤트 로그 수집기 (무로그인)
├── reconstruct_index_panel.py    월말 스냅샷 + 이벤트 로그 → 일별 패널 재구성
└── output/                       수집된 데이터 저장 디렉토리
    ├── sector_mapping.parquet
    ├── index_members.parquet / .csv
    ├── index_changes.parquet / .csv
    ├── index_membership_intervals.parquet / .csv
    ├── index_panel_daily.parquet
    ├── index_reconstruction_sanity.csv
    └── index_reconstruction_synthetic.csv
```

KRX 로그인 세션은 `pykrx` 1.2.x가 내부에서 처리하므로 별도 HTTP 유틸리티는 없다.
`KRX_ID` / `KRX_PW` 환경변수는 `collect_sector.py` 와 `collect_index_members.py`
실행 시 필요하다. `collect_index_changes.py` 는 `index.krx.co.kr` 공개 엔드포인트를
사용하므로 로그인 불필요.
