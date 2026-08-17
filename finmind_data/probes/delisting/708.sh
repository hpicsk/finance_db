# Session 2026-08-17, transcript call 708.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python -c "
import pandas as pd, numpy as np
from finmind_data.delisting_sign import features, substitute_error, _price
f = features()
e = substitute_error(f)
g = e.merge(f[['stock_id','delist_date','last_trade','suspension_days']], on='stock_id')
c = pd.read_csv('finmind_data/delisting_consideration.csv', dtype={'stock_id':str,'successor':str})
g = g.merge(c[['stock_id','successor','per_share']], on='stock_id')
for r in g.itertuples():
    if r.kind!='swap': continue
    p=_price(r.successor)
    print(r.stock_id, r.stock_name, '-> successor', r.successor,
          'first session', p['date'].min().date(),
          '| target last trade', r.last_trade.date(),
          '| delist', r.delist_date.date(),
          '| sessions before target last trade:', int((p['date']<=r.last_trade).sum()))
" 2>&1 | tail -10
