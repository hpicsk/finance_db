# Session 2026-08-17, transcript call 660.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && B=/tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad
cp finmind_data/delisting_sign.py $B/ds3.bak
sed -i 's|^_GATE_NULL = 0.55|_GATE_NULL = 0.60|' finmind_data/delisting_sign.py
/home/st/miniconda3/bin/python - <<'PY'
import sys; sys.path.insert(0, "/home/st/research/finance_db")
from finmind_data.test_assertions import test_taiwan_single_cut_is_registered_unscored as t
try: print("PASS", t()[0][:60])
except AssertionError as e: print("FAIL(as intended):", str(e).split(".")[0][:110])
PY
cp $B/ds3.bak finmind_data/delisting_sign.py; echo restored
