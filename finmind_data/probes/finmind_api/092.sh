# Session 2026-08-17, transcript call 92.
# Verify per-date bulk matches per-stock files
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

python - <<'PY'
import requests, pandas as pd, glob, os
tok = open('.token').read().strip()
U='https://api.finmindtrade.com/api/v4/data'
r = requests.get(U, params={'dataset':'TaiwanStockPriceAdj','start_date':'2018-06-15','token':tok}, timeout=120)
bulk = pd.DataFrame(r.json()['data']).set_index('stock_id')['close']
have = [os.path.basename(p)[:-8] for p in glob.glob('price_adj/*.parquet')]
n=0; bad=[]
for sid in have[:500]:
    d = pd.read_parquet(f'price_adj/{sid}.parquet')
    if 'date' not in d.columns or not len(d): continue
    row = d[d['date']=='2018-06-15']
    if len(row) and sid in bulk.index:
        n+=1
        if abs(float(row['close'].iloc[0]) - float(bulk[sid])) > 1e-9: bad.append(sid)
print(f'compared {n} stocks on 2018-06-15: {len(bad)} mismatches {bad[:5]}')
PY
