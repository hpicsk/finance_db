# Session 2026-08-17, transcript call 723.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python -c "
import sys; sys.path.insert(0,'.')
import pandas as pd
import finmind_data.delisting_sign as ds
from finmind_data.test_assertions import test_taiwan_delisting_substitute_is_biased_low as t
real = pd.read_csv
pd.read_csv = lambda p,*a,**k: (real(p,*a,**k).assign(label='') if str(p).endswith('delisting_labels.csv') else real(p,*a,**k))
try: t()
except AssertionError as ex: print('FULL:', str(ex))
pd.read_csv = real
" 2>&1 | tail -5
