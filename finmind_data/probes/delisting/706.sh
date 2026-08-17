# Session 2026-08-17, transcript call 706.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python -c "
import pandas as pd
from finmind_data.delisting_sign import features, substitute_error
f = features()
e = substitute_error(f)
g = e.merge(f[['stock_id','delist_date','last_trade','suspension_days']], on='stock_id')
g = g.sort_values('suspension_days')
pd.set_option('display.width', 200)
print(g[['stock_id','stock_name','kind','delist_date','last_trade','suspension_days','last_close','consideration','residual']].to_string(index=False))
print()
sw = g[g['kind']=='swap']
print('swap only, gap vs residual:')
print(sw[['stock_id','suspension_days','residual']].to_string(index=False))
print('  spearman', sw['suspension_days'].corr(sw['residual'], method='spearman'))
print('  pearson ', sw['suspension_days'].corr(sw['residual']))
print('all 6 spearman', g['suspension_days'].corr(g['residual'], method='spearman'))
"
