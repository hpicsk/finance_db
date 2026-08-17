# Session 2026-08-17, transcript call 465.
# Probe TWSE HTML/JSON variants and TPEx openapi
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad
echo "=== TWSE HTML variant ==="
curl -s -m 20 "https://www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?REQ_OPT=HTML&type=html&yy=113" | iconv -f BIG5 -t UTF-8 2>/dev/null | head -c 600
echo; echo "=== TWSE JSON variant ==="
curl -s -m 20 "https://www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?response=json&yy=113" | head -c 500
echo; echo "=== TPEx openapi list ==="
curl -s -m 20 "https://www.tpex.org.tw/openapi/v1/" | python -c "import sys,json;d=json.load(sys.stdin);print(len(d));[print(k) for k in list(d)[:5]]" 2>/dev/null || curl -s -m 20 "https://www.tpex.org.tw/openapi/v1/" | head -c 300
