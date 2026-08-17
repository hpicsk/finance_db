# Session 2026-08-17, transcript call 640.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && timeout 280 /home/st/miniconda3/bin/python - <<'PY' 2>&1 | tail -25
import pandas as pd
from pathlib import Path
from finmind_data.delisting_sign import features
H = Path("finmind_data")
f = features()
pay = f[f["sign"] == "merger"]
# first session of every 4-digit code in the panel
first = {}
for p in H.glob("ohlcv/*.parquet"):
    sid = p.stem
    if not sid.isdigit() or len(sid) != 4: continue
    d = pd.read_parquet(p, columns=["date"])
    if len(d): first[sid] = pd.to_datetime(d["date"]).min()
fs = pd.Series(first).sort_values()
alive = {s for s in fs.index
         if pd.read_parquet(H/f"ohlcv/{s}.parquet", columns=["date"])["date"].max() >= "2024-12-01"}
hits = 0
for r in pay.itertuples():
    near = fs[(fs >= r.delist_date - pd.Timedelta(days=30)) &
              (fs <= r.delist_date + pd.Timedelta(days=30))]
    near = [s for s in near.index if s in alive and s not in set(pay["stock_id"])]
    if near: hits += 1
print(f"payout-classified names: {len(pay)}")
print(f"  with a still-trading code first listed within 30d of the delisting: {hits}")
print(f"  without: {len(pay) - hits}")
PY
