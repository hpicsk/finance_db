# Session 2026-08-17, transcript call 803.
# Extract and bucket the substantive commands
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

mkdir -p /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad/probes && /home/st/miniconda3/bin/python - <<'PY'
import json, re, os
T="/home/st/.claude/projects/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2.jsonl"
OUT="/tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad/probes"
cmds=[]
for line in open(T):
    try: r=json.loads(line)
    except Exception: continue
    m=r.get("message") or {}
    cont=m.get("content")
    if not isinstance(cont, list): continue
    for c in cont:
        if isinstance(c,dict) and c.get("type")=="tool_use" and c.get("name")=="Bash":
            cmds.append((c["input"].get("command",""), c["input"].get("description","")))

def cat(c):
    if re.search(r"twse\.com\.tw|tpex\.org\.tw", c): return "exchange_probe"
    if re.search(r"finmindtrade\.com", c): return "finmind_api_probe"
    if re.search(r"NOT CAUGHT|shutil\.copy\(BAK", c): return "mutation_test"
    if re.search(r"delisting_sign|substitute_error|band_holdout|terminal_value|delisting_labels|delisting_band", c): return "delisting_analysis"
    return None

buckets={}
for i,(c,d) in enumerate(cmds):
    k = cat(c)
    if k and len(c) > 300:
        buckets.setdefault(k, []).append((i, d, c))
for k, items in buckets.items():
    print(f"{k}: {len(items)} commands, {sum(len(c) for _,_,c in items):,} chars")
# token safety: no literal token anywhere
bad = [i for k,v in buckets.items() for i,_,c in v
       if re.search(r"token\s*=\s*['\"][A-Za-z0-9_.\-]{20,}", c)]
print("commands with a literal token:", bad)
json.dump({k:[{"idx":i,"desc":d,"cmd":c} for i,d,c in v] for k,v in buckets.items()},
          open(os.path.join(OUT,"raw.json"),"w"), ensure_ascii=False, indent=1)
print("wrote raw.json")
PY
