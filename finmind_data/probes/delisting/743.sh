# Session 2026-08-17, transcript call 743.
# Print all 38 labels with sources
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python - <<'PY'
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 90)
l = pd.read_csv("finmind_data/delisting_labels.csv", dtype={"stock_id": str})
print(l[["stock_id","stock_name","delist_date","drawdown","suspension_days","sign","label","source"]].to_string(index=False))
PY
