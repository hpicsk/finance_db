# Session 2026-08-17, transcript call 741.
# Print the 12 with observables
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python - <<'PY'
import pandas as pd
from finmind_data.delisting_sign import features, band_holdout, _LABEL_FILE

f = features()
labels = pd.read_csv(_LABEL_FILE, dtype={"stock_id": str})
hold = band_holdout(f, labels)
print(list(hold.columns))
h = hold[["stock_id"]].merge(f, on="stock_id")
pd.set_option("display.width", 200)
print(h[["stock_id","stock_name","delist_date","drawdown","suspension_days",
         "tail_sessions","shared_date","long_suspension","corroborated"]]
      .sort_values("drawdown").to_string(index=False))
PY
