# Session 2026-08-17, transcript call 87.
# Probe bulk calling conventions
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

python - <<'PY'
import requests, pandas as pd, time
tok = open('.token').read().strip()
U = 'https://api.finmindtrade.com/api/v4/data'
def probe(label, params, timeout=300):
    p = {'dataset':'TaiwanStockPriceAdj','token':tok}; p.update(params)
    t=time.time()
    try: r = requests.get(U, params=p, timeout=timeout)
    except Exception as e: print(f'{label:44s} EXC {e}'); return
    try:
        j=r.json(); d=pd.DataFrame(j.get('data',[]))
        print(f'{label:44s} {r.status_code} rows={len(d):8,} stocks={d.stock_id.nunique() if len(d) else 0:5} '
              f'dates={d.date.nunique() if len(d) else 0:5} {time.time()-t:6.1f}s  {j.get("msg","")[:40]}')
    except Exception:
        print(f'{label:44s} {r.status_code} {r.text[:120]}')

probe('start only, no end, no data_id',   {'start_date':'2024-01-02'})
probe('2-day range, no data_id',          {'start_date':'2024-01-02','end_date':'2024-01-03'})
probe('same start==end, no data_id',      {'start_date':'2024-01-03','end_date':'2024-01-03'})
probe('no dates at all, no data_id',      {})
probe('comma data_id',                    {'data_id':'2330,2317','start_date':'2024-01-02','end_date':'2024-01-05'})
PY
