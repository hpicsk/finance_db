# Session 2026-08-17, transcript call 645.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && cp finmind_data/delisting_sign.py /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad/ds2.bak
run() { /home/st/miniconda3/bin/python - <<PY 2>&1 | tail -3
import sys; sys.path.insert(0, "/home/st/research/finance_db")
from finmind_data.test_assertions import $1 as t
try: print("PASS", t()[0][:70])
except AssertionError as e: print("FAIL(as intended):", str(e).split(";")[0][:110])
PY
}
for m in "0.50/0.45" "_GATE_NULL = 0.55/_GATE_NULL = 0.70"; do
  a=${m%%/*}; b=${m##*/}
  sed -i "s|^_DD_SINGLE = $a|_DD_SINGLE = $b|; s|^$a|$b|" finmind_data/delisting_sign.py
  echo "--- mutate: $a -> $b"; run test_taiwan_single_cut_is_registered_unscored
  cp /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad/ds2.bak finmind_data/delisting_sign.py
done
echo "--- mutate: flip a swap ratio in the consideration CSV"
cp finmind_data/delisting_consideration.csv /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad/dc.bak
sed -i 's|3698,隆達,2021-01-06,swap,3714,0.275|3698,隆達,2021-01-06,swap,3714,0.20|' finmind_data/delisting_consideration.csv
run test_taiwan_delisting_substitute_is_biased_low
cp /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad/dc.bak finmind_data/delisting_consideration.csv
echo "--- baseline restored"; run test_taiwan_single_cut_is_registered_unscored; run test_taiwan_delisting_substitute_is_biased_low
