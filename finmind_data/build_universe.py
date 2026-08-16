"""Filter Taiwan stock universe to common equities on TWSE + TPEx.

Merges in pre-2015 delistings from `delisted_universe.parquet` that
FinMind's live `taiwan_stock_info` endpoint no longer returns. This is
required for symmetry with fnguide's "all codes" filter on the Korean
side — without these names, the Taiwan panel is survivorship-biased
against pre-2015 delistings while fnguide is not.
"""
from FinMind.data import DataLoader
import pandas as pd
from pathlib import Path

OUT = Path("/home/st/research/finance_db/finmind_data")

dl = DataLoader()
info = dl.taiwan_stock_info()

# TWSE + TPEx only (drop 'emerging')
info = info[info["type"].isin(["twse", "tpex"])].copy()

# Keep only 4-digit numeric codes (common stocks).
# Excludes: ETFs (00xxx, 5-6 digits), warrants (6-digit alphanumeric),
# preferred stocks (xxxxA/B). 4-digit 9xxx codes in this set are primary-
# listed Taiwan commons (e.g. 9921 巨大, 9904 寶成) including F-/-KY
# foreign-domiciled primaries — kept, matching how fnguide keeps
# foreign-domiciled primary listings on KOSPI/KOSDAQ. True TDRs carry
# industry_category "存託憑證"/"臺灣存託憑證" and are dropped below.
mask_4digit = info["stock_id"].str.fullmatch(r"\d{4}")
info = info[mask_4digit].copy()

# Exclude industries that are not common equity.
# 創新版股票 / 創新板股票 = TWSE Innovation Board (relaxed-disclosure tier
# for startups); structurally closer to KONEX than to ordinary KOSDAQ, so
# excluded to match the fnguide root-level universe.
exclude_industries = {
    "ETF", "ETN", "受益證券", "存託憑證", "臺灣存託憑證",
    "創新版股票", "創新板股票",
}
info = info[~info["industry_category"].isin(exclude_industries)].copy()

# Deduplicate by stock_id (the info endpoint returns one row per stock)
info = info.drop_duplicates(subset=["stock_id"]).reset_index(drop=True)

# Merge in pre-2015 4-digit common-stock delistings that the live
# taiwan_stock_info endpoint has dropped. These are needed for the
# 2005+ window to mirror fnguide root-level "all codes" coverage.
delisted = pd.read_parquet(OUT / "delisted_universe.parquet")
pre2015 = delisted[(delisted["date"] >= "2005-01-01")
                   & (delisted["date"] < "2015-01-01")].copy()
pre2015 = pre2015[pre2015["stock_id"].str.fullmatch(r"\d{4}")]
missing = pre2015[~pre2015["stock_id"].isin(info["stock_id"])].copy()
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

print(f"Universe size: {len(info)}")
print(f"  TWSE: {(info['type']=='twse').sum()}")
print(f"  TPEx: {(info['type']=='tpex').sum()}")
print(f"  pre-2015 delistings (type unknown): "
      f"{info['type'].isna().sum()}")
print("\nTop industries:")
print(info["industry_category"].value_counts().head(15))

info.to_parquet(OUT / "universe.parquet", index=False)
print(f"\nSaved to {OUT / 'universe.parquet'}")
