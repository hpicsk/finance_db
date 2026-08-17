# Session 2026-08-17, transcript call 659.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && sed -i 's|        _DD_SINGLE, _GATE_MIN_LABELS, band_holdout, features, gate_threshold,|        _DD_SINGLE, _GATE_MIN_LABELS, _GATE_NULL, band_holdout, features,\n        gate_threshold,|' finmind_data/test_assertions.py && /home/st/miniconda3/bin/python - <<'PY'
import sys; sys.path.insert(0, "/home/st/research/finance_db")
from finmind_data.test_assertions import test_taiwan_single_cut_is_registered_unscored as t
print("PASS:", t()[0])
PY
