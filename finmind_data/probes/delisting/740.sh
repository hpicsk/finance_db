# Session 2026-08-17, transcript call 740.
# Print the 12 held-out band names with their observables
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python - <<'PY'
import pandas as pd, numpy as np
from pathlib import Path
from finmind_data.delisting_sign import features, band_holdout, _LABEL_FILE, HERE

f = features()
labels = pd.read_csv(_LABEL_FILE, dtype={"stock_id": str})
hold = band_holdout(f, labels)
print("held-out band names:", len(hold))
print(hold[["stock_id","stock_name","delist_date","drawdown","suspension_days",
            "tail_sessions","shared_date","long_suspension"]].to_string(index=False))
PY
