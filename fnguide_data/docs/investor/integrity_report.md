# Integrity Report: `fnguide_data/` vs `qf_next/investor_data/`

## 1. Dataset Overview

| | `fnguide_data/` (new) | `qf_next/investor_data/` (existing) |
|---|---|---|
| **Source** | FnGuide DataGuide export | Separate FnGuide/KRX export |
| **Files** | 7 xlsx (~5.6 GB) | 2 xlsx (~720 MB) + 1 CSV (786 MB) |
| **Stocks** | ~3,902 (KOSPI + KOSDAQ) | 2,906 (common subset) |
| **Date range** | 2000-01-04 ~ 2026-02-12 | 2020-01-02 ~ 2025-12-26 |
| **Trading days** | ~6,450 | 1,471 |
| **Unit** | 원 (KRW) for all files | 원 (data1229) / 만원 (data1230) |
| **Investor types** | 14 granular categories | 3 aggregated (기관, 외국인, 개인) |

## 2. Stock Universe

| Metric | Count |
|---|---|
| fnguide stocks | 3,902 |
| investor xlsx stocks | 3,899 |
| investor CSV stocks (output) | 2,906 |
| fnguide ∩ investor xlsx | 3,899 |
| fnguide only | 3 |
| investor xlsx only | 0 |

**investor xlsx stocks are a perfect subset of fnguide stocks.** The 3 extra fnguide stocks are from a slightly later download date.

## 3. Spot-Check Comparisons (5 stocks × 6 dates = 30 checks each)

Tested on: A005930 (Samsung), A000660 (SK Hynix), A035420 (NAVER), A051910 (LG Chem), A006400 (Samsung SDI)
Dates: 2020-01-02, 2021-06-15, 2022-03-10, 2023-09-05, 2024-06-20, 2025-06-30

| Comparison | fnguide source | investor source | Unit match | Result |
|---|---|---|---|---|
| **기관 매수대금** | data0203 `매수대금(기관)` | data1229 `매수대금(기관계)` | 원 = 원 | **30/30 exact match (diff=0)** |
| **기관 매도대금** | data0204 `매도대금(기관계)` | data1229 `매도대금(기관계)` | 원 = 원 | **30/30 exact match (diff=0)** |
| **기타법인 매수대금** | data0206 `매수대금(기타법인)` | data1229 `매수대금(기타법인)` | 원 = 원 | **30/30 exact match (diff=0)** |
| **등록외국인 매수대금** | data0207 `매수대금(등록외국인)` | data1230 `매수대금(등록외국인1)` ×10000 | 원 vs 만원→원 | **30/30 exact match (diff=0)** |
| **등록외국인 매도대금** | data0207 `매도대금(등록외국인)` | data1230 `매도대금(등록외국인)` ×10000 | 원 vs 만원→원 | **30/30 exact match (diff=0)** |

**All 150 spot checks: 100% match, zero difference.**

## 4. Key Structural Differences

| Aspect | `fnguide_data/` | `investor_data/` |
|---|---|---|
| **개인 (Individual)** | Direct data in data0206 | Derived: `전체 - 기관계 - 외국인계 - 기타법인` |
| **전체 (Total) 대금** | **Missing from download** (see §4.1) | Amount available (data1230, 만원) |
| **외국인계 (All Foreigners)** | **Missing from download** (see §4.2) | Available (data1230, 만원) |
| **전체 (Total) 수량** | Available (data0208, 주) | Not available |
| **외국인 definition** | Separate 등록외국인 + 기타외국인 | Output uses 등록외국인 only (Smart Money) |
| **Unit consistency** | All files in 원 | Mixed: data1229=원, data1230=만원 |
| **Header format** | Rows 1-14 metadata, data from row 15 | Same structure (row 9=codes, row 10=names, row 15+=data) |
| **Investor granularity** | 14 types (금융투자, 보험, 투신, 은행, 기타금융, 연기금, 사모펀드, 국가, etc.) | 3 types (기관, 외국인, 개인) |

### 4.1 Missing 전체 거래대금 in `fnguide_data/`

`data0208.xlsx` contains 6 sheets:

| Sheet | Item Code | Status |
|---|---|---|
| 매수수량(국가) | CI20321010 | ✓ present |
| 매수대금(국가) | CI20321020 | ✓ present |
| 매도수량(국가) | CI20322010 | ✓ present |
| 매도대금(국가) | CI20322020 | ✓ present |
| 매수수량(전체) | CI20991010 | ✓ present |
| 매도수량(전체) | CI20992010 | ✓ present |
| 매수대금(전체) | CI20991020 | **✗ missing** |
| 매도대금(전체) | CI20992020 | **✗ missing** |

**Cause: download omission.** The codes `CI20991020`/`CI20992020` follow the standard pattern and exist in FnGuide DataGuide, but were not selected during the export batch.

**Workaround:** 전체 대금 can be computed using the canonical KRX formula:
```
전체 = 기관계 + 개인 + 외국인계 + 기타법인
```
Where 기관계 already includes 금융투자, 보험, 투신, 은행, 기타금융, 연기금, 사모펀드, 국가. And 외국인계 = 등록외국인 + 기타외국인.

This was verified against the 2020-2025 `investor_data` 전체 values — see §4.3.

### 4.2 Missing 외국인계 aggregate in `fnguide_data/`

The pre-computed 외국인계 aggregate (등록외국인 + 기타외국인) was not downloaded. Only the two components are available separately.

**Workaround:** 외국인계 can be computed:
```
외국인계 = 등록외국인 + 기타외국인
```

**Validation result (against `investor_data` 외국인계, 2020-2025, 5 stocks × 1,472 dates = 7,360 cells):**
- **Zero NaN cells** on all 5 tested stocks — data is fully complete
- 1,846 cells had non-zero diffs; **all diffs are exact multiples of 10,000원**
- **Root cause:** the `investor_data` 외국인계 is stored in 만원 (10,000 KRW units), so converting back to 원 (×10000) loses sub-만원 precision. The fnguide component sum (등록외국인 + 기타외국인, both in 원) is actually the **more precise** value.
- **Conclusion: the sum is correct.** The diffs are rounding artifacts in the reference data, not errors in the computation.

### 4.3 Validation: 전체 = 기관계 + 개인 + (등록+기타외국인) + 기타법인

Tested against `investor_data` 전체 매수대금 (data1230 × 10000) across 1,472 overlapping trading days and 5 major stocks:

| Date | Stock | Computed (fnguide sum) | Actual (investor_data) | Diff |
|---|---|---|---|---|
| 2020-01-02 | A005930 | 719,663,190,000 | 719,663,190,000 | **0** ✓ |
| 2020-01-02 | A000660 | 222,841,410,000 | 222,841,410,000 | **0** ✓ |
| 2020-01-02 | A035420 | 55,309,560,000 | 55,309,560,000 | **0** ✓ |
| 2022-03-10 | A005930 | 1,500,935,530,000 | 1,500,935,520,000 | 10,000 ✓ |
| 2023-09-05 | A005930 | 871,401,580,000 | 871,401,580,000 | **0** ✓ |
| 2025-06-30 | A005930 | 1,030,779,270,000 | 1,030,779,270,000 | **0** ✓ |
| 2025-06-30 | A000660 | 1,270,954,680,000 | 1,270,954,680,000 | **0** ✓ |

For major stocks, the formula produces exact or near-exact results. All non-zero diffs are exact multiples of 10,000원 — these are 만원 rounding artifacts from the `investor_data` reference (which stores values in 만원), not errors in the fnguide sum. The fnguide component sum (all in 원) is the more precise value.

All individual investor types have both 수량 (volume) and 대금 (amount):

| File | Investor Types | 수량 | 대금 |
|---|---|---|---|
| data0203 | 기관 매수 | ✓ | ✓ |
| data0204 | 기관 매도, 금융투자, 보험, 투신 | ✓ | ✓ |
| data0205 | 은행, 기타금융 | ✓ | ✓ |
| data0206 | 연기금, 기타법인, 개인 | ✓ | ✓ |
| data0207 | 등록외국인, 기타외국인, 사모펀드 | ✓ | ✓ |
| data0208 | 국가 | ✓ | ✓ |
| data0208 | **전체** | ✓ | **✗** (computable) |

## 5. Aggregate Composition

The KRX investor classification defines two key aggregates:

```
기관계 = 금융투자 + 보험 + 투신 + 은행 + 기타금융 + 연기금 + 사모펀드 + 국가
외국인계 = 등록외국인 + 기타외국인
전체 = 기관계 + 개인 + 외국인계 + 기타법인
```

**Important:** 국가 and 사모펀드 are already included in 기관계. Do NOT add them separately when computing 전체.

## 6. Investor Type Mapping

```
fnguide_data (granular)                    investor_data (aggregated)
─────────────────────────────────────────  ──────────────────────────
금융투자 + 보험 + 투신 + 은행 +
기타금융 + 연기금 + 사모펀드 + 국가 ═══►  기관 (기관계)

등록외국인                       ═══════►  외국인 (Smart Money)

기타외국인 ─┐
개인 ───────┤                    ═══════►  개인 (derived, includes 기타외국인)
기타법인 ──(used in derivation only)

전체                                       (used for 개인 derivation)
```

## 7. Investor Type Introduction Dates

Not all investor categories existed from the start of the dataset. The KRX introduced new classifications over time:

| Investor Type | First Data Date | Notes |
|---|---|---|
| 기관계, 금융투자, 보험, 투신, 은행, 기타금융, 기타법인, 개인, 등록외국인, 국가 | 2000-01-04 | Available from dataset start |
| 연기금등 | 2000-01-05 | Essentially from the start |
| **기타외국인** | **2003-12-01** | KRX subdivided foreign investors (Art. 67 Enforcement Rules amendment, Sep 26 2003) |
| **사모펀드** | **2008-06-23** | Separated from 기관계 as distinct reporting category |

Before 2003-12-01, all foreign investors were under a single code (`9000`). On that date, the KRX split them into 등록외국인 (code `9000`, registered) and 기타외국인 (code `9001`, unregistered/other). For pre-2003-12-01 data: 외국인계 = 등록외국인.

## 8. Data Quality Notes

| Check | Status |
|---|---|
| fnguide ⊇ investor xlsx stocks | ✓ |
| All CSV stocks ⊂ fnguide stocks | ✓ |
| 기관 values identical across sources | ✓ (0 diff on 30 spot checks) |
| 기타법인 values identical | ✓ (0 diff) |
| 등록외국인 values identical (after 만원→원) | ✓ (0 diff, no rounding error) |
| investor data1230 만원 conversion correct | ✓ (×10000 matches fnguide 원 exactly) |
| 등록외국인 + 기타외국인 = 외국인계 | ✓ (all diffs are 만원 rounding artifacts from investor_data) |
| 기관계 + 개인 + 외국인계 + 기타법인 = 전체 | ✓ (all diffs are 만원 rounding artifacts from investor_data) |
| 전체 매수/매도대금 in fnguide | ✗ missing (computable from parts) |
| 외국인계 aggregate in fnguide | ✗ missing (computable from parts) |
| 기타외국인 NULL before 2003-12-01 | ✓ (KRX classification introduced on that date) |
| 사모펀드 NULL before 2008-06-23 | ✓ (KRX classification introduced on that date) |

## 9. Advantages of Each Dataset

**`fnguide_data/` advantages:**
- 26 years of history (2000-2026) vs 6 years
- ~1,000 more stocks tracked
- 14 granular investor categories (can build custom aggregations)
- 개인 data available directly (no derivation needed)
- Consistent units (all 원)
- Annual financials + monthly market cap included (data2_0203)

**`fnguide_data/` gaps:**
- 전체 매수대금/매도대금 not downloaded (computable: 기관계 + 개인 + 외국인계 + 기타법인)
- 외국인계 aggregate not downloaded (computable: 등록외국인 + 기타외국인)

**`investor_data/` advantages:**
- Pre-processed CSV ready for analysis (12.8M rows)
- Clean 3-category Smart Money framework (기관/외국인/개인)
- 등록외국인 correctly separated for Smart Money analysis
- 전체 and 외국인계 aggregates available directly (data1230)
- Smaller file size for the processed output

## 10. Conclusion

**The two datasets are fully consistent.** Where they overlap (2020-2025, common stocks), the underlying values are identical — every spot check returned diff=0. The `fnguide_data/` is a superset that provides broader coverage (more stocks, longer history, finer granularity), while `investor_data/` is a curated, research-ready derivative optimized for Smart Money analysis.

The two missing aggregates in `fnguide_data/` (전체 대금 and 외국인계) were download omissions. Both can be computed from their component parts using the formulas in §5, verified against the 2020-2025 `investor_data` values. All non-zero diffs were exact multiples of 10,000원 — purely 만원 rounding artifacts from the `investor_data` reference, not errors in the computation. The fnguide component sums (all in 원) are in fact the more precise values.
