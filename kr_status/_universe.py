"""Shared working universe loader for the DART collectors."""

from pathlib import Path
import pandas as pd

DELISTING_CSV = Path(__file__).parent / ".." / "kr_delisted" / "data" / "delisting_calendar.csv"


def load_working_universe(include_dates: bool = False) -> pd.DataFrame:
    """Load the working universe of live and delisted Korean common stocks.

    Parameters
    ----------
    include_dates : bool, default False
        If True, include first_date and last_date columns from universe_panel.
        If False, return only ticker and name (suitable for quick lookups).

    Returns
    -------
    DataFrame with columns:
        - ticker, name (always)
        - first_date, last_date (if include_dates=True)
    """
    panel_path = Path(__file__).resolve().parents[0] / ".." / "kr_marcap" / "cache" / "universe_panel.parquet"
    # Both halves are required: without one the universe shrinks, and every
    # collector reading it silently skips the missing tickers.
    if not panel_path.exists():
        raise FileNotFoundError(
            f"{panel_path} not found — build it with python -m kr_marcap.universe build")
    if not DELISTING_CSV.exists():
        raise FileNotFoundError(
            f"{DELISTING_CSV} not found — it is tracked in kr_delisted; restore it from git")
    rows: list[dict] = []
    cols = ["code", "name", "kind"]
    if include_dates:
        cols.extend(["first_date", "last_date"])
    p = pd.read_parquet(panel_path, columns=cols)
    live = p[p["kind"] == "common"]
    renamed = live.rename(columns={"code": "ticker"})
    keep_cols = ["ticker", "name", "first_date", "last_date"] if include_dates else ["ticker", "name"]
    rows.extend(renamed[keep_cols].to_dict("records"))
    d = pd.read_csv(DELISTING_CSV, dtype={"ticker": str})
    d["ticker"] = d["ticker"].str.zfill(6)
    if include_dates:
        d["delisting_date"] = pd.to_datetime(d["delisting_date"])
        for _, r in d.iterrows():
            rows.append({
                "ticker":     r["ticker"],
                "name":       r["name"],
                "first_date": pd.NaT,
                "last_date":  r["delisting_date"],
            })
    else:
        rows.extend(d[["ticker", "name"]].to_dict("records"))
    return pd.DataFrame(rows).drop_duplicates("ticker").reset_index(drop=True)
