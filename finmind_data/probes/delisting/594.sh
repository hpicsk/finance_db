# Session 2026-08-17, transcript call 594.
# Inspect the drawn label sample
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

/home/st/miniconda3/bin/python -c "
import pandas as pd
l=pd.read_csv('delisting_labels.csv',dtype={'stock_id':str})
print(l.shape, '| purpose:', l.purpose.value_counts().to_dict())
print('era:', l.era.value_counts().to_dict())
print('stratum:', l.stratum.value_counts().to_dict())
print()
print(l[['stock_id','stock_name','delist_date','drawdown','sign','stratum','era','purpose']].to_string(index=False))
" 2>&1 | grep -v 'terminate called\|Aborted\|core dumped'
