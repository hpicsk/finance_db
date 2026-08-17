# Session 2026-08-17, transcript call 699.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad && for y in 2005 2010 2015 2020 2023 2024 2025; do
 curl -s -m 25 "https://www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?type=html&year=$y&response=json" -o "t$y.html"
 python3 -c "
import re,html,sys
s=open('t$y.html',encoding='utf-8').read()
rows=re.findall(r'<tr>(.*?)</tr>',s,re.S)
cells=[[html.unescape(re.sub(r'<[^>]+>','',c)).strip() for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>',r,re.S)] for r in rows]
data=[c for c in cells if len(c)>=3 and re.match(r'^\d',c[0] or '')]
hdr=[c for c in cells if c and c[0].startswith('終止上市日期')]
print(f'$y: data rows={len(data)}  cols={hdr[0] if hdr else cells}')
if data: print('     e.g.', ' | '.join(data[0]))
"
done
