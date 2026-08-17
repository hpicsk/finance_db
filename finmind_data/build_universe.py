"""Filter Taiwan stock universe to common equities on TWSE + TPEx.

Merges in pre-2015 delistings from `delisted_universe.parquet` that
FinMind's live `taiwan_stock_info` endpoint no longer returns. This is
required for symmetry with fnguide's "all codes" filter on the Korean
side — without these names, the Taiwan panel is survivorship-biased
against pre-2015 delistings while fnguide is not.

`taiwan_stock_info` returns one row per (market, industry) a stock has been
classified under, not one row per stock: 835 of 2,162 four-digit TWSE/TPEx
codes carry more than one. Rows still in force carry the query date; a
classification the exchange has retired keeps the date it was retired on.
So the exclusions below drop the *stock*, on the evidence of any of its
rows, rather than dropping rows and deduplicating afterwards — that order
keeps a stock alive on whichever classification the response happened to
list first. Every Innovation Board name also carries an ordinary industry
row, so under the old order the tier exclusion removed a row and admitted
the stock: replaying it against the 2026-08-17 table leaks all 36 ids the
endpoint marks as an excluded instrument, which is what the assertion
below counts.
"""
from FinMind.data import DataLoader
import pandas as pd
from pathlib import Path

OUT = Path("/home/st/research/finance_db/finmind_data")

dl = DataLoader()
raw = dl.taiwan_stock_info()

# Instrument types that are not common equity. A stock is dropped if *any* of
# its rows carries one: these mark what an instrument is, and within the 2005-
# 2024 window none of them is a status a name held for only part of the span.
# 創新版股票 / 創新板股票 = TWSE Innovation Board (relaxed-disclosure tier for
# startups, opened 2021-07-20); structurally closer to KONEX than to ordinary
# KOSDAQ, so excluded to match the fnguide root-level universe. Six names have
# since graduated to the ordinary board and are excluded here too — the
# earliest retired Innovation Board classification is stamped 2024-11-25, so
# each was on the relaxed tier for all but the last five weeks of the window.
exclude_industries = {
    "ETF", "ETN", "受益證券", "存託憑證", "臺灣存託憑證",
    "創新版股票", "創新板股票",
}
excluded_ids = set(raw.loc[raw["industry_category"].isin(exclude_industries),
                           "stock_id"])

# TWSE + TPEx only (drop 'emerging'), again on the evidence of any row: a name
# that moved up from the emerging board keeps its frozen `emerging` row.
listed_ids = set(raw.loc[raw["type"].isin(["twse", "tpex"]), "stock_id"])

# Keep only 4-digit numeric codes (common stocks).
# Excludes: ETFs (00xxx, 5-6 digits), warrants (6-digit alphanumeric),
# preferred stocks (xxxxA/B). 4-digit 9xxx codes in this set are primary-
# listed Taiwan commons (e.g. 9921 巨大, 9904 寶成) including F-/-KY
# foreign-domiciled primaries — kept, matching how fnguide keeps
# foreign-domiciled primary listings on KOSPI/KOSDAQ. True TDRs carry
# industry_category "存託憑證"/"臺灣存託憑證" and are dropped by `excluded_ids`.
keep = (raw["stock_id"].isin(listed_ids)
        & ~raw["stock_id"].isin(excluded_ids)
        & raw["stock_id"].str.fullmatch(r"\d{4}"))

# One row per surviving stock, and it must be a row still in force — a retired
# classification would publish a stale market and a stale industry.
info = raw[keep].sort_values("date").drop_duplicates(
    subset=["stock_id"], keep="last").reset_index(drop=True)

assert not (set(info["stock_id"]) & excluded_ids), (
    "an excluded instrument type survived on a second classification row — "
    "the filter is dropping rows where it must drop stocks"
)

# Merge in pre-2015 4-digit common-stock delistings that the live
# taiwan_stock_info endpoint has dropped. These are needed for the
# 2005+ window to mirror fnguide root-level "all codes" coverage.
#
# What has to be absent is the *company*, not the code. Testing the code
# against `info` re-admitted the four TDRs 9101/9102/9104/9151 for years: the
# exclusion above had just removed them, so this line read them as names the
# endpoint had dropped and put them straight back. Testing it against `raw`
# instead loses 2432, whose code was reissued — 倚天資訊 delisted in 2008 and
# 倚天酷碁-創 holds the code now, so the endpoint knows the code while knowing
# nothing about the company the universe row stands for. Match on the name the
# delisting was recorded under: those four are still listed under their own,
# and 2432 is not.
delisted = pd.read_parquet(OUT / "delisted_universe.parquet")
pre2015 = delisted[(delisted["date"] >= "2005-01-01")
                   & (delisted["date"] < "2015-01-01")].copy()
pre2015 = pre2015[pre2015["stock_id"].str.fullmatch(r"\d{4}")]
live_names = raw.groupby("stock_id")["stock_name"].apply(set)
same_company = pd.Series(
    [nm in live_names.get(sid, set())
     for sid, nm in zip(pre2015["stock_id"], pre2015["stock_name"])],
    index=pre2015.index)
missing = pre2015[~pre2015["stock_id"].isin(info["stock_id"])
                  & ~same_company].copy()
missing = pd.DataFrame({
    "industry_category": pd.Series([None] * len(missing), dtype="object"),
    "stock_id": missing["stock_id"].astype(str).values,
    "stock_name": missing["stock_name"].astype(str).values,
    "type": pd.Series([None] * len(missing), dtype="object"),
    # date column = first-known date; for delistings we use delisting date.
    "date": missing["date"].astype(str).values,
})
print(f"Adding {len(missing)} pre-2015 delistings missing from live "
      f"taiwan_stock_info.")
info = pd.concat([info, missing], ignore_index=True)

assert info["stock_id"].is_unique, "duplicate stock_id in the built universe"

print(f"Universe size: {len(info)}")
print(f"  TWSE: {(info['type']=='twse').sum()}")
print(f"  TPEx: {(info['type']=='tpex').sum()}")
print(f"  pre-2015 delistings (type unknown): "
      f"{info['type'].isna().sum()}")
print(f"Excluded by instrument type: {len(excluded_ids)}")
print("\nTop industries:")
print(info["industry_category"].value_counts().head(15))

info.to_parquet(OUT / "universe.parquet", index=False)
print(f"\nSaved to {OUT / 'universe.parquet'}")
