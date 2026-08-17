# Session 2026-08-17, transcript call 725.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python -c "
import sys; sys.path.insert(0,'.')
import pandas as pd
from finmind_data.delisting_sign import features, substitute_error
f = features()
e = substitute_error(f).merge(f[['stock_id','sign','drawdown']], on='stock_id')
pd.set_option('display.width',200)
print(e[['stock_id','stock_name','kind','sign','drawdown','gap','overlap','residual']].to_string(index=False, float_format=lambda x: f'{x:.3f}'))
"
