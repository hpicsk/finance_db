"""kr_status — point-in-time status flags for Korean equities.

Data-gathering scripts for the four status-flag panels the kr_marcap
`tradable_universe()` consumes:

    admin             — 관리종목 designation (entry/exit)
    audit_qualified   — 감사의견 비적정 (한정/부적정/의견거절)
    insincere         — 불성실공시법인 designation
    halt              — 거래정지

Each collector is a standalone CLI (`python -m kr_status.<name>`) that writes
event-long parquets under `kr_status/data/`.  Outputs are consumed by
`kr_marcap.status.build_panel` to produce the daily PIT cube.

See README.md for endpoint docs, schema, and rerun procedure.
"""
from kr_status.schema import (
    STATUS_COLUMNS,
    STATUS_KINDS,
    DATA_DIR,
    events_path,
)

__all__ = ["STATUS_COLUMNS", "STATUS_KINDS", "DATA_DIR", "events_path"]
