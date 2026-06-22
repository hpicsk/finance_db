# FnGuide DataGuide XLSX Dataset

## Overview

- **8 xlsx files** in `raw/`, ~5.7 GB total
- **Source:** FnGuide DataGuide (Korean financial data platform)
- **Layout:** Raw vendor exports live under `raw/`. Two flat helper
  modules (`fnguide_io.py`, `investor_loader.py`) sit at the directory
  root for backward compatibility with older research projects. **Going
  forward, new projects should parse the sheets inline rather than
  depending on these helpers** — the layout is simple enough that
  centralizing the parsers earns little.
- **Coverage:** ~3,900 Korean listed stocks (KOSPI / KOSDAQ) for
  investor trading & financials.
- **Price data is NOT in this directory.** Use `kr_marcap/` instead —
  `kr_marcap.market_loader.load_market_data` is the canonical
  survivorship-bias-free price loader (`date, ticker, open, high, low,
  close, volume, amount, market_cap, listed_shares`), and
  `kr_marcap.adjust.load_adjusted(ticker)` returns split-adjusted
  series for single-ticker work. For point-in-time membership, use
  `kr_marcap.universe(date, kind='common')`.
- **Survivorship bias — not a problem for the files kept here.** All
  eight xlsx files were exported with DataGuide's **"all codes"
  (전체 / 상폐 포함)** filter and are **effectively
  survivorship-bias-free for KOSPI/KOSDAQ common stocks** — paired with
  `kr_marcap.universe(date, 'common', strict=True)`, the live universe
  matches 100 %, and 99.1 % of common-stock delistings since 2021 are
  present (only 1 irreducible fnguide hole remains; 98.2 % under the
  default `strict=False`). Each delisted ticker's column carries data
  through its delisting date and goes NaN after. For most analyses that
  stay within these files, no external delisted-data merge is needed.
  See `DELISTED_COVERAGE.md` for the full breakdown.
- **If you re-pull additional metrics from DataGuide,** choose the
  "all codes" (전체 / 상폐 포함) filter to preserve delisted coverage.
  A previous `raw/currently_listed/` sub-batch pulled with the
  "currently listed" filter had 0% delisted coverage by construction
  and was removed.
- **Ticker-reassignment caveat (IFRS-C only):** `data2_0203.xlsx`
  annual financials may return values from a later listing that
  inherited the 6-digit KRX code. Truncate each series at
  `delisting_date.year - 1` before use.
- **Always-missing buckets:** preferred shares (우/우B/1우/MF, ~0.9%),
  KONEX (~2.6%), and specialty funds (선박투자/리츠/호, ~2.9%). These
  are usually excluded on methodological grounds anyway.
- **Data domains in this directory:**
  - **Daily investor trading flow** (6 files: data0203--data0208) —
    buy/sell volume & amount by investor type, 2000-01-04 to Feb 2026
  - **Annual financial statements + monthly market cap** (1 file:
    data2\_0203) — balance sheet, income statement items (IFRS
    consolidated), 1999--2025
  - **Short-selling / securities-lending / free-float** (1 file:
    short_sale_lending) — daily short-sale balance & turnover, lending
    balance, and free-float ratio, split KOSPI/KOSDAQ, 2002--2026

## Data Summary

| Domain | Files | Granularity | Coverage |
|--------|-------|-------------|----------|
| **Investor Trading (12 types, buy+sell, volume+amount)** | data0203--data0208 | Daily | ~3,902 stocks, 2000--2026 |
| **Financials (consolidated)** | data2_0203 | Annual + Monthly (시가총액) | IFRS(C): balance sheet, operating profit, total assets, market cap |
| **Short-selling / lending / free-float** | short_sale_lending | Daily | ~4,041 stocks (KOSPI+KOSDAQ split), 2002--2026 |

**NOT available in this dataset:** OHLCV / market cap / shares (use
`kr_marcap/` and `kr_delisted/` instead), main-entity
(IFRS-M) financials, L2 order book / tick data, bid-ask spread,
analyst coverage / consensus estimates, CB/BW/mezzanine event
calendar, index composition & rebalancing events, tick size /
institutional rules calendar, broker-level / account-level data.

## Common File Structure (Header Rows 1--14)

All sheets share the same FnGuide DataGuide export format:

| Row | Field | Description |
|-----|-------|-------------|
| 1 | (blank) | -- |
| 2 | Calendar Basis | Calendar system used |
| 3 | Portfolio | Currency unit (원 = KRW) |
| 4 | Item | Spacer |
| 5 | Frequency | Data frequency (일간=Daily / 월간=Monthly / 연간=Annual), currency code |
| 6 | Non-Trading Day | Handling rule (Exclusive = skip non-trading days) |
| 7 | Include Weekend | "ALL" |
| 8 | Term | Date range: start (e.g. 20000101) to end (e.g. Current(20260203)) |
| 9 | **Symbol** | Stock ticker codes (e.g. A005930, A000660) |
| 10 | **Symbol Name** | Company names in Korean (e.g. 삼성전자, SK하이닉스) |
| 11 | Kind | Data category: CIA (investor trading), NFS-IFRS(C) (consolidated financials), SSC (stock stats) |
| 12 | **Item** | FnGuide item code (e.g. CI20001010, 6000903007) |
| 13 | **Item Name** | Full metric name in Korean |
| 14 | Frequency | DAILY / MONTHLY / ANNUAL |

**Data starts at row 15.** Column A = date (datetime), columns B
onward = one column per stock (~3,902--3,904 stocks).

## Stock Universe

- ~3,902--3,904 Korean listed stocks across KOSPI and KOSDAQ
- Identified by ticker codes with "A" prefix + 6 digits (e.g. A005930
  = Samsung Electronics)
- Columns are ordered approximately by market cap
- Stocks not yet listed on a given date have `None`/NaN values
- Minor column count differences between files (3,903 vs 3,905) due to
  different download dates
- **Survivorship-bias status:** all files in this directory were
  pulled with DataGuide's "all codes" (전체 / 상폐 포함) filter and
  are effectively survivorship-bias-free — ~90% of genuine delistings
  present, ~99% from 2021 onward. See `DELISTED_COVERAGE.md` for the
  full breakdown.

## Python Loading Example

Two flat helper modules ship in this directory for the common cases.
They have no package boilerplate — put `~/finance_db/fnguide_data/` on
`sys.path` and import them by module name. **These exist for backward
compat with current research projects; new projects should prefer
inline parsing using the documented 14-row layout.**

- `fnguide_io.py` — `load_fnguide_sheet(filepath, sheet_name)` returns
  a date-indexed wide DataFrame; `melt_fnguide_wide(df, value_name)`
  pivots it long.
- `investor_loader.py` —
  `load_investor_flow(start, end, *, raw_dir, investor_types=('기관','개인','외국인'), foreign_definition='등록외국인', cache_dir=None)`
  returns a long
  `(date, ticker, investor_type, buy_value, sell_value, net_buy_value)`
  panel (KRW) for any date range, derived from
  `raw/data0203/0204/0206/0207.xlsx`. `foreign_definition='등록외국인'`
  (Smart Money, default) restricts 외국인 to registered foreigners;
  `'외국인계'` adds 기타외국인. Sibling helper `to_wide_net(flow)`
  pivots to wide `(date, ticker, institutional, individual, foreign)`
  net columns. Design rationale and an integrity report (vs the
  legacy `qf_next/investor_data/` data1229/data1230 export) live in
  `docs/investor/`.
- `subinvestor_loader.py` —
  `load_subinvestor_flow(start, end, *, raw_dir, subinvestor_types=<all 8>, cache_dir=None)`
  returns a long `(date, ticker, subinvestor_type, buy_value, sell_value,
  net_buy_value)` panel (KRW) decomposing the 기관계 aggregate into its 8 KRX
  sub-types (pension/연기금등, insurance/보험, investment_trust/투신,
  pe_funds/사모펀드, financial_inv/금융투자, other_financial/기타금융,
  bank/은행, government/국가) from `raw/data0204/0205/0206/0207/0208.xlsx`.
  `SUBINVESTOR_SOURCES` is the canonical 8-type → (file, sheet) map; sibling
  `to_wide_net_sub(flow)` pivots to one net column per sub-type. A missing/
  renamed sheet raises (fail loud); consumers requiring all 8 (e.g. qf_paper's
  Capacity-Bound = pension + insurance) should error on an absent type rather
  than zero-fill.

For OHLCV / market cap / listed shares, see `kr_marcap` in this repo —
`kr_marcap.market_loader.load_market_data` (`date, ticker, open, high,
low, close, volume, amount, market_cap, listed_shares`),
`kr_marcap.adjust.load_adjusted(ticker)` (split-adjusted single-ticker
series), and `kr_marcap.universe(date, kind='common')` (point-in-time
common-stock membership). Both are survivorship-bias-free.

For ad-hoc reads, the underlying xlsx layout is documented above —
column codes on row 9, names on row 10, item codes on row 12, data
starts row 15.

```python
import pandas as pd

# Read a single sheet (skip first 14 header rows, use row 9 as column names)
# For large files, consider using openpyxl read_only mode or chunked reading

# Step 1: Read metadata rows to get stock symbols and item info
meta = pd.read_excel("raw/data0203.xlsx", sheet_name="매수수량(기관)", header=None, nrows=14)
symbols = meta.iloc[8, 1:]       # Row 9: ticker codes (A005930, ...)
names = meta.iloc[9, 1:]         # Row 10: company names (삼성전자, ...)
item_code = meta.iloc[11, 1]     # Row 12: FnGuide item code
item_name = meta.iloc[12, 1]     # Row 13: metric name in Korean

# Step 2: Read the time series data
df = pd.read_excel("raw/data0203.xlsx", sheet_name="매수수량(기관)",
                   header=None, skiprows=14)
df.columns = ["date"] + list(symbols)
df["date"] = pd.to_datetime(df["date"])
df = df.set_index("date")
```

---

## File-by-File Documentation

### 1. `raw/data0203.xlsx` (220 MB)

**Content:** Institutional investors (aggregate) -- **buy** side only

| Sheet Name | English | Item Code | Unit |
|---|---|---|---|
| 매수수량(기관) | Institutional Buy Volume (total) | CI20001010 | Shares (주) |
| 매수대금(기관) | Institutional Buy Amount (total) | CI20001020 | KRW (원) |

- **Sheets:** 2
- **Rows per sheet:** ~6,446 (trading days)
- **Columns:** 3,903 (1 date + ~3,902 stocks)
- **Frequency:** Daily
- **Date range:** 2000-01-04 to ~2026-02-03
- **Kind:** CIA
- **Notes:** Aggregate institutional buy data. The sell side for aggregate institutional is in data0204.

---

### 2. `raw/data0204.xlsx` (1.4 GB)

**Content:** Institutional investors (aggregate sell) + breakdown by sub-type: Securities firms, Insurance companies, Asset management/Mutual funds

| Sheet Name | English | Item Code | Unit |
|---|---|---|---|
| 매도수량(기관계) | Institutional Sell Volume (total) | CI20002010 | Shares |
| 매도대금(기관계) | Institutional Sell Amount (total) | CI20002020 | KRW |
| 매수수량(금융투자) | Securities Firm Buy Volume | CI20011010 | Shares |
| 매수대금(금융투자) | Securities Firm Buy Amount | CI20011020 | KRW |
| 매도수량(금융투자) | Securities Firm Sell Volume | CI20012010 | Shares |
| 매도대금(금융투자) | Securities Firm Sell Amount | CI20012020 | KRW |
| 매수수량(보험) | Insurance Co. Buy Volume | CI20021010 | Shares |
| 매수대금(보험) | Insurance Co. Buy Amount | CI20021020 | KRW |
| 매도수량(보험) | Insurance Co. Sell Volume | CI20022010 | Shares |
| 매도대금(보험) | Insurance Co. Sell Amount | CI20022020 | KRW |
| 매수수량(투신) | Asset Mgmt (Mutual Fund) Buy Volume | CI20031010 | Shares |
| 매수대금(투신) | Asset Mgmt (Mutual Fund) Buy Amount | CI20031020 | KRW |
| 매도수량(투신) | Asset Mgmt (Mutual Fund) Sell Volume | CI20032010 | Shares |
| 매도대금(투신) | Asset Mgmt (Mutual Fund) Sell Amount | CI20032020 | KRW |
| Sheet16 | (empty) | -- | -- |

- **Sheets:** 15 (14 data + 1 empty)
- **Rows per sheet:** ~6,449
- **Columns:** 3,903
- **Frequency:** Daily
- **Date range:** 2000-01-04 to ~2026-02-06
- **Kind:** CIA
- **Notes:** Largest file. Contains the aggregate institutional sell side (counterpart to data0203 buy side) plus full buy/sell breakdown for three institutional sub-types. Ignore Sheet16 (empty).

---

### 3. `raw/data0205.xlsx` (666 MB)

**Content:** Institutional sub-types continued: Banks, Other Financial Institutions

| Sheet Name | English | Item Code | Unit |
|---|---|---|---|
| 매수수량(은행) | Bank Buy Volume | CI20041010 | Shares |
| 매수대금(은행) | Bank Buy Amount | CI20041020 | KRW |
| 매도수량(은행) | Bank Sell Volume | CI20042010 | Shares |
| 매도대금(은행) | Bank Sell Amount | CI20042020 | KRW |
| 매수수량(기타금융) | Other Financial Buy Volume | CI20051010 | Shares |
| 매수대금(기타금융) | Other Financial Buy Amount | CI20051020 | KRW |
| 매도수량(기타금융) | Other Financial Sell Volume | CI20052010 | Shares |
| 매도대금(기타금융) | Other Financial Sell Amount | CI20052020 | KRW |

- **Sheets:** 8
- **Rows per sheet:** ~6,450
- **Columns:** 3,903
- **Frequency:** Daily
- **Date range:** 2000-01-04 to ~2026-02-09
- **Kind:** CIA
- **Notes:** Sheet tabs were corrected from truncated forms (기타 -> 기타금융).

---

### 4. `raw/data0206.xlsx` (1.4 GB)

**Content:** Pension Funds, Other Corporations, Individuals

| Sheet Name | English | Item Code | Unit |
|---|---|---|---|
| 매수수량(연기금등) | Pension Fund Buy Volume | CI20061010 | Shares |
| 매수대금(연기금등) | Pension Fund Buy Amount | CI20061020 | KRW |
| 매도수량(연기금등) | Pension Fund Sell Volume | CI20062010 | Shares |
| 매도대금(연기금등) | Pension Fund Sell Amount | CI20062020 | KRW |
| 매수수량(기타법인) | Other Corporation Buy Volume | CI20071010 | Shares |
| 매수대금(기타법인) | Other Corporation Buy Amount | CI20071020 | KRW |
| 매도수량(기타법인) | Other Corporation Sell Volume | CI20072010 | Shares |
| 매도대금(기타법인) | Other Corporation Sell Amount | CI20072020 | KRW |
| 매수수량(개인) | Individual Buy Volume | CI20081010 | Shares |
| 매수대금(개인) | Individual Buy Amount | CI20081020 | KRW |
| 매도수량(개인) | Individual Sell Volume | CI20082010 | Shares |
| 매도대금(개인) | Individual Sell Amount | CI20082020 | KRW |

- **Sheets:** 12
- **Rows per sheet:** ~6,450
- **Columns:** 3,903
- **Frequency:** Daily
- **Date range:** 2000-01-04 to ~2026-02-09
- **Kind:** CIA
- **Notes:** Sheet 8 tab was corrected from truncated "매도대금" to "매도대금(기타법인)".

---

### 5. `raw/data0207.xlsx` (1.3 GB)

**Content:** Registered Foreigners, Other Foreigners, Private Funds

| Sheet Name | English | Item Code | Unit |
|---|---|---|---|
| 매수수량(등록외국인) | Registered Foreign Buy Volume | CI20091010 | Shares |
| 매수대금(등록외국인) | Registered Foreign Buy Amount | CI20091020 | KRW |
| 매도수량(등록외국인) | Registered Foreign Sell Volume | CI20092010 | Shares |
| 매도대금(등록외국인) | Registered Foreign Sell Amount | CI20092020 | KRW |
| 매수수량(기타외국인) | Other Foreign Buy Volume | CI20101010 | Shares |
| 매수대금(기타외국인) | Other Foreign Buy Amount | CI20101020 | KRW |
| 매도수량(기타외국인) | Other Foreign Sell Volume | CI20102010 | Shares |
| 매도대금(기타외국인) | Other Foreign Sell Amount | CI20102020 | KRW |
| 매수수량(사모펀드) | Private Fund Buy Volume | CI20311010 | Shares |
| 매수대금(사모펀드) | Private Fund Buy Amount | CI20311020 | KRW |
| 매도수량(사모펀드) | Private Fund Sell Volume | CI20312010 | Shares |
| 매도대금(사모펀드) | Private Fund Sell Amount | CI20312020 | KRW |

- **Sheets:** 12
- **Rows per sheet:** ~6,452
- **Columns:** 3,905
- **Frequency:** Daily
- **Date range:** 2000-01-04 to ~2026-02-11
- **Kind:** CIA
- **Notes:** Sheet tabs were corrected (typos and truncations fixed). **기타외국인 data is NULL before 2003-12-01** and **사모펀드 is NULL before 2008-06-23** -- see "Investor Type Introduction Dates" section for details.

---

### 6. `raw/data0208.xlsx` (616 MB)

**Content:** Government/National entities, Total (all investors aggregate)

| Sheet Name | English | Item Code | Unit |
|---|---|---|---|
| 매수수량(국가) | Government Buy Volume | CI20321010 | Shares |
| 매수대금(국가) | Government Buy Amount | CI20321020 | KRW |
| 매도수량(국가) | Government Sell Volume | CI20322010 | Shares |
| 매도대금(국가) | Government Sell Amount | CI20322020 | KRW |
| 매수수량(전체) | Total (All Investors) Buy Volume | CI20991010 | Shares |
| 매도수량(전체) | Total (All Investors) Sell Volume | CI20992010 | Shares |

- **Sheets:** 6
- **Rows per sheet:** ~6,453
- **Columns:** 3,905
- **Frequency:** Daily
- **Date range:** 2000-01-04 to ~2026-02-12
- **Kind:** CIA
- **Notes:** Sheet tabs were corrected: truncated names restored, and sheets 5--6 renamed from misleading "국가" to "전체" to match their actual content (Total/All Investors).

---

### 7. `raw/data2_0203.xlsx` (11 MB)

**Content:** Annual financial statements (IFRS consolidated) + Monthly market capitalization

| Sheet Name | English | Item Code | Kind | Frequency |
|---|---|---|---|---|
| 보통주자본금 | Common Stock Capital | 6000903007 | NFS-IFRS(C) | Annual |
| 자본잉여금 | Capital Surplus | 6000903012 | NFS-IFRS(C) | Annual |
| 이익잉여금 | Retained Earnings | 6000903016 | NFS-IFRS(C) | Annual |
| 이연법인세부채 | Deferred Tax Liabilities | 6000911019 | NFS-IFRS(C) | Annual |
| 자기주식 | Treasury Stock | 6000903019 | NFS-IFRS(C) | Annual |
| 자기주식 처분손실 | Loss on Disposal of Treasury Stock | 6000991046 | NFS-IFRS(C) | Annual |
| 영업이익 | Operating Profit | 6000906001 | NFS-IFRS(C) | Annual |
| 총자산 | Total Assets | 6000901001 | NFS-IFRS(C) | Annual |
| 시가총액 | Market Capitalization (millions KRW) | S410001250 | SSC | Monthly |
| Sheet13 | (empty) | -- | -- | -- |

- **Sheets:** 10 (8 annual financials + 1 monthly market cap + 1 empty)
- **Rows:** 42 (annual sheets, 28 entries = 27 fiscal years 1999--2025 + one 2026-02-02 current-snapshot row) / 340 (시가총액, monthly: 326 entries, ~27 years)
- **Columns:** 3,903
- **Date range:** 1999-12-31 to 2025-12-31 (annual; trailing 2026-02-02 current-snapshot row); 1999-01-31 to 2026-01-31 (monthly; trailing 2026-02-02 current-snapshot row)
- **Kind:** NFS-IFRS(C) for financial statements, SSC for market cap
- **Notes:** This is the only file with non-daily data. Annual dates are fiscal year-end dates (typically 12-31). Market cap is in millions of KRW. Ignore Sheet13 (empty). For daily market cap on currently-listed names, prefer `kr_marcap.market_loader.load_market_data` (column `market_cap`).

---

### 8. `raw/short_sale_lending.xlsx` (876 MB)

**Content:** Short-selling, securities-lending, and free-float series.
This is the **only** short-selling/lending source in the repo — the
investor-flow and financials files carry none of it.

| Sheet (per KOSPI + KOSDAQ) | English | Item Code | Unit | First obs |
|---|---|---|---|---|
| 대차잔고 | Securities-lending balance | S410100400 | Shares | 2002-01-04 |
| 차입공매도금액 | Covered short-sale turnover (daily) | S410000920 | KRW | 2008-01-03 |
| 공매도잔고금액 | Short-sale balance (value) | S410000994 | mn KRW | 2008-08-07 |
| 공매도잔고 | Short-sale balance (shares) | S410000992 | Shares | 2016-06-30 |
| 유동주식비율 | Free-float ratio | S420005150 | % | 2003-01-02 |

- **Sheets:** 10 — each metric has a **separate KOSPI and KOSDAQ sheet**.
  Unlike the investor-flow files, tickers are NOT pooled across markets:
  read the market sheet you need, or concatenate both.
- **Tickers:** 1,284 KOSPI + 2,773 KOSDAQ = 4,041 unique
- **Frequency:** Daily
- **Kind:** SSC
- **Date axis:** padded back to a 1979-12-24 placeholder; real data
  begins per-metric as in the table above and runs to 2026-06-10/12.
- **Notes:** Short-sale *balance in shares* begins 2016-06-30, matching
  KRX's public short-sale-balance disclosure start; the value series
  (백만원) carries earlier dates. Tabs are named `KOSPI_<metric>` /
  `KOSDAQ_<metric>` (e.g. `KOSDAQ_대차잔고`); the vendor's original
  full-width `ＫＯＳＰＩ＿` / `ＫＯＳＤＡＱ＿` prefixes were normalized to
  plain ASCII. Row 13 (Item Name) and row 11 (Kind) remain authoritative.
  Survivorship-bias-free: 99.4% of genuine common KOSPI/KOSDAQ
  delistings present (better than the investor-flow files) — see
  `DELISTED_COVERAGE.md`.

---

## Investor Type Code Reference (CI20 prefix)

| Code Prefix | Korean | English | Files |
|---|---|---|---|
| CI2000 | 기관계 | Institutional Total | data0203 (buy), data0204 (sell) |
| CI2001 | 금융투자 | Securities/Brokerage Firms | data0204 |
| CI2002 | 보험 | Insurance Companies | data0204 |
| CI2003 | 투신 | Asset Mgmt / Mutual Funds | data0204 |
| CI2004 | 은행 | Banks | data0205 |
| CI2005 | 기타금융 | Other Financial Institutions | data0205 |
| CI2006 | 연기금등 | Pension Funds | data0206 |
| CI2007 | 기타법인 | Other Corporations | data0206 |
| CI2008 | 개인 | Individuals (Retail) | data0206 |
| CI2009 | 등록외국인 | Registered Foreigners | data0207 |
| CI2010 | 기타외국인 | Other Foreigners | data0207 |
| CI2031 | 사모펀드 | Private Funds | data0207 |
| CI2032 | 국가 | Government / National | data0208 |
| CI2099 | 전체 | Total (All Investors) | data0208 |

**Item code pattern:** `CI20[investor_group][1=buy, 2=sell][010=volume(shares), 020=amount(KRW)]`

## Missing Aggregates (Download Omissions)

Two aggregate items were not included in the download batch but **can be computed** from existing data:

### 전체 매수대금/매도대금 (Total Trading Amount)

Item codes `CI20991020` (전체 매수대금) and `CI20992020` (전체 매도대금) were not downloaded. Only 전체 수량 (volume) is present in data0208.

**Formula (canonical KRX classification):**
```
전체 = 기관계 + 개인 + 외국인계 + 기타법인
```
Where:
- **기관계** (data0203/0204) already includes: 금융투자, 보험, 투신, 은행, 기타금융, 연기금, 사모펀드, 국가
- **외국인계** = 등록외국인 + 기타외국인

**Important:** Do NOT add 국가 or 사모펀드 separately -- they are already included in the 기관계 aggregate.

### 외국인계 (All Foreigners Aggregate)

The pre-computed 외국인계 aggregate was not downloaded. It can be computed:
```
외국인계 = 등록외국인 + 기타외국인
```

**Note:** 기타외국인 data is NULL before 2003-12-01 (see "Investor Type Introduction Dates" below). For those periods, 외국인계 = 등록외국인 (since 기타외국인 did not exist as a category).

### Verification

Both formulas were verified by cross-checking against `qf_next/investor_data/` (which has pre-computed 전체 and 외국인계 from a separate FnGuide download covering 2020-01-02 to 2025-12-26, 5 stocks × 1,472 dates):
- All non-zero diffs were **exact multiples of 10,000원** — purely 만원 rounding artifacts from the reference data (stored in 만원 units)
- The fnguide component sums (all in 원) are the **more precise** values
- **Conclusion: manual summation is correct**

See `integrity_report.md` for full details.

## Investor Type Introduction Dates

Not all investor categories existed from the start of the dataset. The KRX introduced new classifications over time, so earlier dates have NULL values for categories that did not yet exist.

| Investor Type | First Data Date | Notes |
|---|---|---|
| 기관계, 금융투자, 보험, 투신, 은행, 기타금융, 기타법인, 개인, 등록외국인, 국가 | **2000-01-04** | Available from dataset start |
| 연기금등 | **2000-01-05** | Essentially from the start |
| **기타외국인 (Other Foreigners)** | **2003-12-01** | KRX introduced this classification on Dec 1, 2003 |
| **사모펀드 (Private Funds)** | **2008-06-23** | KRX introduced this classification in mid-2008 |

### 기타외국인 (Other Foreigners) -- introduced 2003-12-01

Before December 1, 2003, the KRX grouped all foreign investors under a single classification (code `9000`, "외국인"). On that date, per the amendment to Article 67 of the Enforcement Rules of the Market Operations Regulation (passed September 26, 2003), the KRX subdivided foreign investors into:

- **등록외국인 (Registered Foreigners, code `9000`):** Foreign investors with a formal foreign investment registration ID
- **기타외국인 (Other Foreigners, code `9001`):** Unregistered foreigners, foreign corporations without an ID, or other foreign entities

**Implications for data processing:**
- For dates **before 2003-12-01**: 기타외국인 values are NULL. Treat 등록외국인 as the total foreign investor figure (외국인계 = 등록외국인).
- For dates **from 2003-12-01 onward**: 외국인계 = 등록외국인 + 기타외국인.

### 사모펀드 (Private Funds) -- introduced 2008-06-23

사모펀드 was separated out from 기관계 as a distinct reporting category in mid-2008. Values are NULL before this date. Note that 사모펀드 is included in the 기관계 aggregate, so its introduction does not affect the 기관계 total -- only the granularity of the breakdown.

## Known Data Quality Notes

1. **Sheet tab names corrected:** Truncated, misspelled, and misleading sheet tab names have been fixed in-place. Row 13 (Item Name) remains the authoritative source.
2. **Empty sheets:** data0204/Sheet16, data2\_0203/Sheet13 are empty -- skip these.
3. **NULL values:** Stocks not yet listed have None/NaN. Delisted stocks present in the universe (e.g. A117930 한진해운) carry values up to their delisting date and NaN afterward. 기타외국인 and 사모펀드 are NULL before their respective introduction dates (see above).
4. **Survivorship bias:** all files were pulled with DataGuide's "all codes" filter — **effectively survivorship-bias-free** for KOSPI/KOSDAQ common stocks (~90% of genuine delistings present, ~99% from 2021+). Each delisted ticker carries data through its delisting date and goes NaN after. See `DELISTED_COVERAGE.md` for the full breakdown.
5. **Slight column count differences:** Files downloaded on different dates have slightly different stock counts (3,903 vs 3,905).
6. **Date column differences:** Row counts vary slightly (6,446--6,453) across investor trading files due to different download end dates (Feb 3--12, 2026).

## Verification

- Open each file with `pd.read_excel(..., sheet_name=None, nrows=15)` to confirm header structure
- Verify row 9 (Symbol) contains stock tickers starting with "A"
- Verify row 13 (Item Name) matches the documented metric names
- Spot-check numeric values are reasonable (e.g., Samsung trading volumes in hundreds of thousands)
