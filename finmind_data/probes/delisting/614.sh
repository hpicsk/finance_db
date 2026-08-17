# Session 2026-08-17, transcript call 614.
# Check imports, register the check and its population
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && grep -n "^import math\|^import\|^from" finmind_data/test_assertions.py | head -8 && sed -i 's/^    test_taiwan_delisting_sign_sample_is_preregistered,$/    test_taiwan_delisting_sign_sample_is_preregistered,\n    test_taiwan_delisting_sign_accuracy,/' finmind_data/test_assertions.py && /home/st/miniconda3/bin/python -c "
import json
p='finmind_data/populations.json'
d=json.load(open(p)); d['test_taiwan_delisting_sign_accuracy']={'bound':'exact','n':38}
json.dump(dict(sorted(d.items())),open(p,'w'),indent=2); open(p,'a').write('\n')
print('registered')"
