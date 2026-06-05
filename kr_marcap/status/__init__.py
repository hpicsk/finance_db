"""Consumer-side projection of kr_status event tables into a tradable universe.

Layers:
  build_panel — concat kr_status/data/*_events.parquet → events.parquet
  query       — TradableConfig + tradable_universe(date) using events.parquet
                plus marcap rows for price/marcap/ADV filters
"""
from kr_marcap.status.query import (
    TradableConfig,
    tradable_universe,
    load_events,
)

__all__ = [
    "TradableConfig",
    "tradable_universe",
    "load_events",
]
