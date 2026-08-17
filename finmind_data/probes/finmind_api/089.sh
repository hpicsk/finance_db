# Session 2026-08-17, transcript call 89.
# Classify the extra names a per-date sweep would reach
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

python - <<'PY'
import requests, pandas as pd, re
tok = open('.token').read().strip()
r = requests.get('https://api.finmindtrade.com/api/v4/data',
                 params={'dataset':'TaiwanStockInfo','token':tok}, timeout=180)
info = pd.DataFrame(r.json()['data'])
print('TaiwanStockInfo rows', len(info), 'unique ids', info.stock_id.nunique())
u = pd.read_parquet('universe.parquet'); uid=set(u.stock_id.astype(str))
sample = ['1260','1269','1271','1293','1333','1343','1480','1585','1594','1780','2071','0050']
print(info[info.stock_id.isin(sample)][['stock_id','stock_name','type','industry_category']].drop_duplicates().to_string(index=False))
print('\nin info but not universe (4-digit, twse/tpex):')
x = info[(info.type.isin(['twse','tpex'])) & (~info.stock_id.isin(uid)) & (info.stock_id.str.fullmatch(r'\d{4}'))]
print(len(x.stock_id.unique()), 'ids;', x.industry_category.value_counts().head(12).to_string())
PY
