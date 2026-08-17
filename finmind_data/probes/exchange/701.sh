# Session 2026-08-17, transcript call 701.
# (no description recorded)
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad && curl -s -m 30 "https://www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?type=csv&response=json" -o twse_all.csv && python3 - <<'PY'
import csv, io, re
raw = open("twse_all.csv","rb").read().decode("big5hkscs", errors="replace")
rows = [r for r in csv.reader(io.StringIO(raw)) if len(r) >= 3]
print("header:", rows[0] if not rows[0][0].startswith("民國") else rows[1])
data = [r for r in rows if r[0].startswith("民國")]
def yr(s):
    m = re.match(r"民國(\d+)年", s); return int(m.group(1)) + 1911 if m else None
years = sorted(y for y in (yr(r[0]) for r in data) if y)
print(f"rows: {len(data)}   years: {years[0]} .. {years[-1]}")
print("in 2005-2024:", sum(1 for y in years if 2005 <= y <= 2024))
print("columns per row:", sorted(set(len(r) for r in data)))
print("\noldest 3:", [(r[0], r[1], r[2]) for r in data[-3:]])
print("newest 3:", [(r[0], r[1], r[2]) for r in data[:3]])
PY
