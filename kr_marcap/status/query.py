"""Point-in-time tradable universe query API.

Layered on top of kr_marcap.universe (base kind='common' universe), the
marcap parquets (price/marcap/ADV liquidity filters), and the kr_status
event panel (관리종목 / 감사의견 비적정 / 불성실공시 / 거래정지 exclusions).

    from kr_marcap.status import tradable_universe, TradableConfig
    tradable_universe('2015-06-15')                               # defaults
    tradable_universe('2015-06-15', price_min_won=500)            # override
    cfg = TradableConfig(exclude_audit_qualified=False)
    tradable_universe('2015-06-15', config=cfg)

Phase A scope: the four status exclusions read from any *_events.parquet
that kr_status has produced — currently fdr_admin + historical_audit.  The
insincere / halt exclusions are no-ops until Phase B collectors land.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import pandas as pd

from kr_marcap.universe import universe as _base_universe, MARCAP_DIR

EVENTS_PATH = Path(__file__).resolve().parent / "events.parquet"


@dataclass(frozen=True)
class TradableConfig:
    """Tradable-universe filter knobs.  All defaults documented in kr_status/coverage.md."""
    kind:                              str  = "common"
    price_min_won:                   float  = 1000.0       # exclude 동전주
    marcap_min_won:                  float  = 5e10         # 500억
    adv20_min_won:                   float  = 1e8          # 1억 20-day ADV
    exclude_admin:                    bool  = True
    exclude_audit_qualified:          bool  = True
    exclude_insincere:                bool  = True
    exclude_halt:                     bool  = True
    # window (months) within which a past 불성실공시 designation still excludes
    insincere_lookback_months:         int  = 6


# ── events loader ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_events(path: str | None = None) -> pd.DataFrame:
    """Load the merged status-events panel.  Builds it if absent."""
    p = Path(path) if path else EVENTS_PATH
    if not p.exists():
        from kr_marcap.status.build_panel import build_events_panel
        build_events_panel(out_path=p)
    df = pd.read_parquet(p)
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"]   = pd.to_datetime(df["end_date"])
    df["ticker"]     = df["ticker"].astype(str).str.zfill(6)
    return df


def _active_tickers(events: pd.DataFrame, status: str, date: pd.Timestamp,
                    lookback_months: int = 0) -> set[str]:
    """Return tickers whose `status` event window covers `date`.

    A row covers the date when ``start_date - lookback <= date <= end_date``
    (NaT end_date is treated as +∞, meaning "still active as of latest fetch").
    """
    sub = events[events["status"] == status]
    if sub.empty:
        return set()
    start_floor = date - pd.DateOffset(months=lookback_months) if lookback_months else date
    end_filled = sub["end_date"].fillna(pd.Timestamp.max)
    mask = (sub["start_date"] <= start_floor) & (end_filled >= date)
    # Without lookback: standard interval test against `date`.
    # With lookback>0: a row also counts if its start_date is within
    # `lookback_months` before `date`, even if end_date has passed.
    if lookback_months:
        recent_past = (
            (sub["start_date"] >= start_floor)
            & (sub["start_date"] <= date)
        )
        mask = mask | recent_past
    return set(sub.loc[mask, "ticker"].tolist())


# ── marcap row lookup (price / marcap / ADV20) ────────────────────────────────

@lru_cache(maxsize=32)
def _marcap_year(year: int) -> pd.DataFrame:
    fp = MARCAP_DIR / f"marcap-{year}.parquet"
    df = pd.read_parquet(fp, columns=["Code", "Date", "Close", "Marcap", "Amount"])
    df["Code"] = df["Code"].astype(str).str.zfill(6)
    df["Date"] = pd.to_datetime(df["Date"])
    return df


def _marcap_window(end_date: pd.Timestamp, n_calendar_days: int = 40) -> pd.DataFrame:
    """Marcap rows for the last ~n_calendar_days ending at end_date.

    Concatenates two year-parquets if the window straddles Jan 1.
    """
    start = end_date - pd.Timedelta(days=n_calendar_days)
    years = sorted({start.year, end_date.year})
    parts = [_marcap_year(y) for y in years if (MARCAP_DIR / f"marcap-{y}.parquet").exists()]
    if not parts:
        raise FileNotFoundError(
            f"no marcap parquets for year(s) {years} under {MARCAP_DIR}"
        )
    df = pd.concat(parts, ignore_index=True)
    return df.loc[(df["Date"] >= start) & (df["Date"] <= end_date)]


def _liquid_set(date: pd.Timestamp,
                price_min: float, marcap_min: float, adv20_min: float) -> set[str]:
    """Return tickers passing price/marcap/ADV20 floors on `date`.

    Uses the marcap row on `date` (or the latest ≤ date if `date` is non-trading)
    for price/marcap, and the trailing 20 trading days' mean Amount for ADV20.
    Tickers without enough history for the ADV calc are dropped when adv20_min>0.
    """
    win = _marcap_window(date, n_calendar_days=40)
    if win.empty:
        return set()

    # collapse to per-ticker: latest row ≤ date, plus ADV over the window
    win = win.sort_values(["Code", "Date"])

    # latest-on-or-before-date row for each ticker
    on_date = win[win["Date"] <= date]
    if on_date.empty:
        return set()
    idx = on_date.groupby("Code")["Date"].idxmax()
    snap = on_date.loc[idx].set_index("Code")[["Close", "Marcap"]]

    # 20-trading-day mean of Amount per ticker.  We don't know the official
    # exchange calendar here, but every (Code, Date) row in marcap *is* a
    # trading day for that ticker, so simply take the last 20 observations
    # ending at `date`.
    if adv20_min > 0:
        # last 20 dates per ticker within the window
        adv = (
            win.groupby("Code")["Amount"]
               .apply(lambda s: s.tail(20).mean())
               .rename("ADV20")
        )
        snap = snap.join(adv, how="left")
    else:
        snap["ADV20"] = 0.0

    mask = (
        (snap["Close"]  >= price_min)
        & (snap["Marcap"] >= marcap_min)
        & (snap["ADV20"]  >= adv20_min if adv20_min > 0 else True)
    )
    return set(snap.index[mask].tolist())


# ── public API ────────────────────────────────────────────────────────────────

def tradable_universe(date,
                      config: TradableConfig | None = None,
                      **overrides) -> list[str]:
    """Return tradable 6-digit tickers as of `date`.

    Pipeline:
      1. base = kr_marcap.universe(date, kind=config.kind)
      2. ∩ liquid set (Close ≥ price_min, Marcap ≥ marcap_min, ADV20 ≥ adv20_min)
      3. − active status exclusions (admin / audit_qualified / insincere / halt)

    Phase A note: insincere and halt are no-ops until kr_status Phase B
    collectors land — the events panel currently has only admin +
    audit_qualified rows.
    """
    cfg = config or TradableConfig()
    if overrides:
        cfg = replace(cfg, **overrides)

    d = pd.to_datetime(date)
    base = set(_base_universe(d, kind=cfg.kind))
    if not base:
        return []

    liquid = _liquid_set(d, cfg.price_min_won, cfg.marcap_min_won, cfg.adv20_min_won)
    keep = base & liquid

    events = load_events()
    excl: set[str] = set()
    if cfg.exclude_admin:
        excl |= _active_tickers(events, "admin", d)
    if cfg.exclude_audit_qualified:
        excl |= _active_tickers(events, "audit_qualified", d)
    if cfg.exclude_insincere:
        excl |= _active_tickers(events, "insincere", d,
                                lookback_months=cfg.insincere_lookback_months)
    if cfg.exclude_halt:
        excl |= _active_tickers(events, "halt", d)

    return sorted(keep - excl)


if __name__ == "__main__":
    # quick smoke
    for d in ("2010-06-15", "2015-06-15", "2020-06-15", "2025-06-15"):
        tu = tradable_universe(d)
        bu = _base_universe(pd.Timestamp(d), kind="common")
        print(f"{d}  base common={len(bu)}  tradable={len(tu)}  dropped={len(bu) - len(tu)}")
