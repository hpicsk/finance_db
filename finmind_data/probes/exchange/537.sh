# Session 2026-08-17, transcript call 537.
# Probe TPEx open API for a delisted-companies list
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad && for u in \
 "https://www.tpex.org.tw/openapi/v1/tpex_delisting_companies" \
 "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O" ; do
  echo "=== $u"; curl -s --max-time 25 "$u" | head -c 400; echo; done
