# Session 2026-08-17, transcript call 612.
# Show every labelled name against its prediction
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python -c "
import pandas as pd
from finmind_data.delisting_sign import features
f=features()
l=pd.read_csv('finmind_data/delisting_labels.csv',dtype={'stock_id':str})
m=l.merge(f[['stock_id','sign','stratum','drawdown']],on='stock_id',suffixes=('_c',''))
m=m.sort_values('drawdown')
for r in m.itertuples():
    mark='' if r.sign=='ambiguous' else ('OK ' if r.sign==r.label else 'MISS')
    print(f'{r.stock_id} {r.stock_name:8s} dd={r.drawdown:.3f} {r.stratum:8s} pred={r.sign:9s} true={r.label:8s} {mark} [{r.purpose}]')
" 2>&1 | grep -v 'terminate called\|Aborted\|core dumped'
