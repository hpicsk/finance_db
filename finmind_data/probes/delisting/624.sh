# Session 2026-08-17, transcript call 624.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

/home/st/miniconda3/bin/python - <<'PY'
import pandas as pd
from finmind_data.delisting_sign import features, _DD_DISTRESS, _DD_MERGER
import sys
sys.path.insert(0, "/home/st/research/finance_db")
f = features()
lab = pd.read_csv("delisting_labels.csv", dtype={"stock_id": str})
band = f[f["sign"] == "ambiguous"]
print("band size:", len(band))
m = band.merge(lab[["stock_id","label","purpose"]], on="stock_id", how="left")
print("labelled in band:", m["label"].notna().sum())
print(m["purpose"].value_counts(dropna=False))
lb = m[m["label"].notna()]
lb = lb.assign(side=lb["drawdown"] > 0.50)
print(pd.crosstab(lb["side"], lb["label"]))
print("unlabelled in band:", (m["label"].isna()).sum())
print("majority class in band (labelled):", lb["label"].value_counts(normalize=True).to_dict())
PY
