# Session 2026-08-17, transcript call 9.
# Probe TaiwanStockPriceAdj with current token
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

python -c "
import requests
tok = open('.token').read().strip()
r = requests.get('https://api.finmindtrade.com/api/v4/data',
    params={'dataset':'TaiwanStockPriceAdj','data_id':'2330','start_date':'2024-01-01','end_date':'2024-01-31','token':tok}, timeout=60)
print(r.status_code)
print(r.text[:800])
"
