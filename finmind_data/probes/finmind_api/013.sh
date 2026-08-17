# Session 2026-08-17, transcript call 13.
# Test whether FinMind adj matches our TR or PR series
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && python - <<'PY'
import requests, pandas as pd, numpy as np, sys
sys.path.insert(0, '/home/st/research/finance_db')
from finmind_data.adjust import load_adjusted
tok = open('finmind_data/.token').read().strip()

def adj(sid):
    r = requests.get('https://api.finmindtrade.com/api/v4/data',
        params={'dataset':'TaiwanStockPriceAdj','data_id':sid,
                'start_date':'2005-01-01','end_date':'2024-12-31','token':tok}, timeout=120)
    d = pd.DataFrame(r.json()['data'])
    d['date'] = pd.to_datetime(d['date'])
    return d[['date','close']].rename(columns={'close':'fm_adj'})

for sid in ['2330','2317','1101']:
    ours = load_adjusted(sid)
    ours['date'] = pd.to_datetime(ours['date'])
    m = ours.merge(adj(sid), on='date', how='inner')
    m = m[m['is_valid'] & (m['close'] > 0) & m['fm_adj'].notna()]
    # renormalise all three to 1.0 on the last common row
    last = m.iloc[-1]
    for c in ['fm_adj','adj_close_pr','adj_close_tr']:
        m[c+'_n'] = m[c] / last[c]
    m['raw_n'] = m['close'] / last['close']
    dev_tr = (m['fm_adj_n']/m['adj_close_tr_n'] - 1).abs()
    dev_pr = (m['fm_adj_n']/m['adj_close_pr_n'] - 1).abs()
    dev_raw = (m['fm_adj_n']/m['raw_n'] - 1).abs()
    print(f"{sid}: n={len(m)}  median|dev| vs TR={dev_tr.median():.3e}  PR={dev_pr.median():.3e}  raw={dev_raw.median():.3e}")
    print(f"      p95 vs TR={dev_tr.quantile(.95):.3e}  PR={dev_pr.quantile(.95):.3e}")
PY
