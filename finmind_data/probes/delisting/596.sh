# Session 2026-08-17, transcript call 596.
# Re-run with transfers excluded
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && rm -f finmind_data/delisting_labels.csv && /home/st/miniconda3/bin/python -m finmind_data.delisting_sign 2>&1 | grep -v 'terminate called\|Aborted\|core dumped' && echo "--- sample ---" && /home/st/miniconda3/bin/python -c "
import pandas as pd
l=pd.read_csv('finmind_data/delisting_labels.csv',dtype={'stock_id':str})
print(l.shape[0],'rows | purpose:',l.purpose.value_counts().to_dict(),'| era:',l.era.value_counts().to_dict())
print('6446 present:', (l.stock_id=='6446').any())
" 2>&1 | grep -v 'terminate called\|Aborted\|core dumped'
