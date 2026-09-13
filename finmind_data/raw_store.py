"""The raw store: what the vendor answered, as it answered it, by the day asked.

``raw/<vintage>/<name>/<year>.parquet``: one directory per sweep, named by the
day it started; under it one directory per dataset and one file per calendar
year of the dates asked for, plus ``manifest.json`` recording per (name, year)
the dates asked and answered, the rows, and when. Nothing under a vintage is
edited after the sweep that wrote it. A later sweep is a later vintage beside
it, and a difference between two is a fact about the vendor, which is the reason
for keeping both.

    from finmind_data.raw_store import Vintage, vintages
    v = Vintage("2026-09-13")
    v.read("ohlcv", columns=["date", "stock_id", "close"])
    v.dates("ohlcv")                 # the sessions that vintage answered for
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .paths import RAW

_VINTAGE = re.compile(r"\d{4}-\d{2}-\d{2}")


def vintages() -> list[str]:
    """Every vintage the store holds, oldest first."""
    if not RAW.exists():
        return []
    return sorted(p.name for p in RAW.iterdir() if p.is_dir() and _VINTAGE.fullmatch(p.name))


class Vintage:
    def __init__(self, vintage: str):
        if not _VINTAGE.fullmatch(vintage):
            raise ValueError(f"a vintage is the day its sweep started, YYYY-MM-DD, not {vintage!r}")
        self.name = vintage
        self.root = RAW / vintage

    def __repr__(self) -> str:
        return f"Vintage({self.name!r})"

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    def manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {}
        return json.loads(self.manifest_path.read_text())

    def record(self, key: str, entry: dict) -> None:
        m = self.manifest()
        m[key] = entry
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")

    def path(self, name: str, year: int | str) -> Path:
        return self.root / name / f"{year}.parquet"

    def files(self, name: str) -> list[Path]:
        d = self.root / name
        return sorted(d.glob("*.parquet")) if d.exists() else []

    def read(self, name: str, columns: list[str] | None = None) -> pd.DataFrame:
        """Every row the vintage holds for `name`. Raises where it holds none:
        an absent dataset read as an empty frame is the silent answer this
        store exists to refuse."""
        files = [f for f in self.files(name) if pq.ParquetFile(f).metadata.num_rows]
        if not files:
            raise FileNotFoundError(f"{self.root / name} holds no rows; sweep it first")
        return pd.concat([pd.read_parquet(f, columns=columns) for f in files],
                         ignore_index=True)

    def dates(self, name: str) -> list[str]:
        """The dates `name` answered at least one row for, sorted."""
        return sorted(self.read(name, columns=["date"])["date"].unique())
