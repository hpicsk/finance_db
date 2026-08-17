# Session 2026-08-17, transcript call 600.
# Register population and run the finmind suite
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python -c "
import json,sys
p='finmind_data/populations.json'
d=json.load(open(p))
d['test_taiwan_delisting_sign_sample_is_preregistered']={'bound':'exact','n':172}
json.dump(dict(sorted(d.items())),open(p,'w'),indent=2)
open(p,'a').write('\n')
print('added')
" && /home/st/miniconda3/bin/python finmind_data/test_assertions.py 2>&1 | tail -12
