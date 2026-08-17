# Session 2026-08-17, transcript call 620.
# Check margins and re-run the module
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && awk 'length>86 {print FILENAME":"FNR" ("length")"}' finmind_data/delisting_sign.py finmind_data/test_assertions.py && echo "(margins ok if nothing above)" && /home/st/miniconda3/bin/python -m finmind_data.delisting_sign 2>&1 | grep -v 'terminate\|Aborted\|core dumped'
