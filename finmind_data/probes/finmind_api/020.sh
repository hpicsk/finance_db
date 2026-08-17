# Session 2026-08-17, transcript call 20.
# Check vendor handling of no-trade rows and unpriced 2010 reduction
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && python - <<'PY'
import requests, pandas as pd, numpy as np, sys
sys.path.insert(0,'/home/st/research/finance_db')
tok = open('finmind_data/.token').read().strip()
def fm(sid):
    r = requests.get('https://api.finmindtrade.com/api/v4/data',
      params={'dataset':'TaiwanStockPriceAdj','data_id':sid,'start_date':'2005-01-01','end_date':'2024-12-31','token':tok}, timeout=120)
    d = pd.DataFrame(r.json()['data']); d['date']=pd.to_datetime(d['date']); return d

# 8934: does the vendor keep FinMind's close==0 no-trade encoding?
raw = pd.read_parquet('finmind_data/ohlcv/8934.parquet'); raw['date']=pd.to_datetime(raw['date'])
a = fm('8934')
print('8934 raw rows', len(raw), 'zero-close raw', int((raw.close==0).sum()))
print('8934 adj rows', len(a), 'zero-close adj', int((a.close==0).sum()))
z = set(raw.loc[raw.close==0,'date']); print('  zero dates present in adj:', len(z & set(a.date)))

# 2357: the 2010-06-24 unpriced 85% cancellation — does the vendor price it?
a = fm('2357'); a=a.sort_values('date')
w = a[(a.date>=pd.Timestamp('2010-06-18'))&(a.date<=pd.Timestamp('2010-07-01'))]
print('\n2357 around 2010-06-24 (vendor adj close):'); print(w[['date','close']].to_string(index=False))
r2 = pd.read_parquet('finmind_data/ohlcv/2357.parquet'); r2['date']=pd.to_datetime(r2['date'])
w2 = r2[(r2.date>=pd.Timestamp('2010-06-18'))&(r2.date<=pd.Timestamp('2010-07-01'))]
print('2357 raw close:'); print(w2[['date','close']].to_string(index=False))
PY
