# Session 2026-08-17, transcript call 724.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python -c "
import sys; sys.path.insert(0,'.')
import numpy as np
import finmind_data.delisting_sign as ds
from finmind_data.test_assertions import test_taiwan_delisting_substitute_is_biased_low as t
real_tv = ds.terminal_value
def one_fewer(f, labels=None):
    x = real_tv(f, labels); i = x.index[x['basis']=='undecided'][0]
    x.loc[i,['basis','terminal']] = ['substituted', x.loc[i,'last_close']]; return x
ds.terminal_value = one_fewer
try: t(); print('count 12 -> 11   NOT CAUGHT')
except AssertionError as ex: print('count 12 -> 11   caught:', str(ex)[:92])
"
