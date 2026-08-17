# Session 2026-08-17, transcript call 628.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python - <<'PY'
import pandas as pd
from finmind_data.delisting_sign import features
f = features()
b = pd.read_csv("finmind_data/delisting_band.csv", dtype={"stock_id": str})
m = b.merge(f[["stock_id","has_tail","long_suspension","shared_date","suspension_days","tail_sessions"]], on="stock_id")
print(m[["stock_id","stock_name","drawdown","call","has_tail","long_suspension","shared_date","suspension_days","tail_sessions"]].to_string(index=False))
# and on the 20 already-labelled band names: does corroboration predict the label?
lab = pd.read_csv("finmind_data/delisting_labels.csv", dtype={"stock_id": str})
lb = f[f["sign"]=="ambiguous"].merge(lab[["stock_id","label"]], on="stock_id")
lb = lb[lb["label"].fillna("") != ""]
print("\nlabelled band, corroboration vs truth:")
for col in ["has_tail","long_suspension","shared_date"]:
    print(col); print(pd.crosstab(lb[col], lb["label"]))
PY
