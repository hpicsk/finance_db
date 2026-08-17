# Session 2026-08-17, transcript call 544.
# Inspect the page form and try a POST query
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad && grep -oE '<(input|select)[^>]{0,200}' dl2.html | head -20 && echo "=== try POST:" && curl -s --max-time 30 -X POST "https://www.tpex.org.tw/www/zh-tw/mainboard/listed/delisted" -d "date=2006/01/01&cate=&response=json" -H "X-Requested-With: XMLHttpRequest" | head -c 500
