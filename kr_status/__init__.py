"""kr_status — DART collectors for Korean equities.

Each collector is a standalone CLI (`python -m kr_status.<name>`) that writes
one parquet under `kr_status/data/`:

    dart_audit         — 감사의견, one row per (ticker, bsns_year), FY2015+
    dart_corp_actions  — 증자 / 감자 / 합병 / 분할 / 주식교환 filings

See README.md for endpoint docs and rerun procedure.
"""
