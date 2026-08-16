"""Reconstructed adjusted-price loader — both conventions, whole panel.

``kr_marcap.adjust.load_adjusted`` returns one ticker with its full OHLCV;
this returns just the two adjusted-close conventions for every ticker at once,
which is what panel research and the FnGuide benchmark actually read:

| Column | Convention | FnGuide equivalent |
|---|---|---|
| ``adj_close``    | price return — capital changes only     | 수정주가 (``S410000700``) |
| ``adj_close_tr`` | total return — cash dividends reinvested | 수정주가(현금배당포함) (``S410007700``) |

``adj_close`` is read from ``cache/adj_factors.parquet`` as built (the compounded
등락률 series), **not** recomputed as ``raw_close × cum_factor`` — the two differ
on no-trade rows, where ``cum_factor`` is undefined.

``adj_close_tr`` reproduces ``adjust._apply_total_return`` over the whole panel
at once rather than per ticker: each SEIBro cash event is reinvested on its
배당락일 at that session's close, ``1 + dps/close``, events sharing a session
multiply, and the result is normalised to 1 on the ticker's last row exactly as
the per-ticker loader does. The two agree to 3.6e-15 on the shared panel; the
vectorised form exists because the per-ticker path is a Python loop over ~3,900
tickers. Any change to the reinvestment rule must land in both (repo CLAUDE.md
§5, atomic propagation).

This is the *reconstruction*, not the research input. Panels for research read
FnGuide's series via ``fnguide_data.price_loader.load_price_panel``; how close
this gets to it is measured in ``kr_marcap.validate_against_fnguide`` and
written up in ``CONSTRUCTION.md``. Don't mix the two in one panel.

Usage:
    from kr_marcap.adjusted_loader import load_adjusted_panel
    px = load_adjusted_panel()   # date, code, raw_close, adj_close, adj_close_tr, sess
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from kr_marcap.adjust import FACTORS_PATH
from kr_marcap.dividend_events import load_cash_events


def load_adjusted_panel(factors_path: Path = FACTORS_PATH,
                        events_path: Path | None = None,
                        tickers: set[str] | None = None) -> pd.DataFrame:
    """Both adjusted-price conventions for the whole panel, from the factors file.

    Columns: ``date, code, raw_close, adj_close, adj_close_tr, sess``. ``sess``
    is the ticker's session ordinal, so a consumer that merges against another
    source knows how many marcap sessions a pair of its rows spans.

    Rows flagged ``valid=False`` — pre-series-break history belonging to a
    different economic entity — are dropped, matching what ``load_adjusted``
    serves and what the current listing carries at the vendors.
    """
    fac = pd.read_parquet(factors_path,
                          columns=["date", "code", "raw_close", "adj_close", "valid"])
    fac["date"] = pd.to_datetime(fac["date"])
    fac["code"] = fac["code"].astype(str).str.zfill(6)
    if tickers is not None:
        fac = fac[fac["code"].isin(tickers)]
    fac = (fac[fac["valid"] & (fac["adj_close"] > 0)]
           .drop(columns="valid")
           .sort_values(["code", "date"])
           .reset_index(drop=True))

    ev = load_cash_events(events_path)[["code", "ex_date", "dps"]]
    ev = ev.rename(columns={"ex_date": "date"})
    e = ev.merge(fac[["code", "date", "raw_close"]], on=["code", "date"], how="inner")
    e = e[e["raw_close"] > 0].copy()
    e["step"] = 1.0 + e["dps"] / e["raw_close"]
    day_step = e.groupby(["code", "date"])["step"].prod().rename("step")

    fac = fac.merge(day_step, on=["code", "date"], how="left")
    fac["step"] = fac["step"].fillna(1.0)
    # A ticker's first row carries no return for the bump to offset.
    fac.loc[~fac["code"].duplicated(), "step"] = 1.0
    tr = fac.groupby("code", sort=False)["step"].cumprod()
    fac["adj_close_tr"] = fac["adj_close"] * tr / tr.groupby(fac["code"]).transform("last")
    fac["sess"] = fac.groupby("code", sort=False).cumcount()
    return fac.drop(columns="step")
