# Session 2026-08-17, transcript call 745.
# List every labelled payout with its band membership and source text
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python - <<'PY'
import pandas as pd, re
from finmind_data.delisting_sign import features, band_holdout, _LABEL_FILE

f = features()
l = pd.read_csv(_LABEL_FILE, dtype={"stock_id": str})
l = l[l["label"].fillna("") != ""]
m = l[l["label"] == "merger"].merge(f[["stock_id","sign"]], on="stock_id",
                                    suffixes=("_lbl",""))
print("labelled payouts:", len(m))
for r in m.itertuples():
    print(f"  {r.stock_id} {r.sign:9s} dd={r.drawdown_lbl if hasattr(r,'drawdown_lbl') else r.drawdown:.3f} | {r.source}")
PY
