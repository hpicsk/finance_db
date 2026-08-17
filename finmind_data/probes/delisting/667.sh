# Session 2026-08-17, transcript call 667.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python - <<'PY'
import sys; sys.path.insert(0, "/home/st/research/finance_db")
from finmind_data.test_assertions import (
    test_taiwan_single_cut_is_registered_unscored as t1,
    test_taiwan_delisting_substitute_is_biased_low as t2,
    test_taiwan_delisting_sign_accuracy as t3,
    test_taiwan_delisting_sign_sample_is_preregistered as t4)
for t in (t4, t3, t1, t2):
    m, n = t(); print(f"PASS [n={n}] {m}")
PY
