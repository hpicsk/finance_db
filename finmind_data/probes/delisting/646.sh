# Session 2026-08-17, transcript call 646.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db
run() { /home/st/miniconda3/bin/python - <<PY 2>&1 | tail -2
import sys; sys.path.insert(0, "/home/st/research/finance_db")
from finmind_data.test_assertions import $1 as t
try: print("PASS", t()[0][:65])
except AssertionError as e: print("FAIL(as intended):", str(e).split(";")[0][:105])
PY
}
B=/tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad/ds2.bak
echo "--- mutate: _LONG_SUSPENSION_DAYS 30 -> 60 (moves the registered halt rule)"
sed -i 's|^_LONG_SUSPENSION_DAYS = 30|_LONG_SUSPENSION_DAYS = 60|' finmind_data/delisting_sign.py
run test_taiwan_single_cut_is_registered_unscored
cp $B finmind_data/delisting_sign.py
echo "--- mutate: give the undecided band a terminal value instead of NaN"
sed -i 's|np.where(t\["sign"\] == "merger", t\["last_close"\],\n *np.nan)|X|' finmind_data/delisting_sign.py
python - <<'PY'
import pathlib; p=pathlib.Path("finmind_data/delisting_sign.py"); s=p.read_text()
p.write_text(s.replace('np.where(t["sign"] == "merger", t["last_close"],\n                                      np.nan))',
                       'np.where(t["sign"] == "merger", t["last_close"],\n                                      t["last_close"]))'))
PY
run test_taiwan_delisting_substitute_is_biased_low
cp $B finmind_data/delisting_sign.py; echo "--- restored"; run test_taiwan_delisting_substitute_is_biased_low
