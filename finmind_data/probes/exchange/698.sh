# Session 2026-08-17, transcript call 698.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad && curl -s -m 30 "https://www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?type=html&year=2007&response=json" > twse2007.html && python3 - <<'PY'
import re, html
s = open("twse2007.html", encoding="utf-8").read()
rows = re.findall(r"<tr>(.*?)</tr>", s, re.S)
print("rows:", len(rows))
for r in rows[:6]:
    cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
    print(" | ".join(cells)[:220])
PY
