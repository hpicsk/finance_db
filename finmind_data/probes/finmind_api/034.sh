# Session 2026-08-17, transcript call 34.
# Re-probe previously paid-only endpoints at sponsor tier
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

python - <<'PY'
import requests
tok = open('.token').read().strip()
for ds, kw in [('TaiwanStockHoldingSharesPer', {'data_id':'2330'}),
               ('TaiwanStockConvertibleBondInfo', {}),
               ('TaiwanStockConvertibleBondDaily', {'data_id':'23301'}),
               ('TaiwanStockConvertibleBondDailyOverview', {}),
               ('TaiwanStockConvertibleBondInstitutionalInvestors', {'data_id':'23301'})]:
    p = {'dataset': ds, 'token': tok, 'start_date':'2024-01-01','end_date':'2024-01-31'}; p.update(kw)
    r = requests.get('https://api.finmindtrade.com/api/v4/data', params=p, timeout=60)
    try: j = r.json(); n = len(j.get('data', [])); msg = j.get('msg','')[:80]
    except Exception: n, msg = -1, r.text[:80]
    print(f'{ds:52s} HTTP {r.status_code}  rows={n:5d}  {msg}')
PY
