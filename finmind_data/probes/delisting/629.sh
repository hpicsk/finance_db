# Session 2026-08-17, transcript call 629.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python - <<'PY'
import numpy as np, pandas as pd
from finmind_data.delisting_sign import features
f = features(); lab = pd.read_csv("finmind_data/delisting_labels.csv", dtype={"stock_id": str})
lb = f[f["sign"]=="ambiguous"].merge(lab[["stock_id","label"]], on="stock_id")
lb = lb[lb["label"].fillna("") != ""].copy()
lb["dd50"]  = np.where(lb["drawdown"] <= 0.50, "distress", "merger")
lb["halt"]  = np.where(lb["has_tail"] | lb["long_suspension"], "distress", "merger")
lb["both"]  = np.where(lb["has_tail"] | lb["long_suspension"], "distress", lb["dd50"])
for r in ["dd50", "halt", "both"]:
    print(f"{r:5s} on the labelled 20: {(lb[r]==lb['label']).sum()}/20")
b = pd.read_csv("finmind_data/delisting_band.csv", dtype={"stock_id": str}).merge(
    f[["stock_id","has_tail","long_suspension"]], on="stock_id")
b["halt"] = np.where(b["has_tail"] | b["long_suspension"], "distress", "merger")
print("\nheld-out 12, where the two rules disagree:")
print(b.loc[b["call"] != b["halt"], ["stock_id","stock_name","drawdown","call","halt"]].to_string(index=False))
print("\nhalt-rule calls on the 12:", b["halt"].value_counts().to_dict())
PY
