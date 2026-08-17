# Session 2026-08-17, transcript call 22.
# Inspect factor step at 2357 reduction and 8934 no-trade fill
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && python - <<'PY'
import requests, pandas as pd, numpy as np
tok = open('finmind_data/.token').read().strip()
def fm(sid):
    r = requests.get('https://api.finmindtrade.com/api/v4/data',
      params={'dataset':'TaiwanStockPriceAdj','data_id':sid,'start_date':'2005-01-01','end_date':'2024-12-31','token':tok}, timeout=120)
    d = pd.DataFrame(r.json()['data']); d['date']=pd.to_datetime(d['date']); return d.sort_values('date')

a = fm('2357'); raw = pd.read_parquet('finmind_data/ohlcv/2357.parquet'); raw['date']=pd.to_datetime(raw['date'])
m = a.merge(raw[['date','close']], on='date', suffixes=('_adj','_raw'))
m['f'] = m.close_adj/m.close_raw
i = m.index[m.date==pd.Timestamp('2010-06-24')][0]
print('2357 factor rows', i-3, '..', i+2)
print(m.loc[i-3:i+2, ['date','close_raw','close_adj','f']].to_string(index=False))
print('factor step at the reduction:', m.f.iloc[i]/m.f.iloc[i-1])

a8 = fm('8934'); r8 = pd.read_parquet('finmind_data/ohlcv/8934.parquet'); r8['date']=pd.to_datetime(r8['date'])
m8 = a8.merge(r8[['date','close','Trading_Volume']].rename(columns={'Trading_Volume':'vol_raw'}), on='date', suffixes=('_adj','_raw'))
z = m8[m8.close_raw==0]
print('\n8934 no-trade rows n=%d; vendor adj close range %.4f..%.4f; raw volume max %d'
      % (len(z), z.close_adj.min(), z.close_adj.max(), z.vol_raw.max()))
print(z[['date','close_raw','close_adj','vol_raw']].head(5).to_string(index=False))
PY
