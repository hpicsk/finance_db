# Session 2026-08-17, transcript call 540.
# Resolve the final URL and look for data attributes
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad && curl -sL --max-time 25 "https://www.tpex.org.tw/web/regular_emerging/deListed/de-listed_companies.php?l=zh-tw" -o /dev/null -w "final: %{url_effective}\n" && grep -oE 'data-[a-z-]+="[^"]*"' dl.html | sort -u | head -30
