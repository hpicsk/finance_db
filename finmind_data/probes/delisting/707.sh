# Session 2026-08-17, transcript call 707.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python -c "
import pandas as pd, numpy as np
from finmind_data.delisting_sign import features, substitute_error, _price
f = features()
e = substitute_error(f)
g = e.merge(f[['stock_id','delist_date','last_trade','suspension_days']], on='stock_id')
c = pd.read_csv('finmind_data/delisting_consideration.csv', dtype={'stock_id':str,'successor':str})
c['per_share']=c['per_share'].astype(float)
g = g.merge(c[['stock_id','successor','per_share']], on='stock_id')
rows=[]
for r in g.itertuples():
    if r.kind!='swap': 
        rows.append((r.stock_id, r.stock_name, np.nan, np.nan)); continue
    p=_price(r.successor)
    s_last = p[p['date']<=r.last_trade]['close'].iloc[-1]
    s_del  = p[p['date']<=r.delist_date]['close'].iloc[-1]
    parity_at_last = r.per_share*s_last/r.last_close - 1     # deal discount at last trade
    succ_ret = s_del/s_last - 1                              # acquirer move over the gap
    rows.append((r.stock_id, r.stock_name, parity_at_last, succ_ret))
d = pd.DataFrame(rows, columns=['stock_id','stock_name','discount','succ_ret'])
g = g.merge(d[['stock_id','discount','succ_ret']], on='stock_id')
pd.set_option('display.width',200)
print(g[['stock_id','stock_name','kind','suspension_days','residual','discount','succ_ret']].to_string(index=False,
      float_format=lambda x: f'{x:+.4f}'))
sw=g[g['kind']=='swap']
print()
print('swap: median residual %+.3f = discount %+.3f x succ_ret %+.3f' % (sw.residual.median(), sw.discount.median(), sw.succ_ret.median()))
print('swap: |discount| median %.3f  |succ_ret| median %.3f' % (sw.discount.abs().median(), sw.succ_ret.abs().median()))
print('swap: discount>0 on', int((sw.discount>0).sum()), 'of', len(sw), ' succ_ret>0 on', int((sw.succ_ret>0).sum()))
print()
print('gap distribution across the whole priced population:')
print(f['suspension_days'].describe().to_string())
print()
m=f[f['sign']=='merger']
print('merger-shaped only, n=%d:'%len(m))
print(m['suspension_days'].value_counts().sort_index().head(20).to_string())
"
