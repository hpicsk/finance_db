# Session 2026-08-17, transcript call 541.
# Query the TPEx delisted API
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad && for u in \
 "https://www.tpex.org.tw/www/zh-tw/mainboard/listed/delisted?response=json" \
 "https://www.tpex.org.tw/www/zh-tw/mainboard/listed/delisted?startDate=20060101&endDate=20081231&response=json" ; do
 echo "=== $u"; curl -s --max-time 30 "$u" | head -c 600; echo; echo; done
