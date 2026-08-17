# Session 2026-08-17, transcript call 86.
# Probe TaiwanStockPriceAdj without data_id
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

python - <<'PY'
import requests, pandas as pd, time
tok = open('.token').read().strip()
U = 'https://api.finmindtrade.com/api/v4/data'

# 1. no data_id, one day
t=time.time()
r = requests.get(U, params={'dataset':'TaiwanStockPriceAdj','start_date':'2024-01-02','end_date':'2024-01-02','token':tok}, timeout=180)
print('no data_id, 1 day :', r.status_code, end=' ')
try:
    j=r.json(); d=pd.DataFrame(j.get('data',[]))
    print(f'rows={len(d)} stocks={d.stock_id.nunique() if len(d) else 0} {time.time()-t:.1f}s  msg={j.get("msg","")[:60]}')
except Exception as e: print('ERR', r.text[:200])

# 2. no data_id, one month
t=time.time()
r = requests.get(U, params={'dataset':'TaiwanStockPriceAdj','start_date':'2024-01-01','end_date':'2024-01-31','token':tok}, timeout=300)
print('no data_id, 1 month:', r.status_code, end=' ')
try:
    j=r.json(); d=pd.DataFrame(j.get('data',[]))
    print(f'rows={len(d)} stocks={d.stock_id.nunique() if len(d) else 0} dates={d.date.nunique() if len(d) else 0} {time.time()-t:.1f}s')
except Exception as e: print('ERR', r.text[:200])
PY
