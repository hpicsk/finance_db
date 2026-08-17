# Session 2026-08-17, transcript call 625.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python - <<'PY'
import pandas as pd
from finmind_data.delisting_sign import features
f = features()
lab = pd.read_csv("finmind_data/delisting_labels.csv", dtype={"stock_id": str})
band = f[f["sign"] == "ambiguous"]
print("band size:", len(band))
m = band.merge(lab[["stock_id","label","purpose"]], on="stock_id", how="left")
lb = m[m["label"].notna() & (m["label"] != "")]
print("labelled in band:", len(lb), "| unlabelled:", len(m) - len(lb))
print(lb["purpose"].value_counts().to_dict())
lb = lb.assign(above=lb["drawdown"] > 0.50)
print(pd.crosstab(lb["above"], lb["label"]))
print("majority class among labelled band:", lb["label"].value_counts().to_dict())
print()
print("unlabelled band names:")
print(m[m["label"].isna() | (m["label"] == "")][["stock_id","stock_name","drawdown","corroborated","needs_lookup"]].sort_values("drawdown").to_string(index=False))
PY
