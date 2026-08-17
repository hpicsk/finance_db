# Session 2026-08-17, transcript call 543.
# Locate the TPEx delisted data endpoint
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad && curl -s --max-time 25 "https://www.tpex.org.tw/zh-tw/mainboard/listed/delisted.html" -o dl2.html -w "%{http_code} %{size_download}\n" && grep -oE 'url[^,;]{0,120}' dl2.html | head -20 && echo "=== main.js hints:" && curl -s --max-time 25 "https://www.tpex.org.tw/rsrc/js/main.js" | grep -oE '"/www/[^"]{5,90}"' | sort -u | head -30
