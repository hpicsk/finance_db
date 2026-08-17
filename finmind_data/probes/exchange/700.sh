# Session 2026-08-17, transcript call 700.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad && echo "--- csv, no year:" && curl -s -m 25 "https://www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?type=csv&response=json" | head -6
echo "--- csv,民國 year 96 (=2007):" && curl -s -m 25 "https://www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?type=csv&year=96&response=json" | head -5
echo "--- csv, year=113 (=2024):" && curl -s -m 25 "https://www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?type=csv&year=113&response=json" | head -5
