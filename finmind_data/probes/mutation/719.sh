# Session 2026-08-17, transcript call 719.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python -c "
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd
import finmind_data.delisting_sign as ds
from finmind_data.test_assertions import test_taiwan_delisting_substitute_is_biased_low as t
real_tv = ds.terminal_value

# A. one labelled name books against its own label (1613: label distress, shape merger)
def flip_1613(f, labels=None):
    x = real_tv(f, labels); i = x['stock_id']=='1613'
    x.loc[i,'basis']='substituted'; x.loc[i,'terminal']=x.loc[i,'last_close']
    return x
ds.terminal_value = flip_1613
try: t(); print('A label ignored on 1613  NOT CAUGHT')
except AssertionError as ex: print('A label ignored on 1613  caught:', str(ex)[:88])
ds.terminal_value = real_tv

# B. the undecided set is a different set of the same size
def swap_one(f, labels=None):
    x = real_tv(f, labels)
    out = x.index[x['basis']=='undecided'][0]
    into = x.index[x['basis']=='substituted'][0]
    x.loc[out,['basis','terminal']]=['substituted', x.loc[out,'last_close']]
    x.loc[into,['basis','terminal']]=['undecided', np.nan]
    return x
ds.terminal_value = swap_one
try: t(); print('B undecided set swapped  NOT CAUGHT')
except AssertionError as ex: print('B undecided set swapped  caught:', str(ex)[:88])
ds.terminal_value = real_tv
print('unmutated still passes:', t()[1], 'deals')
"
