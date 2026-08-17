# Session 2026-08-17, transcript call 11.
# Probe delisted-stock coverage in adj endpoint
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

python - <<'PY'
import requests, pandas as pd, numpy as np
tok = open('.token').read().strip()
def get(ds, **kw):
    p = {'dataset': ds, 'token': tok}; p.update(kw)
    r = requests.get('https://api.finmindtrade.com/api/v4/data', params=p, timeout=90)
    return r.status_code, r.json()

# delisted coverage probe
for sid in ['9915','9932','9188']:
    s,j = get('TaiwanStockPriceAdj', data_id=sid, start_date='2000-01-01', end_date='2024-12-31')
    d = pd.DataFrame(j.get('data',[]))
    print('delisted', sid, s, 'rows', len(d), (d['date'].min(), d['date'].max()) if len(d) else '')
PY
