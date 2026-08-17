# Session 2026-08-17, transcript call 711.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python -c "
import pandas as pd, numpy as np
from finmind_data.delisting_sign import features
f = features()
lab = pd.read_csv('finmind_data/delisting_labels.csv', dtype={'stock_id':str})
lab = lab[lab['label'].fillna('')!='']
print('labels filled:', len(lab), lab['label'].value_counts().to_dict())
print('by purpose:', lab['purpose'].value_counts().to_dict())
m = f.merge(lab[['stock_id','label']], on='stock_id', how='left')
print()
print('crosstab sign x label:')
print(pd.crosstab(m['sign'], m['label'].fillna('(none)')).to_string())
res = np.where(m['label'].notna(), m['label'], m['sign'])
print()
print('resolved:', pd.Series(res).value_counts().to_dict())
cons = pd.read_csv('finmind_data/delisting_consideration.csv', dtype={'stock_id':str})
print('consideration rows:', len(cons), 'all payout-resolved:', set(pd.Series(res)[m['stock_id'].isin(cons['stock_id'])]))
"
