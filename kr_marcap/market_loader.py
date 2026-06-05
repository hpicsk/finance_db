"""Survivorship-bias-free, split-adjusted Korean OHLCV/market-cap loader.

Drop-in replacement for ``fnguide_data.market_loader.load_market_data``: same
positional signature, same output schema (``date, ticker, close, volume,
market_cap, listed_shares``), so downstream pipeline code is unchanged.

Why this exists
---------------
The FnGuide ``currently_listed/`` Excel exports are a snapshot taken at the
export date. Stocks that were trading historically but delisted between the
data window and the export date silently disappear — a look-ahead survivorship
bias. marcap stores a per-date KRX snapshot for every year, so each historical
date carries every stock that was actually listed and trading on that date.

Sources
-------
- ``$QF_MARCAP_DIR/marcap-{YYYY}.parquet`` — raw OHLCV+Marcap+Stocks per day.
- ``$QF_KR_MARCAP_DIR/cache/adj_factors.parquet`` — ChangesRatio (등락률) back-
  adjustment factors built by ``kr_marcap.adjust``. Used to back-adjust ``Close``
  for splits / 무상·유상증자 / 감자, putting marcap on par with FnGuide's 수정주가;
  the ``valid`` column drops pre-series-break (e.g. pre-SPAC-merger) history.
- ``$QF_KR_MARCAP_DIR/cache/universe_panel.parquet`` — point-in-time common-
  stock membership built by ``kr_marcap.universe``. Used to drop preferred,
  ETFs, REITs, SPACs, KONEX, and funds (matches the implicit universe of the
  current pipeline).

If the kr_marcap caches are missing or stale, rebuild via::

    python -m kr_marcap.universe build
    python -m kr_marcap.adjust build
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import pandas as pd


_MARCAP_COLS = ("Date", "Code", "Open", "High", "Low", "Close",
                "Volume", "Amount", "Marcap", "Stocks")


def _read_year(marcap_dir: Path, year: int) -> pd.DataFrame:
    f = marcap_dir / f"marcap-{year}.parquet"
    if not f.exists():
        raise FileNotFoundError(f"marcap year file missing: {f}")
    return pd.read_parquet(f, columns=list(_MARCAP_COLS))


def _cache_is_fresh(cache_file: Path, source_files: Iterable[Path]) -> bool:
    if not cache_file.exists():
        return False
    cache_mtime = cache_file.stat().st_mtime
    for s in source_files:
        if s.exists() and s.stat().st_mtime > cache_mtime:
            return False
    return True


def _check_kr_marcap_caches(kr_marcap_root: Path,
                            year_files: list[Path]) -> tuple[Path, Path]:
    factors = kr_marcap_root / "cache" / "adj_factors.parquet"
    panel = kr_marcap_root / "cache" / "universe_panel.parquet"
    for f in (factors, panel):
        if not f.exists():
            raise FileNotFoundError(
                f"kr_marcap cache missing: {f}. "
                f"Build with: python -m kr_marcap.universe build "
                f"&& python -m kr_marcap.adjust build"
            )
    newest_year = max((p.stat().st_mtime for p in year_files if p.exists()),
                      default=0)
    for f, builder in ((factors, "kr_marcap.adjust"),
                       (panel, "kr_marcap.universe")):
        if f.stat().st_mtime + 1 < newest_year:
            raise RuntimeError(
                f"{f} is older than marcap parquets — rebuild with "
                f"`python -m {builder} build` before running the pipeline"
            )
    return factors, panel


def load_market_data(
    tickers: Iterable[str] | None,
    start_date: str,
    end_date: str,
    *,
    marcap_dir: str | os.PathLike,
    kr_marcap_root: str | os.PathLike,
    cache_dir: str | os.PathLike | None = None,
    drop_zero_volume: bool = True,
) -> pd.DataFrame:
    """Load Korean common-stock OHLCV from marcap with split adjustment.

    Parameters
    ----------
    tickers
        Optional whitelist of ``"A"``-prefixed tickers (e.g. ``"A005930"``).
        ``None`` returns the full common-stock universe for each day.
    start_date, end_date
        ``YYYY-MM-DD``.
    marcap_dir
        Directory containing ``marcap-YYYY.parquet`` files.
    kr_marcap_root
        Root of ``kr_marcap`` so we can read ``cache/adj_factors.parquet`` and
        ``cache/universe_panel.parquet``.
    cache_dir
        If given, the assembled frame for the window is cached as parquet and
        rebuilt only when an upstream file is newer than the cache.
    drop_zero_volume
        When True (default), filter out rows with ``Volume <= 0`` — matches the
        original FnGuide-replacement semantics. Pass False when the caller
        needs the full OHLCV history including 거래정지 / no-trade days
        (e.g. fn_shared's wide-format build).

    Returns
    -------
    DataFrame with columns and dtypes::

        date           datetime64[ns]
        ticker         object    ("A"-prefixed, 7 chars)
        open           float64   (KRW, RAW — multiply by cum_factor to adjust)
        high           float64   (KRW, RAW)
        low            float64   (KRW, RAW)
        close          float64   (KRW, split-adjusted)
        volume         float64   (shares, scaled so close × volume is continuous)
        amount         float64   (KRW traded, RAW — adjustment not meaningful)
        market_cap     float64   (KRW; marcap's Marcap column is already
                                  in KRW despite what its README claims —
                                  verified close × stocks == Marcap exactly)
        listed_shares  int64
        cum_factor     float64   (split-adjustment multiplier; raw_close *
                                  cum_factor == adjusted close)

    Only rows with ``kind == 'common'`` are returned. ``Volume > 0`` is also
    required by default; pass ``drop_zero_volume=False`` to retain no-trade
    days.
    """
    marcap_dir = Path(marcap_dir)
    kr_marcap_root = Path(kr_marcap_root)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)

    year_files = [marcap_dir / f"marcap-{y}.parquet"
                  for y in range(start.year, end.year + 1)]
    factors_file, panel_file = _check_kr_marcap_caches(kr_marcap_root, year_files)

    upstream = year_files + [factors_file, panel_file]

    cache_file: Path | None = None
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"market_marcap_{start.date()}_{end.date()}.parquet"
        if _cache_is_fresh(cache_file, upstream):
            out = pd.read_parquet(cache_file)
            if tickers is not None:
                out = out[out["ticker"].isin(set(tickers))].reset_index(drop=True)
            return out

    frames = [_read_year(marcap_dir, y) for y in range(start.year, end.year + 1)]
    df = pd.concat(frames, ignore_index=True)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df[(df["Date"] >= start) & (df["Date"] <= end)]
    if drop_zero_volume:
        df = df[df["Volume"] > 0]
    df["Code"] = df["Code"].astype(str).str.zfill(6)

    panel = pd.read_parquet(panel_file)
    panel = panel[panel["kind"] == "common"][["code", "first_date", "last_date"]]
    panel["first_date"] = pd.to_datetime(panel["first_date"])
    panel["last_date"] = pd.to_datetime(panel["last_date"])
    df = df.merge(panel, left_on="Code", right_on="code", how="inner")
    df = df[(df["Date"] >= df["first_date"]) & (df["Date"] <= df["last_date"])]
    df = df.drop(columns=["code", "first_date", "last_date"])

    factors = pd.read_parquet(
        factors_file, columns=["date", "code", "cum_factor", "valid"])
    factors["date"] = pd.to_datetime(factors["date"])
    factors["code"] = factors["code"].astype(str).str.zfill(6)
    df = df.merge(factors, left_on=["Date", "Code"], right_on=["date", "code"],
                  how="left").drop(columns=["date", "code"])
    df["cum_factor"] = df["cum_factor"].fillna(1.0)
    # Drop pre-relisting history (e.g. a SPAC shell's prices before a merger),
    # flagged valid=False by kr_marcap.adjust. Rows with no factor row default
    # to valid.
    df = df[df["valid"].fillna(True)].drop(columns=["valid"])

    out = pd.DataFrame({
        "date": df["Date"].values,
        "ticker": ("A" + df["Code"]).values,
        "open": df["Open"].astype("float64").values,
        "high": df["High"].astype("float64").values,
        "low": df["Low"].astype("float64").values,
        "close": (df["Close"].astype("float64") * df["cum_factor"]).values,
        "volume": (df["Volume"].astype("float64") / df["cum_factor"]).values,
        "amount": df["Amount"].astype("float64").values,
        "market_cap": df["Marcap"].astype("float64").values,
        "listed_shares": df["Stocks"].astype("int64").values,
        "cum_factor": df["cum_factor"].astype("float64").values,
    })
    out = out.sort_values(["date", "ticker"]).reset_index(drop=True)

    if cache_file is not None:
        out.to_parquet(cache_file, index=False)

    if tickers is not None:
        out = out[out["ticker"].isin(set(tickers))].reset_index(drop=True)

    return out
