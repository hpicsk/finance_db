# Research Notes — Korean Investor Trading Aggregates

Background notes on two design decisions baked into `transform_investor_data.py` and the `investor_trading_data.csv` schema:

1. Why the `외국인` column in the output represents **등록외국인 only** (not `외국인계`) — Smart Money classification.
2. Why **개인 = 전체 − 기관계 − 외국인계 − 기타법인** is the mathematically correct derivation.

---

## 1. Smart Money classification: why 등록외국인, not 외국인계

**결론부터 말씀드리면, Informed Trader(정보거래자/스마트머니) 변수를 만드시는 것이 목적이라면 '기타 외국인'은 빼는 것이 좋습니다.**

학술적·실무적 관점에서 **'기타 외국인'**은 스마트머니보다는 **'국내 개인 투자자(Retail)'**와 유사한 성향을 보이기 때문입니다.

구체적인 판단 근거를 정리해 드립니다.

### 1.1 '기타 외국인'의 정체는 '개미'에 가깝습니다.

한국거래소(KRX)의 정의에 따르면, **기타 외국인**은 외국인 투자등록증(ID)이 없는 외국인을 말합니다.
대부분 다음과 같은 투자자들입니다.

* 한국에 6개월 이상 거주 중인 **외국인 개인** (주한미군, 유학생, 국내 기업 외국인 임직원 등)
* 단순 거주 외국인

즉, 우리가 흔히 '외국인 수급'이라고 할 때 기대하는 **골드만삭스, 블랙록 같은 '거대 외국계 자본(Smart Money)'은 모두 '등록 외국인(Registered Foreigner)'**으로 분류됩니다. 따라서 기타 외국인은 정보력이나 자금력 측면에서 기관보다는 개인 투자자와 훨씬 유사합니다.

### 1.2 Informed Trader 변수 생성 팁

학술 연구나 퀀트 분석에서 '정보거래자(Informed Trader)'를 정의할 때는 **[기관 + 외국인]**을 사용하는데, 이때의 외국인은 엄밀히 말해 **'등록 외국인'**을 의미합니다.

따라서 데이터 처리는 다음과 같이 하시는 것을 추천합니다.

* **권장 수식:**



*(또는 데이터에 '등록 외국인' 항목이 따로 있다면 바로 그것을 사용하세요)*
* **기타 외국인 처리:**
오히려 **'개인(Retail)'** 변수를 만드실 때 `개인 + 기타 외국인`으로 합쳐서 "비정보거래자(Uninformed Trader)"로 분류하는 것이 더 정교한 방법일 수 있습니다.

### 1.3 요약

**'기타 외국인'은 포함시키지 마세요.**
그들은 '무늬만 외국인'일 뿐, 실제 매매 패턴은 국내 개인 투자자와 매우 비슷하므로 스마트머니 데이터에 노이즈(Noise)가 될 수 있습니다.

### 1.4 Recommended Investor Classification for Research

| Category | Components |
|----------|------------|
| **Informed Trader (Smart Money)** | 기관 + 외국인 (등록외국인 only) |
| **Uninformed Trader (Retail)** | 개인 + 기타외국인 + 기타법인 |

### 1.5 How this is implemented in the pipeline

`transform_investor_data.py` resolves the two definitions like this:

| Source | Definition | Includes |
|--------|------------|----------|
| **PyKRX API `외국인`** | 등록외국인 only | Goldman Sachs, BlackRock, foreign institutional investors |
| **Excel `외국인계`** | 등록외국인 + 기타외국인 | Above + expats, foreign students, US military personnel |

- Use `외국인계` for *calculating* `개인` (mathematically required — see §2).
- Use `등록외국인` for the `외국인` *output* column (Smart Money only).
- 기타외국인 is implicitly absorbed into the `개인` output (behaves like retail).

This matches the PyKRX API's `외국인` definition (as used in `all_identified_events_enhanced.csv` from the volpre4 project). The pipeline was updated on 2026-01-05 to reflect this.

---

## 2. Deriving 개인 from 전체 − 기관계 − 외국인계 − 기타법인

보여주신 항목 리스트를 보니 **'기타법인'**과 **'외국인계'**, **'기관계'**가 모두 포함되어 있어, 앞서 말씀드린 오차 없이 **정확한 개인 순매수를 계산할 수 있습니다.**

주식시장의 전체 거래대금은 [개인 + 외국인 + 기관 + 기타법인]의 합과 정확히 일치하기 때문입니다.

이미지에 있는 항목명을 기준으로 한 **정확한 계산 공식**은 다음과 같습니다.

### 2.1 개인 매수/매도 대금 구하기

리스트에 있는 **'전체'** 데이터에서 나머지 3개 주체(기관, 외국인, 기타법인)를 빼면 됩니다.

> **참고:** 리스트에 있는 `국가`, `사모펀드`, `금융투자` 등 세부 항목들은 이미 `기관계`에 합산되어 있으므로 따로 빼지 않으셔도 됩니다. 마찬가지로 `기타외국인`은 `외국인계`에 포함됩니다.

### 2.2 최종: 개인 순매수 구하기

위에서 구한 매수/매도 값을 뺍니다.

이제 이 공식을 엑셀이나 프로그램에 그대로 적용하시면 됩니다.
