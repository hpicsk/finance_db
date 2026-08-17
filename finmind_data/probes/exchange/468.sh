# Session 2026-08-17, transcript call 468.
# Check TWSE HTML for reason column and probe TPEx
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad
echo "=== TWSE HTML, looking for a reason column ==="
curl -s -m 20 "https://www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?REQ_OPT=HTML&type=html&yy=113" -o h.html
python - <<'EOF'
import re,html
s=open('h.html',encoding='utf-8',errors='replace').read()
ths=re.findall(r'<th[^>]*>(.*?)</th>',s,re.S)
print('table headers:', [html.unescape(re.sub('<[^>]+>','',t)).strip() for t in ths][:12])
print('len(html)=',len(s), '| mentions 原因/事由:', ('原因' in s) or ('事由' in s))
EOF
echo; echo "=== TPEx delisted (終止上櫃) ==="
for u in "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O" "https://www.tpex.org.tw/www/zh-tw/company/delisted" "https://www.tpex.org.tw/web/regular_emerging/deListed/de-listed_companies.php?l=zh-tw"; do
  echo "-- $u"; curl -sL -m 20 -o t.bin -w "http=%{http_code} bytes=%{size_download} ctype=%{content_type}\n" "$u"; head -c 200 t.bin; echo
done
