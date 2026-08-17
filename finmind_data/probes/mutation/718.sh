# Session 2026-08-17, transcript call 718.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python -c "
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd
import finmind_data.delisting_sign as ds
from finmind_data.test_assertions import test_taiwan_delisting_substitute_is_biased_low as t
real_tv = ds.terminal_value

# label override dropped, but recorded considerations still booked correctly
def no_label_override(f, labels=None):
    x = real_tv(f, labels)
    x['resolved'] = x['sign']
    x['basis'] = np.where(x['sign']=='distress','failed',
                  np.where(x['sign']=='ambiguous','undecided',
                   np.where(x['basis']=='consideration','consideration','substituted')))
    x['terminal'] = np.select(
        [x['basis']=='failed', x['basis']=='consideration', x['basis']=='substituted'],
        [0.0, x['terminal'], x['last_close']], default=np.nan)
    return x
ds.terminal_value = no_label_override
try: t(); print('label override dropped   NOT CAUGHT')
except AssertionError as ex: print('label override dropped   caught:', str(ex)[:95])
ds.terminal_value = real_tv
"
