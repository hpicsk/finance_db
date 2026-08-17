# Session 2026-08-17, transcript call 619.
# Run remaining negative tests and confirm restore
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && S=/tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad
echo "=== mutation 2: blank one label ===" && /home/st/miniconda3/bin/python -c "
import pandas as pd
p='finmind_data/delisting_labels.csv'; d=pd.read_csv(p,dtype={'stock_id':str})
d.loc[d.stock_id=='2475','label']=''; d.to_csv(p,index=False)" && /home/st/miniconda3/bin/python $S/neg.py 2>&1 | grep -v 'terminate\|Aborted\|core' ; cp $S/dl.bak finmind_data/delisting_labels.csv
echo && echo "=== mutation 3: flip the 1613 label to merger (hide the known miss) ===" && /home/st/miniconda3/bin/python -c "
import pandas as pd
p='finmind_data/delisting_labels.csv'; d=pd.read_csv(p,dtype={'stock_id':str})
d.loc[d.stock_id=='1613','label']='merger'; d.to_csv(p,index=False)" && /home/st/miniconda3/bin/python $S/neg.py 2>&1 | grep -v 'terminate\|Aborted\|core' ; cp $S/dl.bak finmind_data/delisting_labels.csv
echo && echo "=== mutation 4: change the seed ===" && sed -i 's/^_SAMPLE_SEED = 20260817$/_SAMPLE_SEED = 20260818/' finmind_data/delisting_sign.py && /home/st/miniconda3/bin/python $S/neg.py 2>&1 | grep -v 'terminate\|Aborted\|core' ; cp $S/ds.bak finmind_data/delisting_sign.py
echo && echo "=== restored ===" && /home/st/miniconda3/bin/python $S/neg.py 2>&1 | grep -v 'terminate\|Aborted\|core' && git diff --stat
