# Session 2026-08-17, transcript call 641.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && timeout 280 /home/st/miniconda3/bin/python - <<'PY' 2>&1 | tail -8
import pandas as pd
from pathlib import Path
from finmind_data.delisting_sign import features
H = Path("finmind_data")
f = features(); pay = set(f.loc[f["sign"]=="merger","stock_id"])
first, last = {}, {}
for p in H.glob("ohlcv/*.parquet"):
    sid = p.stem
    if not (sid.isdigit() and len(sid)==4): continue
    try: d = pd.to_datetime(pd.read_parquet(p, columns=["date"])["date"])
    except Exception: continue
    if len(d): first[sid], last[sid] = d.min(), d.max()
fs = pd.Series(first).sort_values()
alive = {s for s,v in last.items() if v >= pd.Timestamp("2024-12-01")}
hits = [r.stock_id for r in f[f["sign"]=="merger"].itertuples()
        if [s for s in fs[(fs >= r.delist_date - pd.Timedelta(days=30)) &
                          (fs <= r.delist_date + pd.Timedelta(days=30))].index
            if s in alive and s not in pay]]
print(f"payout-classified: {len(pay)}")
print(f"  a still-trading code first listed within 30d of the delisting: {len(hits)}")
print(f"  no such code: {len(pay)-len(hits)}")
PY
