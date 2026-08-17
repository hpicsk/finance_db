# Session 2026-08-17, transcript call 21.
# Inspect vendor series at series break and on no-trade sessions
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && python - <<'PY'
import requests, pandas as pd, numpy as np
tok = open('finmind_data/.token').read().strip()
def fm(sid, s='2005-01-01', e='2024-12-31'):
    r = requests.get('https://api.finmindtrade.com/api/v4/data',
      params={'dataset':'TaiwanStockPriceAdj','data_id':sid,'start_date':s,'end_date':e,'token':tok}, timeout=120)
    d = pd.DataFrame(r.json()['data']); d['date']=pd.to_datetime(d['date']); return d.sort_values('date')

a = fm('2357'); raw = pd.read_parquet('finmind_data/ohlcv/2357.parquet'); raw['date']=pd.to_datetime(raw['date'])
print('2357 adj span', a.date.min().date(), a.date.max().date(), len(a))
print('2357 raw span', raw.date.min().date(), raw.date.max().date(), len(raw))
m = a.merge(raw[['date','close']], on='date', suffixes=('_adj','_raw'))
m['ratio'] = m.close_adj/m.close_raw
print('2357 factor either side of 2010-06-24:')
print(m[(m.date>=pd.Timestamp('2010-06-15'))&(m.date<=pd.Timestamp('2010-06-30'))][['date','close_raw','close_adj','ratio']].to_string(index=False))

# 8934: what does the vendor put on a no-trade session?
a8 = fm('8934'); r8 = pd.read_parquet('finmind_data/ohlcv/8934.parquet'); r8['date']=pd.to_datetime(r8['date'])
m8 = a8.merge(r8[['date','close','Trading_Volume']], on='date', suffixes=('_adj','_raw'))
z = m8[m8.close_raw==0]
print('\n8934 no-trade rows: n=%d, adj close min/max = %.4f / %.4f, volume max %d'
      % (len(z), z.close_adj.min(), z.close_adj.max(), z.Trading_Volume.max()))
print(z[['date','close_raw','close_adj','Trading_Volume']].head(6).to_string(index=False))
PY
