# Session 2026-08-17, transcript call 463.
# Fetch full TWSE delisted list, inspect columns and span
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad && curl -s -m 20 "https://www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?REQ_OPT=CSV&type=csv&yy=113" | iconv -f BIG5 -t UTF-8 > twse_delist.csv
echo "rows: $(wc -l < twse_delist.csv)"
echo "--- header ---"; sed -n '1,3p' twse_delist.csv
echo "--- last 5 ---"; tail -5 twse_delist.csv
echo "--- year span (ROC) ---"; grep -o '民國[0-9]*年' twse_delist.csv | sort -u | head -3; echo ...; grep -o '民國[0-9]*年' twse_delist.csv | sort -u | tail -3
