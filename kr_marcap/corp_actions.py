"""Official corporate-action ground truth for price-adjustment series breaks.

This replaces the *calibrated* entity-change heuristics that used to live in
``adjust.py`` (``_CORROBORATION_TOL``, ``_GAP_DAYS`` and the share-ratio band)
with deterministic lookups against official sources.  It answers one question for
``build_adjustment_factors``: **on which (ticker, date) does the listing's
economic identity change, so that pre-date history belongs to a different entity
and must be dropped (``valid = False``)?**

A break is asserted ONLY from an official source — never from a price/volume/gap
threshold tuned to a validation set:

  1. **SPAC merger** — marcap ``Name`` transitions from ``…스팩…`` to a real
     company (e.g. 미래에셋제4호스팩 → 쎄노텍).  The pre-merger shell is a cash
     vehicle; its price history is not the merged company's.  (marcap, official.)
  2. **Ticker reuse** — the code has a genuine KIND delisting and later trades
     again (a different issuer took the retired code).  Break at the first
     re-appearance after the delisting.  (kr_delisted KIND calendar, official.)
  3. **Entity restructuring** — DART records a 회사합병 / 회사분할 / 회사분할합병 /
     주식교환 around a material share-count jump (reverse merger, 인적분할 재상장,
     지주사 전환).  (kr_status DART events, official.)
  4. **Manual override** — ``corp_action_overrides.csv`` (version-controlled,
     reviewed) for cases official sources do not cover, chiefly pre-2015 where
     DART structured coverage is sparse.

Everything else — including genuine 감자/유상/무상증자, which ``ChangesRatio``
already adjusts correctly — is **not** a break.  A *material* share-count jump
that no source explains is reported to ``corp_action_residuals.csv`` (loud, not
silently guessed) and defaults to *not* a break (the ChangesRatio backbone keeps
the series continuous; the automated oracle validation flags any real miss).

The only numeric parameters here are **materiality / matching bounds**, not
classification thresholds: whether a share change is large enough to warrant
review, and the physical filing→effect lag window for matching a DART event to
its marcap effective date.  The break verdict itself comes from the event *type*.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DART_EVENTS_PATH = REPO_ROOT / "kr_status" / "data" / "dart_corp_action_events.parquet"
DELISTING_CSV = REPO_ROOT / "kr_delisted" / "delisting_calendar.csv"
OVERRIDES_CSV = Path(__file__).resolve().parent / "corp_action_overrides.csv"
RESIDUALS_CSV = Path(__file__).resolve().parent / "cache" / "corp_action_residuals.csv"

# --- materiality / matching bounds (NOT classification thresholds) ---
# Entity changes (SPAC merger, reverse listing, ticker reuse, reverse merger)
# always move the share count by a LARGE factor; ordinary actions (small 증자,
# ESOP, options) do not. Only a >10x share change is a break *candidate* worth
# classifying — this is a materiality floor for locating events, not a decision
# (SPAC/reuse breaks are found by name/delisting regardless of this band). A DART
# 합병 with only a modest share change is a normal absorption (survivor continues,
# not a break), so requiring a large jump for the dart_entity path is correct.
_MATERIAL_LOW, _MATERIAL_HIGH = 0.1, 10.0
# Physical filing→effect lag: a DART 주요사항보고서 is filed on the board-decision
# date; the corporate action takes effect later (감자/증자 기준일 within months).
# Match an event to a marcap share-jump if the jump falls in this window after the
# filing (or just before, for late filings).
_MATCH_BACK = pd.Timedelta(days=400)
_MATCH_FWD = pd.Timedelta(days=30)


def _share_ratio(g: pd.DataFrame) -> pd.Series:
    prev = g["Stocks"].shift(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where((g["Stocks"] > 0) & (prev > 0), prev / g["Stocks"], np.nan)
    return pd.Series(r, index=g.index)


def _spac_breaks(g: pd.DataFrame) -> list[pd.Timestamp]:
    """Days where the name stops being a 스팩 shell — the merger/listing of the
    operating company. The pre-transition shell is a different entity."""
    name = g["Name"].astype(str)
    is_spac = name.str.contains("스팩", na=False)
    prev_spac = is_spac.shift(1, fill_value=False)
    trans = (~is_spac) & prev_spac
    return list(g.loc[trans, "Date"])


def _reuse_breaks(code: str, g: pd.DataFrame,
                  delistings: dict[str, list[pd.Timestamp]]) -> list[pd.Timestamp]:
    """First re-appearance after a genuine delisting = a reused code (new issuer)."""
    out: list[pd.Timestamp] = []
    for d in delistings.get(code, []):
        after = g.loc[g["Date"] > d, "Date"]
        if len(after):
            out.append(after.iloc[0])
    return out


# Delisting reasons that are a SAME-ENTITY relisting/market move, not an exit:
# the company keeps its identity and KRX keeps the price series continuous
# (e.g. 셀트리온/카카오 KOSDAQ→KOSPI 이전상장, 232830 코스닥시장 이전상장). A code
# re-appearing after one of these is the *same* entity, not a reused code.
_TRANSFER_REASON = r"이전상장|재상장|시장\s*상장"


def _load_delistings() -> dict[str, list[pd.Timestamp]]:
    """Delisting dates that END an entity, so a later re-appearance of the code is
    a *different* issuer (ticker reuse). Excludes preferred-share proxy rows (last-
    trade dates, not exits) and same-entity transfers/relistings."""
    if not DELISTING_CSV.exists():
        return {}
    df = pd.read_csv(DELISTING_CSV, dtype={"ticker": str})
    df["ticker"] = df["ticker"].str.zfill(6)
    df["d"] = pd.to_datetime(df["delisting_date"], errors="coerce")
    reason = df["reason"].astype(str)
    df = df[df["d"].notna()
            & ~reason.str.startswith("(not in KIND")
            & ~reason.str.contains(_TRANSFER_REASON, regex=True, na=False)]
    return df.groupby("ticker")["d"].apply(list).to_dict()


def _load_dart_events() -> pd.DataFrame:
    if not DART_EVENTS_PATH.exists():
        return pd.DataFrame(columns=["ticker", "category", "event", "rcept"])
    d = pd.read_parquet(DART_EVENTS_PATH)
    d = d[d["category"] != "none"].copy()
    d["ticker"] = d["ticker"].astype(str).str.zfill(6)
    d["rcept"] = pd.to_datetime(d["rcept_dt"], format="%Y%m%d", errors="coerce")
    return d[d["rcept"].notna()]


def _load_overrides() -> pd.DataFrame:
    if not OVERRIDES_CSV.exists():
        return pd.DataFrame(columns=["ticker", "date", "kind", "note"])
    o = pd.read_csv(OVERRIDES_CSV, dtype={"ticker": str})
    o["ticker"] = o["ticker"].str.zfill(6)
    o["date"] = pd.to_datetime(o["date"], errors="coerce")
    return o


def _near(dart_t: pd.DataFrame, category: str, day: pd.Timestamp) -> bool:
    """Is there a DART event of `category` whose filing is within the lag window?"""
    if dart_t.empty:
        return False
    sub = dart_t[dart_t["category"] == category]
    if sub.empty:
        return False
    lo, hi = day - _MATCH_BACK, day + _MATCH_FWD
    return bool(((sub["rcept"] >= lo) & (sub["rcept"] <= hi)).any())


def classify(marcap: pd.DataFrame,
             write_residuals: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Classify entity-change breaks from official sources.

    `marcap` needs columns Code, Date, Name, Stocks (sorted by Code, Date).
    Returns (breaks, residuals):
      breaks    — DataFrame[code, date, source]  (entity-change days)
      residuals — DataFrame[code, date, ratio]   (material jumps left unexplained)
    """
    delistings = _load_delistings()
    dart = _load_dart_events()
    dart_by_t = {t: g for t, g in dart.groupby("ticker")}
    overrides = _load_overrides()
    ov_break = {(r.ticker, r.date) for r in overrides[overrides["kind"] == "break"].itertuples()}
    ov_genuine = {(r.ticker, r.date) for r in overrides[overrides["kind"] == "genuine"].itertuples()}

    break_rows: list[dict] = []
    residual_rows: list[dict] = []

    for code, g in marcap.groupby("Code", sort=False):
        g = g.sort_values("Date")
        breaks: dict[pd.Timestamp, str] = {}

        for d in _spac_breaks(g):
            breaks.setdefault(d, "spac")
        for d in _reuse_breaks(code, g, delistings):
            breaks.setdefault(d, "reuse")

        # DART entity events explaining a material share jump
        ratio = _share_ratio(g)
        material = g.loc[(ratio < _MATERIAL_LOW) | (ratio > _MATERIAL_HIGH), "Date"]
        dart_t = dart_by_t.get(code, pd.DataFrame(columns=dart.columns))
        for day in material:
            if day in breaks:
                continue
            if (code, day) in ov_genuine:
                continue
            if _near(dart_t, "entity", day):
                breaks.setdefault(day, "dart_entity")
            elif (code, day) in ov_break:
                breaks.setdefault(day, "override")
            elif _near(dart_t, "genuine", day):
                # explained by an official 증자/감자 filing — genuine, not a break
                # and not an unexplained residual.
                continue
            else:
                # 액면분할/병합 (not in DART's event API) and true unknowns land
                # here: default to not-a-break; the oracle validation flags real
                # missed breaks, and corp_action_overrides.csv handles the rest.
                residual_rows.append({"code": code, "date": day,
                                      "ratio": float(ratio[g["Date"] == day].iloc[0])})

        # override breaks not tied to a material jump (e.g. curated pre-2015)
        for (t, d) in ov_break:
            if t == code:
                breaks.setdefault(d, "override")

        for d, src in breaks.items():
            break_rows.append({"code": code, "date": d, "source": src})

    breaks_df = pd.DataFrame(break_rows, columns=["code", "date", "source"])
    if len(breaks_df):
        breaks_df = breaks_df.sort_values(["code", "date"]).reset_index(drop=True)
    residuals_df = pd.DataFrame(residual_rows, columns=["code", "date", "ratio"])
    if len(residuals_df):
        residuals_df = residuals_df.sort_values(["code", "date"]).reset_index(drop=True)

    if write_residuals:
        RESIDUALS_CSV.parent.mkdir(parents=True, exist_ok=True)
        if len(residuals_df):
            residuals_df.to_csv(RESIDUALS_CSV, index=False)
        elif RESIDUALS_CSV.exists():
            RESIDUALS_CSV.unlink()

    return breaks_df, residuals_df
