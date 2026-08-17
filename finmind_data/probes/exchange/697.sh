# Session 2026-08-17, transcript call 697.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad && for u in \
 "https://www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?type=html&year=2007&response=json" \
 "https://www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?year=2007&response=json"; do
 echo "--- $u"; curl -s -m 25 "$u" | head -c 600; echo; done
