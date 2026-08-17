# Session 2026-08-17, transcript call 10.
# Probe adj price date range and delisted list
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

python -c "
import requests, pandas as pd
tok = open('.token').read().strip()

def get(ds, **kw):
    p = {'dataset': ds, 'token': tok}; p.update(kw)
    r = requests.get('https://api.finmindtrade.com/api/v4/data', params=p, timeout=90)
    return r.status_code, r.json()

# 1. earliest available date
s, j = get('TaiwanStockPriceAdj', data_id='2330', start_date='1990-01-01', end_date='1999-12-31')
d = pd.DataFrame(j.get('data', []))
print('1990-1999 rows:', len(d), d['date'].min() if len(d) else '')
s, j = get('TaiwanStockPriceAdj', data_id='2330', start_date='2000-01-01', end_date='2005-12-31')
d = pd.DataFrame(j.get('data', []))
print('2000-2005 rows:', len(d), d['date'].min() if len(d) else '')

# 2. delisted stock coverage: pick one from delisted_universe
du = pd.read_parquet('delisted_universe.parquet')
print(du.tail(3).to_string())
" 2>&1 | tail -20
