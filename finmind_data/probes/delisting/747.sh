# Session 2026-08-17, transcript call 747.
# Cross-tabulate deal form against band membership
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python - <<'PY'
import pandas as pd
from scipy.stats import fisher_exact
from finmind_data.delisting_sign import features, band_holdout, _LABEL_FILE

f = features()
l = pd.read_csv(_LABEL_FILE, dtype={"stock_id": str})
l = l[l["label"].fillna("") != ""]
m = l[l["label"] == "merger"].drop(columns=["sign"]).merge(
        f[["stock_id", "sign", "drawdown"]], on="stock_id", suffixes=("_lbl", ""))
m["in_band"] = m["sign"] == "ambiguous"
m["form"] = m["form"].fillna("unstated")
print(pd.crosstab(m["in_band"], m["form"], margins=True))
tab = [[int((m.in_band & (m.form=="swap")).sum()), int((m.in_band & (m.form=="cash")).sum())],
       [int((~m.in_band & (m.form=="swap")).sum()), int((~m.in_band & (m.form=="cash")).sum())]]
print("2x2 stated-form only:", tab, "fisher p =", round(fisher_exact(tab)[1], 3))
print("\ndrawdown by form:")
print(m.groupby("form")["drawdown"].agg(["count", "min", "median", "max"]).round(3))
hold = band_holdout(f, l)
print("\nheld-out 12 — halt rule:", hold["halt_call"].value_counts().to_dict(),
      "| 0.50 cut:", hold["call"].value_counts().to_dict())
PY
