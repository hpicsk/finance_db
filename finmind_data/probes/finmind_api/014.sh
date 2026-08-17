# Session 2026-08-17, transcript call 14.
# Check universe size and probe user_info for rate limit
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

python - <<'PY'
import requests, pandas as pd
tok = open('.token').read().strip()
u = pd.read_parquet('universe.parquet')
print('universe:', len(u), 'cols', list(u.columns))
print(u.head(3).to_string())
import os
print('ohlcv files:', len(os.listdir('ohlcv')), ' div_result:', len(os.listdir('div_result')))
for url in ['https://api.finmindtrade.com/api/v4/user_info',
            'https://api.web.finmindtrade.com/v2/user_info',
            'https://api.finmindtrade.com/v4/user_info']:
    try:
        r = requests.get(url, params={'token': tok}, timeout=20)
        print(url, r.status_code, r.text[:300])
    except Exception as e:
        print(url, 'ERR', e)
PY
