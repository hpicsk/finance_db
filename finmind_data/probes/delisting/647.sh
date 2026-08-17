# Session 2026-08-17, transcript call 647.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db
run() { /home/st/miniconda3/bin/python - <<PY 2>&1 | tail -2
import sys; sys.path.insert(0, "/home/st/research/finance_db")
from finmind_data.test_assertions import $1 as t
try: print("PASS", t()[0][:60])
except AssertionError as e: print("FAIL(as intended):", str(e).split(";")[0][:100])
PY
}
B=/tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad/ds2.bak
for v in 100 300; do
  sed -i "s|^_LONG_SUSPENSION_DAYS = 30|_LONG_SUSPENSION_DAYS = $v|" finmind_data/delisting_sign.py
  echo "--- _LONG_SUSPENSION_DAYS 30 -> $v"; run test_taiwan_single_cut_is_registered_unscored
  cp $B finmind_data/delisting_sign.py
done
echo "--- halt-flag margin: how far can the constant move before a call flips?"
/home/st/miniconda3/bin/python - <<'PY'
import sys, pandas as pd; sys.path.insert(0,"/home/st/research/finance_db")
b = pd.read_csv("/home/st/research/finance_db/finmind_data/delisting_band.csv", dtype={"stock_id":str})
from finmind_data.delisting_sign import features
f = features(); m = b.merge(f[["stock_id","suspension_days","has_tail"]], on="stock_id")
print(sorted(m.loc[~m["has_tail"], "suspension_days"]))
PY
