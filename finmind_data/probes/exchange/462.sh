# Session 2026-08-17, transcript call 462.
# Probe TWSE delisted-company CSV endpoint
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad && for u in \
 "https://www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?REQ_OPT=CSV&type=csv&yy=113&response=csv" \
 "https://www.twse.com.tw/company/suspendListingCsvAndHtml?REQ_OPT=CSV&type=csv&yy=113" ; do
  echo "=== $u"
  curl -s -m 20 -o out.bin -w "http=%{http_code} bytes=%{size_download} ctype=%{content_type}\n" "$u"
  head -c 400 out.bin | iconv -f BIG5 -t UTF-8 2>/dev/null || head -c 400 out.bin
  echo; echo
done
