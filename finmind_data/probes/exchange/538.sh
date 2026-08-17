# Session 2026-08-17, transcript call 538.
# Probe TPEx for a terminated-listing dataset
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad && for u in \
 "https://www.tpex.org.tw/www/zh-tw/company/terminate" \
 "https://www.tpex.org.tw/web/regular_emerging/deListed/de-listed_companies.php?l=zh-tw" \
 "https://www.tpex.org.tw/openapi/v1/tpex_company_terminate" ; do
  echo "=== $u"; curl -sL --max-time 25 "$u" -o t.out -w "%{http_code} %{size_download}\n"; file t.out; head -c 300 t.out; echo; echo; done
