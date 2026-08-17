# Session 2026-08-17, transcript call 717.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python -c "
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd
import finmind_data.delisting_sign as ds
from finmind_data.test_assertions import test_taiwan_delisting_substitute_is_biased_low as t

real_tv, real_cons = ds.terminal_value, ds.considerations

# 1. terminal_value ignores labels (the old sign-only behaviour)
def sign_only(f, labels=None):
    x = f[['stock_id','stock_name','delist_date','sign','last_close']].copy()
    x['terminal'] = np.where(x['sign']=='distress', 0.0,
                     np.where(x['sign']=='merger', x['last_close'], np.nan))
    x['basis'] = x['sign'].map({'distress':'failed','merger':'substituted','ambiguous':'undecided'})
    x['resolved'] = x['sign']
    return x
ds.terminal_value = sign_only
try: t(); print('1 sign-only          NOT CAUGHT')
except AssertionError as ex: print('1 sign-only          caught:', str(ex).split(';')[0][:70])
ds.terminal_value = real_tv

# 2. a swap successor that traded before the target's last trade
def fake_overlap(f):
    c = real_cons(f); c.loc[c['kind']=='swap','overlap'] = 5; return c
ds.considerations = fake_overlap
try: t(); print('2 acquirer overlap   NOT CAUGHT')
except AssertionError as ex: print('2 acquirer overlap   caught:', str(ex).split(';')[0][:70])
ds.considerations = real_cons

# 3. consideration name booked at last close instead of what was paid
def cons_at_last_close(f, labels=None):
    x = real_tv(f, labels)
    hit = x['basis']=='consideration'
    x.loc[hit,'terminal'] = x.loc[hit,'last_close']
    return x
ds.terminal_value = cons_at_last_close
try: t(); print('3 booked last close  NOT CAUGHT')
except AssertionError as ex: print('3 booked last close  caught:', str(ex).split(';')[0][:70])
ds.terminal_value = real_tv
print()
print('unmutated:', t()[0][:60], '...')
"
