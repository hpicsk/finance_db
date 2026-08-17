# Session 2026-08-17, transcript call 88.
# Measure universe coverage gain from a per-date sweep
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

python - <<'PY'
import requests, pandas as pd, time, re
tok = open('.token').read().strip()
U = 'https://api.finmindtrade.com/api/v4/data'
u = pd.read_parquet('universe.parquet'); uid = set(u.stock_id.astype(str))
dates = ['2005-03-15','2006-09-20','2008-05-14','2010-03-10','2012-06-13','2014-08-20',
         '2016-04-13','2018-10-17','2020-07-15','2022-03-16','2024-05-15','2024-12-30']
allids, per = set(), []
t0=time.time()
for dt in dates:
    r = requests.get(U, params={'dataset':'TaiwanStockPriceAdj','start_date':dt,'token':tok}, timeout=120)
    d = pd.DataFrame(r.json().get('data',[]))
    ids = set(d.stock_id.astype(str)) if len(d) else set()
    allids |= ids
    extra = ids - uid
    extra4 = {i for i in extra if re.fullmatch(r'\d{4}', i)}
    per.append((dt, len(ids), len(extra), len(extra4)))
print(f'{len(dates)} dates in {time.time()-t0:.1f}s ({(time.time()-t0)/len(dates):.2f}s/req)')
print(f"{'date':12s} {'names':>6s} {'not in universe':>15s} {'of those 4-digit':>17s}")
for row in per: print(f'{row[0]:12s} {row[1]:6d} {row[2]:15d} {row[3]:17d}')
extra = allids - uid
extra4 = sorted(i for i in extra if re.fullmatch(r'\d{4}', i))
print(f'\nunion over the 12 dates: {len(allids)} names, {len(extra)} outside universe.parquet')
print(f'  of them 4-digit (would-be commons): {len(extra4)} -> {extra4[:25]}')
print(f'  universe ids never seen on these dates: {len(uid - allids)}')
PY
