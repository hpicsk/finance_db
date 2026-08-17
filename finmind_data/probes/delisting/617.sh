# Session 2026-08-17, transcript call 617.
# Negative test: move a pre-registered cut
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && cp finmind_data/delisting_sign.py /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad/ds.bak && cp finmind_data/delisting_labels.csv /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad/dl.bak && cat > /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad/neg.py <<'EOF'
import importlib, sys, traceback
sys.path.insert(0, "/home/st/research/finance_db")
import finmind_data.test_assertions as t
for name in ("test_taiwan_delisting_sign_sample_is_preregistered",
             "test_taiwan_delisting_sign_accuracy"):
    try:
        msg, n = getattr(t, name)()
        print(f"  {name}: PASSED (n={n})")
    except AssertionError as e:
        print(f"  {name}: FAILED -> {str(e)[:150]}")
EOF
echo "=== mutation 1: move _DD_MERGER 0.70 -> 0.60 ===" && sed -i 's/^_DD_MERGER = 0.70$/_DD_MERGER = 0.60/' finmind_data/delisting_sign.py && /home/st/miniconda3/bin/python /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad/neg.py 2>&1 | grep -v 'terminate\|Aborted\|core dumped'; cp /tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad/ds.bak finmind_data/delisting_sign.py
