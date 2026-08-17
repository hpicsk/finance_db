# Session 2026-08-17, transcript call 15.
# Check whether adjusted series depends on requested date range
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

python - <<'PY'
import requests, pandas as pd
tok = open('.token').read().strip()
def q(**kw):
    p = {'dataset':'TaiwanStockPriceAdj','data_id':'2330','token':tok}; p.update(kw)
    d = pd.DataFrame(requests.get('https://api.finmindtrade.com/api/v4/data', params=p, timeout=90).json()['data'])
    return d.set_index('date')['close']
a = q(start_date='2024-01-01', end_date='2024-01-31')
b = q(start_date='2005-01-01', end_date='2024-12-31')
c = q(start_date='2005-01-01', end_date='2026-08-16')
print('slice-invariant (short vs 2005-2024):', (a - b.reindex(a.index)).abs().max())
print('slice-invariant (2005-2024 vs to-today):', (b - c.reindex(b.index)).abs().max())
print('last row of full pull:', c.index[-1], c.iloc[-1])
PY
