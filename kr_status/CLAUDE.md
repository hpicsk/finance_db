# Claude notes for kr_status

Per-source point-in-time event collectors for KRX status flags. Each writes one
parquet to `kr_status/data/`, independent of the others;
`kr_marcap.status.build_panel` unifies them.

## Canonical source mapping for the status flags

`STATUS_KINDS = ("admin", "audit_qualified", "insincere", "halt", "alert")`
in `schema.py`.

- `halt`, `admin`, `alert` → `marcap_halt_infer.py`. Halt is
  `marcap.ChangeCode == "0"` (KRX's own daily flag — not the older
  `(Volume==0) & (Open==0)` inference). Admin / alert are
  `marcap.Dept.str.contains("관리종목")` / `("투자주의환기")`.
- `audit_qualified` → `dart_audit.py` (DART filings) + historical seed from
  the kr_delisted CSV via `fdr_collect.py --seed-historical`.
- `insincere` → `dart_insincere.py` (DART filings).

FDR `KRX-ADMINISTRATIVE` snapshots and per-corp DART 관리종목 harvests were
retired — `marcap.Dept` is the authoritative admin source. Don't reintroduce
them without checking with the user.

## The halt mask is tuned for KOSPI + KOSDAQ

KONEX rows are collected and kept filterable (`market == 'KONEX'`) but are not
the analysis target. The `ChangeCode == "0"` halt mask optimizes for
KOSPI+KOSDAQ accuracy; the older `(Volume==0) & (Open==0)` inference it
replaced over-counted KONEX no-trade days.
