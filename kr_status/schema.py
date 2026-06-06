"""Shared schema constants for kr_status event tables.

All per-source collectors write parquet files matching STATUS_COLUMNS so the
downstream consumer (kr_marcap.status.build_panel) can concatenate them
without per-source casing.
"""
from __future__ import annotations

from pathlib import Path

STATUS_COLUMNS = [
    "ticker",        # str, 6-char zero-padded (e.g. "001470")
    "status",        # one of STATUS_KINDS
    "start_date",    # pd.Timestamp — designation/halt/qualified date
    "end_date",      # pd.Timestamp or NaT — release date if known
    "source",        # provenance string: "fdr_admin", "dart_admin", "kind_audit_rejected", ...
    "fetched_at",    # pd.Timestamp — when the row was collected
    "detail",        # str — raw reason / opinion code / halt cause
]

STATUS_KINDS = ("admin", "audit_qualified", "insincere", "halt", "alert")

DATA_DIR = Path(__file__).resolve().parent / "data"


def events_path(name: str) -> Path:
    """Standard event-parquet path for a collector source name."""
    return DATA_DIR / f"{name}_events.parquet"
