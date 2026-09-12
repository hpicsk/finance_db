"""Filter Taiwan stock universe to common equities on TWSE + TPEx.

Merges in delistings from `delisted_universe.parquet` that FinMind's live
`taiwan_stock_info` endpoint no longer returns. Without these names the
universe is what the endpoint still lists, which is the survivors — see
README "Survivorship bias".

The re-add used to be gated at `date < 2015-01-01`, on the premise that the
live endpoint keeps every name that delisted from 2015 on. It does not, and
the gate was never evidence for it: the delisting table the premise was
checked against held 315 rows and simply did not know about the names that
would have falsified it. The 2026-08-17 refresh brings the table to 723, and
46 of the names it adds delisted in 2015 or later with no row in the live
endpoint at all. The gate is now the window itself, and the test of whether a
name needs re-adding is the one the gate stood in for — whether the endpoint
still serves it.

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

from .pit_universe import emerging_boundary
from .window import COVERAGE_START, COVERAGE_END

OUT = Path(__file__).resolve().parent

dl = DataLoader()
raw = dl.taiwan_stock_info()

# Instrument types that are not common equity. A stock is dropped if *any* of
# its rows carries one: these mark what an instrument is, and within the 2005-
# 2024 window none of them is a status a name held for only part of the span.
# 創新版股票 / 創新板股票 = TWSE Innovation Board (relaxed-disclosure tier for
# startups, opened 2021-07-20); a separate tier with its own disclosure
# obligations rather than a main-board listing, so excluded. Six names have
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
# That row is undated evidence, and the registry dates its rows. A code whose
# 興櫃 row runs to or past `COVERAGE_END` is still on the emerging board when the
# panel ends, so its twse/tpex row, read as the promotion that follows 興櫃, is a
# listing that begins after the panel: it trades on the tape without ever being
# a listed common here. A name that fell back to 興櫃 after a delisting would
# read the same way and be dropped with them. `pit_universe` draws the same
# boundary per session, and the rule is imported rather than restated so the
# two cannot disagree about which side of it a name is on.
boundary = emerging_boundary(raw)
listed_ids -= set(boundary.index[boundary >= COVERAGE_END])

# Keep only 4-digit numeric codes (common stocks).
# Excludes: ETFs (00xxx, 5-6 digits), warrants (6-digit alphanumeric),
# preferred stocks (xxxxA/B). 4-digit 9xxx codes in this set are primary-
# listed Taiwan commons (e.g. 9921 巨大, 9904 寶成) including F-/-KY
# foreign-domiciled primaries — kept, because these price here rather than
# tracking a listing somewhere else. True TDRs carry
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

# Merge in in-window 4-digit common-stock delistings that the live
# taiwan_stock_info endpoint has dropped. Without them the universe is the
# set of names that survived to the pull date.
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
exits = delisted[delisted["date"] >= str(COVERAGE_START.date())].copy()
exits = exits[exits["stock_id"].str.fullmatch(r"\d{4}")]
live_names = raw.groupby("stock_id")["stock_name"].apply(set)
same_company = pd.Series(
    [nm in live_names.get(sid, set())
     for sid, nm in zip(exits["stock_id"], exits["stock_name"])],
    index=exits.index)
# A 4-digit code is not by itself a common stock: Taiwan numbers its ETFs
# 00xx and its depositary receipts 91xx, so the regex above admits both. The
# overlay drops both blocks by code. `excluded_ids` cannot do this, because it
# reads the instrument type from the endpoint, which no longer serves the
# companies the overlay re-adds. The endpoint has no row for 0015, a 00xx code
# that trades on the tape until 2014-02-18. The delisting table lacks 0015 too.
# Nothing else kept 0015 out of this overlay.
NON_COMMON_CODE_BLOCK = r"(?:00|91)\d\d"
missing = exits[~exits["stock_id"].isin(info["stock_id"])
                & ~exits["stock_id"].isin(excluded_ids)
                & ~exits["stock_id"].str.fullmatch(NON_COMMON_CODE_BLOCK)
                & ~same_company].copy()
missing = pd.DataFrame({
    "industry_category": pd.Series([None] * len(missing), dtype="object"),
    "stock_id": missing["stock_id"].astype(str).values,
    "stock_name": missing["stock_name"].astype(str).values,
    "type": pd.Series([None] * len(missing), dtype="object"),
    # date column = first-known date; for delistings we use delisting date.
    "date": missing["date"].astype(str).values,
})
print(f"Adding {len(missing)} in-window delistings missing from live "
      f"taiwan_stock_info.")
info = pd.concat([info, missing], ignore_index=True)

assert info["stock_id"].is_unique, "duplicate stock_id in the built universe"

print(f"Universe size: {len(info)}  "
      f"({COVERAGE_START.date()}..{COVERAGE_END.date()})")
print(f"  TWSE: {(info['type']=='twse').sum()}")
print(f"  TPEx: {(info['type']=='tpex').sum()}")
print(f"  delistings the endpoint dropped (type unknown): "
      f"{info['type'].isna().sum()}")
print(f"Excluded by instrument type: {len(excluded_ids)}")
print("\nTop industries:")
print(info["industry_category"].value_counts().head(15))

info.to_parquet(OUT / "universe.parquet", index=False)
print(f"\nSaved to {OUT / 'universe.parquet'}")
