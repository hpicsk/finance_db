# Session 2026-08-17, transcript call 709.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python -c "
import pandas as pd, numpy as np
from finmind_data.delisting_sign import features
f = features()
m = f[f['sign']=='merger']
print('merger-shaped n=%d, suspension_days:' % len(m))
print('  median %.0f  IQR %.0f..%.0f  min %d max %d' % (m.suspension_days.median(),
      m.suspension_days.quantile(.25), m.suspension_days.quantile(.75),
      m.suspension_days.min(), m.suspension_days.max()))
print('  share in 7..14 days: %d of %d (%.0f%%)' % ((m.suspension_days.between(7,14)).sum(), len(m),
      100*(m.suspension_days.between(7,14)).mean()))
print()
print('  full distribution:')
print(m['suspension_days'].value_counts().sort_index().to_string())
"
